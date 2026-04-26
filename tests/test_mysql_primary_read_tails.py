import unittest
from unittest import mock

from services.transaction_service import TransactionService


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class MySqlPrimaryReadTailsTestCase(unittest.TestCase):
    def test_transactions_for_export_use_mysql_read_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.get_transactions.return_value = [
            {
                "id": 1,
                "type": "income",
                "category": "Salary",
                "amount": 1000.0,
                "comment": "April",
                "date": "2026-04-26",
                "status": "actual",
                "money_source": "cashless",
            }
        ]

        with (
            mock.patch("services.transaction_service._mysql_read_repo_for_current_user", return_value=(repo, 12)),
            mock.patch("services.transaction_service.core.get_all_transactions") as core_get,
        ):
            rows = service.get_transactions_for_export()

        self.assertEqual(len(rows), 1)
        core_get.assert_not_called()
        repo.get_transactions.assert_called_once_with(conn, 12, limit=100000, offset=0)

    def test_reconciliation_history_uses_mysql_read_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.get_reconciliations_history.return_value = [{"id": 3, "difference": 0.0}]

        with (
            mock.patch("services.transaction_service._mysql_read_repo_for_current_user", return_value=(repo, 12)),
            mock.patch("services.transaction_service.core.get_reconciliations_history") as core_get,
        ):
            rows = service.get_reconciliations_history(limit=5)

        self.assertEqual(rows, [{"id": 3, "difference": 0.0}])
        core_get.assert_not_called()
        repo.get_reconciliations_history.assert_called_once_with(conn, 12, limit=5)


if __name__ == "__main__":
    unittest.main()
