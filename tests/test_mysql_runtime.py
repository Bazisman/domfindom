import unittest
from types import SimpleNamespace

from backend.storage import mysql_runtime


def _settings(**overrides):
    defaults = {
        "storage_backend": "mysql",
        "mysql_database_url": "mysql+pymysql://user:pass@localhost:3306/db",
        "mysql_shadow_write_enabled": True,
        "mysql_strict_write_auth_enabled": True,
        "mysql_strict_write_transactions_enabled": True,
        "mysql_strict_write_accounts_capital_enabled": True,
        "mysql_strict_write_categories_budgets_recurring_enabled": True,
        "mysql_strict_write_reconciliation_enabled": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class MySqlRuntimeTestCase(unittest.TestCase):
    def test_mysql_runtime_mode_is_ready_when_all_strict_flags_are_enabled(self):
        self.assertTrue(mysql_runtime.mysql_strict_dual_write_ready(_settings()))
        self.assertEqual(mysql_runtime.mysql_runtime_mode(_settings()), "mysql-primary-read-strict-dual-write")

    def test_mysql_runtime_mode_blocks_without_shadow_write(self):
        config = _settings(mysql_shadow_write_enabled=False)

        self.assertFalse(mysql_runtime.mysql_strict_dual_write_ready(config))
        self.assertEqual(mysql_runtime.mysql_runtime_mode(config), "blocked")

    def test_sqlite_backend_stays_sqlite_primary(self):
        config = _settings(storage_backend="sqlite")

        self.assertEqual(mysql_runtime.mysql_runtime_mode(config), "sqlite-primary")


if __name__ == "__main__":
    unittest.main()
