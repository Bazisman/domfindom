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


def build_probe(database_url: str, legacy_user_id: int, source_db_path: str) -> Dict[str, Any]:
    repo = MySqlWriteRepository(database_url)
    conn = repo.connect()
    try:
        mysql_user_id = repo.get_user_id_by_legacy(conn, legacy_user_id)
        if mysql_user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        before_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        category = _category_name(conn, mysql_user_id)
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
        after_delete_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        conn.rollback()
        after_rollback_count = _scalar(conn, "SELECT COUNT(*) AS count FROM finance_transactions WHERE user_id = %s", (mysql_user_id,))
        return {
            "status": "ok" if before_count == after_rollback_count else "failed",
            "legacy_user_id": legacy_user_id,
            "mysql_user_id": mysql_user_id,
            "before_count": before_count,
            "after_delete_count": after_delete_count,
            "after_rollback_count": after_rollback_count,
            "insert": insert_result,
            "update": update_result,
            "delete": delete_result,
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
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    report = build_probe(args.database_url, args.legacy_user_id, args.source_db_path)
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
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
