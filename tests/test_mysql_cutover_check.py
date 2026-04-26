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
        check = mysql_cutover_check.check_runtime_adapter_status(allow_mysql_backend=True)

        self.assertEqual(check["status"], "blocked")
        self.assertIn("primary MySQL write adapters", check["reason"])
        self.assertIn("transactions", check["missing_groups"])
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

    def test_build_report_can_be_shadow_ready_but_not_runtime_ready(self):
        with (
            patch.object(mysql_cutover_check, "check_python_dependencies", return_value={"status": "ok"}),
            patch.object(mysql_cutover_check, "check_database_connection", return_value={"status": "ok"}),
            patch.object(mysql_cutover_check, "check_schema_tables", return_value={"status": "ok"}),
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


if __name__ == "__main__":
    unittest.main()
