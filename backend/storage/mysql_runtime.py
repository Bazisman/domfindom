from __future__ import annotations

from backend.config import settings


MYSQL_RUNTIME_GUARD_FLAGS = {
    "auth_and_sessions": "mysql_strict_write_auth_enabled",
    "transactions": "mysql_strict_write_transactions_enabled",
    "accounts_and_capital": "mysql_strict_write_accounts_capital_enabled",
    "categories_budgets_recurring": "mysql_strict_write_categories_budgets_recurring_enabled",
    "reconciliation_settings": "mysql_strict_write_reconciliation_enabled",
}


def mysql_strict_dual_write_ready(config=settings) -> bool:
    return bool(
        getattr(config, "mysql_database_url", "")
        and getattr(config, "mysql_shadow_write_enabled", False)
        and all(bool(getattr(config, flag, False)) for flag in MYSQL_RUNTIME_GUARD_FLAGS.values())
    )


def mysql_runtime_mode(config=settings) -> str:
    if getattr(config, "storage_backend", "sqlite") != "mysql":
        return "sqlite-primary"
    if mysql_strict_dual_write_ready(config):
        return "mysql-primary-read-strict-dual-write"
    return "blocked"
