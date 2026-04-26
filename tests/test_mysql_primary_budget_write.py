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


class MySqlPrimaryBudgetWriteTestCase(unittest.TestCase):
    def test_set_budget_uses_mysql_primary_write_repo_when_enabled(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.set_budget.return_value = {"status": "inserted", "legacy_budget_id": 88}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.set_budget(77, 1234.56, "monthly")

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.set_budget.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            legacy_category_id=77,
            amount=1234.56,
            period="monthly",
        )

    def test_delete_budget_uses_mysql_primary_write_repo_when_enabled(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.delete_budget.return_value = {"status": "deleted", "budget_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.delete_budget(88)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.delete_budget.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_budget_id=88,
        )


if __name__ == "__main__":
    unittest.main()
