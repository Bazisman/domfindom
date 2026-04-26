from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.mysql_write import MySqlWriteRepository


def _first_legacy_user_id(repo: MySqlWriteRepository, conn) -> Optional[int]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT legacy_sqlite_user_id
            FROM auth_users
            WHERE legacy_sqlite_user_id IS NOT NULL
              AND is_active = TRUE
            ORDER BY legacy_sqlite_user_id
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    return int(row["legacy_sqlite_user_id"]) if row else None


def run_probe(database_url: str, legacy_user_id: Optional[int] = None) -> Dict[str, Any]:
    repo = MySqlWriteRepository(database_url)
    source_legacy_user_id = legacy_user_id
    source_local_id = 910_000_001
    with repo.connect() as conn:
        try:
            if source_legacy_user_id is None:
                source_legacy_user_id = _first_legacy_user_id(repo, conn)
            if source_legacy_user_id is None:
                return {"status": "blocked", "reason": "no active auth_users.legacy_sqlite_user_id found"}

            source_db_path = f"data/users/{source_legacy_user_id}/finance.db"
            category = {
                "id": source_local_id,
                "name": "__mysql_strict_probe_category__",
                "type": "expense",
                "color": "#607d8b",
                "icon": "probe",
                "is_active": True,
            }
            budget = {
                "id": source_local_id,
                "category_id": source_local_id,
                "amount": 1234.56,
                "period": "monthly",
            }
            template = {
                "id": source_local_id,
                "type": "expense",
                "name": "__mysql_strict_probe_template__",
                "amount": 1234.56,
                "day_of_month": 1,
                "category_id": source_local_id,
                "comment_template": "rollback probe",
                "money_source": "cashless",
                "months_ahead": 1,
                "working_days_only": False,
                "is_active": True,
            }
            planned = {
                "id": source_local_id,
                "type": "expense",
                "category": category["name"],
                "amount": 1234.56,
                "comment": "rollback probe",
                "date": "2099-01-01",
                "money_source": "cashless",
                "status": "planned",
                "template_id": source_local_id,
            }
            actual_transaction_id = source_local_id + 1
            actual_transaction = {
                "id": actual_transaction_id,
                "type": "expense",
                "category": category["name"],
                "amount": 321.09,
                "comment": "rollback probe actual",
                "date": "2099-01-02",
                "money_source": "cashless",
                "status": "actual",
            }
            updated_transaction = {
                **actual_transaction,
                "amount": 654.32,
                "comment": "rollback probe actual updated",
            }
            capital_account = {
                "id": source_local_id + 2,
                "name": "__mysql_strict_probe_capital__",
                "balance": 1000.0,
                "currency": "RUB",
                "icon": "probe",
                "color": "#795548",
                "is_default": False,
                "is_active": True,
            }
            transfer = {
                "id": source_local_id + 3,
                "from_account_id": 1,
                "to_account_id": capital_account["id"],
                "amount": 111.11,
                "date": "2099-01-03",
                "comment": "rollback probe transfer",
                "is_active": True,
            }

            category_result = repo.mirror_category(conn, source_legacy_user_id, source_db_path, category)
            budget_result = repo.mirror_budget(conn, source_legacy_user_id, source_db_path, budget)
            template_result = repo.mirror_recurring_template(conn, source_legacy_user_id, source_db_path, template)
            planned_result = repo.mirror_planned_transaction(conn, source_legacy_user_id, source_db_path, planned)
            actual_result = repo.mirror_actual_transaction(
                conn,
                source_legacy_user_id,
                source_db_path,
                actual_transaction,
            )
            update_result = repo.mirror_update_transaction(
                conn,
                source_legacy_user_id,
                source_db_path,
                updated_transaction,
            )
            transaction_delete_result = repo.mirror_delete_transaction(
                conn,
                source_legacy_user_id,
                actual_transaction_id,
            )
            capital_account_result = repo.mirror_capital_account(
                conn,
                source_legacy_user_id,
                source_db_path,
                capital_account,
            )
            transfer_result = repo.mirror_standalone_transfer(
                conn,
                source_legacy_user_id,
                source_db_path,
                transfer,
            )
            budget_delete_result = repo.mirror_delete_budget(conn, source_legacy_user_id, source_local_id)
            template_delete_result = repo.mirror_delete_recurring_template(conn, source_legacy_user_id, source_local_id)

            return {
                "status": "ok",
                "legacy_user_id": source_legacy_user_id,
                "rolled_back": True,
                "results": {
                    "category": category_result,
                    "budget": budget_result,
                    "template": template_result,
                    "planned": planned_result,
                    "actual_transaction": actual_result,
                    "transaction_update": update_result,
                    "transaction_delete": transaction_delete_result,
                    "capital_account": capital_account_result,
                    "transfer": transfer_result,
                    "budget_delete": budget_delete_result,
                    "template_delete": template_delete_result,
                },
            }
        finally:
            conn.rollback()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Rollback probe for MySQL strict category/budget/recurring writes.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--legacy-user-id", type=int, default=None)
    args = parser.parse_args()

    report = run_probe(args.database_url, legacy_user_id=args.legacy_user_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
