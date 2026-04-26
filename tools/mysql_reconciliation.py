from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mysql_schema import mysql_connect
from tools.postgres_reconciliation import (
    FAMILY_TABLE_MAPPING,
    MONEY_TABLE_COLUMNS,
    RECONCILIATION_COLUMNS,
    build_sqlite_family_summary,
    build_sqlite_finance_summary,
    compare_dicts,
    compare_summaries,
)
from tools.sqlite_inventory import classify_db, discover_databases
from tools.sqlite_to_postgres_etl import FINANCE_TABLE_ORDER, finance_user_hint


MYSQL_FINANCE_TABLES = {
    "accounts": "finance_accounts",
    "budgets": "finance_budgets",
    "capital_accounts": "finance_capital_accounts",
    "categories": "finance_categories",
    "reconciliation_sources": "finance_reconciliation_sources",
    "reconciliations": "finance_reconciliations",
    "recurring_templates": "finance_recurring_templates",
    "transactions": "finance_transactions",
    "transfers": "finance_transfers",
    "app_settings": "finance_app_settings",
}

MYSQL_FAMILY_TABLES = {
    "families": "family_families",
    "family_memberships": "family_memberships",
    "family_invites": "family_invites",
    "family_capital_accounts": "family_capital_accounts",
    "family_capital_member_settings": "family_capital_member_settings",
    "family_capital_contributions": "family_capital_contributions",
    "family_categories": "family_categories",
    "family_category_bindings": "family_category_bindings",
    "family_category_audit_resolutions": "family_category_audit_resolutions",
}


def mysql_scalar(cursor, query: str, params: Tuple[Any, ...]) -> int:
    cursor.execute(query, params)
    row = cursor.fetchone()
    if not row:
        return 0
    return int(next(iter(row.values())) or 0)


def mysql_group_sum(cursor, query: str, params: Tuple[Any, ...]) -> Dict[str, int]:
    cursor.execute(query, params)
    result: Dict[str, int] = {}
    for row in cursor.fetchall():
        values = list(row.values())
        key = "|".join(str(value if value is not None else "") for value in values[:-1])
        result[key] = int(values[-1] or 0)
    return result


def mysql_user_id(cursor, legacy_user_id: Optional[int]) -> Optional[int]:
    cursor.execute(
        "SELECT id FROM auth_users WHERE legacy_sqlite_user_id <=> %s",
        (legacy_user_id,),
    )
    row = cursor.fetchone()
    return int(row["id"]) if row else None


def build_mysql_finance_summary(cursor, user_id: int) -> Dict[str, Any]:
    counts = {
        table: mysql_scalar(cursor, f"SELECT COUNT(*) AS count FROM {MYSQL_FINANCE_TABLES[table]} WHERE user_id = %s", (user_id,))
        for table in FINANCE_TABLE_ORDER
    }
    money_sums = {
        table: mysql_scalar(
            cursor,
            f"SELECT COALESCE(SUM({target_column}), 0) AS total FROM {MYSQL_FINANCE_TABLES[table]} WHERE user_id = %s",
            (user_id,),
        )
        for table, (_source_column, target_column) in MONEY_TABLE_COLUMNS.items()
    }
    money_sums.update(
        {
            f"reconciliations.{source_column}": mysql_scalar(
                cursor,
                f"SELECT COALESCE(SUM({target_column}), 0) AS total FROM finance_reconciliations WHERE user_id = %s",
                (user_id,),
            )
            for source_column, target_column in RECONCILIATION_COLUMNS.items()
        }
    )
    return {
        "counts": counts,
        "money_sums": money_sums,
        "transaction_monthly_sums": mysql_group_sum(
            cursor,
            """
            SELECT type, status, money_source, DATE_FORMAT(date, '%%Y-%%m') AS month, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance_transactions
            WHERE user_id = %s
            GROUP BY type, status, money_source, DATE_FORMAT(date, '%%Y-%%m')
            ORDER BY type, status, money_source, month
            """,
            (user_id,),
        ),
        "transaction_type_status_sums": mysql_group_sum(
            cursor,
            """
            SELECT type, status, money_source, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance_transactions
            WHERE user_id = %s
            GROUP BY type, status, money_source
            ORDER BY type, status, money_source
            """,
            (user_id,),
        ),
        "transfer_kind_sums": mysql_group_sum(
            cursor,
            """
            SELECT CAST(is_active AS UNSIGNED) AS is_active, COALESCE(SUM(amount_minor), 0) AS total
            FROM finance_transfers
            WHERE user_id = %s
            GROUP BY is_active
            ORDER BY is_active
            """,
            (user_id,),
        ),
    }


def build_mysql_family_summary(cursor) -> Dict[str, Any]:
    return {
        "counts": {
            sqlite_table: mysql_scalar(cursor, f"SELECT COUNT(*) AS count FROM {MYSQL_FAMILY_TABLES[sqlite_table]}", ())
            for sqlite_table in FAMILY_TABLE_MAPPING
        }
    }


def build_reconciliation_report(root: Path, auth_db: str, root_finance_db: str, users_dir: str, database_url: str) -> Dict[str, Any]:
    auth_db_path = root / auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / users_dir
    checks = []
    conn = mysql_connect(database_url)
    try:
        with conn.cursor() as cursor:
            expected_family = build_sqlite_family_summary(auth_db_path)
            actual_family = build_mysql_family_summary(cursor)
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
                user_id = mysql_user_id(cursor, legacy_user_id)
                if user_id is None:
                    checks.append(
                        {
                            "path": str(path),
                            "kind": db_kind,
                            "legacy_user_id": legacy_user_id,
                            "status": "failed",
                            "issues": [{"section": "users", "key": "legacy_sqlite_user_id", "expected": legacy_user_id, "actual": None, "delta": None}],
                        }
                    )
                    continue
                expected = build_sqlite_finance_summary(path)
                actual = build_mysql_finance_summary(cursor, user_id)
                issues = compare_summaries(expected, actual)
                checks.append(
                    {
                        "path": str(path),
                        "kind": db_kind,
                        "legacy_user_id": legacy_user_id,
                        "mysql_user_id": user_id,
                        "status": "ok" if not issues else "failed",
                        "issues": issues,
                        "expected": expected,
                        "actual": actual,
                    }
                )
    finally:
        conn.close()
    failed = sum(1 for check in checks if check["status"] != "ok")
    return {"source_root": str(root), "checks": checks, "failed": failed}


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# SQLite/MySQL Reconciliation", "", f"Source root: `{report['source_root']}`", ""]
    for check in report["checks"]:
        lines.append(f"## `{check['path']}`")
        lines.append("")
        lines.append(f"Status: `{check['status']}`")
        if check.get("legacy_user_id") is not None:
            lines.append(f"Legacy user id: `{check.get('legacy_user_id')}`")
            lines.append(f"MySQL user id: `{check.get('mysql_user_id')}`")
        issues = check.get("issues") or []
        if not issues:
            lines.extend(["", "No differences found.", ""])
            continue
        lines.extend(["", "| Section | Key | Expected | Actual | Delta |", "| --- | --- | ---: | ---: | ---: |"])
        for issue in issues:
            lines.append(f"| `{issue['section']}` | `{issue['key']}` | {issue['expected']} | {issue['actual']} | {issue['delta']} |")
        lines.append("")
    lines.append(f"Failed checks: `{report['failed']}`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare SQLite source data with MySQL migration target.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    report = build_reconciliation_report(
        Path(args.source_root),
        args.auth_db,
        args.root_finance_db,
        args.users_dir,
        args.database_url,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
