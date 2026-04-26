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


class MySqlPrimaryReconciliationWriteTestCase(unittest.TestCase):
    def test_add_reconciliation_source_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_reconciliation_source.return_value = {"status": "inserted", "legacy_source_id": 44}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            source_id = service.add_reconciliation_source("Bank", 123.45)

        self.assertEqual(source_id, 44)
        self.assertTrue(conn.committed)
        repo.create_reconciliation_source.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            name="Bank",
            balance=123.45,
        )

    def test_update_reconciliation_source_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.update_reconciliation_source.return_value = {"status": "updated", "source_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.update_reconciliation_source(44, balance=222.0)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.update_reconciliation_source.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_source_id=44,
            balance=222.0,
        )

    def test_delete_reconciliation_source_uses_mysql_primary_write_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.delete_reconciliation_source.return_value = {"status": "updated", "source_id": 501}

        with mock.patch(
            "services.transaction_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            result = service.delete_reconciliation_source(44)

        self.assertTrue(result)
        self.assertTrue(conn.committed)
        repo.delete_reconciliation_source.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_source_id=44,
        )

    def test_get_reconciliation_sources_uses_mysql_read_repo(self):
        service = TransactionService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.get_reconciliation_sources.return_value = [{"id": 44, "name": "Bank"}]

        with mock.patch(
            "services.transaction_service._mysql_read_repo_for_current_user",
            return_value=(repo, 12),
        ):
            sources = service.get_reconciliation_sources()

        self.assertEqual(sources, [{"id": 44, "name": "Bank"}])
        repo.get_reconciliation_sources.assert_called_once_with(conn, 12)


if __name__ == "__main__":
    unittest.main()
