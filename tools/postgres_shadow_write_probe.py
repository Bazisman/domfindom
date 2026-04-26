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
        category = scalar(
            conn,
            """
            SELECT name
            FROM finance.categories
            WHERE user_id = %s AND is_active = true AND type IN ('expense', 'both')
            ORDER BY id
            LIMIT 1
            """,
            (pg_user_id,),
        )
        if category is None:
            raise RuntimeError("No expense category available for write probe")
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
        conn.rollback()
    return {
        "legacy_user_id": legacy_user_id,
        "postgres_user_id": pg_user_id,
        "status": "ok" if result["status"] == "inserted" and after_count == before_count + 1 else "failed",
        "insert_status": result["status"],
        "before_count": before_count,
        "after_count_inside_transaction": after_count,
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
            f"Before count: `{report['before_count']}`",
            f"After count inside transaction: `{report['after_count_inside_transaction']}`",
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
