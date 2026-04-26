from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from backend.storage.postgres_read import PostgresReadRepository
from tools.money_minor import to_minor
from tools.money_minor import from_minor_float


DAILY_ACCOUNT_IDS = {1, 2}


class PostgresWriteRepository(PostgresReadRepository):
    """PostgreSQL write adapter for the future SQLite -> PostgreSQL dual-write path."""

    def _account_ref(self, legacy_account_id: int) -> Dict[str, Any]:
        legacy_account_id = int(legacy_account_id)
        if legacy_account_id in DAILY_ACCOUNT_IDS:
            return {
                "kind": "daily",
                "daily_legacy_id": legacy_account_id,
                "capital_legacy_id": None,
            }
        return {
            "kind": "capital",
            "daily_legacy_id": None,
            "capital_legacy_id": legacy_account_id,
        }

    def _finance_id_by_legacy(
        self,
        conn,
        table: str,
        user_id: int,
        legacy_local_id: Optional[int],
    ) -> Optional[int]:
        if legacy_local_id is None:
            return None
        row = conn.execute(
            f"SELECT id FROM finance.{table} WHERE user_id = %s AND legacy_local_id = %s",
            (int(user_id), int(legacy_local_id)),
        ).fetchone()
        return int(row["id"]) if row else None

    def _category_id_by_name(self, conn, user_id: int, category: str) -> Optional[int]:
        row = conn.execute(
            """
            SELECT id
            FROM finance.categories
            WHERE user_id = %s
              AND name = %s
              AND is_active = true
            ORDER BY id
            LIMIT 1
            """,
            (int(user_id), str(category)),
        ).fetchone()
        return int(row["id"]) if row else None

    def _category_id_by_legacy(self, conn, user_id: int, legacy_category_id: Optional[int]) -> Optional[int]:
        if legacy_category_id is None:
            return None
        return self._finance_id_by_legacy(conn, "categories", user_id, int(legacy_category_id))

    def _adjust_account_minor(
        self,
        conn,
        user_id: int,
        legacy_account_id: int,
        delta_minor: int,
    ) -> None:
        ref = self._account_ref(legacy_account_id)
        if ref["kind"] == "daily":
            row = conn.execute(
                """
                UPDATE finance.accounts
                SET balance_minor = balance_minor + %s, updated_at = now()
                WHERE user_id = %s
                  AND legacy_local_id = %s
                  AND is_active = true
                RETURNING id
                """,
                (int(delta_minor), int(user_id), int(legacy_account_id)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE finance.capital_accounts
                SET balance_minor = balance_minor + %s, updated_at = now()
                WHERE user_id = %s
                  AND legacy_local_id = %s
                  AND is_active = true
                RETURNING id
                """,
                (int(delta_minor), int(user_id), int(legacy_account_id)),
            ).fetchone()
        if not row:
            raise RuntimeError(f"PostgreSQL account legacy_local_id={legacy_account_id} was not found")

    def _legacy_account_id_from_transfer_row(self, row: Dict[str, Any], prefix: str) -> int:
        kind = str(row[f"{prefix}_account_kind"])
        if kind == "daily":
            lookup_table = "accounts"
            lookup_id = row[f"{prefix}_daily_account_id"]
        else:
            lookup_table = "capital_accounts"
            lookup_id = row[f"{prefix}_capital_account_id"]
        legacy_row = row.get(f"legacy_{prefix}_account_id")
        if legacy_row is not None:
            return int(legacy_row)
        resolved = row.get(f"{prefix}_legacy_local_id")
        if resolved is not None:
            return int(resolved)
        raise RuntimeError(f"Cannot resolve legacy {prefix} account id for finance.{lookup_table} id={lookup_id}")

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
        conn.execute(
            """
            INSERT INTO migration.id_map (
                source_db_path, source_user_id, source_table, source_local_id,
                target_schema, target_table, target_id
            )
            VALUES (%s, %s, %s, %s, 'finance', %s, %s)
            ON CONFLICT (source_db_path, source_user_id, source_table, source_local_id)
            DO UPDATE SET target_id = excluded.target_id
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
        source_user_id: Optional[int],
        source_table: str,
        source_local_id: Optional[int],
    ) -> Optional[int]:
        if source_local_id is None:
            return None
        row = conn.execute(
            """
            SELECT target_id
            FROM migration.id_map
            WHERE source_db_path = %s
              AND source_user_id IS NOT DISTINCT FROM %s
              AND source_table = %s
              AND source_local_id = %s
            """,
            (str(source_db_path), source_user_id, str(source_table), int(source_local_id)),
        ).fetchone()
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
        updated = conn.execute(
            """
            UPDATE migration.id_map
            SET target_schema = %s, target_table = %s, target_id = %s
            WHERE source_db_path = %s
              AND source_user_id IS NULL
              AND source_table = %s
              AND source_local_id = %s
            """,
            (
                target_schema,
                target_table,
                int(target_id),
                str(source_db_path),
                str(source_table),
                int(source_local_id),
            ),
        )
        if getattr(updated, "rowcount", 0):
            return
        conn.execute(
            """
            INSERT INTO migration.id_map (
                source_db_path, source_user_id, source_table, source_local_id,
                target_schema, target_table, target_id
            )
            VALUES (%s, NULL, %s, %s, %s, %s, %s)
            """,
            (
                str(source_db_path),
                str(source_table),
                int(source_local_id),
                str(target_schema),
                str(target_table),
                int(target_id),
            ),
        )

    def mirror_actual_transaction(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transaction: Dict[str, Any],
        transfers: Iterable[Dict[str, Any]] = (),
    ) -> Dict[str, Any]:
        """Mirror one already-committed SQLite transaction into PostgreSQL exactly once."""
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_transaction_id = int(transaction["id"])
        existing = self._finance_id_by_legacy(conn, "transactions", pg_user_id, legacy_transaction_id)
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
        category_id = self._category_id_by_name(conn, pg_user_id, category)

        row = conn.execute(
            """
            INSERT INTO finance.transactions (
                user_id, legacy_local_id, type, category, category_id,
                amount_minor, comment, date, money_source, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'actual')
            RETURNING id
            """,
            (
                pg_user_id,
                legacy_transaction_id,
                transaction_type,
                category,
                category_id,
                amount_minor,
                transaction.get("comment"),
                transaction["date"],
                money_source,
            ),
        ).fetchone()
        pg_transaction_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "transactions",
            legacy_transaction_id,
            "transactions",
            pg_transaction_id,
        )

        mirrored_transfer_ids = []
        active_transfers = [item for item in transfers if bool(item.get("is_active", True))]
        if transaction_type == "income":
            transfer_minor = 0
            for transfer in active_transfers:
                transfer_minor += to_minor(transfer["amount"])
                mirrored_transfer_ids.append(
                    self._mirror_transfer(
                        conn,
                        pg_user_id,
                        legacy_user_id,
                        source_db_path,
                        transfer,
                        pg_transaction_id,
                    )
                )
            self._adjust_account_minor(conn, pg_user_id, source_account_id, amount_minor - transfer_minor)
        else:
            self._adjust_account_minor(conn, pg_user_id, source_account_id, -amount_minor)

        return {
            "status": "inserted",
            "transaction_id": pg_transaction_id,
            "transfer_ids": mirrored_transfer_ids,
        }

    def mirror_planned_transaction(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transaction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mirror a planned SQLite transaction without touching account balances."""
        status = str(transaction.get("status") or "actual")
        if status != "planned":
            raise RuntimeError("mirror_planned_transaction expects a planned transaction")
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_transaction_id = int(transaction["id"])
        transaction_type = str(transaction["type"])
        amount_minor = to_minor(transaction["amount"])
        money_source = str(transaction.get("money_source") or "cashless")
        category = str(transaction["category"])
        category_id = self._category_id_by_name(conn, pg_user_id, category)
        template_id = None
        if transaction.get("template_id") is not None:
            template_id = self._finance_id_by_legacy(
                conn,
                "recurring_templates",
                pg_user_id,
                int(transaction["template_id"]),
            )
            if template_id is None:
                return {"status": "skipped", "reason": "recurring_template_not_mirrored"}
        existing = self._finance_id_by_legacy(conn, "transactions", pg_user_id, legacy_transaction_id)

        if existing is not None:
            conn.execute(
                """
                UPDATE finance.transactions
                SET
                    type = %s,
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
                (
                    transaction_type,
                    category,
                    category_id,
                    amount_minor,
                    transaction.get("comment"),
                    transaction["date"],
                    money_source,
                    template_id,
                    existing,
                ),
            )
            return {"status": "updated", "transaction_id": existing}

        row = conn.execute(
            """
            INSERT INTO finance.transactions (
                user_id, legacy_local_id, type, category, category_id,
                amount_minor, comment, date, money_source, status, template_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'planned', %s)
            RETURNING id
            """,
            (
                pg_user_id,
                legacy_transaction_id,
                transaction_type,
                category,
                category_id,
                amount_minor,
                transaction.get("comment"),
                transaction["date"],
                money_source,
                template_id,
            ),
        ).fetchone()
        pg_transaction_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "transactions",
            legacy_transaction_id,
            "transactions",
            pg_transaction_id,
        )
        return {"status": "inserted", "transaction_id": pg_transaction_id}

    def mirror_recurring_template(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        template: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mirror one SQLite recurring template into PostgreSQL."""
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_template_id = int(template["id"])
        category_id = self._category_id_by_legacy(conn, pg_user_id, template.get("category_id"))
        amount_minor = to_minor(template["amount"])
        money_source = str(template.get("money_source") or "cashless")
        months_ahead = int(template.get("months_ahead") or 12)
        working_days_only = bool(template.get("working_days_only"))
        is_active = bool(template.get("is_active", True))
        existing = self._finance_id_by_legacy(conn, "recurring_templates", pg_user_id, legacy_template_id)

        if existing is not None:
            conn.execute(
                """
                UPDATE finance.recurring_templates
                SET
                    type = %s,
                    name = %s,
                    amount_minor = %s,
                    day_of_month = %s,
                    category_id = %s,
                    comment_template = %s,
                    money_source = %s,
                    months_ahead = %s,
                    working_days_only = %s,
                    is_active = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    str(template["type"]),
                    str(template["name"]),
                    amount_minor,
                    int(template["day_of_month"]),
                    category_id,
                    template.get("comment_template"),
                    money_source,
                    months_ahead,
                    working_days_only,
                    is_active,
                    existing,
                ),
            )
            return {"status": "updated", "template_id": existing}

        row = conn.execute(
            """
            INSERT INTO finance.recurring_templates (
                user_id, legacy_local_id, type, name, amount_minor, day_of_month, category_id,
                comment_template, money_source, months_ahead, working_days_only, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                pg_user_id,
                legacy_template_id,
                str(template["type"]),
                str(template["name"]),
                amount_minor,
                int(template["day_of_month"]),
                category_id,
                template.get("comment_template"),
                money_source,
                months_ahead,
                working_days_only,
                is_active,
            ),
        ).fetchone()
        pg_template_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "recurring_templates",
            legacy_template_id,
            "recurring_templates",
            pg_template_id,
        )
        return {"status": "inserted", "template_id": pg_template_id}

    def mirror_category(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        category: Dict[str, Any],
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_category_id = int(category["id"])
        existing = self._finance_id_by_legacy(conn, "categories", pg_user_id, legacy_category_id)
        values = (
            str(category["name"]),
            str(category.get("type") or "both"),
            category.get("color"),
            category.get("icon"),
            bool(category.get("is_active", True)),
        )
        if existing is not None:
            conn.execute(
                """
                UPDATE finance.categories
                SET name = %s, type = %s, color = %s, icon = %s, is_active = %s, updated_at = now()
                WHERE id = %s
                """,
                (*values, existing),
            )
            return {"status": "updated", "category_id": existing}

        row = conn.execute(
            """
            INSERT INTO finance.categories (user_id, legacy_local_id, name, type, color, icon, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (pg_user_id, legacy_category_id, *values),
        ).fetchone()
        pg_category_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "categories",
            legacy_category_id,
            "categories",
            pg_category_id,
        )
        return {"status": "inserted", "category_id": pg_category_id}

    def mirror_budget(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        budget: Dict[str, Any],
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_budget_id = int(budget["id"])
        category_id = self._category_id_by_legacy(conn, pg_user_id, budget.get("category_id"))
        if category_id is None:
            return {"status": "skipped", "reason": "category_not_mirrored"}
        amount_minor = to_minor(budget["amount"])
        period = str(budget.get("period") or "monthly")
        existing = self._finance_id_by_legacy(conn, "budgets", pg_user_id, legacy_budget_id)
        if existing is not None:
            conn.execute(
                """
                UPDATE finance.budgets
                SET category_id = %s, amount_minor = %s, period = %s
                WHERE id = %s
                """,
                (category_id, amount_minor, period, existing),
            )
            return {"status": "updated", "budget_id": existing}

        row = conn.execute(
            """
            INSERT INTO finance.budgets (user_id, legacy_local_id, category_id, amount_minor, period)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (pg_user_id, legacy_budget_id, category_id, amount_minor, period),
        ).fetchone()
        pg_budget_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "budgets",
            legacy_budget_id,
            "budgets",
            pg_budget_id,
        )
        return {"status": "inserted", "budget_id": pg_budget_id}

    def mirror_delete_budget(self, conn, legacy_user_id: int, legacy_budget_id: int) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")
        pg_budget_id = self._finance_id_by_legacy(conn, "budgets", pg_user_id, legacy_budget_id)
        if pg_budget_id is None:
            return {"status": "missing"}
        conn.execute("DELETE FROM finance.budgets WHERE id = %s", (pg_budget_id,))
        return {"status": "deleted", "budget_id": pg_budget_id}

    def mirror_capital_account(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        account: Dict[str, Any],
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_account_id = int(account["id"])
        existing = self._finance_id_by_legacy(conn, "capital_accounts", pg_user_id, legacy_account_id)
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
            conn.execute(
                """
                UPDATE finance.capital_accounts
                SET
                    name = %s,
                    balance_minor = %s,
                    currency = %s,
                    icon = %s,
                    color = %s,
                    is_default = %s,
                    is_active = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (*values, existing),
            )
            return {"status": "updated", "account_id": existing}

        row = conn.execute(
            """
            INSERT INTO finance.capital_accounts (
                user_id, legacy_local_id, name, balance_minor, currency, icon, color, is_default, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (pg_user_id, legacy_account_id, *values),
        ).fetchone()
        pg_account_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "capital_accounts",
            legacy_account_id,
            "capital_accounts",
            pg_account_id,
        )
        return {"status": "inserted", "account_id": pg_account_id}

    def mirror_standalone_transfer(
        self,
        conn,
        legacy_user_id: int,
        source_db_path: str,
        transfer: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mirror a manual transfer row and the account balance effect SQLite applied."""
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        legacy_transfer_id = int(transfer["id"])
        existing = self._finance_id_by_legacy(conn, "transfers", pg_user_id, legacy_transfer_id)
        if existing is not None:
            return {"status": "exists", "transfer_id": existing}

        from_legacy = int(transfer["from_account_id"])
        to_legacy = int(transfer["to_account_id"])
        from_ref = self._account_ref(from_legacy)
        to_ref = self._account_ref(to_legacy)
        from_daily_id = self._finance_id_by_legacy(conn, "accounts", pg_user_id, from_ref["daily_legacy_id"])
        to_daily_id = self._finance_id_by_legacy(conn, "accounts", pg_user_id, to_ref["daily_legacy_id"])
        from_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", pg_user_id, from_ref["capital_legacy_id"])
        to_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", pg_user_id, to_ref["capital_legacy_id"])
        amount_minor = to_minor(transfer["amount"])

        row = conn.execute(
            """
            INSERT INTO finance.transfers (
                user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                date, comment, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
            RETURNING id
            """,
            (
                pg_user_id,
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
        ).fetchone()
        pg_transfer_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "transfers",
            legacy_transfer_id,
            "transfers",
            pg_transfer_id,
        )
        if bool(transfer.get("is_active", True)):
            self._adjust_account_minor(conn, pg_user_id, from_legacy, -amount_minor)
            self._adjust_account_minor(conn, pg_user_id, to_legacy, amount_minor)
        return {"status": "inserted", "transfer_id": pg_transfer_id}

    def mirror_family_snapshot(
        self,
        conn,
        source_db_path: str,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mirror one auth.db family snapshot into PostgreSQL family/auth schemas."""
        family = snapshot.get("family") or {}
        legacy_family_id = int(family["id"])
        owner_user_id = self.get_user_id_by_legacy(conn, int(family["owner_user_id"]))
        if owner_user_id is None:
            raise RuntimeError(f"PostgreSQL owner for legacy user {family['owner_user_id']} was not found")

        pg_family_id = self._mapped_id(conn, source_db_path, None, "families", legacy_family_id)
        if pg_family_id is None:
            row = conn.execute(
                """
                INSERT INTO family.families (name, owner_user_id, archived_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (family["name"], owner_user_id, family.get("archived_at")),
            ).fetchone()
            pg_family_id = int(row["id"])
            self._upsert_null_user_id_map(conn, source_db_path, "families", legacy_family_id, "family", "families", pg_family_id)
            family_status = "inserted"
        else:
            conn.execute(
                """
                UPDATE family.families
                SET name = %s, owner_user_id = %s, archived_at = %s, updated_at = now()
                WHERE id = %s
                """,
                (family["name"], owner_user_id, family.get("archived_at"), pg_family_id),
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
            self._mirror_family_membership(conn, source_db_path, pg_family_id, row)
            counts["memberships"] += 1
        for row in snapshot.get("invites", []):
            self._mirror_family_invite(conn, source_db_path, pg_family_id, row)
            counts["invites"] += 1
        for row in snapshot.get("capital_accounts", []):
            if self._mirror_family_capital_account(conn, source_db_path, pg_family_id, row):
                counts["capital_accounts"] += 1
        for row in snapshot.get("capital_member_settings", []):
            if self._mirror_family_capital_member_setting(conn, pg_family_id, row):
                counts["capital_member_settings"] += 1
        for row in snapshot.get("categories", []):
            self._mirror_family_category(conn, source_db_path, pg_family_id, row)
            counts["categories"] += 1
        for row in snapshot.get("category_bindings", []):
            if self._mirror_family_category_binding(conn, source_db_path, pg_family_id, row):
                counts["category_bindings"] += 1
        for row in snapshot.get("category_audit_resolutions", []):
            self._mirror_family_category_audit_resolution(conn, source_db_path, pg_family_id, row)
            counts["category_audit_resolutions"] += 1
        self._prune_family_category_audit_resolutions(
            conn,
            source_db_path,
            pg_family_id,
            {int(row["id"]) for row in snapshot.get("category_audit_resolutions", [])},
        )
        return {"status": family_status, "family_id": pg_family_id, "counts": counts}

    def _prune_family_category_audit_resolutions(
        self,
        conn,
        source_db_path: str,
        pg_family_id: int,
        current_legacy_ids: Set[int],
    ) -> None:
        mapped_rows = conn.execute(
            """
            SELECT source_local_id, target_id
            FROM migration.id_map
            WHERE source_db_path = %s
              AND source_user_id IS NULL
              AND source_table = 'family_category_audit_resolutions'
            """,
            (str(source_db_path),),
        ).fetchall()
        stale_target_ids = [
            int(row["target_id"])
            for row in mapped_rows
            if int(row["source_local_id"]) not in current_legacy_ids
        ]
        if not stale_target_ids:
            return
        deleted = conn.execute(
            """
            DELETE FROM family.category_audit_resolutions
            WHERE family_id = %s
              AND id = ANY(%s)
            RETURNING id
            """,
            (pg_family_id, stale_target_ids),
        ).fetchall()
        for row in deleted:
            conn.execute(
                """
                DELETE FROM migration.id_map
                WHERE source_db_path = %s
                  AND source_user_id IS NULL
                  AND source_table = 'family_category_audit_resolutions'
                  AND target_id = %s
                """,
                (str(source_db_path), int(row["id"])),
            )

    def _normalize_family_role(self, role: Any) -> str:
        return str(role or "member") if str(role or "member") in {"owner", "member", "viewer"} else "member"

    def _normalize_family_status(self, status: Any) -> str:
        value = str(status or "active")
        return "removed" if value == "revoked" else value if value in {"active", "inactive", "removed"} else "active"

    def _mirror_family_membership(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> None:
        pg_user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        invited_by = self.get_user_id_by_legacy(conn, int(row["invited_by_user_id"])) if row.get("invited_by_user_id") else None
        if pg_user_id is None:
            return
        pg_row = conn.execute(
            """
            INSERT INTO family.memberships (family_id, user_id, role, status, invited_by_user_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (family_id, user_id) DO UPDATE SET
                role = excluded.role,
                status = excluded.status,
                invited_by_user_id = excluded.invited_by_user_id,
                updated_at = now()
            RETURNING id
            """,
            (pg_family_id, pg_user_id, self._normalize_family_role(row.get("role")), self._normalize_family_status(row.get("status")), invited_by),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_memberships", int(row["id"]), "family", "memberships", int(pg_row["id"]))

    def _mirror_family_invite(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> None:
        invited_by = self.get_user_id_by_legacy(conn, int(row["invited_by_user_id"]))
        if invited_by is None:
            return
        pg_row = conn.execute(
            """
            INSERT INTO family.invites (
                family_id, email, role, token_hash, invited_by_user_id, expires_at, accepted_at, revoked_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (token_hash) DO UPDATE SET
                accepted_at = excluded.accepted_at,
                revoked_at = excluded.revoked_at
            RETURNING id
            """,
            (
                pg_family_id,
                row["email"],
                self._normalize_family_role(row.get("role")),
                row["token_hash"],
                invited_by,
                row["expires_at"],
                row.get("accepted_at"),
                row.get("revoked_at"),
            ),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_invites", int(row["id"]), "family", "invites", int(pg_row["id"]))

    def _mirror_family_capital_account(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> bool:
        owner = self.get_user_id_by_legacy(conn, int(row["owner_user_id"]))
        account_id = self._finance_id_by_legacy(conn, "capital_accounts", owner or 0, int(row["capital_account_id"]))
        if owner is None or account_id is None:
            return False
        pg_row = conn.execute(
            """
            INSERT INTO family.capital_accounts (family_id, owner_user_id, capital_account_id, is_visible, is_default_target)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (family_id, owner_user_id, capital_account_id) DO UPDATE SET
                is_visible = excluded.is_visible,
                is_default_target = excluded.is_default_target,
                updated_at = now()
            RETURNING id
            """,
            (pg_family_id, owner, account_id, bool(row.get("is_visible")), bool(row.get("is_default_target"))),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_capital_accounts", int(row["id"]), "family", "capital_accounts", int(pg_row["id"]))
        return True

    def _mirror_family_capital_member_setting(self, conn, pg_family_id: int, row: Dict[str, Any]) -> bool:
        user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        target_owner = self.get_user_id_by_legacy(conn, int(row["target_owner_user_id"])) if row.get("target_owner_user_id") else None
        target_account = self._finance_id_by_legacy(conn, "capital_accounts", target_owner or 0, row.get("target_capital_account_id")) if target_owner else None
        if user_id is None:
            return False
        conn.execute(
            """
            INSERT INTO family.capital_member_settings (
                family_id, user_id, target_owner_user_id, target_capital_account_id
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (family_id, user_id) DO UPDATE SET
                target_owner_user_id = excluded.target_owner_user_id,
                target_capital_account_id = excluded.target_capital_account_id,
                updated_at = now()
            """,
            (pg_family_id, user_id, target_owner, target_account),
        )
        return True

    def _mirror_family_category(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> None:
        created_by = self.get_user_id_by_legacy(conn, int(row["created_by_user_id"])) if row.get("created_by_user_id") else None
        pg_row = conn.execute(
            """
            INSERT INTO family.categories (family_id, semantic_key, display_name, type, is_active, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (family_id, semantic_key) DO UPDATE SET
                display_name = excluded.display_name,
                type = excluded.type,
                is_active = excluded.is_active,
                updated_at = now()
            RETURNING id
            """,
            (pg_family_id, row["semantic_key"], row["display_name"], row.get("type") or "both", bool(row.get("is_active", True)), created_by),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_categories", int(row["id"]), "family", "categories", int(pg_row["id"]))

    def _mirror_family_category_binding(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> bool:
        family_category_id = self._mapped_id(conn, source_db_path, None, "family_categories", int(row["family_category_id"]))
        user_id = self.get_user_id_by_legacy(conn, int(row["user_id"]))
        local_category_id = self._finance_id_by_legacy(conn, "categories", user_id or 0, int(row["local_category_id"]))
        confirmed_by = self.get_user_id_by_legacy(conn, int(row["confirmed_by_user_id"])) if row.get("confirmed_by_user_id") else None
        if None in (family_category_id, user_id, local_category_id):
            return False
        pg_row = conn.execute(
            """
            INSERT INTO family.category_bindings (
                family_id, family_category_id, user_id, local_category_id,
                local_category_name, local_category_type, status, confirmed_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (family_id, user_id, local_category_id) DO UPDATE SET
                family_category_id = excluded.family_category_id,
                status = excluded.status,
                confirmed_by_user_id = excluded.confirmed_by_user_id,
                updated_at = now()
            RETURNING id
            """,
            (
                pg_family_id,
                family_category_id,
                user_id,
                local_category_id,
                row["local_category_name"],
                row["local_category_type"],
                row.get("status") or "confirmed",
                confirmed_by,
            ),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_category_bindings", int(row["id"]), "family", "category_bindings", int(pg_row["id"]))
        return True

    def _mirror_family_category_audit_resolution(self, conn, source_db_path: str, pg_family_id: int, row: Dict[str, Any]) -> None:
        resolved_by = self.get_user_id_by_legacy(conn, int(row["resolved_by_user_id"])) if row.get("resolved_by_user_id") else None
        pg_row = conn.execute(
            """
            INSERT INTO family.category_audit_resolutions (
                family_id, code, group_key, action, category_names_json, note, resolved_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (family_id, code, group_key, action) DO UPDATE SET
                category_names_json = excluded.category_names_json,
                note = excluded.note,
                resolved_by_user_id = excluded.resolved_by_user_id,
                updated_at = now()
            RETURNING id
            """,
            (
                pg_family_id,
                row["code"],
                row["group_key"],
                row["action"],
                row.get("category_names_json") or "[]",
                row.get("note") or "",
                resolved_by,
            ),
        ).fetchone()
        self._upsert_null_user_id_map(conn, source_db_path, "family_category_audit_resolutions", int(row["id"]), "family", "category_audit_resolutions", int(pg_row["id"]))

    def delete_planned_transactions_for_template(
        self,
        conn,
        legacy_user_id: int,
        legacy_template_id: int,
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")
        pg_template_id = self._finance_id_by_legacy(conn, "recurring_templates", pg_user_id, legacy_template_id)
        if pg_template_id is None:
            return {"status": "missing_template", "deleted": 0}
        rows = conn.execute(
            """
            DELETE FROM finance.transactions
            WHERE user_id = %s
              AND template_id = %s
              AND status = 'planned'
            RETURNING id
            """,
            (pg_user_id, pg_template_id),
        ).fetchall()
        return {"status": "deleted", "deleted": len(rows), "template_id": pg_template_id}

    def mirror_delete_recurring_template(
        self,
        conn,
        legacy_user_id: int,
        legacy_template_id: int,
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")
        pg_template_id = self._finance_id_by_legacy(conn, "recurring_templates", pg_user_id, legacy_template_id)
        if pg_template_id is None:
            return {"status": "missing"}
        planned_result = self.delete_planned_transactions_for_template(conn, legacy_user_id, legacy_template_id)
        conn.execute("DELETE FROM finance.recurring_templates WHERE id = %s", (pg_template_id,))
        return {
            "status": "deleted",
            "template_id": pg_template_id,
            "planned_deleted": planned_result.get("deleted", 0),
        }

    def _mirror_transfer(
        self,
        conn,
        pg_user_id: int,
        legacy_user_id: int,
        source_db_path: str,
        transfer: Dict[str, Any],
        pg_transaction_id: int,
    ) -> int:
        legacy_transfer_id = int(transfer["id"])
        existing = conn.execute(
            """
            SELECT id, is_active
            FROM finance.transfers
            WHERE user_id = %s AND legacy_local_id = %s
            """,
            (int(pg_user_id), legacy_transfer_id),
        ).fetchone()

        from_legacy = int(transfer["from_account_id"])
        to_legacy = int(transfer["to_account_id"])
        from_ref = self._account_ref(from_legacy)
        to_ref = self._account_ref(to_legacy)
        from_daily_id = self._finance_id_by_legacy(conn, "accounts", pg_user_id, from_ref["daily_legacy_id"])
        to_daily_id = self._finance_id_by_legacy(conn, "accounts", pg_user_id, to_ref["daily_legacy_id"])
        from_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", pg_user_id, from_ref["capital_legacy_id"])
        to_capital_id = self._finance_id_by_legacy(conn, "capital_accounts", pg_user_id, to_ref["capital_legacy_id"])
        amount_minor = to_minor(transfer["amount"])

        if existing is not None:
            pg_transfer_id = int(existing["id"])
            if bool(existing["is_active"]):
                return pg_transfer_id
            conn.execute(
                """
                UPDATE finance.transfers
                SET
                    legacy_from_account_id = %s,
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
                    is_active = true
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
                    int(pg_transaction_id),
                    transfer["date"],
                    transfer.get("comment"),
                    pg_transfer_id,
                ),
            )
            self._adjust_account_minor(conn, pg_user_id, to_legacy, amount_minor)
            return pg_transfer_id

        row = conn.execute(
            """
            INSERT INTO finance.transfers (
                user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                date, comment, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            RETURNING id
            """,
            (
                pg_user_id,
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
                int(pg_transaction_id),
                transfer["date"],
                transfer.get("comment"),
            ),
        ).fetchone()
        pg_transfer_id = int(row["id"])
        self._insert_id_map(
            conn,
            source_db_path,
            legacy_user_id,
            "transfers",
            legacy_transfer_id,
            "transfers",
            pg_transfer_id,
        )
        self._adjust_account_minor(conn, pg_user_id, to_legacy, amount_minor)
        return pg_transfer_id

    def mirror_delete_transaction(
        self,
        conn,
        legacy_user_id: int,
        legacy_transaction_id: int,
    ) -> Dict[str, Any]:
        pg_user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")

        row = conn.execute(
            """
            SELECT id, type, amount_minor, money_source, status
            FROM finance.transactions
            WHERE user_id = %s AND legacy_local_id = %s
            """,
            (int(pg_user_id), int(legacy_transaction_id)),
        ).fetchone()
        if not row:
            return {"status": "missing"}
        status = str(row["status"] or "actual")
        pg_transaction_id = int(row["id"])
        if status == "planned":
            conn.execute("DELETE FROM finance.transactions WHERE id = %s", (pg_transaction_id,))
            return {
                "status": "deleted",
                "transaction_id": pg_transaction_id,
                "planned": True,
                "transfers_deactivated": 0,
            }
        if status != "actual":
            return {"status": "skipped", "reason": "non_actual_transaction"}

        amount_minor = int(row["amount_minor"] or 0)
        source_account_id = 2 if str(row["money_source"] or "cashless") == "cash" else 1
        transfer_rows = conn.execute(
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
            FROM finance.transfers t
            LEFT JOIN finance.accounts from_daily ON from_daily.id = t.from_daily_account_id
            LEFT JOIN finance.accounts to_daily ON to_daily.id = t.to_daily_account_id
            LEFT JOIN finance.capital_accounts from_capital ON from_capital.id = t.from_capital_account_id
            LEFT JOIN finance.capital_accounts to_capital ON to_capital.id = t.to_capital_account_id
            WHERE t.user_id = %s
              AND t.transaction_id = %s
              AND t.is_active = true
            ORDER BY t.id
            """,
            (int(pg_user_id), pg_transaction_id),
        ).fetchall()

        transfer_minor = 0
        for transfer in transfer_rows:
            transfer_amount_minor = int(transfer["amount_minor"] or 0)
            transfer_minor += transfer_amount_minor
            to_legacy = self._legacy_account_id_from_transfer_row(transfer, "to")
            self._adjust_account_minor(conn, pg_user_id, to_legacy, -transfer_amount_minor)
            conn.execute("UPDATE finance.transfers SET is_active = false WHERE id = %s", (int(transfer["id"]),))

        if str(row["type"]) == "income":
            self._adjust_account_minor(conn, pg_user_id, source_account_id, -(amount_minor - transfer_minor))
        else:
            self._adjust_account_minor(conn, pg_user_id, source_account_id, amount_minor)

        conn.execute("DELETE FROM finance.transactions WHERE id = %s", (pg_transaction_id,))
        return {
            "status": "deleted",
            "transaction_id": pg_transaction_id,
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
        if status == "planned":
            return self.mirror_planned_transaction(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                transaction=transaction,
            )
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
