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


class MySqlPrimaryCapitalAccountWriteTestCase(unittest.TestCase):
    def test_add_capital_account_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_capital_account.return_value = {"status": "inserted", "legacy_account_id": 101}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            account_id = service.add_capital_account("Reserve", 1000.0, "safe", "#abcdef")

        self.assertEqual(account_id, 101)
        self.assertTrue(conn.committed)
        repo.create_capital_account.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            name="Reserve",
            balance=1000.0,
            icon="safe",
            color="#abcdef",
        )

    def test_update_capital_account_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.update_capital_account.return_value = {"status": "updated", "account_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.update_capital_account(101, name="Reserve 2")

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.update_capital_account.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_account_id=101,
            name="Reserve 2",
        )

    def test_set_default_capital_account_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.set_default_capital_account.return_value = {"status": "updated", "account_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.set_default_capital_account(101)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.set_default_capital_account.assert_called_once_with(conn, 12, 101)

    def test_delete_capital_account_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.delete_capital_account.return_value = {"status": "updated", "account_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.delete_capital_account(101)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.delete_capital_account.assert_called_once_with(conn, 12, 101)


if __name__ == "__main__":
    unittest.main()
