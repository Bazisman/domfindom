from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.money_minor import MoneyConversionError, to_minor
from tools.sqlite_inventory import classify_db, discover_databases, open_readonly


FINANCE_MONEY_COLUMNS = {
    "accounts": ["balance"],
    "budgets": ["amount"],
    "capital_accounts": ["balance"],
    "reconciliation_sources": ["balance"],
    "reconciliations": ["real_balance", "program_balance", "difference"],
    "recurring_templates": ["amount"],
    "transactions": ["amount"],
    "transfers": ["amount"],
}


FINANCE_TABLE_ORDER = [
    "accounts",
    "categories",
    "transactions",
    "budgets",
    "capital_accounts",
    "recurring_templates",
    "reconciliation_sources",
    "reconciliations",
    "app_settings",
    "transfers",
]


FAMILY_TABLE_ORDER = [
    "families",
    "family_memberships",
    "family_invites",
    "family_capital_accounts",
    "family_capital_member_settings",
    "family_capital_contributions",
    "family_categories",
    "family_category_bindings",
    "family_category_audit_resolutions",
]


ID_MAP_TABLES = {
    "accounts": ("finance", "accounts"),
    "budgets": ("finance", "budgets"),
    "capital_accounts": ("finance", "capital_accounts"),
    "categories": ("finance", "categories"),
    "reconciliation_sources": ("finance", "reconciliation_sources"),
    "reconciliations": ("finance", "reconciliations"),
    "recurring_templates": ("finance", "recurring_templates"),
    "transactions": ("finance", "transactions"),
    "transfers": ("finance", "transfers"),
}


class EtlError(RuntimeError):
    pass


def normalize_psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def integer_set(conn: sqlite3.Connection, table: str, column: str) -> set:
    if table not in table_names(conn):
        return set()
    rows = conn.execute(f'SELECT "{column}" AS value FROM "{table}"').fetchall()
    return {int(row["value"]) for row in rows if row["value"] is not None}


def classify_transfer_account(account_id: int, daily_ids: set, capital_ids: set) -> Dict[str, Any]:
    in_daily = account_id in daily_ids
    in_capital = account_id in capital_ids
    if in_daily and in_capital:
        return {"kind": None, "issue": "ambiguous"}
    if in_daily:
        return {"kind": "daily", "issue": None}
    if in_capital:
        return {"kind": "capital", "issue": None}
    return {"kind": None, "issue": "missing"}


def validate_transfer_refs(conn: sqlite3.Connection) -> Dict[str, Any]:
    names = set(table_names(conn))
    if "transfers" not in names:
        return {"checked": False, "issues": []}

    daily_ids = integer_set(conn, "accounts", "id")
    capital_ids = integer_set(conn, "capital_accounts", "id")
    rows = conn.execute(
        """
        SELECT id, from_account_id, to_account_id
        FROM transfers
        ORDER BY id
        """
    ).fetchall()
    issues = []
    for row in rows:
        transfer_id = int(row["id"])
        for side, column in (("from", "from_account_id"), ("to", "to_account_id")):
            account_id = int(row[column])
            result = classify_transfer_account(account_id, daily_ids, capital_ids)
            if result["issue"]:
                issues.append(
                    {
                        "transfer_id": transfer_id,
                        "side": side,
                        "account_id": account_id,
                        "issue": result["issue"],
                    }
                )
    return {"checked": True, "issues": issues}


def table_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()
    return int(row["count"]) if row else 0


def select_all(conn: sqlite3.Connection, table: str) -> List[sqlite3.Row]:
    if table not in table_names(conn):
        return []
    return conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()


