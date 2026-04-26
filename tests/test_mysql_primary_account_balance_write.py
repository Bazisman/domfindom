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


class MySqlPrimaryAccountBalanceWriteTestCase(unittest.TestCase):
    def test_adjust_daily_account_balance_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.adjust_account_balance.return_value = {"status": "updated"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.update_account_balance") as update_balance,
        ):
            service.adjust_daily_account_balance("cash", 150.0)

        self.assertTrue(conn.committed)
        notify.assert_called_once()
        update_balance.assert_not_called()
        repo.adjust_account_balance.assert_called_once_with(conn, 12, 2, 150.0)

    def test_adjust_capital_account_balance_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.adjust_account_balance.return_value = {"status": "updated"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.get_connection") as get_connection,
        ):
            result = service.adjust_capital_account_balance(101, -50.0)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        get_connection.assert_not_called()
        repo.adjust_account_balance.assert_called_once_with(conn, 12, 101, -50.0)

    def test_adjust_capital_account_balance_returns_false_when_mysql_repo_misses(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.adjust_account_balance.return_value = {"status": "missing"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
        ):
            result = service.adjust_capital_account_balance(101, -50.0)

        self.assertFalse(result)
        self.assertTrue(conn.committed)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
