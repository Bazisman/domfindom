from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from backend.storage.mysql_read import MySqlReadRepository
from tools.money_minor import from_minor_float, to_minor


DAILY_ACCOUNT_IDS = {1, 2}


class MySqlWriteRepository(MySqlReadRepository):
    """MySQL write adapter for the SQLite -> MySQL shadow-write path."""

    def _account_ref(self, legacy_account_id: int) -> Dict[str, Any]:
        legacy_account_id = int(legacy_account_id)
        if legacy_account_id in DAILY_ACCOUNT_IDS:
            return {"kind": "daily", "daily_legacy_id": legacy_account_id, "capital_legacy_id": None}
        return {"kind": "capital", "daily_legacy_id": None, "capital_legacy_id": legacy_account_id}

    def _finance_id_by_legacy(self, conn, table: str, user_id: int, legacy_local_id: Optional[int]) -> Optional[int]:
        if legacy_local_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM finance_{table} WHERE user_id = %s AND legacy_local_id = %s",
                (int(user_id), int(legacy_local_id)),
            )
            row = cursor.fetchone()
        return int(row["id"]) if row else None

    def _category_id_by_name(self, conn, user_id: int, category: str) -> Optional[int]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM finance_categories
                WHERE user_id = %s
                  AND name = %s
                  AND is_active = TRUE
                ORDER BY id
                LIMIT 1
                """,
                (int(user_id), str(category)),
            )
            row = cursor.fetchone()
        return int(row["id"]) if row else None

    def _adjust_account_minor(self, conn, user_id: int, legacy_account_id: int, delta_minor: int) -> None:
        ref = self._account_ref(legacy_account_id)
        with conn.cursor() as cursor:
            if ref["kind"] == "daily":
                cursor.execute(
                    """
                    UPDATE finance_accounts
                    SET balance_minor = balance_minor + %s
                    WHERE user_id = %s
                      AND legacy_local_id = %s
                      AND is_active = TRUE
                    """,
                    (int(delta_minor), int(user_id), int(legacy_account_id)),
                )
            else:
                cursor.execute(
                    """
                    UPDATE finance_capital_accounts
                    SET balance_minor = balance_minor + %s
                    WHERE user_id = %s
                      AND legacy_local_id = %s
                      AND is_active = TRUE
                    """,
                    (int(delta_minor), int(user_id), int(legacy_account_id)),
                )
            if cursor.rowcount <= 0:
                raise RuntimeError(f"MySQL account legacy_local_id={legacy_account_id} was not found")

    def _insert_id_map(
        self,
        conn,
        source_db_path: str,
        legacy_user_id: int,
        source_table: str,
        source_local_id: int,
        target_table: str,
        target_id: int,
    ) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO migration_id_map (
                    source_db_path, source_user_id, source_table, source_local_id,
                    target_schema, target_table, target_id
                )
                VALUES (%s, %s, %s, %s, 'finance', %s, %s)
                ON DUPLICATE KEY UPDATE target_id = VALUES(target_id)
                """,
                (
                    str(source_db_path),
                    int(legacy_user_id),
                    str(source_table),
                    int(source_local_id),
                    str(target_table),
                    int(target_id),
                ),
            )

    def _mapped_id(
        self,
        conn,
        source_db_path: str,
        legacy_user_id: Optional[int],
        source_table: str,
        source_local_id: int,
    ) -> Optional[int]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT target_id
                FROM migration_id_map
                WHERE source_db_path = %s
                  AND source_user_id <=> %s
                  AND source_table = %s
                  AND source_local_id = %s
                """,
                (str(source_db_path), legacy_user_id, str(source_table), int(source_local_id)),
            )
            row = cursor.fetchone()
        return int(row["target_id"]) if row else None

    def _upsert_null_user_id_map(
        self,
        conn,
        source_db_path: str,
        source_table: str,
        source_local_id: int,
        target_schema: str,
        target_table: str,
        target_id: int,
    ) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO migration_id_map (
                    source_db_path, source_user_id, source_table, source_local_id,
                    target_schema, target_table, target_id
                )
                VALUES (%s, NULL, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    target_schema = VALUES(target_schema),
                    target_table = VALUES(target_table),
                    target_id = VALUES(target_id)
                """,
                (str(source_db_path), str(source_table), int(source_local_id), str(target_schema), str(target_table), int(target_id)),
            )

    def _legacy_account_id_from_transfer_row(self, row: Dict[str, Any], prefix: str) -> int:
        legacy_row = row.get(f"legacy_{prefix}_account_id")
        if legacy_row is not None:
            return int(legacy_row)
        resolved = row.get(f"{prefix}_legacy_local_id")
        if resolved is not None:
            return int(resolved)
        raise RuntimeError(f"Cannot resolve legacy {prefix} account id for MySQL transfer id={row.get('id')}")

    def mirror_actual_transaction(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transaction: Dict[str, Any],
        transfers: Iterable[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")

        legacy_transaction_id = int(transaction["id"])
        existing = self._finance_id_by_legacy(conn, "transactions", mysql_user_id, legacy_transaction_id)
        if existing is not None:
            return {"status": "exists", "transaction_id": existing}

        transaction_type = str(transaction["type"])
        status = str(transaction.get("status") or "actual")
        if status != "actual":
            raise RuntimeError("mirror_actual_transaction expects an actual transaction")

        amount_minor = to_minor(transaction["amount"])
        money_source = str(transaction.get("money_source") or "cashless")
        source_account_id = 2 if money_source == "cash" else 1
        category = str(transaction["category"])
        category_id = self._category_id_by_name(conn, mysql_user_id, category)

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_transactions (
                    user_id, legacy_local_id, type, category, category_id,
                    amount_minor, comment, date, money_source, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'actual')
                """,
                (
                    mysql_user_id,
                    legacy_transaction_id,
                    transaction_type,
                    category,
                    category_id,
                    amount_minor,
                    transaction.get("comment"),
                    transaction["date"],
                    money_source,
                ),
            )
            mysql_transaction_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "transactions", legacy_transaction_id, "transactions", mysql_transaction_id)

        mirrored_transfer_ids = []
        active_transfers = [item for item in transfers if bool(item.get("is_active", True))]
        if transaction_type == "income":
            transfer_minor = 0
            for transfer in active_transfers:
                transfer_minor += to_minor(transfer["amount"])
                mirrored_transfer_ids.append(
                    self._mirror_transfer(conn, mysql_user_id, legacy_user_id, source_db_path, transfer, mysql_transaction_id)
                )
            self._adjust_account_minor(conn, mysql_user_id, source_account_id, amount_minor - transfer_minor)
        else:
            self._adjust_account_minor(conn, mysql_user_id, source_account_id, -amount_minor)

        return {"status": "inserted", "transaction_id": mysql_transaction_id, "transfer_ids": mirrored_transfer_ids}

    def _mirror_transfer(
        self,
        conn,
        mysql_user_id: int,
        legacy_user_id: int,
        source_db_path: str,
        transfer: Dict[str, Any],
        mysql_transaction_id: int,
    ) -> int:
        legacy_transfer_id = int(transfer["id"])
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, is_active
                FROM finance_transfers
                WHERE user_id = %s AND legacy_local_id = %s
                """,
                (int(mysql_user_id), legacy_transfer_id),
            )
            existing = cursor.fetchone()

        from_legacy = int(transfer["from_account_id"])
        to_legacy = int(transfer["to_account_id"])
        from_ref = self._account_ref(from_legacy)
        to_ref = self._account_ref(to_legacy)
        from_daily_id = self._finance_id_by_legacy(conn, "accounts", mysql_user_id, from_ref["daily_legacy_id"])
        to_daily_id = self._finance_id_by_legacy(conn, "accounts", mysql_user_id, to_ref["daily_legacy_id"])
        from_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", mysql_user_id, from_ref["capital_legacy_id"])
        to_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", mysql_user_id, to_ref["capital_legacy_id"])
        amount_minor = to_minor(transfer["amount"])

        if existing is not None:
            mysql_transfer_id = int(existing["id"])
            if bool(existing["is_active"]):
                return mysql_transfer_id
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_transfers
                    SET legacy_from_account_id = %s,
                        legacy_to_account_id = %s,
                        from_account_kind = %s,
                        to_account_kind = %s,
                        from_daily_account_id = %s,
                        to_daily_account_id = %s,
                        from_capital_account_id = %s,
                        to_capital_account_id = %s,
                        amount_minor = %s,
                        transaction_id = %s,
                        date = %s,
                        comment = %s,
                        is_active = TRUE
                    WHERE id = %s
                    """,
                    (
                        from_legacy,
                        to_legacy,
                        from_ref["kind"],
                        to_ref["kind"],
                        from_daily_id,
                        to_daily_id,
                        from_capital_id,
                        to_capital_id,
                        amount_minor,
                        int(mysql_transaction_id),
                        transfer["date"],
                        transfer.get("comment"),
                        mysql_transfer_id,
                    ),
                )
            self._adjust_account_minor(conn, mysql_user_id, to_legacy, amount_minor)
            return mysql_transfer_id

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_transfers (
                    user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                    from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                    from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                    date, comment, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                """,
                (
                    mysql_user_id,
                    legacy_transfer_id,
                    from_legacy,
                    to_legacy,
                    from_ref["kind"],
                    to_ref["kind"],
                    from_daily_id,
                    to_daily_id,
                    from_capital_id,
                    to_capital_id,
                    amount_minor,
                    int(mysql_transaction_id),
                    transfer["date"],
                    transfer.get("comment"),
                ),
            )
            mysql_transfer_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "transfers", legacy_transfer_id, "transfers", mysql_transfer_id)
        self._adjust_account_minor(conn, mysql_user_id, to_legacy, amount_minor)
        return mysql_transfer_id

    def mirror_delete_transaction(self, conn, legacy_user_id: int, legacy_transaction_id: int) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, type, amount_minor, money_source, status
                FROM finance_transactions
                WHERE user_id = %s AND legacy_local_id = %s
                """,
                (int(mysql_user_id), int(legacy_transaction_id)),
            )
            row = cursor.fetchone()
        if not row:
            return {"status": "missing"}
        status = str(row["status"] or "actual")
        mysql_transaction_id = int(row["id"])
        if status != "actual":
            return {"status": "skipped", "reason": "non_actual_transaction"}

        amount_minor = int(row["amount_minor"] or 0)
        source_account_id = 2 if str(row["money_source"] or "cashless") == "cash" else 1
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    t.id,
                    t.amount_minor,
                    t.legacy_from_account_id,
                    t.legacy_to_account_id,
                    t.from_account_kind,
                    t.to_account_kind,
                    t.from_daily_account_id,
                    t.to_daily_account_id,
                    t.from_capital_account_id,
                    t.to_capital_account_id,
                    from_daily.legacy_local_id AS from_daily_legacy_local_id,
                    to_daily.legacy_local_id AS to_daily_legacy_local_id,
                    from_capital.legacy_local_id AS from_capital_legacy_local_id,
                    to_capital.legacy_local_id AS to_capital_legacy_local_id
                FROM finance_transfers t
                LEFT JOIN finance_accounts from_daily ON from_daily.id = t.from_daily_account_id
                LEFT JOIN finance_accounts to_daily ON to_daily.id = t.to_daily_account_id
                LEFT JOIN finance_capital_accounts from_capital ON from_capital.id = t.from_capital_account_id
                LEFT JOIN finance_capital_accounts to_capital ON to_capital.id = t.to_capital_account_id
                WHERE t.user_id = %s
                  AND t.transaction_id = %s
                  AND t.is_active = TRUE
                ORDER BY t.id
                """,
                (int(mysql_user_id), mysql_transaction_id),
            )
            transfer_rows = cursor.fetchall()

        transfer_minor = 0
        for transfer in transfer_rows:
            transfer_amount_minor = int(transfer["amount_minor"] or 0)
            transfer_minor += transfer_amount_minor
            to_legacy = self._legacy_account_id_from_transfer_row(transfer, "to")
            self._adjust_account_minor(conn, mysql_user_id, to_legacy, -transfer_amount_minor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE finance_transfers SET is_active = FALSE WHERE id = %s", (int(transfer["id"]),))

        if str(row["type"]) == "income":
            self._adjust_account_minor(conn, mysql_user_id, source_account_id, -(amount_minor - transfer_minor))
        else:
            self._adjust_account_minor(conn, mysql_user_id, source_account_id, amount_minor)

        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM finance_transactions WHERE id = %s", (mysql_transaction_id,))
        return {
            "status": "deleted",
            "transaction_id": mysql_transaction_id,
            "amount": from_minor_float(amount_minor),
            "transfers_deactivated": len(transfer_rows),
        }

    def mirror_update_transaction(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transaction: Dict[str, Any],
        transfers: Iterable[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        status = str(transaction.get("status") or "actual")
        if status != "actual":
            return {"status": "skipped", "reason": "non_actual_transaction"}
        legacy_transaction_id = int(transaction["id"])
        delete_result = self.mirror_delete_transaction(conn, legacy_user_id, legacy_transaction_id)
        if delete_result.get("status") == "skipped":
            return delete_result
        insert_result = self.mirror_actual_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction=transaction,
            transfers=transfers,
        )
        return {
            "status": "updated" if delete_result.get("status") == "deleted" else "inserted_missing",
            "delete": delete_result,
            "insert": insert_result,
        }

    def mirror_planned_transaction(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transaction: Dict[str, Any],
    ) -> Dict[str, Any]:
        status = str(transaction.get("status") or "actual")
        if status != "planned":
            raise RuntimeError("mirror_planned_transaction expects a planned transaction")
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")

        legacy_transaction_id = int(transaction["id"])
        template_id = None
        if transaction.get("template_id") is not None:
            template_id = self._finance_id_by_legacy(conn, "recurring_templates", mysql_user_id, int(transaction["template_id"]))
            if template_id is None:
                return {"status": "skipped", "reason": "recurring_template_not_mirrored"}
        existing = self._finance_id_by_legacy(conn, "transactions", mysql_user_id, legacy_transaction_id)
        category = str(transaction["category"])
        params = (
            str(transaction["type"]),
            category,
            self._category_id_by_name(conn, mysql_user_id, category),
            to_minor(transaction["amount"]),
            transaction.get("comment"),
            transaction["date"],
            str(transaction.get("money_source") or "cashless"),
            template_id,
        )
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_transactions
                    SET type = %s,
                        category = %s,
                        category_id = %s,
                        amount_minor = %s,
                        comment = %s,
                        date = %s,
                        money_source = %s,
                        status = 'planned',
                        template_id = %s
                    WHERE id = %s
                    """,
                    (*params, existing),
                )
            return {"status": "updated", "transaction_id": existing}

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_transactions (
                    user_id, legacy_local_id, type, category, category_id,
                    amount_minor, comment, date, money_source, status, template_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'planned', %s)
                """,
                (mysql_user_id, legacy_transaction_id, *params),
            )
            mysql_transaction_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "transactions", legacy_transaction_id, "transactions", mysql_transaction_id)
        return {"status": "inserted", "transaction_id": mysql_transaction_id}

    def mirror_recurring_template(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        template: Dict[str, Any],
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")

        legacy_template_id = int(template["id"])
        category_id = self._finance_id_by_legacy(conn, "categories", mysql_user_id, template.get("category_id"))
        params = (
            str(template["type"]),
            str(template["name"]),
            to_minor(template["amount"]),
            int(template["day_of_month"]),
            category_id,
            template.get("comment_template"),
            str(template.get("money_source") or "cashless"),
            int(template.get("months_ahead") or 12),
            bool(template.get("working_days_only")),
            bool(template.get("is_active", True)),
        )
        existing = self._finance_id_by_legacy(conn, "recurring_templates", mysql_user_id, legacy_template_id)
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_recurring_templates
                    SET type = %s,
                        name = %s,
                        amount_minor = %s,
                        day_of_month = %s,
                        category_id = %s,
                        comment_template = %s,
                        money_source = %s,
                        months_ahead = %s,
                        working_days_only = %s,
                        is_active = %s
                    WHERE id = %s
                    """,
                    (*params, existing),
                )
            return {"status": "updated", "template_id": existing}

        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_recurring_templates (
                    user_id, legacy_local_id, type, name, amount_minor, day_of_month, category_id,
                    comment_template, money_source, months_ahead, working_days_only, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_template_id, *params),
            )
            mysql_template_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "recurring_templates", legacy_template_id, "recurring_templates", mysql_template_id)
        return {"status": "inserted", "template_id": mysql_template_id}

    def delete_planned_transactions_for_template(self, conn, legacy_user_id: int, legacy_template_id: int) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_template_id = self._finance_id_by_legacy(conn, "recurring_templates", mysql_user_id, legacy_template_id)
        if mysql_template_id is None:
            return {"status": "missing_template", "deleted": 0}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM finance_transactions
                WHERE user_id = %s
                  AND template_id = %s
                  AND status = 'planned'
                """,
                (mysql_user_id, mysql_template_id),
            )
            deleted = int(cursor.rowcount)
        return {"status": "deleted", "deleted": deleted, "template_id": mysql_template_id}

    def mirror_delete_recurring_template(self, conn, legacy_user_id: int, legacy_template_id: int) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_template_id = self._finance_id_by_legacy(conn, "recurring_templates", mysql_user_id, legacy_template_id)
        if mysql_template_id is None:
            return {"status": "missing"}
        planned_result = self.delete_planned_transactions_for_template(conn, legacy_user_id, legacy_template_id)
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM finance_recurring_templates WHERE id = %s", (mysql_template_id,))
        return {"status": "deleted", "template_id": mysql_template_id, "planned_deleted": planned_result.get("deleted", 0)}

    def mirror_category(self, conn, legacy_user_id: int, source_db_path: str, category: Dict[str, Any]) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_category_id = int(category["id"])
        existing = self._finance_id_by_legacy(conn, "categories", mysql_user_id, legacy_category_id)
        values = (
            str(category["name"]),
            str(category.get("type") or "both"),
            category.get("color"),
            category.get("icon"),
            bool(category.get("is_active", True)),
        )
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_categories
                    SET name = %s, type = %s, color = %s, icon = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (*values, existing),
                )
            return {"status": "updated", "category_id": existing}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_categories (user_id, legacy_local_id, name, type, color, icon, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_category_id, *values),
            )
            mysql_category_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "categories", legacy_category_id, "categories", mysql_category_id)
        return {"status": "inserted", "category_id": mysql_category_id}

    def _next_legacy_id(self, conn, mysql_user_id: int, table: str) -> int:
        allowed_tables = {
            "budgets",
            "capital_accounts",
            "categories",
            "reconciliation_sources",
            "reconciliations",
            "recurring_templates",
            "transactions",
            "transfers",
        }
        if table not in allowed_tables:
            raise ValueError(f"Unsupported MySQL legacy id table: {table}")
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COALESCE(MAX(legacy_local_id), 0) + 1 AS next_id FROM finance_{table} WHERE user_id = %s",
                (int(mysql_user_id),),
            )
            row = cursor.fetchone()
        return int(row["next_id"] or 1)

    def create_category(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        name: str,
        category_type: str = "both",
        color: str = "#808080",
        icon: str = "",
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_category_id = self._next_legacy_id(conn, mysql_user_id, "categories")
        category = {
            "id": legacy_category_id,
            "name": name,
            "type": category_type,
            "color": color,
            "icon": icon,
            "is_active": True,
        }
        result = self.mirror_category(conn, legacy_user_id, source_db_path, category)
        return {**result, "legacy_category_id": legacy_category_id}

    def update_category(
        self,
        conn,
        legacy_user_id: int,
        legacy_category_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_category_id = self._finance_id_by_legacy(conn, "categories", mysql_user_id, legacy_category_id)
        if mysql_category_id is None:
            return {"status": "missing"}
        allowed = {
            "name": "name",
            "type": "type",
            "color": "color",
            "icon": "icon",
            "is_active": "is_active",
        }
        assignments = []
        values = []
        for key, column in allowed.items():
            if key in kwargs:
                assignments.append(f"{column} = %s")
                values.append(bool(kwargs[key]) if key == "is_active" else kwargs[key])
        if not assignments:
            return {"status": "noop", "category_id": mysql_category_id}
        values.append(mysql_category_id)
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE finance_categories SET {', '.join(assignments)} WHERE id = %s",
                tuple(values),
            )
        return {"status": "updated", "category_id": mysql_category_id}

    def delete_category(self, conn, legacy_user_id: int, legacy_category_id: int) -> Dict[str, Any]:
        return self.update_category(
            conn,
            legacy_user_id=legacy_user_id,
            legacy_category_id=legacy_category_id,
            is_active=False,
        )

    def mirror_budget(self, conn, legacy_user_id: int, source_db_path: str, budget: Dict[str, Any]) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_budget_id = int(budget["id"])
        category_id = self._finance_id_by_legacy(conn, "categories", mysql_user_id, budget.get("category_id"))
        if category_id is None:
            return {"status": "skipped", "reason": "category_not_mirrored"}
        values = (category_id, to_minor(budget["amount"]), str(budget.get("period") or "monthly"))
        existing = self._finance_id_by_legacy(conn, "budgets", mysql_user_id, legacy_budget_id)
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE finance_budgets SET category_id = %s, amount_minor = %s, period = %s WHERE id = %s",
                    (*values, existing),
                )
            return {"status": "updated", "budget_id": existing}
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO finance_budgets (user_id, legacy_local_id, category_id, amount_minor, period) VALUES (%s, %s, %s, %s, %s)",
                (mysql_user_id, legacy_budget_id, *values),
            )
            mysql_budget_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "budgets", legacy_budget_id, "budgets", mysql_budget_id)
        return {"status": "inserted", "budget_id": mysql_budget_id}

    def mirror_delete_budget(self, conn, legacy_user_id: int, legacy_budget_id: int) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_budget_id = self._finance_id_by_legacy(conn, "budgets", mysql_user_id, legacy_budget_id)
        if mysql_budget_id is None:
            return {"status": "missing"}
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM finance_budgets WHERE id = %s", (mysql_budget_id,))
        return {"status": "deleted", "budget_id": mysql_budget_id}

    def set_budget(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        legacy_category_id: int,
        amount: float,
        period: str = "monthly",
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_category_id = self._finance_id_by_legacy(conn, "categories", mysql_user_id, legacy_category_id)
        if mysql_category_id is None:
            raise RuntimeError(f"MySQL category legacy_local_id={legacy_category_id} was not found")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, legacy_local_id
                FROM finance_budgets
                WHERE user_id = %s AND category_id = %s
                LIMIT 1
                """,
                (mysql_user_id, mysql_category_id),
            )
            existing = cursor.fetchone()
        amount_minor = to_minor(amount)
        normalized_period = str(period or "monthly")
        if existing:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_budgets
                    SET amount_minor = %s, period = %s
                    WHERE id = %s
                    """,
                    (amount_minor, normalized_period, int(existing["id"])),
                )
            return {
                "status": "updated",
                "budget_id": int(existing["id"]),
                "legacy_budget_id": int(existing["legacy_local_id"]),
            }

        legacy_budget_id = self._next_legacy_id(conn, mysql_user_id, "budgets")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_budgets (user_id, legacy_local_id, category_id, amount_minor, period)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_budget_id, mysql_category_id, amount_minor, normalized_period),
            )
            mysql_budget_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "budgets", legacy_budget_id, "budgets", mysql_budget_id)
        return {"status": "inserted", "budget_id": mysql_budget_id, "legacy_budget_id": legacy_budget_id}

    def delete_budget(self, conn, legacy_user_id: int, legacy_budget_id: int) -> Dict[str, Any]:
        return self.mirror_delete_budget(conn, legacy_user_id, legacy_budget_id)

    def mirror_capital_account(self, conn, legacy_user_id: int, source_db_path: str, account: Dict[str, Any]) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_account_id = int(account["id"])
        existing = self._finance_id_by_legacy(conn, "capital_accounts", mysql_user_id, legacy_account_id)
        values = (
            str(account["name"]),
            to_minor(account.get("balance") or 0),
            str(account.get("currency") or "RUB"),
            account.get("icon"),
            account.get("color"),
            bool(account.get("is_default", False)),
            bool(account.get("is_active", True)),
        )
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_capital_accounts
                    SET name = %s,
                        balance_minor = %s,
                        currency = %s,
                        icon = %s,
                        color = %s,
                        is_default = %s,
                        is_active = %s
                    WHERE id = %s
                    """,
                    (*values, existing),
                )
            return {"status": "updated", "account_id": existing}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_capital_accounts (
                    user_id, legacy_local_id, name, balance_minor, currency, icon, color, is_default, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_account_id, *values),
            )
            mysql_account_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "capital_accounts", legacy_account_id, "capital_accounts", mysql_account_id)
        return {"status": "inserted", "account_id": mysql_account_id}

    def mirror_standalone_transfer(self, conn, legacy_user_id: int, source_db_path: str, transfer: Dict[str, Any]) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_transfer_id = int(transfer["id"])
        existing = self._finance_id_by_legacy(conn, "transfers", mysql_user_id, legacy_transfer_id)
        if existing is not None:
            return {"status": "exists", "transfer_id": existing}

        from_legacy = int(transfer["from_account_id"])
        to_legacy = int(transfer["to_account_id"])
        from_ref = self._account_ref(from_legacy)
        to_ref = self._account_ref(to_legacy)
        amount_minor = to_minor(transfer["amount"])
        from_daily_id = self._finance_id_by_legacy(conn, "accounts", mysql_user_id, from_ref["daily_legacy_id"])
        to_daily_id = self._finance_id_by_legacy(conn, "accounts", mysql_user_id, to_ref["daily_legacy_id"])
        from_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", mysql_user_id, from_ref["capital_legacy_id"])
        to_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", mysql_user_id, to_ref["capital_legacy_id"])
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_transfers (
                    user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                    from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                    from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                    date, comment, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
                """,
                (
                    mysql_user_id,
                    legacy_transfer_id,
                    from_legacy,
                    to_legacy,
                    from_ref["kind"],
                    to_ref["kind"],
                    from_daily_id,
                    to_daily_id,
                    from_capital_id,
                    to_capital_id,
                    amount_minor,
                    transfer["date"],
                    transfer.get("comment"),
                    bool(transfer.get("is_active", True)),
                ),
            )
            mysql_transfer_id = int(cursor.lastrowid)
        self._insert_id_map(conn, source_db_path, legacy_user_id, "transfers", legacy_transfer_id, "transfers", mysql_transfer_id)
        if bool(transfer.get("is_active", True)):
            self._adjust_account_minor(conn, mysql_user_id, from_legacy, -amount_minor)
            self._adjust_account_minor(conn, mysql_user_id, to_legacy, amount_minor)
        return {"status": "inserted", "transfer_id": mysql_transfer_id}

    def mirror_reconciliation_source(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_source_id = int(source["id"])
        existing = self._finance_id_by_legacy(conn, "reconciliation_sources", mysql_user_id, legacy_source_id)
        values = (
            str(source["name"]),
            to_minor(source.get("balance") or 0),
            bool(source.get("is_active", True)),
        )
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_reconciliation_sources
                    SET name = %s, balance_minor = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (*values, existing),
                )
            return {"status": "updated", "source_id": existing}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_reconciliation_sources (
                    user_id, legacy_local_id, name, balance_minor, is_active
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_source_id, *values),
            )
            mysql_source_id = int(cursor.lastrowid)
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "reconciliation_sources",
            legacy_source_id,
            "reconciliation_sources",
            mysql_source_id,
        )
        return {"status": "inserted", "source_id": mysql_source_id}

    def create_reconciliation_source(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        name: str,
        balance: float = 0,
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_source_id = self._next_legacy_id(conn, mysql_user_id, "reconciliation_sources")
        source = {
            "id": legacy_source_id,
            "name": name,
            "balance": balance,
            "is_active": True,
        }
        result = self.mirror_reconciliation_source(conn, legacy_user_id, source_db_path, source)
        return {**result, "legacy_source_id": legacy_source_id}

    def update_reconciliation_source(
        self,
        conn,
        legacy_user_id: int,
        legacy_source_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        mysql_source_id = self._finance_id_by_legacy(conn, "reconciliation_sources", mysql_user_id, legacy_source_id)
        if mysql_source_id is None:
            return {"status": "missing"}
        allowed = {
            "name": "name",
            "balance": "balance_minor",
            "is_active": "is_active",
        }
        assignments = []
        values = []
        for key, column in allowed.items():
            if key in kwargs:
                assignments.append(f"{column} = %s")
                if key == "balance":
                    values.append(to_minor(kwargs[key]))
                elif key == "is_active":
                    values.append(bool(kwargs[key]))
                else:
                    values.append(kwargs[key])
        if not assignments:
            return {"status": "noop", "source_id": mysql_source_id}
        values.append(mysql_source_id)
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE finance_reconciliation_sources SET {', '.join(assignments)} WHERE id = %s",
                tuple(values),
            )
        return {"status": "updated", "source_id": mysql_source_id}

    def delete_reconciliation_source(self, conn, legacy_user_id: int, legacy_source_id: int) -> Dict[str, Any]:
        return self.update_reconciliation_source(
            conn,
            legacy_user_id=legacy_user_id,
            legacy_source_id=legacy_source_id,
            is_active=False,
        )

    def mirror_reconciliation(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        reconciliation: Dict[str, Any],
    ) -> Dict[str, Any]:
        mysql_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        legacy_reconciliation_id = int(reconciliation["id"])
        adjustment_transaction_id = None
        if reconciliation.get("adjustment_transaction_id") is not None:
            adjustment_transaction_id = self._finance_id_by_legacy(
                conn,
                "transactions",
                mysql_user_id,
                int(reconciliation["adjustment_transaction_id"]),
            )
        values = (
            to_minor(reconciliation.get("real_balance") or 0),
            to_minor(reconciliation.get("program_balance") or 0),
            to_minor(reconciliation.get("difference") or 0),
            adjustment_transaction_id,
        )
        existing = self._finance_id_by_legacy(conn, "reconciliations", mysql_user_id, legacy_reconciliation_id)
        if existing is not None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE finance_reconciliations
                    SET real_balance_minor = %s,
                        program_balance_minor = %s,
                        difference_minor = %s,
                        adjustment_transaction_id = %s
                    WHERE id = %s
                    """,
                    (*values, existing),
                )
            return {"status": "updated", "reconciliation_id": existing}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO finance_reconciliations (
                    user_id, legacy_local_id, real_balance_minor, program_balance_minor,
                    difference_minor, adjustment_transaction_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (mysql_user_id, legacy_reconciliation_id, *values),
            )
            mysql_reconciliation_id = int(cursor.lastrowid)
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "reconciliations",
            legacy_reconciliation_id,
            "reconciliations",
            mysql_reconciliation_id,
        )
        return {"status": "inserted", "reconciliation_id": mysql_reconciliation_id}

    def mirror_family_snapshot(self, conn, source_db_path: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        family = snapshot.get("family") or {}
        legacy_family_id = int(family["id"])
        owner_user_id = self.get_user_id_by_legacy(conn, int(family["owner_user_id"]))
        if owner_user_id is None:
            raise RuntimeError(f"MySQL owner for legacy user {family['owner_user_id']} was not found")

        mysql_family_id = self._mapped_id(conn, source_db_path, None, "families", legacy_family_id)
        if mysql_family_id is None:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO family_families (name, owner_user_id, archived_at)
                    VALUES (%s, %s, %s)
                    """,
                    (family["name"], owner_user_id, family.get("archived_at")),
                )
                mysql_family_id = int(cursor.lastrowid)
            self._upsert_null_user_id_map(conn, source_db_path, "families", legacy_family_id, "family", "families", mysql_family_id)
            family_status = "inserted"
        else:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE family_families
                    SET name = %s, owner_user_id = %s, archived_at = %s
                    WHERE id = %s
                    """,
                    (family["name"], owner_user_id, family.get("archived_at"), mysql_family_id),
                )
            family_status = "updated"

        counts = {
            "family": 1,
            "memberships": 0,
            "invites": 0,
            "capital_accounts": 0,
            "capital_member_settings": 0,
            "categories": 0,
            "category_bindings": 0,
            "category_audit_resolutions": 0,
        }
        for row in snapshot.get("memberships", []):
            self._mirror_family_membership(conn, source_db_path, mysql_family_id, row)
            counts["memberships"] += 1
        for row in snapshot.get("invites", []):
            self._mirror_family_invite(conn, source_db_path, mysql_family_id, row)
            counts["invites"] += 1
        for row in snapshot.get("capital_accounts", []):
            if self._mirror_family_capital_account(conn, source_db_path, mysql_family_id, row):
                counts["capital_accounts"] += 1
        for row in snapshot.get("capital_member_settings", []):
            if self._mirror_family_capital_member_setting(conn, mysql_family_id, row):
                counts["capital_member_settings"] += 1
        for row in snapshot.get("categories", []):
            self._mirror_family_category(conn, source_db_path, mysql_family_id, row)
            counts["categories"] += 1
        for row in snapshot.get("category_bindings", []):
            if self._mirror_family_category_binding(conn, source_db_path, mysql_family_id, row):
                counts["category_bindings"] += 1
        for row in snapshot.get("category_audit_resolutions", []):
            self._mirror_family_category_audit_resolution(conn, source_db_path, mysql_family_id, row)
            counts["category_audit_resolutions"] += 1
        self._prune_family_category_audit_resolutions(
            conn,
            source_db_path,
            mysql_family_id,
            {int(row["id"]) for row in snapshot.get("category_audit_resolutions", [])},
        )
        return {"status": family_status, "family_id": mysql_family_id, "counts": counts}

    def _normalize_family_role(self, role: Any) -> str:
        value = str(role or "member")
        return value if value in {"owner", "member", "viewer"} else "member"

    def _normalize_family_status(self, status: Any) -> str:
        value = str(status or "active")
        return "removed" if value == "revoked" else value if value in {"active", "inactive", "removed"} else "active"

    def _mirror_family_membership(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> None:
        user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        invited_by = self.get_user_id_by_legacy(conn, int(row["invited_by_user_id"])) if row.get("invited_by_user_id") else None
        if user_id is None:
            return
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_memberships (family_id, user_id, role, status, invited_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    role = VALUES(role),
                    status = VALUES(status),
                    invited_by_user_id = VALUES(invited_by_user_id)
                """,
                (family_id, user_id, self._normalize_family_role(row.get("role")), self._normalize_family_status(row.get("status")), invited_by),
            )
            membership_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(conn, source_db_path, "family_memberships", int(row["id"]), "family", "memberships", membership_id)

    def _mirror_family_invite(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> None:
        invited_by = self.get_user_id_by_legacy(conn, int(row["invited_by_user_id"]))
        if invited_by is None:
            return
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_invites (
                    family_id, email, role, token_hash, invited_by_user_id, expires_at, accepted_at, revoked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    accepted_at = VALUES(accepted_at),
                    revoked_at = VALUES(revoked_at)
                """,
                (
                    family_id,
                    row["email"],
                    self._normalize_family_role(row.get("role")),
                    row["token_hash"],
                    invited_by,
                    row["expires_at"],
                    row.get("accepted_at"),
                    row.get("revoked_at"),
                ),
            )
            invite_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(conn, source_db_path, "family_invites", int(row["id"]), "family", "invites", invite_id)

    def _mirror_family_capital_account(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> bool:
        owner = self.get_user_id_by_legacy(conn, int(row["owner_user_id"]))
        account_id = self._finance_id_by_legacy(conn, "capital_accounts", owner or 0, int(row["capital_account_id"]))
        if owner is None or account_id is None:
            return False
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_capital_accounts (family_id, owner_user_id, capital_account_id, is_visible, is_default_target)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    is_visible = VALUES(is_visible),
                    is_default_target = VALUES(is_default_target)
                """,
                (family_id, owner, account_id, bool(row.get("is_visible")), bool(row.get("is_default_target"))),
            )
            family_account_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(conn, source_db_path, "family_capital_accounts", int(row["id"]), "family", "capital_accounts", family_account_id)
        return True

    def _mirror_family_capital_member_setting(self, conn, family_id: int, row: Dict[str, Any]) -> bool:
        user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        target_owner = self.get_user_id_by_legacy(conn, int(row["target_owner_user_id"])) if row.get("target_owner_user_id") else None
        target_account = self._finance_id_by_legacy(conn, "capital_accounts", target_owner or 0, row.get("target_capital_account_id")) if target_owner else None
        if user_id is None:
            return False
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_capital_member_settings (
                    family_id, user_id, target_owner_user_id, target_capital_account_id
                )
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    target_owner_user_id = VALUES(target_owner_user_id),
                    target_capital_account_id = VALUES(target_capital_account_id)
                """,
                (family_id, user_id, target_owner, target_account),
            )
        return True

    def _mirror_family_category(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> None:
        created_by = self.get_user_id_by_legacy(conn, int(row["created_by_user_id"])) if row.get("created_by_user_id") else None
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_categories (family_id, semantic_key, display_name, type, is_active, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    display_name = VALUES(display_name),
                    type = VALUES(type),
                    is_active = VALUES(is_active)
                """,
                (family_id, row["semantic_key"], row["display_name"], row.get("type") or "both", bool(row.get("is_active", True)), created_by),
            )
            category_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(conn, source_db_path, "family_categories", int(row["id"]), "family", "categories", category_id)

    def _mirror_family_category_binding(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> bool:
        family_category_id = self._mapped_id(conn, source_db_path, None, "family_categories", int(row["family_category_id"]))
        user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        local_category_id = self._finance_id_by_legacy(conn, "categories", user_id or 0, int(row["local_category_id"]))
        confirmed_by = self.get_user_id_by_legacy(conn, int(row["confirmed_by_user_id"])) if row.get("confirmed_by_user_id") else None
        if None in (family_category_id, user_id, local_category_id):
            return False
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_category_bindings (
                    family_id, family_category_id, user_id, local_category_id,
                    local_category_name, local_category_type, status, confirmed_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    family_category_id = VALUES(family_category_id),
                    status = VALUES(status),
                    confirmed_by_user_id = VALUES(confirmed_by_user_id)
                """,
                (
                    family_id,
                    family_category_id,
                    user_id,
                    local_category_id,
                    row["local_category_name"],
                    row["local_category_type"],
                    row.get("status") or "confirmed",
                    confirmed_by,
                ),
            )
            binding_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(conn, source_db_path, "family_category_bindings", int(row["id"]), "family", "category_bindings", binding_id)
        return True

    def _mirror_family_category_audit_resolution(self, conn, source_db_path: str, family_id: int, row: Dict[str, Any]) -> None:
        resolved_by = self.get_user_id_by_legacy(conn, int(row["resolved_by_user_id"])) if row.get("resolved_by_user_id") else None
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO family_category_audit_resolutions (
                    family_id, code, group_key, action, category_names_json, note, resolved_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    category_names_json = VALUES(category_names_json),
                    note = VALUES(note),
                    resolved_by_user_id = VALUES(resolved_by_user_id)
                """,
                (
                    family_id,
                    row["code"],
                    row["group_key"],
                    row["action"],
                    row.get("category_names_json") or "[]",
                    row.get("note") or "",
                    resolved_by,
                ),
            )
            resolution_id = int(cursor.lastrowid)
        self._upsert_null_user_id_map(
            conn,
            source_db_path,
            "family_category_audit_resolutions",
            int(row["id"]),
            "family",
            "category_audit_resolutions",
            resolution_id,
        )

    def _prune_family_category_audit_resolutions(
        self,
        conn,
        source_db_path: str,
        family_id: int,
        current_legacy_ids: Set[int],
    ) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT source_local_id, target_id
                FROM migration_id_map
                WHERE source_db_path = %s
                  AND source_user_id IS NULL
                  AND source_table = 'family_category_audit_resolutions'
                """,
                (str(source_db_path),),
            )
            mapped_rows = cursor.fetchall()
        stale_target_ids = [
            int(row["target_id"])
            for row in mapped_rows
            if int(row["source_local_id"]) not in current_legacy_ids
        ]
        if not stale_target_ids:
            return
        placeholders = ", ".join(["%s"] * len(stale_target_ids))
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM family_category_audit_resolutions
                WHERE family_id = %s
                  AND id IN ({placeholders})
                """,
                (int(family_id), *stale_target_ids),
            )
            cursor.execute(
                f"""
                DELETE FROM migration_id_map
                WHERE source_db_path = %s
                  AND source_user_id IS NULL
                  AND source_table = 'family_category_audit_resolutions'
                  AND target_id IN ({placeholders})
                """,
                (str(source_db_path), *stale_target_ids),
            )