def column_names(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [str(row["name"]) for row in rows]


def validate_money_columns(conn: sqlite3.Connection, table: str, columns: List[str]) -> List[Dict[str, Any]]:
    existing_columns = set(column_names(conn, table))
    checks = []
    for column in columns:
        if column not in existing_columns:
            checks.append({"column": column, "exists": False, "invalid_values": None})
            continue
        invalid_values = 0
        rows = conn.execute(f'SELECT "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL').fetchall()
        for row in rows:
            try:
                to_minor(row["value"])
            except MoneyConversionError:
                invalid_values += 1
        checks.append({"column": column, "exists": True, "invalid_values": invalid_values})
    return checks


def inspect_source_db(db_path: Path, db_kind: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "path": str(db_path),
        "kind": db_kind,
        "exists": db_path.exists(),
        "tables": [],
        "money_checks": [],
        "transfer_ref_check": {"checked": False, "issues": []},
        "error": None,
    }
    if not db_path.exists():
        return result

    try:
        with open_readonly(db_path) as conn:
            names = table_names(conn)
            for name in names:
                result["tables"].append({"name": name, "row_count": table_count(conn, name)})
                if db_kind in {"user_finance", "legacy_root_finance"} and name in FINANCE_MONEY_COLUMNS:
                    result["money_checks"].append(
                        {
                            "table": name,
                            "columns": validate_money_columns(conn, name, FINANCE_MONEY_COLUMNS[name]),
                        }
                    )
            if db_kind in {"user_finance", "legacy_root_finance"}:
                result["transfer_ref_check"] = validate_transfer_refs(conn)
    except sqlite3.DatabaseError as exc:
        result["error"] = str(exc)
    return result


def build_report(root: Path, auth_db: str, root_finance_db: str, users_dir: str) -> Dict[str, Any]:
    auth_db_path = root / auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / users_dir
    databases = []
    for path in discover_databases(root, users_dir, auth_db, root_finance_db or None):
        db_kind = classify_db(path, auth_db_path, root_finance_path, users_root)
        databases.append(inspect_source_db(path, db_kind))
    return {"source_root": str(root), "databases": databases}


def row_value(row: sqlite3.Row, columns: Iterable[str], name: str, default: Any = None) -> Any:
    return row[name] if name in columns else default


def row_bool(row: sqlite3.Row, columns: Iterable[str], name: str, default: bool = False) -> bool:
    value = row_value(row, columns, name, 1 if default else 0)
    return bool(value)


def finance_user_hint(db_path: Path, db_kind: str, root: Path, users_dir: str) -> Tuple[Optional[int], str]:
    if db_kind == "legacy_root_finance":
        return 0, "legacy-root@local.invalid"
    users_root = root / users_dir
    try:
        user_dir = db_path.resolve().parent.relative_to(users_root.resolve())
    except ValueError:
        return None, "unknown-finance@local.invalid"
    try:
        legacy_user_id = int(user_dir.parts[0])
    except (IndexError, ValueError):
        return None, f"user-{user_dir.parts[0]}@local.invalid" if user_dir.parts else "unknown-finance@local.invalid"
    return legacy_user_id, f"user-{legacy_user_id}@local.invalid"


class PostgresEtlWriter:
    def __init__(self, database_url: str, source_root: Path):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise EtlError("Install requirements-postgres.txt before using --write-target") from exc
        self._psycopg = psycopg
        self._dict_row = dict_row
        self.database_url = normalize_psycopg_url(database_url)
        self.source_root = source_root.resolve()
        self.id_maps: Dict[Tuple[str, Optional[int], str, int], int] = {}
        self.category_name_maps: Dict[Tuple[str, Optional[int], str], int] = {}
        self.finance_db_by_legacy_user_id: Dict[int, Path] = {}

    def connect(self):
        return self._psycopg.connect(self.database_url, row_factory=self._dict_row)

    def wipe_target(self, conn) -> None:
        conn.execute(
            """
            TRUNCATE
                family.category_audit_resolutions,
                family.category_bindings,
                family.categories,
                family.capital_contributions,
                family.capital_member_settings,
                family.capital_accounts,
                family.invites,
                family.memberships,
                family.families,
                security.support_access_audit,
                security.support_access_grants,
                security.user_data_keys,
                finance.app_settings,
                finance.transfers,
                finance.reconciliations,
                finance.reconciliation_sources,
                finance.recurring_templates,
                finance.budgets,
                finance.transactions,
                finance.categories,
                finance.capital_accounts,
                finance.accounts,
                auth.user_backup_slot,
                auth.user_preferences,
                auth.account_deletion_tokens,
                auth.email_verification_tokens,
                auth.password_reset_tokens,
                auth.auth_events,
                auth.login_attempts,
                auth.sessions,
                auth.users,
                migration.id_map,
                migration.etl_runs
            RESTART IDENTITY CASCADE
            """
        )

    def source_key(self, db_path: Path) -> str:
        try:
            return str(db_path.resolve().relative_to(self.source_root))
        except ValueError:
            return str(db_path.resolve())

    def remember_id(
        self,
        conn,
        db_path: Path,
        source_user_id: Optional[int],
        source_table: str,
        source_local_id: int,
        target_schema: str,
        target_table: str,
        target_id: int,
    ) -> None:
        source_db_path = self.source_key(db_path)
        self.id_maps[(source_db_path, source_user_id, source_table, int(source_local_id))] = int(target_id)
        conn.execute(
            """
            INSERT INTO migration.id_map (
                source_db_path, source_user_id, source_table, source_local_id,
                target_schema, target_table, target_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_db_path, source_user_id, source_table, source_local_id)
            DO UPDATE SET target_id = excluded.target_id
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

    def remember_category_name(self, db_path: Path, source_user_id: Optional[int], name: str, target_id: int) -> None:
        self.category_name_maps[(self.source_key(db_path), source_user_id, str(name))] = int(target_id)

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
            local_id = int(source_local_id)
        except (TypeError, ValueError):
            return None
        return self.id_maps.get((self.source_key(db_path), source_user_id, source_table, local_id))

    def mapped_user_id(self, user_map: Dict[int, int], legacy_user_id: Any) -> Optional[int]:
        if legacy_user_id is None:
            return None
        try:
            return user_map.get(int(legacy_user_id))
        except (TypeError, ValueError):
            return None

    def mapped_finance_id(
        self,
        legacy_user_id: Any,
        source_table: str,
        source_local_id: Any,
    ) -> Optional[int]:
        try:
            user_id = int(legacy_user_id)
        except (TypeError, ValueError):
            return None
        db_path = self.finance_db_by_legacy_user_id.get(user_id)
        if db_path is None:
            return None
        return self.mapped_id(db_path, user_id, source_table, source_local_id)

    def ensure_user(self, conn, legacy_user_id: Optional[int], email: str, password_hash: str = "migration-placeholder") -> int:
        row = conn.execute(
            """
            INSERT INTO auth.users (email, password_hash, email_verified, is_active, legacy_sqlite_user_id)
            VALUES (%s, %s, true, true, %s)
            ON CONFLICT (email) DO UPDATE SET email = excluded.email
            RETURNING id
            """,
            (email, password_hash, legacy_user_id),
        ).fetchone()
        return int(row["id"])

    def load_auth(self, conn, db_path: Path) -> Dict[int, int]:
        user_map: Dict[int, int] = {}
        if not db_path.exists() or db_path.stat().st_size == 0:
            return user_map
        with open_readonly(db_path) as sqlite_conn:
            users = select_all(sqlite_conn, "users")
            for row in users:
                columns = set(row.keys())
                legacy_id = int(row["id"])
                pg_id = self.ensure_user(
                    conn,
                    legacy_id,
                    str(row["email"]),
                    str(row_value(row, columns, "password_hash", "migration-placeholder")),
                )
                user_map[legacy_id] = pg_id
                self.remember_id(conn, db_path, legacy_id, "users", legacy_id, "auth", "users", pg_id)

            for row in select_all(sqlite_conn, "user_preferences"):
                columns = set(row.keys())
                legacy_user_id = int(row["user_id"])
                pg_user_id = user_map.get(legacy_user_id)
                if pg_user_id is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO auth.user_preferences (user_id, theme_mode, workspace_mode, display_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        theme_mode = excluded.theme_mode,
                        workspace_mode = excluded.workspace_mode,
                        display_name = excluded.display_name
                    """,
                    (
                        pg_user_id,
                        row_value(row, columns, "theme_mode", "system") or "system",
                        row_value(row, columns, "workspace_mode", "personal") or "personal",
                        row_value(row, columns, "display_name", "") or "",
                    ),
                )
        return user_map

    def load_finance_db(
        self,
        conn,
        db_path: Path,
        db_kind: str,
        root: Path,
        users_dir: str,
        user_map: Dict[int, int],
    ) -> Dict[str, int]:
        legacy_user_id, fallback_email = finance_user_hint(db_path, db_kind, root, users_dir)
        pg_user_id = user_map.get(legacy_user_id) if legacy_user_id is not None else None
        if pg_user_id is None:
            pg_user_id = self.ensure_user(conn, legacy_user_id, fallback_email)
            if legacy_user_id is not None:
                user_map[legacy_user_id] = pg_user_id
        if legacy_user_id is not None:
            self.finance_db_by_legacy_user_id[int(legacy_user_id)] = db_path

        counts = {table: 0 for table in FINANCE_TABLE_ORDER}
        with open_readonly(db_path) as sqlite_conn:
            self._load_accounts(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_categories(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_transactions(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_capital_accounts(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_budgets(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_recurring_templates(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_reconciliation_sources(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_reconciliations(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
            self._load_app_settings(conn, db_path, sqlite_conn, pg_user_id, counts)
            self._load_transfers(conn, db_path, sqlite_conn, legacy_user_id, pg_user_id, counts)
        return counts

    def load_family_auth(self, conn, db_path: Path, user_map: Dict[int, int]) -> Dict[str, int]:
        counts = {table: 0 for table in FAMILY_TABLE_ORDER}
        if not db_path.exists() or db_path.stat().st_size == 0:
            return counts
        with open_readonly(db_path) as sqlite_conn:
            self._load_families(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_memberships(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_invites(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_capital_accounts(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_capital_member_settings(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_capital_contributions(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_categories(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_category_bindings(conn, db_path, sqlite_conn, user_map, counts)
            self._load_family_category_audit_resolutions(conn, db_path, sqlite_conn, user_map, counts)
        return counts

    def _insert_mapped(self, conn, db_path: Path, legacy_user_id: Optional[int], table: str, local_id: int, sql: str, params: Tuple[Any, ...]) -> int:
        row = conn.execute(sql, params).fetchone()
        target_id = int(row["id"])
        target_schema, target_table = ID_MAP_TABLES[table]
        self.remember_id(conn, db_path, legacy_user_id, table, local_id, target_schema, target_table, target_id)
        return target_id

    def _load_accounts(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "accounts"):
            columns = set(row.keys())
            local_id = int(row["id"])
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "accounts",
                local_id,
                """
                INSERT INTO finance.accounts (
                    user_id, legacy_local_id, name, type, money_source, balance_minor, currency, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET name = excluded.name
                RETURNING id
                """,
                (
                    pg_user_id,
                    local_id,
                    row["name"],
                    row["type"],
                    row_value(row, columns, "money_source"),
                    to_minor(row_value(row, columns, "balance", 0)),
                    row_value(row, columns, "currency", "RUB") or "RUB",
                    row_bool(row, columns, "is_active", True),
                ),
            )
            counts["accounts"] += 1

    def _load_categories(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "categories"):
            columns = set(row.keys())
            local_id = int(row["id"])
            target_id = self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "categories",
                local_id,
                """
                INSERT INTO finance.categories (
                    user_id, legacy_local_id, name, type, color, icon, is_active,
                    semantic_key, scope, sync_status, original_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET name = excluded.name
                RETURNING id
                """,
                (
                    pg_user_id,
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
            self.remember_category_name(db_path, legacy_user_id, str(row["name"]), target_id)
            counts["categories"] += 1

    def _load_transactions(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "transactions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            category_id = self._category_id_for_transaction(db_path, legacy_user_id, row["category"])
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "transactions",
                local_id,
                """
                INSERT INTO finance.transactions (
                    user_id, legacy_local_id, type, category, category_id, amount_minor,
                    comment, date, money_source, status, executed_at, template_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET amount_minor = excluded.amount_minor
                RETURNING id
                """,
                (
                    pg_user_id,
                    local_id,
                    row["type"],
                    row["category"],
                    category_id,
                    to_minor(row["amount"]),
                    row_value(row, columns, "comment"),
                    row["date"],
                    row_value(row, columns, "money_source", "cashless") or "cashless",
                    row_value(row, columns, "status", "actual") or "actual",
                    row_value(row, columns, "executed_at"),
                    row_value(row, columns, "template_id"),
                ),
            )
            counts["transactions"] += 1

    def _category_id_for_transaction(self, db_path: Path, legacy_user_id: Optional[int], category_name: str) -> Optional[int]:
        # SQLite transactions historically store category by name, not by FK.
        return self.category_name_maps.get((self.source_key(db_path), legacy_user_id, str(category_name)))

    def _load_budgets(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "budgets"):
            local_id = int(row["id"])
            category_id = self.mapped_id(db_path, legacy_user_id, "categories", row["category_id"])
            if category_id is None:
                raise EtlError(f"Missing category mapping for budget {local_id} in {db_path}")
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "budgets",
                local_id,
                """
                INSERT INTO finance.budgets (user_id, legacy_local_id, category_id, amount_minor, period)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET amount_minor = excluded.amount_minor
                RETURNING id
                """,
                (pg_user_id, local_id, category_id, to_minor(row["amount"]), row["period"]),
            )
            counts["budgets"] += 1

    def _load_capital_accounts(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "capital_accounts"):
            columns = set(row.keys())
            local_id = int(row["id"])
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "capital_accounts",
                local_id,
                """
                INSERT INTO finance.capital_accounts (
                    user_id, legacy_local_id, name, balance_minor, currency, icon, color, is_default, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET name = excluded.name
                RETURNING id
                """,
                (
                    pg_user_id,
                    local_id,
                    row["name"],
                    to_minor(row_value(row, columns, "balance", 0)),
                    row_value(row, columns, "currency", "RUB") or "RUB",
                    row_value(row, columns, "icon"),
                    row_value(row, columns, "color"),
                    row_bool(row, columns, "is_default", False),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            counts["capital_accounts"] += 1

    def _load_recurring_templates(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "recurring_templates"):
            columns = set(row.keys())
            local_id = int(row["id"])
            category_id = self.mapped_id(db_path, legacy_user_id, "categories", row_value(row, columns, "category_id"))
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "recurring_templates",
                local_id,
                """
                INSERT INTO finance.recurring_templates (
                    user_id, legacy_local_id, type, name, amount_minor, day_of_month, category_id,
                    comment_template, money_source, months_ahead, working_days_only, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET amount_minor = excluded.amount_minor
                RETURNING id
                """,
                (
                    pg_user_id,
                    local_id,
                    row["type"],
                    row["name"],
                    to_minor(row["amount"]),
                    int(row["day_of_month"]),
                    category_id,
                    row_value(row, columns, "comment_template"),
                    row_value(row, columns, "money_source", "cashless") or "cashless",
                    int(row_value(row, columns, "months_ahead", 12) or 12),
                    row_bool(row, columns, "working_days_only", False),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            counts["recurring_templates"] += 1

    def _load_reconciliation_sources(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "reconciliation_sources"):
            columns = set(row.keys())
            local_id = int(row["id"])
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "reconciliation_sources",
                local_id,
                """
                INSERT INTO finance.reconciliation_sources (user_id, legacy_local_id, name, balance_minor, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET balance_minor = excluded.balance_minor
                RETURNING id
                """,
                (pg_user_id, local_id, row["name"], to_minor(row_value(row, columns, "balance", 0)), row_bool(row, columns, "is_active", True)),
            )
            counts["reconciliation_sources"] += 1

    def _load_reconciliations(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "reconciliations"):
            columns = set(row.keys())
            local_id = int(row["id"])
            adjustment_transaction_id = self.mapped_id(db_path, legacy_user_id, "transactions", row_value(row, columns, "adjustment_transaction_id"))
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "reconciliations",
                local_id,
                """
                INSERT INTO finance.reconciliations (
                    user_id, legacy_local_id, real_balance_minor, program_balance_minor,
                    difference_minor, adjustment_transaction_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET difference_minor = excluded.difference_minor
                RETURNING id
                """,
                (
                    pg_user_id,
                    local_id,
                    to_minor(row["real_balance"]),
                    to_minor(row["program_balance"]),
                    to_minor(row["difference"]),
                    adjustment_transaction_id,
                ),
            )
            counts["reconciliations"] += 1

    def _load_app_settings(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, pg_user_id: int, counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "app_settings"):
            conn.execute(
                """
                INSERT INTO finance.app_settings (user_id, key, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value
                """,
                (pg_user_id, row["key"], row["value"]),
            )
            counts["app_settings"] += 1

    def _load_transfers(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, legacy_user_id: Optional[int], pg_user_id: int, counts: Dict[str, int]) -> None:
        daily_ids = integer_set(sqlite_conn, "accounts", "id")
        capital_ids = integer_set(sqlite_conn, "capital_accounts", "id")
        for row in select_all(sqlite_conn, "transfers"):
            columns = set(row.keys())
            local_id = int(row["id"])
            from_ref = self._transfer_ref(db_path, legacy_user_id, row["from_account_id"], daily_ids, capital_ids)
            to_ref = self._transfer_ref(db_path, legacy_user_id, row["to_account_id"], daily_ids, capital_ids)
            transaction_id = self.mapped_id(db_path, legacy_user_id, "transactions", row_value(row, columns, "transaction_id"))
            self._insert_mapped(
                conn,
                db_path,
                legacy_user_id,
                "transfers",
                local_id,
                """
                INSERT INTO finance.transfers (
                    user_id, legacy_local_id, legacy_from_account_id, legacy_to_account_id,
                    from_account_kind, to_account_kind, from_daily_account_id, to_daily_account_id,
                    from_capital_account_id, to_capital_account_id, amount_minor, transaction_id,
                    date, comment, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, legacy_local_id) DO UPDATE SET amount_minor = excluded.amount_minor
                RETURNING id
                """,
                (
                    pg_user_id,
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
                    transaction_id,
                    row["date"],
                    row_value(row, columns, "comment"),
                    row_bool(row, columns, "is_active", True),
                ),
            )
            counts["transfers"] += 1

    def _transfer_ref(self, db_path: Path, legacy_user_id: Optional[int], account_id: Any, daily_ids: set, capital_ids: set) -> Dict[str, Any]:
        local_id = int(account_id)
        classified = classify_transfer_account(local_id, daily_ids, capital_ids)
        if classified["issue"]:
            raise EtlError(f"Transfer account {local_id} is {classified['issue']} in {db_path}")
        if classified["kind"] == "daily":
            return {
                "kind": "daily",
                "daily_id": self.mapped_id(db_path, legacy_user_id, "accounts", local_id),
                "capital_id": None,
            }
        return {
            "kind": "capital",
            "daily_id": None,
            "capital_id": self.mapped_id(db_path, legacy_user_id, "capital_accounts", local_id),
        }

    def _family_id(self, db_path: Path, legacy_family_id: Any) -> Optional[int]:
        return self.mapped_id(db_path, None, "families", legacy_family_id)

    def _family_category_id(self, db_path: Path, legacy_family_category_id: Any) -> Optional[int]:
        return self.mapped_id(db_path, None, "family_categories", legacy_family_category_id)

    def _load_families(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "families"):
            columns = set(row.keys())
            local_id = int(row["id"])
            owner_user_id = self.mapped_user_id(user_map, row["owner_user_id"])
            if owner_user_id is None:
                raise EtlError(f"Missing owner user mapping for family {local_id}")
            pg_row = conn.execute(
                """
                INSERT INTO family.families (name, owner_user_id, archived_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (row["name"], owner_user_id, row_value(row, columns, "archived_at")),
            ).fetchone()
            target_id = int(pg_row["id"])
            self.remember_id(conn, db_path, None, "families", local_id, "family", "families", target_id)
            counts["families"] += 1

    def _load_family_memberships(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_memberships"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            invited_by_user_id = self.mapped_user_id(user_map, row_value(row, columns, "invited_by_user_id"))
            if family_id is None or user_id is None:
                raise EtlError(f"Missing membership mapping for family_memberships {row['id']}")
            pg_row = conn.execute(
                """
                INSERT INTO family.memberships (family_id, user_id, role, status, invited_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (family_id, user_id) DO UPDATE SET
                    role = excluded.role,
                    status = excluded.status,
                    invited_by_user_id = excluded.invited_by_user_id
                RETURNING id
                """,
                (
                    family_id,
                    user_id,
                    row["role"] if row["role"] not in {"admin", "accountant"} else "member",
                    row_value(row, columns, "status", "active") or "active",
                    invited_by_user_id,
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_memberships", int(row["id"]), "family", "memberships", int(pg_row["id"]))
            counts["family_memberships"] += 1

    def _load_family_invites(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_invites"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            invited_by_user_id = self.mapped_user_id(user_map, row["invited_by_user_id"])
            if family_id is None or invited_by_user_id is None:
                raise EtlError(f"Missing invite mapping for family_invites {row['id']}")
            pg_row = conn.execute(
                """
                INSERT INTO family.invites (
                    family_id, email, role, token_hash, invited_by_user_id,
                    expires_at, accepted_at, revoked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (token_hash) DO UPDATE SET email = excluded.email
                RETURNING id
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
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_invites", int(row["id"]), "family", "invites", int(pg_row["id"]))
            counts["family_invites"] += 1

    def _load_family_capital_accounts(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_capital_accounts"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            owner_user_id = self.mapped_user_id(user_map, row["owner_user_id"])
            capital_account_id = self.mapped_finance_id(row["owner_user_id"], "capital_accounts", row["capital_account_id"])
            if family_id is None or owner_user_id is None or capital_account_id is None:
                raise EtlError(f"Missing capital account mapping for family_capital_accounts {row['id']}")
            pg_row = conn.execute(
                """
                INSERT INTO family.capital_accounts (
                    family_id, owner_user_id, capital_account_id, is_visible, is_default_target
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (family_id, owner_user_id, capital_account_id) DO UPDATE SET
                    is_visible = excluded.is_visible,
                    is_default_target = excluded.is_default_target
                RETURNING id
                """,
                (
                    family_id,
                    owner_user_id,
                    capital_account_id,
                    row_bool(row, columns, "is_visible", False),
                    row_bool(row, columns, "is_default_target", False),
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_capital_accounts", int(row["id"]), "family", "capital_accounts", int(pg_row["id"]))
            counts["family_capital_accounts"] += 1

    def _load_family_capital_member_settings(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_capital_member_settings"):
            columns = set(row.keys())
            family_id = self._family_id(db_path, row["family_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            target_owner_user_id = self.mapped_user_id(user_map, row_value(row, columns, "target_owner_user_id"))
            target_capital_account_id = self.mapped_finance_id(
                row_value(row, columns, "target_owner_user_id"),
                "capital_accounts",
                row_value(row, columns, "target_capital_account_id"),
            )
            if family_id is None or user_id is None:
                raise EtlError("Missing capital member settings family/user mapping")
            conn.execute(
                """
                INSERT INTO family.capital_member_settings (
                    family_id, user_id, target_owner_user_id, target_capital_account_id
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (family_id, user_id) DO UPDATE SET
                    target_owner_user_id = excluded.target_owner_user_id,
                    target_capital_account_id = excluded.target_capital_account_id
                """,
                (family_id, user_id, target_owner_user_id, target_capital_account_id),
            )
            counts["family_capital_member_settings"] += 1

    def _load_family_capital_contributions(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_capital_contributions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            source_user_id = self.mapped_user_id(user_map, row["source_user_id"])
            source_transaction_id = self.mapped_finance_id(row["source_user_id"], "transactions", row["source_transaction_id"])
            target_owner_user_id = self.mapped_user_id(user_map, row["target_owner_user_id"])
            target_capital_account_id = self.mapped_finance_id(row["target_owner_user_id"], "capital_accounts", row["target_capital_account_id"])
            if None in (family_id, source_user_id, target_owner_user_id, target_capital_account_id):
                raise EtlError(f"Missing contribution mapping for family_capital_contributions {local_id}")
            pg_row = conn.execute(
                """
                INSERT INTO family.capital_contributions (
                    family_id, source_user_id, legacy_source_transaction_id, source_transaction_id, target_owner_user_id,
                    target_capital_account_id, amount_minor, date, comment, reversed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_user_id, legacy_source_transaction_id) DO UPDATE SET
                    source_transaction_id = excluded.source_transaction_id,
                    amount_minor = excluded.amount_minor,
                    reversed_at = excluded.reversed_at
                RETURNING id
                """,
                (
                    family_id,
                    source_user_id,
                    int(row["source_transaction_id"]),
                    source_transaction_id,
                    target_owner_user_id,
                    target_capital_account_id,
                    to_minor(row["amount"]),
                    row["date"],
                    row_value(row, columns, "comment"),
                    row_value(row, columns, "reversed_at"),
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_capital_contributions", local_id, "family", "capital_contributions", int(pg_row["id"]))
            counts["family_capital_contributions"] += 1

    def _load_family_categories(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_categories"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            created_by_user_id = self.mapped_user_id(user_map, row_value(row, columns, "created_by_user_id"))
            if family_id is None:
                raise EtlError(f"Missing family mapping for family_categories {local_id}")
            pg_row = conn.execute(
                """
                INSERT INTO family.categories (
                    family_id, semantic_key, display_name, type, is_active, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (family_id, semantic_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    type = excluded.type,
                    is_active = excluded.is_active
                RETURNING id
                """,
                (
                    family_id,
                    row["semantic_key"],
                    row["display_name"],
                    row_value(row, columns, "type", "both") or "both",
                    row_bool(row, columns, "is_active", True),
                    created_by_user_id,
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_categories", local_id, "family", "categories", int(pg_row["id"]))
            counts["family_categories"] += 1

    def _load_family_category_bindings(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_category_bindings"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            family_category_id = self._family_category_id(db_path, row["family_category_id"])
            user_id = self.mapped_user_id(user_map, row["user_id"])
            local_category_id = self.mapped_finance_id(row["user_id"], "categories", row["local_category_id"])
            confirmed_by_user_id = self.mapped_user_id(user_map, row_value(row, columns, "confirmed_by_user_id"))
            if None in (family_id, family_category_id, user_id, local_category_id):
                raise EtlError(f"Missing category binding mapping for family_category_bindings {local_id}")
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
                    confirmed_by_user_id = excluded.confirmed_by_user_id
                RETURNING id
                """,
                (
                    family_id,
                    family_category_id,
                    user_id,
                    local_category_id,
                    row["local_category_name"],
                    row["local_category_type"],
                    row_value(row, columns, "status", "confirmed") or "confirmed",
                    confirmed_by_user_id,
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_category_bindings", local_id, "family", "category_bindings", int(pg_row["id"]))
            counts["family_category_bindings"] += 1

    def _load_family_category_audit_resolutions(self, conn, db_path: Path, sqlite_conn: sqlite3.Connection, user_map: Dict[int, int], counts: Dict[str, int]) -> None:
        for row in select_all(sqlite_conn, "family_category_audit_resolutions"):
            columns = set(row.keys())
            local_id = int(row["id"])
            family_id = self._family_id(db_path, row["family_id"])
            resolved_by_user_id = self.mapped_user_id(user_map, row_value(row, columns, "resolved_by_user_id"))
            if family_id is None:
                raise EtlError(f"Missing family mapping for family_category_audit_resolutions {local_id}")
            pg_row = conn.execute(
                """
                INSERT INTO family.category_audit_resolutions (
                    family_id, code, group_key, action, category_names_json, note, resolved_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (family_id, code, group_key, action) DO UPDATE SET
                    category_names_json = excluded.category_names_json,
                    note = excluded.note,
                    resolved_by_user_id = excluded.resolved_by_user_id
                RETURNING id
                """,
                (
                    family_id,
                    row["code"],
                    row["group_key"],
                    row["action"],
                    row_value(row, columns, "category_names_json", "[]") or "[]",
                    row_value(row, columns, "note", "") or "",
                    resolved_by_user_id,
                ),
            ).fetchone()
            self.remember_id(conn, db_path, None, "family_category_audit_resolutions", local_id, "family", "category_audit_resolutions", int(pg_row["id"]))
            counts["family_category_audit_resolutions"] += 1


def write_target(
    report: Dict[str, Any],
    root: Path,
    auth_db: str,
    root_finance_db: str,
    users_dir: str,
    database_url: str,
    wipe_target: bool,
) -> Dict[str, Any]:
    if not wipe_target:
        raise EtlError("--write-target requires --wipe-target for now, so the local/stage target is explicit")

    writer = PostgresEtlWriter(database_url, root)
    auth_db_path = root / auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / users_dir
    loaded: Dict[str, Any] = {"auth_users": 0, "finance": [], "family": {}}
    with writer.connect() as conn:
        with conn.transaction():
            writer.wipe_target(conn)
            user_map = writer.load_auth(conn, auth_db_path)
            loaded["auth_users"] = len(user_map)
            for path in discover_databases(root, users_dir, auth_db, root_finance_db or None):
                db_kind = classify_db(path, auth_db_path, root_finance_path, users_root)
                if db_kind not in {"user_finance", "legacy_root_finance"} or not path.exists():
                    continue
                counts = writer.load_finance_db(conn, path, db_kind, root, users_dir, user_map)
                loaded["finance"].append({"path": str(path), "kind": db_kind, "tables": counts})
            loaded["family"] = writer.load_family_auth(conn, auth_db_path, user_map)
            conn.execute(
                """
                INSERT INTO migration.etl_runs (source_root, status, report_json, finished_at)
                VALUES (%s, %s, %s, now())
                """,
                (str(root), "loaded", json.dumps({"dry_run": report, "loaded": loaded}, ensure_ascii=False)),
            )
    return loaded


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# SQLite -> PostgreSQL ETL Dry Run", "", f"Source root: `{report['source_root']}`", ""]
    for db in report["databases"]:
        lines.append(f"## `{db['path']}`")
        lines.append("")
        lines.append(f"Kind: `{db['kind']}`")
        if not db["exists"]:
            lines.extend(["", "Missing.", ""])
            continue
        if db["error"]:
            lines.extend(["", f"Error: `{db['error']}`", ""])
            continue
        lines.extend(["", "| Table | Rows |", "| --- | ---: |"])
        for table in db["tables"]:
            lines.append(f"| `{table['name']}` | {table['row_count']} |")
        if db["money_checks"]:
            lines.extend(["", "Money conversion checks:", ""])
            for check in db["money_checks"]:
                for column in check["columns"]:
                    if not column["exists"]:
                        lines.append(f"- `{check['table']}.{column['column']}`: missing")
                    else:
                        lines.append(
                            f"- `{check['table']}.{column['column']}`: "
                            f"{column['invalid_values']} invalid values"
                        )
        transfer_ref_check = db.get("transfer_ref_check") or {}
        if transfer_ref_check.get("checked"):
            issues = transfer_ref_check.get("issues") or []
            lines.extend(["", "Transfer reference checks:", ""])
            if not issues:
                lines.append("- all transfer account references are resolvable")
            for issue in issues:
                lines.append(
                    f"- transfer `{issue['transfer_id']}` {issue['side']} account "
                    f"`{issue['account_id']}`: {issue['issue']}"
                )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="SQLite -> PostgreSQL ETL report and guarded local/stage loader.")
    parser.add_argument("--source-root", default=".", help="Project/source root with auth.db and data/users.")
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    parser.add_argument("--database-url", default="", help="PostgreSQL URL for --write-target.")
    parser.add_argument("--write-target", action="store_true", help="Load data into PostgreSQL after dry-run checks.")
    parser.add_argument("--wipe-target", action="store_true", help="Required with --write-target; truncates target schemas.")
    args = parser.parse_args()

    root = Path(args.source_root).resolve()
    report = build_report(
        root=root,
        auth_db=args.auth_db,
        root_finance_db=args.root_finance_db,
        users_dir=args.users_dir,
    )
    if args.write_target:
        if not args.database_url:
            raise EtlError("--write-target requires --database-url")
        loaded = write_target(
            report=report,
            root=root,
            auth_db=args.auth_db,
            root_finance_db=args.root_finance_db,
            users_dir=args.users_dir,
            database_url=args.database_url,
            wipe_target=args.wipe_target,
        )
        report["loaded"] = loaded
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
        if args.write_target:
            print("")
            print("PostgreSQL load:")
            print(json.dumps(report["loaded"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
