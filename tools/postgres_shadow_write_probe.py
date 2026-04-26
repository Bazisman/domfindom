from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.postgres_write import PostgresWriteRepository


def scalar(conn, sql: str, params=()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def build_probe(database_url: str, legacy_user_id: int, source_db_path: str) -> Dict[str, Any]:
    repo = PostgresWriteRepository(database_url)
    with repo.connect() as conn:
        pg_user_id = repo.get_user_id_by_legacy(conn, legacy_user_id)
        if pg_user_id is None:
            raise RuntimeError(f"PostgreSQL user for legacy user {legacy_user_id} was not found")
        category_row = conn.execute(
            """
            SELECT name, legacy_local_id
            FROM finance.categories
            WHERE user_id = %s AND is_active = true AND type IN ('expense', 'both')
            ORDER BY id
            LIMIT 1
            """,
            (pg_user_id,),
        ).fetchone()
        category = category_row["name"] if category_row else None
        category_legacy_id = category_row["legacy_local_id"] if category_row else None
        if category is None:
            raise RuntimeError("No expense category available for write probe")
        capital_account_id = scalar(
            conn,
            """
            SELECT legacy_local_id
            FROM finance.capital_accounts
            WHERE user_id = %s AND is_active = true
            ORDER BY id
            LIMIT 1
            """,
            (pg_user_id,),
        )
        if capital_account_id is None:
            raise RuntimeError("No active capital account available for transfer probe")
        income_category_row = conn.execute(
            """
            SELECT name, legacy_local_id
            FROM finance.categories
            WHERE user_id = %s AND is_active = true AND type IN ('income', 'both')
            ORDER BY id
            LIMIT 1
            """,
            (pg_user_id,),
        ).fetchone()
        template_category_id = category_legacy_id
        template_type = "expense"
        template_category = category
        if income_category_row:
            template_category_id = income_category_row["legacy_local_id"]
            template_type = "income"
            template_category = income_category_row["name"]
        legacy_local_id = int(
            scalar(
                conn,
                "SELECT COALESCE(MAX(legacy_local_id), 0) + 1000000 FROM finance.transactions WHERE user_id = %s",
                (pg_user_id,),
            )
        )
        before_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        before_transfer_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transfers WHERE user_id = %s", (pg_user_id,))
        )
        result = repo.mirror_actual_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction={
                "id": legacy_local_id,
                "type": "expense",
                "category": category,
                "amount": 1.23,
                "comment": "postgres shadow write rollback probe",
                "date": "2026-04-26",
                "money_source": "cashless",
                "status": "actual",
            },
            transfers=[],
        )
        after_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        update_result = repo.mirror_update_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction={
                "id": legacy_local_id,
                "type": "expense",
                "category": category,
                "amount": 2.34,
                "comment": "postgres shadow write rollback probe updated",
                "date": "2026-04-26",
                "money_source": "cashless",
                "status": "actual",
            },
            transfers=[],
        )
        after_update_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        delete_result = repo.mirror_delete_transaction(conn, legacy_user_id, legacy_local_id)
        after_delete_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        planned_legacy_local_id = legacy_local_id + 1000000
        planned_insert_result = repo.mirror_planned_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction={
                "id": planned_legacy_local_id,
                "type": "expense",
                "category": category,
                "amount": 3.21,
                "comment": "postgres planned shadow write rollback probe",
                "date": "2026-05-26",
                "money_source": "cashless",
                "status": "planned",
                "template_id": None,
            },
        )
        after_planned_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        planned_update_result = repo.mirror_update_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction={
                "id": planned_legacy_local_id,
                "type": "expense",
                "category": category,
                "amount": 4.32,
                "comment": "postgres planned shadow write rollback probe updated",
                "date": "2026-05-27",
                "money_source": "cashless",
                "status": "planned",
                "template_id": None,
            },
            transfers=[],
        )
        after_planned_update_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        planned_delete_result = repo.mirror_delete_transaction(conn, legacy_user_id, planned_legacy_local_id)
        after_planned_delete_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        template_legacy_id = legacy_local_id + 2000000
        template_result = repo.mirror_recurring_template(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            template={
                "id": template_legacy_id,
                "type": template_type,
                "name": "postgres recurring shadow write rollback probe",
                "amount": 5.43,
                "day_of_month": 26,
                "category_id": template_category_id,
                "comment_template": "postgres recurring shadow write rollback probe",
                "money_source": "cashless",
                "months_ahead": 2,
                "working_days_only": False,
                "is_active": True,
            },
        )
        templated_planned_legacy_id = legacy_local_id + 3000000
        templated_planned_result = repo.mirror_planned_transaction(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transaction={
                "id": templated_planned_legacy_id,
                "type": template_type,
                "category": template_category,
                "amount": 5.43,
                "comment": "postgres templated planned rollback probe",
                "date": "2026-06-26",
                "money_source": "cashless",
                "status": "planned",
                "template_id": template_legacy_id,
            },
        )
        after_templated_planned_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        template_delete_result = repo.mirror_delete_recurring_template(conn, legacy_user_id, template_legacy_id)
        after_template_delete_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transactions WHERE user_id = %s", (pg_user_id,))
        )
        transfer_legacy_id = legacy_local_id + 4000000
        transfer_result = repo.mirror_standalone_transfer(
            conn,
            legacy_user_id=legacy_user_id,
            source_db_path=source_db_path,
            transfer={
                "id": transfer_legacy_id,
                "from_account_id": 1,
                "to_account_id": int(capital_account_id),
                "amount": 6.54,
                "date": "2026-04-26",
                "comment": "postgres standalone transfer rollback probe",
                "is_active": True,
            },
        )
        after_transfer_count = int(
            scalar(conn, "SELECT COUNT(*) FROM finance.transfers WHERE user_id = %s", (pg_user_id,))
        )
        conn.rollback()
    return {
        "legacy_user_id": legacy_user_id,
        "postgres_user_id": pg_user_id,
        "status": "ok"
        if (
            result["status"] == "inserted"
            and after_count == before_count + 1
            and update_result["status"] == "updated"
            and after_update_count == before_count + 1
            and delete_result["status"] == "deleted"
            and after_delete_count == before_count
            and planned_insert_result["status"] == "inserted"
            and after_planned_count == before_count + 1
            and planned_update_result["status"] == "updated"
            and after_planned_update_count == before_count + 1
            and planned_delete_result["status"] == "deleted"
            and after_planned_delete_count == before_count
            and template_result["status"] == "inserted"
            and templated_planned_result["status"] == "inserted"
            and after_templated_planned_count == before_count + 1
            and template_delete_result["status"] == "deleted"
            and after_template_delete_count == before_count
            and transfer_result["status"] == "inserted"
            and after_transfer_count == before_transfer_count + 1
        )
        else "failed",
        "insert_status": result["status"],
        "update_status": update_result["status"],
        "delete_status": delete_result["status"],
        "planned_insert_status": planned_insert_result["status"],
        "planned_update_status": planned_update_result["status"],
        "planned_delete_status": planned_delete_result["status"],
        "template_status": template_result["status"],
        "templated_planned_status": templated_planned_result["status"],
        "template_delete_status": template_delete_result["status"],
        "transfer_status": transfer_result["status"],
        "before_count": before_count,
        "before_transfer_count": before_transfer_count,
        "after_count_inside_transaction": after_count,
        "after_update_count_inside_transaction": after_update_count,
        "after_delete_count_inside_transaction": after_delete_count,
        "after_planned_count_inside_transaction": after_planned_count,
        "after_planned_update_count_inside_transaction": after_planned_update_count,
        "after_planned_delete_count_inside_transaction": after_planned_delete_count,
        "after_templated_planned_count_inside_transaction": after_templated_planned_count,
        "after_template_delete_count_inside_transaction": after_template_delete_count,
        "after_transfer_count_inside_transaction": after_transfer_count,
        "rolled_back": True,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# PostgreSQL Shadow Write Probe",
            "",
            f"Legacy user: `{report['legacy_user_id']}`",
            f"PostgreSQL user: `{report['postgres_user_id']}`",
            f"Status: `{report['status']}`",
            f"Insert status: `{report['insert_status']}`",
            f"Update status: `{report['update_status']}`",
            f"Delete status: `{report['delete_status']}`",
            f"Planned insert status: `{report['planned_insert_status']}`",
            f"Planned update status: `{report['planned_update_status']}`",
            f"Planned delete status: `{report['planned_delete_status']}`",
            f"Template status: `{report['template_status']}`",
            f"Templated planned status: `{report['templated_planned_status']}`",
            f"Template delete status: `{report['template_delete_status']}`",
            f"Transfer status: `{report['transfer_status']}`",
            f"Before count: `{report['before_count']}`",
            f"Before transfer count: `{report['before_transfer_count']}`",
            f"After count inside transaction: `{report['after_count_inside_transaction']}`",
            f"After update count inside transaction: `{report['after_update_count_inside_transaction']}`",
            f"After delete count inside transaction: `{report['after_delete_count_inside_transaction']}`",
            f"After planned count inside transaction: `{report['after_planned_count_inside_transaction']}`",
            f"After planned update count inside transaction: `{report['after_planned_update_count_inside_transaction']}`",
            f"After planned delete count inside transaction: `{report['after_planned_delete_count_inside_transaction']}`",
            f"After templated planned count inside transaction: `{report['after_templated_planned_count_inside_transaction']}`",
            f"After template delete count inside transaction: `{report['after_template_delete_count_inside_transaction']}`",
            f"After transfer count inside transaction: `{report['after_transfer_count_inside_transaction']}`",
            f"Rolled back: `{report['rolled_back']}`",
        ]
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Probe PostgreSQL transaction write adapter inside a rollback transaction.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--legacy-user-id", type=int, required=True)
    parser.add_argument("--source-db-path", default="")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()
    source_db_path = args.source_db_path or f"data/users/{args.legacy_user_id}/finance.db"
    report = build_probe(args.database_url, args.legacy_user_id, source_db_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
