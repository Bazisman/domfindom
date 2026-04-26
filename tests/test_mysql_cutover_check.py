import unittest
from unittest.mock import patch

from tools import mysql_cutover_check


class MySqlCutoverCheckTestCase(unittest.TestCase):
    def test_storage_backend_blocks_runtime_mysql_by_default(self):
        check = mysql_cutover_check.check_storage_backend("mysql", allow_mysql_backend=False)

        self.assertEqual(check["status"], "blocked")
        self.assertIn("write backend", check["reason"])

    def test_storage_backend_allows_sqlite(self):
        check = mysql_cutover_check.check_storage_backend("sqlite", allow_mysql_backend=False)

        self.assertEqual(check, {"status": "ok", "storage_backend": "sqlite"})

    def test_runtime_adapter_status_blocks_even_with_allow_flag(self):
        check = mysql_cutover_check.check_runtime_adapter_status(
            allow_mysql_backend=True,
            guarded_groups=["categories_budgets_recurring"],
        )

        self.assertEqual(check["status"], "blocked")
        self.assertIn("primary MySQL write adapters", check["reason"])
        self.assertIn("transactions", check["missing_groups"])
        self.assertNotIn("categories_budgets_recurring", check["missing_groups"])
        self.assertIn("categories_budgets_recurring", check["guarded_groups"])
        self.assertIn("auth_and_sessions", check["details"])

    def test_primary_read_pilot_requires_database_url(self):
        check = mysql_cutover_check.check_primary_read_pilot(
            {"FINANCE_APP_MYSQL_PRIMARY_READ_PILOT": "true"},
            "",
        )

        self.assertEqual(check["status"], "blocked")
        self.assertTrue(check["enabled"])

    def test_primary_read_pilot_can_be_enabled_with_database_url(self):
        check = mysql_cutover_check.check_primary_read_pilot(
            {"FINANCE_APP_MYSQL_PRIMARY_READ_PILOT": "true"},
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check, {"status": "ok", "enabled": True})

    def test_strict_categories_budgets_recurring_requires_shadow_write(self):
        check = mysql_cutover_check.check_strict_categories_budgets_recurring(
            {"FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING": "true"},
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "blocked")
        self.assertIn("FINANCE_APP_MYSQL_SHADOW_WRITE", check["reason"])

    def test_strict_categories_budgets_recurring_can_be_enabled(self):
        check = mysql_cutover_check.check_strict_categories_budgets_recurring(
            {
                "FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING": "true",
                "FINANCE_APP_MYSQL_SHADOW_WRITE": "true",
            },
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "ok")
        self.assertTrue(check["enabled"])
        self.assertEqual(check["mode"], "strict-dual-write")

    def test_strict_transactions_requires_shadow_write(self):
        check = mysql_cutover_check.check_strict_transactions(
            {"FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS": "true"},
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "blocked")
        self.assertIn("FINANCE_APP_MYSQL_SHADOW_WRITE", check["reason"])

    def test_strict_transactions_can_be_enabled(self):
        check = mysql_cutover_check.check_strict_transactions(
            {
                "FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS": "true",
                "FINANCE_APP_MYSQL_SHADOW_WRITE": "true",
            },
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "ok")
        self.assertTrue(check["enabled"])
        self.assertEqual(check["guarded_group"], "transactions")

    def test_strict_accounts_capital_requires_shadow_write(self):
        check = mysql_cutover_check.check_strict_accounts_capital(
            {"FINANCE_APP_MYSQL_STRICT_WRITE_ACCOUNTS_CAPITAL": "true"},
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "blocked")
        self.assertIn("FINANCE_APP_MYSQL_SHADOW_WRITE", check["reason"])

    def test_strict_accounts_capital_can_be_enabled(self):
        check = mysql_cutover_check.check_strict_accounts_capital(
            {
                "FINANCE_APP_MYSQL_STRICT_WRITE_ACCOUNTS_CAPITAL": "true",
                "FINANCE_APP_MYSQL_SHADOW_WRITE": "true",
            },
            "mysql+pymysql://user:pass@localhost:3306/db",
        )

        self.assertEqual(check["status"], "ok")
        self.assertTrue(check["enabled"])
        self.assertEqual(check["guarded_group"], "accounts_and_capital")

    def test_build_report_can_be_shadow_ready_but_not_runtime_ready(self):
        with (
            patch.object(mysql_cutover_check, "check_python_dependencies", return_value={"status": "ok"}),
            patch.object(mysql_cutover_check, "check_database_connection", return_value={"status": "ok"}),
            patch.object(mysql_cutover_check, "check_schema_tables", return_value={"status": "ok"}),
        ):
            with patch.dict(
                mysql_cutover_check.os.environ,
                {
                    "FINANCE_APP_MYSQL_SHADOW_WRITE": "true",
                    "FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING": "true",
                    "FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS": "true",
                    "FINANCE_APP_MYSQL_STRICT_WRITE_ACCOUNTS_CAPITAL": "true",
                },
                clear=False,
            ):
                report = mysql_cutover_check.build_report(
                    source_root=mysql_cutover_check.PROJECT_ROOT,
                    database_url="mysql+pymysql://user:pass@localhost:3306/db",
                    auth_db="auth.db",
                    root_finance_db="finance.db",
                    users_dir="data/users",
                    year=2026,
                    month=4,
                    allow_mysql_backend=False,
                    skip_data_checks=True,
                )

        self.assertTrue(report["ready_for_shadow_read"])
        self.assertFalse(report["ready_for_runtime_mysql"])
        self.assertEqual(report["blockers"], ["runtime_adapter"])
        self.assertIn("strict_categories_budgets_recurring", report["checks"])
        self.assertIn("categories_budgets_recurring", report["checks"]["runtime_adapter"]["guarded_groups"])
        self.assertIn("transactions", report["checks"]["runtime_adapter"]["guarded_groups"])
        self.assertIn("accounts_and_capital", report["checks"]["runtime_adapter"]["guarded_groups"])

    def test_render_markdown_includes_readiness(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "runtime_adapter": {
                    "status": "blocked",
                    "reason": "primary runtime is still SQLite-first",
                }
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("Ready for shadow read: `True`", rendered)
        self.assertIn("Ready for runtime mysql: `False`", rendered)
        self.assertIn("`runtime_adapter`", rendered)

    def test_render_markdown_includes_runtime_missing_groups(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "runtime_adapter": mysql_cutover_check.check_runtime_adapter_status(
                    allow_mysql_backend=False
                )
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("missing: auth_and_sessions", rendered)
        self.assertIn("transactions", rendered)

    def test_render_markdown_includes_runtime_guarded_groups(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "runtime_adapter": mysql_cutover_check.check_runtime_adapter_status(
                    allow_mysql_backend=False,
                    guarded_groups=["categories_budgets_recurring"],
                )
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("guarded: categories_budgets_recurring", rendered)

    def test_render_markdown_includes_strict_categories_budgets_recurring(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "strict_categories_budgets_recurring": {
                    "status": "ok",
                    "enabled": True,
                    "mode": "strict-dual-write",
                }
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("`strict_categories_budgets_recurring`", rendered)
        self.assertIn("mode=strict-dual-write", rendered)

    def test_render_markdown_includes_strict_transactions(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "strict_transactions": {
                    "status": "ok",
                    "enabled": True,
                    "mode": "strict-dual-write",
                }
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("`strict_transactions`", rendered)
        self.assertIn("mode=strict-dual-write", rendered)

    def test_render_markdown_includes_strict_accounts_capital(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": True,
            "ready_for_runtime_mysql": False,
            "blockers": ["runtime_adapter"],
            "checks": {
                "strict_accounts_capital": {
                    "status": "ok",
                    "enabled": True,
                    "mode": "strict-dual-write",
                }
            },
        }

        rendered = mysql_cutover_check.render_markdown(report)

        self.assertIn("`strict_accounts_capital`", rendered)
        self.assertIn("mode=strict-dual-write", rendered)


if __name__ == "__main__":
    unittest.main()
