import unittest
from pathlib import Path

from tools.postgres_stage_check import StageCheckError, is_local_database_url, run_stage_check


class PostgresStageCheckTestCase(unittest.TestCase):
    def test_is_local_database_url_accepts_localhost(self):
        self.assertTrue(is_local_database_url("postgresql+psycopg://user:pass@localhost/db"))
        self.assertTrue(is_local_database_url("postgresql://user:pass@127.0.0.1:5432/db"))

    def test_is_local_database_url_rejects_remote_host(self):
        self.assertFalse(is_local_database_url("postgresql://user:pass@example.com/db"))

    def test_reset_target_is_required(self):
        with self.assertRaises(StageCheckError):
            run_stage_check(
                source_root=Path("."),
                database_url="postgresql://user:pass@localhost/db",
                auth_db="auth.db",
                root_finance_db="finance.db",
                users_dir="data/users",
                reset_target=False,
                allow_nonlocal_target=False,
            )

    def test_nonlocal_target_requires_explicit_flag(self):
        with self.assertRaises(StageCheckError):
            run_stage_check(
                source_root=Path("."),
                database_url="postgresql://user:pass@example.com/db",
                auth_db="auth.db",
                root_finance_db="finance.db",
                users_dir="data/users",
                reset_target=True,
                allow_nonlocal_target=False,
            )


if __name__ == "__main__":
    unittest.main()
