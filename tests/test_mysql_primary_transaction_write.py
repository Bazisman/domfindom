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


class MySqlPrimaryTransactionWriteTestCase(unittest.TestCase):
    def test_add_income_with_capital_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_actual_transaction.return_value = {"status": "inserted", "legacy_transaction_id": 77}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.add_income_with_capital") as core_add,
        ):
            result = service.add_income_with_capital(
                1000.0,
                "Salary",
                "April",
                "2026-04-26",
                capital_percent=10,
                capital_account_id=101,
                money_source="cashless",
            )

        self.assertEqual(result, 77)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        core_add.assert_not_called()
        repo.create_actual_transaction.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            transaction_type="income",
            category="Salary",
            amount=1000.0,
            comment="April",
            date="2026-04-26",
            money_source="cashless",
            capital_percent=10,
            capital_account_id=101,
        )

    def test_add_expense_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_actual_transaction.return_value = {"status": "inserted", "legacy_transaction_id": 78}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners"),
            mock.patch("services.transaction_service.core.add_expense") as core_add,
        ):
            result = service.add_expense(250.0, "Food", "Dinner", "2026-04-26", money_source="cash")

        self.assertEqual(result, 78)
        self.assertTrue(conn.committed)
        core_add.assert_not_called()
        repo.create_actual_transaction.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            transaction_type="expense",
            category="Food",
            amount=250.0,
            comment="Dinner",
            date="2026-04-26",
            money_source="cash",
        )

    def test_update_transaction_fields_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.update_actual_transaction.return_value = {"status": "updated"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.update_transaction_fields") as core_update,
        ):
            result = service.update_transaction_fields(77, amount=1200.0, comment="May")

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        core_update.assert_not_called()
        repo.update_actual_transaction.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            legacy_transaction_id=77,
            amount=1200.0,
            comment="May",
        )

    def test_delete_transaction_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.mirror_delete_transaction.return_value = {"status": "deleted"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.delete_transaction") as core_delete,
        ):
            result = service.delete_transaction(77)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        core_delete.assert_not_called()
        repo.mirror_delete_transaction.assert_called_once_with(conn, 12, 77)


if __name__ == "__main__":
    unittest.main()
