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

from tools.money_minor import to_minor
from tools.sqlite_inventory import classify_db, discover_databases, open_readonly
from tools.sqlite_to_postgres_etl import FINANCE_TABLE_ORDER, finance_user_hint, normalize_psycopg_url


MONEY_TABLE_COLUMNS = {
    "accounts": ("balance", "balance_minor"),
    "budgets": ("amount", "amount_minor"),
    "capital_accounts": ("balance", "balance_minor"),
    "reconciliation_sources": ("balance", "balance_minor"),
    "recurring_templates": ("amount", "amount_minor"),
    "transactions": ("amount", "amount_minor"),
    "transfers": ("amount", "amount_minor"),
}

RECONCILIATION_COLUMNS = {
    "real_balance": "real_balance_minor",
    "program_balance": "program_balance_minor",
    "difference": "difference_minor",
}

FAMILY_TABLE_MAPPING = {
    "families": "families",
    "family_memberships": "memberships",
    "family_invites": "invites",
    "family_capital_accounts": "capital_accounts",
    "family_capital_member_settings": "capital_member_settings",
    "family_capital_contributions": "capital_contributions",
    "family_categories": "categories",
    "family_category_bindings": "category_bindings",
    "family_category_audit_resolutions": "category_audit_resolutions",
}


def table_names(conn: sqlite3.Connection) -> set:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def column_names(conn: sqlite3.Connection, table: str) -> set:
    if table not in table_names(conn):
        return set()
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row["name"]) for row in rows}


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    if table not in table_names(conn):
        return 0
    row = conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()
    return int(row["count"]) if row else 0


def sqlite_money_sum(conn: sqlite3.Connection, table: str, column: str) -> int:
    if table not in table_names(conn) or column not in column_names(conn, table):
        return 0
    rows = conn.execute(f'SELECT "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL').fetchall()
    return sum(to_minor(row["value"]) for row in rows)


def sqlite_group_sum(conn: sqlite3.Connection, table: str, group_columns: Iterable[str], money_column: str) -> Dict[str, int]:
    names = table_names(conn)
    if table not in names:
        return {}
    columns = column_names(conn, table)
    requested_groups = list(group_columns)
    safe_groups = [column for column in requested_groups if column in columns]
    if money_column not in columns:
        return {}
    if safe_groups:
        select_expr = ", ".join(f'"{column}"' for column in safe_groups)
        group_expr = ", ".join(f'"{column}"' for column in safe_groups)
        rows = conn.execute(
            f'SELECT {select_expr}, "{money_column}" AS value FROM "{table}" ORDER BY {group_expr}'
        ).fetchall()
    else:
        rows = conn.execute(f'SELECT "{money_column}" AS value FROM "{table}"').fetchall()

    result: Dict[str, int] = {}
    for row in rows:
        key_parts = []
        for column in requested_groups:
            value = row[column] if column in columns else None
            if column == "money_source" and value is None:
                value = "cashless"
            if column == "status" and value is None:
                value = "actual"
            key_parts.append(str(value if value is not None else ""))
        key = "|".join(key_parts) if key_parts else "all"
        result[key] = result.get(key, 0) + to_minor(row["value"])
    return result


def sqlite_monthly_transaction_sum(conn: sqlite3.Connection) -> Dict[str, int]:
    if "transactions" not in table_names(conn):
        return {}
    columns = column_names(conn, "transactions")
    select_columns = ["type", "date", "amount"]
    if "status" in columns:
        select_columns.append("status")
    if "money_source" in columns:
        select_columns.append("money_source")
    select_expr = ", ".join(f'"{column}"' for column in select_columns)
    rows = conn.execute(f"SELECT {select_expr} FROM transactions ORDER BY type, date").fetchall()
    result: Dict[str, int] = {}
    for row in rows:
        status = row["status"] if "status" in columns and row["status"] else "actual"
        money_source = row["money_source"] if "money_source" in columns and row["money_source"] else "cashless"
        month = str(row["date"] or "")[:7]
        key = "|".join([str(row["type"]), str(status), str(money_source), month])
        result[key] = result.get(key, 0) + to_minor(row["amount"])
    return result


