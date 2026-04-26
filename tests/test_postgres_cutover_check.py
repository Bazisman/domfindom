import unittest

from tools import postgres_cutover_check


class PostgresCutoverCheckTestCase(unittest.TestCase):
    def test_storage_backend_blocks_runtime_postgres_by_default(self):
        check = postgres_cutover_check.check_storage_backend("postgres", allow_postgres_backend=False)

        self.assertEqual(check["status"], "blocked")
        self.assertIn("write backend", check["reason"])

    def test_storage_backend_allows_sqlite(self):
        check = postgres_cutover_check.check_storage_backend("sqlite", allow_postgres_backend=False)

        self.assertEqual(check, {"status": "ok", "storage_backend": "sqlite"})

    def test_render_markdown_includes_readiness(self):
        report = {
            "source_root": ".",
            "ready_for_shadow_read": False,
            "ready_for_runtime_postgres": False,
            "blockers": ["database_connection"],
            "checks": {
                "database_connection": {
                    "status": "blocked",
                    "reason": "FINANCE_APP_DATABASE_URL is empty",
                }
            },
        }

        rendered = postgres_cutover_check.render_markdown(report)

        self.assertIn("Ready for shadow read: `False`", rendered)
        self.assertIn("`database_connection`", rendered)


if __name__ == "__main__":
    unittest.main()
