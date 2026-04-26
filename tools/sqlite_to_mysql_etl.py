from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.money_minor import to_minor
from tools.mysql_schema import apply_schema, mysql_connect
from tools.sqlite_inventory import classify_db, discover_databases, open_readonly
from tools.sqlite_to_postgres_etl import (
    FAMILY_TABLE_ORDER,
    FINANCE_TABLE_ORDER,
    EtlError,
    build_report,
    classify_transfer_account,
    finance_user_hint,
    integer_set,
    row_bool,
    row_value,
    select_all,
)


TARGET_TABLES = {
    "users": ("auth", "users", "auth_users"),
    "families": ("family", "families", "family_families"),
    "family_memberships": ("family", "memberships", "family_memberships"),
    "family_invites": ("family", "invites", "family_invites"),
    "family_capital_accounts": ("family", "capital_accounts", "family_capital_accounts"),
    "family_capital_contributions": ("family", "capital_contributions", "family_capital_contributions"),
    "family_categories": ("family", "categories", "family_categories"),
    "family_category_bindings": ("family", "category_bindings", "family_category_bindings"),
    "family_category_audit_resolutions": ("family", "category_audit_resolutions", "family_category_audit_resolutions"),
    "accounts": ("finance", "accounts", "finance_accounts"),
    "budgets": ("finance", "budgets", "finance_budgets"),
    "capital_accounts": ("finance", "capital_accounts", "finance_capital_accounts"),
    "categories": ("finance", "categories", "finance_categories"),
    "reconciliation_sources": ("finance", "reconciliation_sources", "finance_reconciliation_sources"),
    "reconciliations": ("finance", "reconciliations", "finance_reconciliations"),
    "recurring_templates": ("finance", "recurring_templates", "finance_recurring_templates"),
    "transactions": ("finance", "transactions", "finance_transactions"),
    "transfers": ("finance", "transfers", "finance_transfers"),
}