def build_sqlite_finance_summary(db_path: Path) -> Dict[str, Any]:
    with open_readonly(db_path) as conn:
        counts = {table: sqlite_count(conn, table) for table in FINANCE_TABLE_ORDER}
        money_sums = {
            table: sqlite_money_sum(conn, table, source_column)
            for table, (source_column, _target_column) in MONEY_TABLE_COLUMNS.items()
        }
        money_sums.update(
            {
                f"reconciliations.{source_column}": sqlite_money_sum(conn, "reconciliations", source_column)
                for source_column in RECONCILIATION_COLUMNS
            }
        )
        return {
            "counts": counts,
            "money_sums": money_sums,
            "transaction_monthly_sums": sqlite_monthly_transaction_sum(conn),
            "transaction_type_status_sums": sqlite_group_sum(
                conn,
                "transactions",
                ("type", "status", "money_source"),
                "amount",
            ),
            "transfer_kind_sums": sqlite_group_sum(conn, "transfers", ("is_active",), "amount"),
        }


def pg_scalar(conn, query: str, params: Tuple[Any, ...]) -> int:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    value = row[0] if not isinstance(row, dict) else next(iter(row.values()))
    return int(value or 0)


def pg_group_sum(conn, query: str, params: Tuple[Any, ...]) -> Dict[str, int]:
    rows = conn.execute(query, params).fetchall()
    result: Dict[str, int] = {}
    for row in rows:
        values = list(row.values()) if isinstance(row, dict) else list(row)
        key = "|".join(str(value if value is not None else "") for value in values[:-1])
        result[key] = int(values[-1] or 0)
    return result


def postgres_user_id(conn, legacy_user_id: Optional[int]) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM auth.users WHERE legacy_sqlite_user_id IS NOT DISTINCT FROM %s",
        (legacy_user_id,),
    ).fetchone()
    if not row:
        return None
    return int(row["id"] if isinstance(row, dict) else row[0])


def build_postgres_finance_summary(conn, pg_user_id: int) -> Dict[str, Any]:
    counts = {
        table: pg_scalar(conn, f"SELECT COUNT(*) FROM finance.{table} WHERE user_id = %s", (pg_user_id,))
        for table in FINANCE_TABLE_ORDER
    }
    money_sums = {
        table: pg_scalar(conn, f"SELECT COALESCE(SUM({target_column}), 0) FROM finance.{table} WHERE user_id = %s", (pg_user_id,))
        for table, (_source_column, target_column) in MONEY_TABLE_COLUMNS.items()
    }
    money_sums.update(
        {
            f"reconciliations.{source_column}": pg_scalar(
                conn,
                f"SELECT COALESCE(SUM({target_column}), 0) FROM finance.reconciliations WHERE user_id = %s",
                (pg_user_id,),
            )
            for source_column, target_column in RECONCILIATION_COLUMNS.items()
        }
    )
    return {
        "counts": counts,
        "money_sums": money_sums,
        "transaction_monthly_sums": pg_group_sum(
            conn,
            """
            SELECT type, status, money_source, to_char(date, 'YYYY-MM') AS month, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance.transactions
            WHERE user_id = %s
            GROUP BY type, status, money_source, to_char(date, 'YYYY-MM')
            ORDER BY type, status, money_source, month
            """,
            (pg_user_id,),
        ),
        "transaction_type_status_sums": pg_group_sum(
            conn,
            """
            SELECT type, status, money_source, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance.transactions
            WHERE user_id = %s
            GROUP BY type, status, money_source
            ORDER BY type, status, money_source
            """,
            (pg_user_id,),
        ),
        "transfer_kind_sums": pg_group_sum(
            conn,
            """
            SELECT is_active::int AS is_active, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance.transfers
            WHERE user_id = %s
            GROUP BY is_active
            ORDER BY is_active
            """,
            (pg_user_id,),
        ),
    }


