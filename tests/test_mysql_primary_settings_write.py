import unittest
from unittest import mock

from services.transaction_service import TransactionService


class _Connection:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True


class MySqlPrimarySettingsWriteTestCase(unittest.TestCase):
    def test_set_auto_capital_settings_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.set_auto_capital_settings.return_value = {"status": "upserted", "enabled": False, "percent": 7}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            service.set_auto_capital_settings(False, 7)

        self.assertFalse(service._auto_enabled)
        self.assertEqual(service._auto_percent, 7)
        self.assertTrue(conn.committed)
        repo.set_auto_capital_settings.assert_called_once_with(conn, 12, False, 7)

    def test_get_auto_capital_settings_uses_mysql_read_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.get_auto_capital_settings.return_value = {"enabled": True, "percent": 15}

        with mock.patch(
            "services.transaction_service._mysql_read_repo_for_current_user",
            return_value=(repo, 12),
        ):
            settings = service.get_auto_capital_settings()

        self.assertEqual(settings, (True, 15))
        repo.get_auto_capital_settings.assert_called_once_with(conn, 12)

    def test_set_default_money_source_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.set_default_money_source.return_value = {"status": "upserted", "default_money_source": "cash"}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.set_default_money_source("cash")

        self.assertEqual(result, "cash")
        self.assertTrue(conn.committed)
        repo.set_default_money_source.assert_called_once_with(conn, 12, "cash")

    def test_get_default_money_source_uses_mysql_read_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.get_default_money_source.return_value = "cash"

        with mock.patch(
            "services.transaction_service._mysql_read_repo_for_current_user",
            return_value=(repo, 12),
        ):
            result = service.get_default_money_source()

        self.assertEqual(result, "cash")
        repo.get_default_money_source.assert_called_once_with(conn, 12)


if __name__ == "__main__":
    unittest.main()