class MySqlEtlWriter:
    def __init__(self, source_root: Path):
        self.source_root = source_root.resolve()
        self.id_maps: Dict[Tuple[str, Optional[int], str, int], int] = {}
        self.category_name_maps: Dict[Tuple[str, Optional[int], str], int] = {}
        self.finance_db_by_legacy_user_id: Dict[int, Path] = {}

    def source_key(self, db_path: Path) -> str:
        try:
            return str(db_path.resolve().relative_to(self.source_root))
        except ValueError:
            return str(db_path.resolve())

    def insert(self, cursor, sql: str, params: Tuple[Any, ...]) -> int:
        cursor.execute(sql, params)
        return int(cursor.lastrowid)

    def remember_id(
        self,
        cursor,
        db_path: Path,
        source_user_id: Optional[int],
        source_table: str,
        source_local_id: int,
        target_id: int,
    ) -> None:
        target_schema, target_table, _ = TARGET_TABLES[source_table]
        source_db_path = self.source_key(db_path)
        self.id_maps[(source_db_path, source_user_id, source_table, int(source_local_id))] = int(target_id)
        cursor.execute(
            """
            INSERT INTO migration_id_map (
                source_db_path, source_user_id, source_table, source_local_id,
                target_schema, target_table, target_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                source_db_path,
                source_user_id,
                source_table,
                int(source_local_id),
                target_schema,
                target_table,
                int(target_id),
            ),
        )

    def mapped_id(
        self,
        db_path: Path,
        source_user_id: Optional[int],
        source_table: str,
        source_local_id: Any,
    ) -> Optional[int]:
        if source_local_id is None:
            return None
        try:
            return self.id_maps.get((self.source_key(db_path), source_user_id, source_table, int(source_local_id)))
        except (TypeError, ValueError):
            return None

    def mapped_user_id(self, user_map: Dict[int, int], legacy_user_id: Any) -> Optional[int]:
        if legacy_user_id is None:
            return None
        try:
            return user_map.get(int(legacy_user_id))
        except (TypeError, ValueError):
            return None

    def mapped_finance_id(self, legacy_user_id: Any, source_table: str, source_local_id: Any) -> Optional[int]:
        try:
            user_id = int(legacy_user_id)
        except (TypeError, ValueError):
            return None
        db_path = self.finance_db_by_legacy_user_id.get(user_id)
        if db_path is None:
            return None
        return self.mapped_id(db_path, user_id, source_table, source_local_id)

    def ensure_user(self, cursor, legacy_user_id: Optional[int], email: str, password_hash: str = "migration-placeholder") -> int:
        cursor.execute(
            """
            SELECT id
            FROM auth_users
            WHERE email = %s
               OR (legacy_sqlite_user_id <=> %s)
            LIMIT 1
            """,
            (email, legacy_user_id),
        )
        row = cursor.fetchone()
        if row:
            return int(row["id"])
        return self.insert(
            cursor,
            """
            INSERT INTO auth_users (email, password_hash, email_verified, is_active, legacy_sqlite_user_id)
            VALUES (%s, %s, TRUE, TRUE, %s)
            """,
            (email, password_hash, legacy_user_id),
        )

    def load_auth(self, cursor, db_path: Path) -> Dict[int, int]:
        user_map: Dict[int, int] = {}
        if not db_path.exists() or db_path.stat().st_size == 0:
            return user_map
        with open_readonly(db_path) as sqlite_conn:
            for row in select_all(sqlite_conn, "users"):
                columns = set(row.keys())
                legacy_id = int(row["id"])
                user_id = self.ensure_user(
                    cursor,
                    legacy_id,
                    str(row["email"]),
                    str(row_value(row, columns, "password_hash", "migration-placeholder")),
                )
                user_map[legacy_id] = user_id
                self.remember_id(cursor, db_path, legacy_id, "users", legacy_id, user_id)
            for row in select_all(sqlite_conn, "user_preferences"):
                columns = set(row.keys())
                user_id = user_map.get(int(row["user_id"]))
                if user_id is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO auth_user_preferences (user_id, theme_mode, workspace_mode, display_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        row_value(row, columns, "theme_mode", "system") or "system",
                        row_value(row, columns, "workspace_mode", "personal") or "personal",
                        row_value(row, columns, "display_name", "") or "",
                    ),
                )
        return user_map

    def load_finance_db(
        self,
        cursor,
        db_path: Path,
        db_kind: str,
        root: Path,
        users_dir: str,
        user_map: Dict[int, int],
    ) -> Dict[str, int]:
        legacy_user_id, fallback_email = finance_user_hint(db_path, db_kind, root, users_dir)
        user_id = user_map.get(legacy_user_id) if legacy_user_id is not None else None
        if user_id is None:
            user_id = self.ensure_user(cursor, legacy_user_id, fallback_email)
            if legacy_user_id is not None:
                user_map[legacy_user_id] = user_id
        if legacy_user_id is not None:
            self.finance_db_by_legacy_user_id[int(legacy_user_id)] = db_path

        counts = {table: 0 for table in FINANCE_TABLE_ORDER}
        with open_readonly(db_path) as sqlite_conn:
            self._load_accounts(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_categories(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_transactions(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_capital_accounts(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_budgets(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_recurring_templates(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_reconciliation_sources(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_reconciliations(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
            self._load_app_settings(cursor, sqlite_conn, user_id, counts)
            self._load_transfers(cursor, db_path, sqlite_conn, legacy_user_id, user_id, counts)
        return counts

    def _remember_category_name(self, db_path: Path, legacy_user_id: Optional[int], name: str, target_id: int) -> None:
        self.category_name_maps[(self.source_key(db_path), legacy_user_id, str(name))] = int(target_id)

    def _category_id_for_transaction(self, db_path: Path, legacy_user_id: Optional[int], category_name: str) -> Optional[int]:
        return self.category_name_maps.get((self.source_key(db_path), legacy_user_id, str(category_name)))

    def _load_accounts(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "accounts"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_accounts (
                    user_id, legacy_local_id, name, type, money_source, balance_minor, currency, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    row["name"],
                    row["type"],
                    row_value(row, columns, "money_source"),
                    to_minor(row_value(row, columns, "balance", 0)),
                    row_value(row, columns, "currency", "RUB") or "RUB",
                    row_bool(row, columns, "is_active", True),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "accounts", local_id, target_id)
            counts["accounts"] += 1

    def _load_categories(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "categories"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_categories (
                    user_id, legacy_local_id, name, type, color, icon, is_active,
                    semantic_key, scope, sync_status, original_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    row["name"],
                    row["type"],
                    row_value(row, columns, "color"),
                    row_value(row, columns, "icon"),
                    row_bool(row, columns, "is_active", True),
                    row_value(row, columns, "semantic_key"),
                    row_value(row, columns, "scope", "personal") or "personal",
                    row_value(row, columns, "sync_status", "unlinked") or "unlinked",
                    row_value(row, columns, "original_name"),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "categories", local_id, target_id)
            self._remember_category_name(db_path, legacy_user_id, str(row["name"]), target_id)
            counts["categories"] += 1

    def _load_transactions(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "transactions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_transactions (
                    user_id, legacy_local_id, type, category, category_id, semantic_key,
                    original_category_name, amount_minor, comment, date, money_source,
                    status, executed_at, template_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    row["type"],
                    row["category"],
                    self._category_id_for_transaction(db_path, legacy_user_id, row["category"]),
                    row_value(row, columns, "semantic_key"),
                    row_value(row, columns, "original_category_name"),
                    to_minor(row["amount"]),
                    row_value(row, columns, "comment"),
                    row["date"],
                    row_value(row, columns, "money_source", "cashless") or "cashless",
                    row_value(row, columns, "status", "actual") or "actual",
                    row_value(row, columns, "executed_at"),
                    row_value(row, columns, "template_id"),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "transactions", local_id, target_id)
            counts["transactions"] += 1

    def _load_budgets(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "budgets"):
            local_id = int(row["id"])
            category_id = self.mapped_id(db_path, legacy_user_id, "categories", row["category_id"])
            if category_id is None:
                raise EtlError(f"Missing category mapping for budget {local_id} in {db_path}")
            target_id = self.insert(
                cursor,
                "INSERT INTO finance_budgets (user_id, legacy_local_id, category_id, amount_minor, period) VALUES (%s, %s, %s, %s, %s)",
                (user_id, local_id, category_id, to_minor(row["amount"]), row["period"]),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "budgets", local_id, target_id)
            counts["budgets"] += 1

    def _load_capital_accounts(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "capital_accounts"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_capital_accounts (
                    user_id, legacy_local_id, name, balance_minor, currency, icon, color, purpose, is_default, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    row["name"],
                    to_minor(row_value(row, columns, "balance", 0)),
                    row_value(row, columns, "currency", "RUB") or "RUB",
                    row_value(row, columns, "icon"),
                    row_value(row, columns, "color"),
                    row_value(row, columns, "purpose", "cushion") or "cushion",
                    row_bool(row, columns, "is_default", False),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "capital_accounts", local_id, target_id)
            counts["capital_accounts"] += 1

    def _load_recurring_templates(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "recurring_templates"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_recurring_templates (
                    user_id, legacy_local_id, type, name, amount_minor, day_of_month, category_id,
                    comment_template, money_source, months_ahead, working_days_only, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    row["type"],
                    row["name"],
                    to_minor(row["amount"]),
                    int(row["day_of_month"]),
                    self.mapped_id(db_path, legacy_user_id, "categories", row_value(row, columns, "category_id")),
                    row_value(row, columns, "comment_template"),
                    row_value(row, columns, "money_source", "cashless") or "cashless",
                    int(row_value(row, columns, "months_ahead", 12) or 12),
                    row_bool(row, columns, "working_days_only", False),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "recurring_templates", local_id, target_id)
            counts["recurring_templates"] += 1

    def _load_reconciliation_sources(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "reconciliation_sources"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                "INSERT INTO finance_reconciliation_sources (user_id, legacy_local_id, name, balance_minor, is_active) VALUES (%s, %s, %s, %s, %s)",
                (user_id, local_id, row["name"], to_minor(row_value(row, columns, "balance", 0)), row_bool(row, columns, "is_active", True)),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "reconciliation_sources", local_id, target_id)
            counts["reconciliation_sources"] += 1

    def _load_reconciliations(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "reconciliations"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_reconciliations (
                    user_id, legacy_local_id, real_balance_minor, program_balance_minor,
                    difference_minor, adjustment_transaction_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    to_minor(row["real_balance"]),
                    to_minor(row["program_balance"]),
                    to_minor(row["difference"]),
                    self.mapped_id(db_path, legacy_user_id, "transactions", row_value(row, columns, "adjustment_transaction_id")),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "reconciliations", local_id, target_id)
            counts["reconciliations"] += 1

    def _load_app_settings(self, cursor, conn: sqlite3.Connection, user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(conn, "app_settings"):
            cursor.execute(
                "INSERT INTO finance_app_settings (user_id, `key`, value) VALUES (%s, %s, %s)",
                (user_id, row["key"], row["value"]),
            )
            counts["app_settings"] += 1

    def _load_transfers(self, cursor, db_path: Path, conn: sqlite3.Connection, legacy_user_id: Optional[int], user_id: int, counts: Dict[str, int]) -> None:
        daily_ids = integer_set(conn, "accounts", "id")
        capital_ids = integer_set(conn, "capital_accounts", "id")
        for row in select_all(conn, "transfers"):
            columns = set(row.keys())
            local_id = int(row["id"])
            from_ref = self._transfer_ref(db_path, legacy_user_id, row["from_account_id"], daily_ids, capital_ids)
            to_ref = self._transfer_ref(db_path, legacy_user_id, row["to_account_id"], daily_ids, capital_ids)
            target_id = self.insert(
                cursor,
                """
                INSERT INTO finance_transfers (
                    user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                    from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                    from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                    date, comment, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    local_id,
                    int(row["from_account_id"]),
                    int(row["to_account_id"]),
                    from_ref["kind"],
                    to_ref["kind"],
                    from_ref["daily_id"],
                    to_ref["daily_id"],
                    from_ref["capital_id"],
                    to_ref["capital_id"],
                    to_minor(row["amount"]),
                    self.mapped_id(db_path, legacy_user_id, "transactions", row_value(row, columns, "transaction_id")),
                    row["date"],
                    row_value(row, columns, "comment"),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            self.remember_id(cursor, db_path, legacy_user_id, "transfers", local_id, target_id)
            counts["transfers"] += 1

    def _transfer_ref(self, db_path: Path, legacy_user_id: Optional[int], account_id: Any, daily_ids: set, capital_ids: set) -> Dict[str, Any]:
        local_id = int(account_id)
        classified = classify_transfer_account(local_id, daily_ids, capital_ids)
        if classified["issue"]:
            raise EtlError(f"Transfer account {local_id} is {classified['issue']} in {db_path}")
        if classified["kind"] == "daily":
            return {"kind": "daily", "daily_id": self.mapped_id(db_path, legacy_user_id, "accounts", local_id), "capital_id": None}
        return {"kind": "capital", "daily_id": None, "capital_id": self.mapped_id(db_path, legacy_user_id, "capital_accounts", local_id)}

    def _family_id(self, db_path: Path, legacy_family_id: Any) -> Optional[int]:
        return self.mapped_id(db_path, None, "families", legacy_family_id)

    def _family_category_id(self, db_path: Path, legacy_family_category_id: Any) -> Optional[int]:
        return self.mapped_id(db_path, None, "family_categories", legacy_family_category_id)

    def load_family_auth(self, cursor, db_path: Path, user_map: Dict[int, int]) -> Dict[str, int]:
        counts = {table: 0 for table in FAMILY_TABLE_ORDER}
        if not db_path.exists() or db_path.stat().st_size == 0:
            return counts
        with open_readonly(db_path) as conn:
            self._load_families(cursor, db_path, conn, user_map, counts)
            self._load_family_memberships(cursor, db_path, conn, user_map, counts)
            self._load_family_invites(cursor, db_path, conn, user_map, counts)
            self._load_family_capital_accounts(cursor, db_path, conn, user_map, counts)
            self._load_family_capital_member_settings(cursor, db_path, conn, user_map, counts)
            self._load_family_capital_contributions(cursor, db_path, conn, user_map, counts)
            self._load_family_categories(cursor, db_path, conn, user_map, counts)
            self._load_family_category_bindings(cursor, db_path, conn, user_map, counts)
            self._load_family_category_audit_resolutions(cursor, db_path, conn, user_map, counts)
        return counts

    def _load_families(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "families"):
            columns = set(row.keys())
            local_id = int(row["id"])
            owner_user_id = self.mapped_user_id(user_map, row["owner_user_id"])
            if owner_user_id is None:
                raise EtlError(f"Missing owner user mapping for family {local_id}")
            target_id = self.insert(
                cursor,
                "INSERT INTO family_families (name, owner_user_id, archived_at) VALUES (%s, %s, %s)",
                (row["name"], owner_user_id, row_value(row, columns, "archived_at")),
            )
            self.remember_id(cursor, db_path, None, "families", local_id, target_id)
            counts["families"] += 1

    def _load_family_memberships(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_memberships"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            if family_id is None or user_id is None:
                raise EtlError(f"Missing membership mapping for family_memberships {row['id']}")
            status = row_value(row, columns, "status", "active") or "active"
            target_id = self.insert(
                cursor,
                "INSERT INTO family_memberships (family_id, user_id, role, status, invited_by_user_id) VALUES (%s, %s, %s, %s, %s)",
                (
                    family_id,
                    user_id,
                    row["role"] if row["role"] not in {"admin", "accountant"} else "member",
                    "removed" if status == "revoked" else status,
                    self.mapped_user_id(user_map, row_value(row, columns, "invited_by_user_id")),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_memberships", int(row["id"]), target_id)
            counts["family_memberships"] += 1

    def _load_family_invites(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_invites"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            invited_by_user_id = self.mapped_user_id(user_map, row["invited_by_user_id"])
            if family_id is None or invited_by_user_id is None:
                raise EtlError(f"Missing invite mapping for family_invites {row['id']}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_invites (
                    family_id, email, role, token_hash, invited_by_user_id,
                    expires_at, accepted_at, revoked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    row["email"],
                    row["role"] if row["role"] not in {"admin", "accountant"} else "member",
                    row["token_hash"],
                    invited_by_user_id,
                    row["expires_at"],
                    row_value(row, columns, "accepted_at"),
                    row_value(row, columns, "revoked_at"),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_invites", int(row["id"]), target_id)
            counts["family_invites"] += 1

    def _load_family_capital_accounts(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_capital_accounts"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            owner_user_id = self.mapped_user_id(user_map, row["owner_user_id"])
            capital_account_id = self.mapped_finance_id(row["owner_user_id"], "capital_accounts", row["capital_account_id"])
            if family_id is None or owner_user_id is None or capital_account_id is None:
                raise EtlError(f"Missing capital account mapping for family_capital_accounts {row['id']}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_capital_accounts (
                    family_id, owner_user_id, capital_account_id, is_visible, is_default_target
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    owner_user_id,
                    capital_account_id,
                    row_bool(row, columns, "is_visible", False),
                    row_bool(row, columns, "is_default_target", False),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_capital_accounts", int(row["id"]), target_id)
            counts["family_capital_accounts"] += 1

    def _load_family_capital_member_settings(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_capital_member_settings"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            if family_id is None or user_id is None:
                raise EtlError("Missing capital member settings family/user mapping")
            target_owner_user_id = self.mapped_user_id(user_map, row_value(row, columns, "target_owner_user_id"))
            cursor.execute(
                """
                INSERT INTO family_capital_member_settings (
                    family_id, user_id, target_owner_user_id, target_capital_account_id
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    family_id,
                    user_id,
                    target_owner_user_id,
                    self.mapped_finance_id(
                        row_value(row, columns, "target_owner_user_id"),
                        "capital_accounts",
                        row_value(row, columns, "target_capital_account_id"),
                    ) if target_owner_user_id is not None else None,
                ),
            )
            counts["family_capital_member_settings"] += 1

    def _load_family_capital_contributions(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_capital_contributions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            source_user_id = self.mapped_user_id(user_map, row["source_user_id"])
            target_owner_user_id = self.mapped_user_id(user_map, row["target_owner_user_id"])
            target_capital_account_id = self.mapped_finance_id(row["target_owner_user_id"], "capital_accounts", row["target_capital_account_id"])
            if None in (family_id, source_user_id, target_owner_user_id, target_capital_account_id):
                raise EtlError(f"Missing contribution mapping for family_capital_contributions {local_id}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_capital_contributions (
                    family_id, source_user_id, legacy_source_transaction_id, source_transaction_id,
                    target_owner_user_id, target_capital_account_id, amount_minor, date, comment, reversed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    source_user_id,
                    int(row["source_transaction_id"]),
                    self.mapped_finance_id(row["source_user_id"], "transactions", row["source_transaction_id"]),
                    target_owner_user_id,
                    target_capital_account_id,
                    to_minor(row["amount"]),
                    row["date"],
                    row_value(row, columns, "comment"),
                    row_value(row, columns, "reversed_at"),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_capital_contributions", local_id, target_id)
            counts["family_capital_contributions"] += 1

    def _load_family_categories(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_categories"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            if family_id is None:
                raise EtlError(f"Missing family mapping for family_categories {local_id}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_categories (family_id, semantic_key, display_name, type, is_active, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    row["semantic_key"],
                    row["display_name"],
                    row_value(row, columns, "type", "both") or "both",
                    row_bool(row, columns, "is_active", True),
                    self.mapped_user_id(user_map, row_value(row, columns, "created_by_user_id")),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_categories", local_id, target_id)
            counts["family_categories"] += 1

    def _load_family_category_bindings(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_category_bindings"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            family_category_id = self._family_category_id(db_path, row["family_category_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            local_category_id = self.mapped_finance_id(row["user_id"], "categories", row["local_category_id"])
            if None in (family_id, family_category_id, user_id, local_category_id):
                raise EtlError(f"Missing category binding mapping for family_category_bindings {local_id}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_category_bindings (
                    family_id, family_category_id, user_id, local_category_id,
                    local_category_name, local_category_type, status, confirmed_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    family_category_id,
                    user_id,
                    local_category_id,
                    row["local_category_name"],
                    row["local_category_type"],
                    row_value(row, columns, "status", "confirmed") or "confirmed",
                    self.mapped_user_id(user_map, row_value(row, columns, "confirmed_by_user_id")),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_category_bindings", local_id, target_id)
            counts["family_category_bindings"] += 1

    def _load_family_category_audit_resolutions(self, cursor, db_path: Path, conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(conn, "family_category_audit_resolutions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            if family_id is None:
                raise EtlError(f"Missing family mapping for family_category_audit_resolutions {local_id}")
            target_id = self.insert(
                cursor,
                """
                INSERT INTO family_category_audit_resolutions (
                    family_id, code, group_key, action, category_names_json, note, resolved_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    family_id,
                    row["code"],
                    row["group_key"],
                    row["action"],
                    row_value(row, columns, "category_names_json", "[]") or "[]",
                    row_value(row, columns, "note", "") or "",
                    self.mapped_user_id(user_map, row_value(row, columns, "resolved_by_user_id")),
                ),
            )
            self.remember_id(cursor, db_path, None, "family_category_audit_resolutions", local_id, target_id)
            counts["family_category_audit_resolutions"] += 1


def write_target(root: Path, auth_db: str, root_finance_db: str, users_dir: str, database_url: str, reset_target: bool) -> Dict[str, Any]:
    if not reset_target:
        raise EtlError("--write-target requires --reset-target for MySQL fresh-load")

    report = build_report(root, auth_db, root_finance_db, users_dir)
    apply_schema(database_url, reset_target=True)
    writer = MySqlEtlWriter(root)
    auth_db_path = root / auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / users_dir
    loaded: Dict[str, Any] = {"auth_users": 0, "finance": [], "family": {}}

    conn = mysql_connect(database_url)
    try:
        with conn.cursor() as cursor:
            user_map = writer.load_auth(cursor, auth_db_path)
            loaded["auth_users"] = len(user_map)
            for path in discover_databases(root, users_dir, auth_db, root_finance_db or None):
                db_kind = classify_db(path, auth_db_path, root_finance_path, users_root)
                if db_kind not in {"user_finance", "legacy_root_finance"} or not path.exists():
                    continue
                counts = writer.load_finance_db(cursor, path, db_kind, root, users_dir, user_map)
                loaded["finance"].append({"path": str(path), "kind": db_kind, "tables": counts})
            loaded["family"] = writer.load_family_auth(cursor, auth_db_path, user_map)
            cursor.execute(
                """
                INSERT INTO migration_etl_runs (source_root, finished_at, status, report_json)
                VALUES (%s, NOW(), %s, %s)
                """,
                (str(root), "loaded", json.dumps({"dry_run": report, "loaded": loaded}, ensure_ascii=False)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite -> MySQL guarded fresh-load ETL.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--write-target", action="store_true")
    parser.add_argument("--reset-target", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    root = Path(args.source_root)
    if args.write_target:
        result = write_target(root, args.auth_db, args.root_finance_db, args.users_dir, args.database_url, args.reset_target)
    else:
        result = build_report(root, args.auth_db, args.root_finance_db, args.users_dir)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"MySQL ETL {'loaded' if args.write_target else 'dry-run'}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
