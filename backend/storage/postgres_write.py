from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

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
        existing = self._finance_id_by_legacy(conn, "transfers", pg_user_id, legacy_transfer_id)
        if existing is not None:
            return existing

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
        if str(row["status"] or "actual") != "actual":
            return {"status": "skipped", "reason": "non_actual_transaction"}

        pg_transaction_id = int(row["id"])
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
