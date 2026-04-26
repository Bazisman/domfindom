import unittest
from unittest import mock

from services.transaction_service import TransactionService


class _Connection:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class MySqlPrimaryTransferWriteTestCase(unittest.TestCase):
    def test_transfer_money_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_standalone_transfer.return_value = {"status": "inserted", "legacy_transfer_id": 55}

        with (
            mock.patch.object(service, "get_account_balance", return_value=1000.0),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
            mock.patch("services.transaction_service.core.update_account_balance") as update_balance,
            mock.patch("services.transaction_service.core.add_transfer_record") as add_transfer_record,
        ):
            result = service.transfer_money(1, 100, 250.0, date="2026-04-26", comment="Reserve")

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        notify.assert_called_once()
        update_balance.assert_not_called()
        add_transfer_record.assert_not_called()
        repo.create_standalone_transfer.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            from_account_id=1,
            to_account_id=100,
            amount=250.0,
            date="2026-04-26",
            comment="Reserve",
        )

    def test_transfer_money_rolls_back_when_mysql_repo_rejects(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_standalone_transfer.return_value = {"status": "insufficient_funds"}

        with (
            mock.patch.object(service, "get_account_balance", return_value=1000.0),
            mock.patch.object(service, "notify_listeners") as notify,
            mock.patch(
                "services.transaction_service._mysql_write_repo_for_current_user",
                return_value=(repo, 12, "data/users/12/finance.db"),
            ),
        ):
            result = service.transfer_money(1, 100, 250.0, date="2026-04-26", comment="Reserve")

        self.assertFalse(result)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