def build_sqlite_family_summary(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return {"counts": {table: 0 for table in FAMILY_TABLE_MAPPING}}
    with open_readonly(db_path) as conn:
        return {"counts": {table: sqlite_count(conn, table) for table in FAMILY_TABLE_MAPPING}}


def build_postgres_family_summary(conn) -> Dict[str, Any]:
    return {
        "counts": {
            sqlite_table: pg_scalar(conn, f"SELECT COUNT(*) FROM family.{pg_table}", ())
            for sqlite_table, pg_table in FAMILY_TABLE_MAPPING.items()
        }
    }


def compare_dicts(section: str, expected: Dict[str, int], actual: Dict[str, int]) -> List[Dict[str, Any]]:
    issues = []
    keys = sorted(set(expected) | set(actual))
    for key in keys:
        expected_value = int(expected.get(key, 0))
        actual_value = int(actual.get(key, 0))
        if expected_value != actual_value:
            issues.append(
                {
                    "section": section,
                    "key": key,
                    "expected": expected_value,
                    "actual": actual_value,
                    "delta": actual_value - expected_value,
                }
            )
    return issues


def compare_summaries(expected: Dict[str, Any], actual: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues = []
    for section in ("counts", "money_sums", "transaction_monthly_sums", "transaction_type_status_sums", "transfer_kind_sums"):
        issues.extend(compare_dicts(section, expected.get(section, {}), actual.get(section, {})))
    return issues


def connect_postgres(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("Install requirements-postgres.txt before running reconciliation") from exc
    return psycopg.connect(normalize_psycopg_url(database_url), row_factory=dict_row)


def build_reconciliation_report(root: Path, auth_db: str, root_finance_db: str, users_dir: str, database_url: str) -> Dict[str, Any]:
    auth_db_path = root / auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / users_dir
    checks = []
    with connect_postgres(database_url) as pg_conn:
        expected_family = build_sqlite_family_summary(auth_db_path)
        actual_family = build_postgres_family_summary(pg_conn)
        family_issues = compare_dicts("family_counts", expected_family["counts"], actual_family["counts"])
        checks.append(
            {
                "path": str(auth_db_path),
                "kind": "auth_family",
                "status": "ok" if not family_issues else "failed",
                "issues": family_issues,
                "expected": expected_family,
                "actual": actual_family,
            }
        )
        for path in discover_databases(root, users_dir, auth_db, root_finance_db or None):
            db_kind = classify_db(path, auth_db_path, root_finance_path, users_root)
            if db_kind not in {"user_finance", "legacy_root_finance"} or not path.exists():
                continue
            legacy_user_id, _email = finance_user_hint(path, db_kind, root, users_dir)
            pg_user_id = postgres_user_id(pg_conn, legacy_user_id)
            if pg_user_id is None:
                checks.append(
                    {
                        "path": str(path),
                        "kind": db_kind,
                        "legacy_user_id": legacy_user_id,
                        "status": "failed",
                        "issues": [
                            {
                                "section": "users",
                                "key": "legacy_sqlite_user_id",
                                "expected": legacy_user_id,
                                "actual": None,
                                "delta": None,
                            }
                        ],
                    }
                )
                continue
            expected = build_sqlite_finance_summary(path)
            actual = build_postgres_finance_summary(pg_conn, pg_user_id)
            issues = compare_summaries(expected, actual)
            checks.append(
                {
                    "path": str(path),
                    "kind": db_kind,
                    "legacy_user_id": legacy_user_id,
                    "postgres_user_id": pg_user_id,
                    "status": "ok" if not issues else "failed",
                    "issues": issues,
                    "expected": expected,
                    "actual": actual,
                }
            )
    failed = sum(1 for check in checks if check["status"] != "ok")
    return {"source_root": str(root), "checks": checks, "failed": failed}


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# SQLite/PostgreSQL Reconciliation", "", f"Source root: `{report['source_root']}`", ""]
    for check in report["checks"]:
        lines.append(f"## `{check['path']}`")
        lines.append("")
        lines.append(f"Status: `{check['status']}`")
        lines.append(f"Legacy user id: `{check.get('legacy_user_id')}`")
        lines.append(f"PostgreSQL user id: `{check.get('postgres_user_id')}`")
        issues = check.get("issues") or []
        if not issues:
            lines.extend(["", "No differences found.", ""])
            continue
        lines.extend(["", "| Section | Key | Expected | Actual | Delta |", "| --- | --- | ---: | ---: | ---: |"])
        for issue in issues:
            lines.append(
                f"| `{issue['section']}` | `{issue['key']}` | {issue['expected']} | {issue['actual']} | {issue['delta']} |"
            )
        lines.append("")
    lines.append(f"Failed checks: `{report['failed']}`")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Compare SQLite source aggregates with PostgreSQL ETL target.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    report = build_reconciliation_report(
        root=Path(args.source_root).resolve(),
        auth_db=args.auth_db,
        root_finance_db=args.root_finance_db,
        users_dir=args.users_dir,
        database_url=args.database_url,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
