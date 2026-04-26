from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.mysql_write import MySqlWriteRepository


def _scalar(conn, query: str, params=()) -> int:
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    return int(next(iter(row.values())) or 0) if row else 0


def _category_name(conn, user_id: int) -> str:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT name
            FROM finance_categories
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY id
            LIMIT 1
            """,
            (int(user_id),),
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"No active category found for MySQL user {user_id}")
    return str(row["name"])


def _daily_account_legacy_id(conn, user_id: int) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT legacy_local_id
            FROM finance_accounts
            WHERE user_id = %s AND legacy_local_id IN (1, 2)
            ORDER BY legacy_local_id
            LIMIT 1
            """,
            (int(user_id),),
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"No daily account found for MySQL user {user_id}")
    return int(row["legacy_local_id"])


def build_probe(database_url: str, legacy_user_id: int, source_db_path: str, family_id: int | None = None) -> Dict[str, Any]:
    repo = MySqlWriteRepository(database_url)
    conn = repo.connect()
    try:
        mysql_user_id = repo.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        before_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        before_category_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_categories WHERE user_id = %s", (mysql_user_id,))
        before_budget_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_budgets WHERE user_id = %s", (mysql_user_id,))
        before_capital_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_capital_accounts WHERE user_id = %s", (mysql_user_id,))
        before_transfer_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transfers WHERE user_id = %s", (mysql_user_id,))
        category = _category_name(conn, mysql_user_id)
        daily_account_id = _daily_account_legacy_id(conn, mysql_user_id)
        legacy_transaction_id = 900000001
        transaction = {
            "id": legacy_transaction_id,
            "type": "income",
            "category": category,
            "amount": 123.45,
            "comment": "mysql shadow write rollback probe",
            "date": date.today().isoformat(),
            "money_source": "cashless",
            "status": "actual",
        }
        insert_result = repo.mirror_actual_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction=transaction,
            transfers=[],
        )
        transaction["amount"] = 125.45
        transaction["comment"] = "mysql shadow write rollback probe updated"
        update_result = repo.mirror_update_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction=transaction,
            transfers=[],
        )
        delete_result = repo.mirror_delete_transaction(conn, legacy_user_id, legacy_transaction_id)
        probe_category = {
            "id": 900000101,
            "name": "mysql shadow write rollback category",
            "type": "expense",
            "color": "#64748b",
            "icon": "probe",
            "is_active": 1,
        }
        category_result = repo.mirror_category(conn, legacy_user_id, source_db_path, probe_category)
        budget_result = repo.mirror_budget(
            conn,
            legacy_user_id,
            source_db_path,
            {"id": 900000102, "category_id": probe_category["id"], "amount": 321.0, "period": "monthly"},
        )
        capital_result = repo.mirror_capital_account(
            conn,
            legacy_user_id,
            source_db_path,
            {
                "id": 900000103,
                "name": "mysql shadow write rollback capital",
                "balance": 0,
                "currency": "RUB",
                "icon": "probe",
                "color": "#64748b",
                "is_default": 0,
                "is_active": 1,
            },
        )
        transfer_result = repo.mirror_standalone_transfer(
            conn,
            legacy_user_id,
            source_db_path,
            {
                "id": 900000104,
                "from_account_id": daily_account_id,
                "to_account_id": 900000103,
                "amount": 10.0,
                "date": date.today().isoformat(),
                "comment": "mysql shadow write rollback transfer",
                "is_active": 1,
            },
        )
        delete_budget_result = repo.mirror_delete_budget(conn, legacy_user_id, 900000102)
        family_result = None
        if family_id is not None:
            from backend.storage.shadow_write import _auth_rows_for_family

            snapshot = _auth_rows_for_family(int(family_id))
            if not snapshot:
                raise RuntimeError(f"Family {family_id} was not found")
            family_result = repo.mirror_family_snapshot(conn, source_db_path="auth.db", snapshot=snapshot)
        after_delete_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        conn.rollback()
        after_rollback_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        after_category_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_categories WHERE user_id = %s", (mysql_user_id,))
        after_budget_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_budgets WHERE user_id = %s", (mysql_user_id,))
        after_capital_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_capital_accounts WHERE user_id = %s", (mysql_user_id,))
        after_transfer_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transfers WHERE user_id = %s", (mysql_user_id,))
        counts_ok = (
            before_count == after_rollback_count
            and before_category_count == after_category_count
            and before_budget_count == after_budget_count
            and before_capital_count == after_capital_count
            and before_transfer_count == after_transfer_count
        )
        return {
            "status": "ok" if counts_ok else "failed",
            "legacy_user_id": legacy_user_id,
            "mysql_user_id": mysql_user_id,
            "before_count": before_count,
            "after_delete_count": after_delete_count,
            "after_rollback_count": after_rollback_count,
            "metadata_counts": {
                "categories": [before_category_count, after_category_count],
                "budgets": [before_budget_count, after_budget_count],
                "capital_accounts": [before_capital_count, after_capital_count],
                "transfers": [before_transfer_count, after_transfer_count],
            },
            "insert": insert_result,
            "update": update_result,
            "delete": delete_result,
            "category": category_result,
            "budget": budget_result,
            "capital_account": capital_result,
            "transfer": transfer_result,
            "budget_delete": delete_budget_result,
            "family": family_result,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MySQL shadow-write rollback probe.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--legacy-user-id", type=int, required=True)
    parser.add_argument("--source-db-path", required=True)
    parser.add_argument("--family-id", type=int)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    report = build_probe(args.database_url, args.legacy_user_id, args.source_db_path, family_id=args.family_id)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("# MySQL Shadow Write Rollback Probe")
        print("")
        print(f"Status: `{report['status']}`")
        print(f"Legacy user: `{report['legacy_user_id']}`")
        print(f"MySQL user: `{report['mysql_user_id']}`")
        print(f"Before count: `{report['before_count']}`")
        print(f"After delete count: `{report['after_delete_count']}`")
        print(f"After rollback count: `{report['after_rollback_count']}`")
        if report.get("family") is not None:
            print(f"Family snapshot: `{report['family']['status']}`")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
