from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.postgres_read import PostgresReadRepository
from tools.money_minor import to_minor
from tools.sqlite_inventory import open_readonly


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


def from_minor(value: int) -> float:
    return round(float(value) / 100.0, 2)


def sqlite_money_sum(conn: sqlite3.Connection, table: str, column: str, where: str = "", params: Iterable[Any] = ()) -> float:
    if table not in table_names(conn) or column not in column_names(conn, table):
        return 0.0
    sql = f'SELECT "{column}" AS value FROM "{table}"'
    if where:
        sql += f" WHERE {where}"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return from_minor(sum(to_minor(row["value"]) for row in rows if row["value"] is not None))


def sqlite_balance(conn: sqlite3.Connection) -> Dict[str, float]:
    return {
        "main_balance": sqlite_money_sum(conn, "accounts", "balance", "id IN (1, 2) AND is_active = 1"),
        "income": sqlite_money_sum(conn, "transactions", "amount", "type = 'income' AND (status = 'actual' OR status IS NULL)"),
        "expense": sqlite_money_sum(conn, "transactions", "amount", "type = 'expense' AND (status = 'actual' OR status IS NULL)"),
    }


def sqlite_transactions(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    if "transactions" not in table_names(conn):
        return []
    columns = column_names(conn, "transactions")
    rows = conn.execute(
        """
        SELECT *
        FROM transactions
        ORDER BY date DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "date": str(row["date"]),
                "type": str(row["type"]),
                "category": str(row["category"]),
                "amount": from_minor(to_minor(row["amount"])),
                "comment": str(row["comment"] or ""),
                "money_source": str(row["money_source"] if "money_source" in columns and row["money_source"] else "cashless"),
                "status": str(row["status"] if "status" in columns and row["status"] else "actual"),
                "template_id": row["template_id"] if "template_id" in columns else None,
            }
        )
    return result


def sqlite_category_totals(
    conn: sqlite3.Connection,
    transaction_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if "transactions" not in table_names(conn):
        return []
    params: List[Any] = [transaction_type]
    filters = ["type = ?", "(status = 'actual' OR status IS NULL)"]
    if start_date:
        filters.append("date >= ?")
        params.append(start_date)
    if end_date:
        filters.append("date <= ?")
        params.append(end_date)
    rows = conn.execute(
        f"""
        SELECT category, amount
        FROM transactions
        WHERE {' AND '.join(filters)}
        """,
        tuple(params),
    ).fetchall()
    totals: Dict[str, int] = {}
    for row in rows:
        category = str(row["category"])
        totals[category] = totals.get(category, 0) + to_minor(row["amount"])
    return [
        {"category": category, "total": from_minor(total)}
        for category, total in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def sqlite_capital_contributions_total(conn: sqlite3.Connection, start_date: Optional[str], end_date: Optional[str]) -> float:
    if "transfers" not in table_names(conn):
        return 0.0
    params: List[Any] = []
    filters = ["is_active = 1", "to_account_id IN (SELECT id FROM capital_accounts WHERE is_active = 1)"]
    if start_date:
        filters.append("date >= ?")
        params.append(start_date)
    if end_date:
        filters.append("date <= ?")
        params.append(end_date)
    return sqlite_money_sum(conn, "transfers", "amount", " AND ".join(filters), params)


def sqlite_monthly_stats(conn: sqlite3.Connection, year: int, month: int) -> Dict[str, Any]:
    import calendar

    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    income = sum(item["total"] for item in sqlite_category_totals(conn, "income", start_date, end_date))
    expense = sum(item["total"] for item in sqlite_category_totals(conn, "expense", start_date, end_date))
    capital = sqlite_capital_contributions_total(conn, start_date, end_date)
    return {"income": round(income, 2), "expense": round(expense, 2), "capital": round(capital, 2), "year": year, "month": month}


def compare_values(section: str, expected: Any, actual: Any) -> List[Dict[str, Any]]:
    return [] if expected == actual else [{"section": section, "expected": expected, "actual": actual}]


def compare_user(repo: PostgresReadRepository, pg_conn, db_path: Path, legacy_user_id: int, year: int, month: int) -> Dict[str, Any]:
    with open_readonly(db_path) as sqlite_conn:
        expected_balance = sqlite_balance(sqlite_conn)
        expected_transactions = sqlite_transactions(sqlite_conn, limit=25)
        expected_income_totals = sqlite_category_totals(sqlite_conn, "income")
        expected_expense_totals = sqlite_category_totals(sqlite_conn, "expense")
        expected_monthly_stats = sqlite_monthly_stats(sqlite_conn, year, month)

    actual_balance = repo.get_balance(pg_conn, legacy_user_id)
    actual_transactions = repo.get_transactions(pg_conn, legacy_user_id, limit=25)
    actual_income_totals = repo.get_category_totals(pg_conn, legacy_user_id, "income")
    actual_expense_totals = repo.get_category_totals(pg_conn, legacy_user_id, "expense")
    actual_monthly_stats = repo.get_monthly_stats(pg_conn, legacy_user_id, year, month)

    issues: List[Dict[str, Any]] = []
    issues.extend(compare_values("balance", expected_balance, actual_balance))
    issues.extend(compare_values("transactions", expected_transactions, actual_transactions))
    issues.extend(compare_values("income_totals", expected_income_totals, actual_income_totals))
    issues.extend(compare_values("expense_totals", expected_expense_totals, actual_expense_totals))
    issues.extend(compare_values("monthly_stats", expected_monthly_stats, actual_monthly_stats))
    return {"legacy_user_id": legacy_user_id, "path": str(db_path), "status": "ok" if not issues else "failed", "issues": issues}


def build_report(source_root: Path, database_url: str, users_dir: str, year: int, month: int) -> Dict[str, Any]:
    repo = PostgresReadRepository(database_url)
    checks = []
    with repo.connect() as pg_conn:
        for db_path in sorted((source_root / users_dir).glob("*/finance.db")):
            try:
                legacy_user_id = int(db_path.parent.name)
            except ValueError:
                continue
            checks.append(compare_user(repo, pg_conn, db_path, legacy_user_id, year, month))
    failed = sum(1 for check in checks if check["status"] != "ok")
    return {"source_root": str(source_root), "checks": checks, "failed": failed}


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# PostgreSQL Read Model Compare", "", f"Source root: `{report['source_root']}`", ""]
    lines.extend(["| User | Status | Issues |", "| ---: | --- | ---: |"])
    for check in report["checks"]:
        lines.append(f"| {check['legacy_user_id']} | `{check['status']}` | {len(check['issues'])} |")
    lines.extend(["", f"Failed checks: `{report['failed']}`"])
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Compare first PostgreSQL read repository with SQLite snapshot.")
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
        print(render_markdown(report))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
