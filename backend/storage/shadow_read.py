from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.storage.postgres_read import PostgresReadRepository
from utils.logger import app_logger


def _money(value: Any) -> float:
    return round(float(value or 0.0), 2)


def _compare_money(section: str, field: str, expected: Any, actual: Any) -> Optional[Dict[str, Any]]:
    expected_money = _money(expected)
    actual_money = _money(actual)
    if expected_money == actual_money:
        return None
    return {
        "section": section,
        "field": field,
        "expected": expected_money,
        "actual": actual_money,
    }


def postgres_shadow_read_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "postgres_read_shadow_enabled", False)
        and getattr(config, "database_url", "")
    )


def compare_dashboard_shadow_read(
    current_user: Optional[Dict[str, Any]],
    sqlite_balance: Any,
    sqlite_monthly_stats: Dict[str, Any],
    year: int,
    month: int,
    config=settings,
) -> Dict[str, Any]:
    """Compare a live SQLite dashboard read with PostgreSQL without changing the response."""
    if not current_user or not postgres_shadow_read_enabled(config):
        return {"enabled": False, "issues": []}

    legacy_user_id = int(current_user["id"])
    issues: List[Dict[str, Any]] = []
    try:
        repo = PostgresReadRepository(config.database_url)
        with repo.connect() as conn:
            pg_balance = repo.get_balance(conn, legacy_user_id)
            pg_monthly_stats = repo.get_monthly_stats(conn, legacy_user_id, year, month)
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow read failed for dashboard user_id=%s: %s",
            legacy_user_id,
            exc,
        )
        return {"enabled": True, "issues": [{"section": "exception", "message": str(exc)}]}

    balance_checks = [
        ("main_balance", getattr(sqlite_balance, "main_balance", 0.0), pg_balance.get("main_balance")),
        ("income", getattr(sqlite_balance, "income", 0.0), pg_balance.get("income")),
        ("expense", getattr(sqlite_balance, "expense", 0.0), pg_balance.get("expense")),
    ]
    for field, expected, actual in balance_checks:
        issue = _compare_money("balance", field, expected, actual)
        if issue:
            issues.append(issue)

    for field in ("income", "expense", "capital"):
        issue = _compare_money(
            "monthly_stats",
            field,
            sqlite_monthly_stats.get(field),
            pg_monthly_stats.get(field),
        )
        if issue:
            issues.append(issue)

    if issues:
        app_logger.warning(
            "PostgreSQL shadow read mismatch for dashboard user_id=%s: issues=%s",
            legacy_user_id,
            len(issues),
        )
    else:
        app_logger.info("PostgreSQL shadow read matched dashboard user_id=%s", legacy_user_id)
    return {"enabled": True, "issues": issues}
