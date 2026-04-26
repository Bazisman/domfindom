import unittest
from types import SimpleNamespace
from unittest.mock import patch

import core
from services import transaction_service as transaction_service_module


class MySqlPrimaryReadSliceTestCase(unittest.TestCase):
    def setUp(self):
        transaction_service_module._AUTH_USER_TO_LEGACY_CACHE.clear()

    def test_legacy_user_id_from_current_db_path(self):
        token = core.push_db_name("data/users/12/finance.db")
        try:
            self.assertEqual(transaction_service_module._legacy_user_id_from_current_db(), 12)
        finally:
            core.pop_db_name(token)

    def test_legacy_user_id_returns_none_for_root_db(self):
        token = core.push_db_name("finance.db")
        try:
            self.assertIsNone(transaction_service_module._legacy_user_id_from_current_db())
        finally:
            core.pop_db_name(token)

    def test_mysql_read_repo_is_disabled_for_root_db(self):
        token = core.push_db_name("finance.db")
        try:
            with patch.object(transaction_service_module, "_mysql_primary_reads_enabled", return_value=True):
                repo, legacy_user_id = transaction_service_module._mysql_read_repo_for_current_user()
        finally:
            core.pop_db_name(token)

        self.assertIsNone(repo)
        self.assertIsNone(legacy_user_id)

    def test_mysql_primary_reads_can_use_pilot_flag(self):
        settings = SimpleNamespace(
            storage_backend="sqlite",
            mysql_database_url="mysql+pymysql://user:pass@localhost:3306/db",
            mysql_primary_read_pilot_enabled=True,
        )

        with patch("backend.config.settings", settings):
            self.assertTrue(transaction_service_module._mysql_primary_reads_enabled())

    def test_mysql_primary_path_user_id_is_mapped_to_legacy_user_id(self):
        settings = SimpleNamespace(
            storage_backend="mysql",
            mysql_database_url="mysql+pymysql://user:pass@localhost:3306/db",
            mysql_primary_read_pilot_enabled=False,
        )

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, _sql, _params):
                return None

            def fetchone(self):
                return {"legacy_sqlite_user_id": 12}

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

        token = core.push_db_name("data/users/9/finance.db")
        try:
            with patch("backend.config.settings", settings), patch("tools.mysql_schema.mysql_connect", return_value=FakeConnection()):
                self.assertEqual(transaction_service_module._legacy_user_id_from_current_db(), 12)
        finally:
            core.pop_db_name(token)


if __name__ == "__main__":
    unittest.main()
