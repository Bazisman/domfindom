from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.mysql_read import MySqlReadRepository
from tools.postgres_read_compare import compare_user, render_markdown


def build_report(source_root: Path, database_url: str, users_dir: str, year: int, month: int) -> dict:
    repo = MySqlReadRepository(database_url)
    checks = []
    conn = repo.connect()
    try:
        for db_path in sorted((source_root / users_dir).glob("*/finance.db")):
            try:
                legacy_user_id = int(db_path.parent.name)
            except ValueError:
                continue
            checks.append(compare_user(repo, conn, db_path, legacy_user_id, year, month))
    finally:
        conn.close()
    failed = sum(1 for check in checks if check["status"] != "ok")
    return {"source_root": str(source_root), "checks": checks, "failed": failed}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Compare first MySQL read repository with SQLite snapshot.")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    report = build_report(
        source_root=Path(args.source_root).resolve(),
        database_url=args.database_url,
        users_dir=args.users_dir,
        year=args.year,
        month=args.month,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report).replace("PostgreSQL", "MySQL"))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
