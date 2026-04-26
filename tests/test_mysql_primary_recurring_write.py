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


class MySqlPrimaryRecurringWriteTestCase(unittest.TestCase):
    def test_add_planned_transaction_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_planned_transaction.return_value = {"status": "inserted", "legacy_transaction_id": 91}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.add_planned_transaction") as core_add,
        ):
            result = service.add_planned_transaction(
                "expense",
                "Rent",
                1000.0,
                "May",
                "2026-05-01",
                template_id=7,
                money_source="cashless",
            )

        self.assertEqual(result, 91)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        core_add.assert_not_called()
        repo.create_planned_transaction.assert_called_once()

    def test_create_recurring_template_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_recurring_template.return_value = {"status": "inserted", "legacy_template_id": 7}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners"),
            mock.patch("services.transaction_service.core.create_recurring_template") as core_create,
        ):
            result = service.create_recurring_template(
                "expense",
                "Rent",
                1000.0,
                1,
                category_id=5,
                comment_template="May rent",
                months_ahead=6,
                working_days_only=True,
                money_source="cashless",
            )

        self.assertEqual(result, 7)
        self.assertTrue(conn.committed)
        core_create.assert_not_called()
        repo.create_recurring_template.assert_called_once()

    def test_update_recurring_template_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.update_recurring_template.return_value = {"status": "updated"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "execute_planned_transactions", return_value=0) as execute_due,
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.update_recurring_template") as core_update,
        ):
            result = service.update_recurring_template(7, day_of_month=5)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        execute_due.assert_called_once()
        notify.assert_called_once()
        core_update.assert_not_called()
        repo.update_recurring_template.assert_called_once()

    def test_delete_recurring_template_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.mirror_delete_recurring_template.return_value = {"status": "deleted"}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.delete_recurring_template") as core_delete,
        ):
            result = service.delete_recurring_template(7)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        notify.assert_called_once()
        core_delete.assert_not_called()
        repo.mirror_delete_recurring_template.assert_called_once_with(conn, 12, 7)

    def test_execute_planned_transactions_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.execute_due_planned_transactions.return_value = {"status": "executed", "count": 2}

        with (
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch.object(service, "get_default_capital_account", return_value={"id": 101}),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch("services.transaction_service.core.execute_all_planned_transactions") as core_execute,
        ):
            result = service.execute_planned_transactions()

        self.assertEqual(result, 2)
        self.assertTrue(conn.committed)
        notify.assert_called_once_with(update_all=True)
        core_execute.assert_not_called()
        repo.execute_due_planned_transactions.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            auto_percent=10,
            capital_account_id=101,
        )


if __name__ == "__main__":
    unittest.main()
