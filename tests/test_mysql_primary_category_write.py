import unittest
from unittest import mock

from services.category_service import CategoryService


class _Connection:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True


class MySqlPrimaryCategoryWriteTestCase(unittest.TestCase):
    def test_add_category_uses_mysql_primary_write_repo_when_enabled(self):
        service = CategoryService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.create_category.return_value = {"status": "inserted", "legacy_category_id": 77}

        with mock.patch(
            "services.category_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            category_id = service.add_category("Travel", "expense", color="#123456", icon="plane")

        self.assertEqual(category_id, 77)
        self.assertTrue(conn.committed)
        repo.create_category.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            name="Travel",
            category_type="expense",
            color="#123456",
            icon="plane",
        )

    def test_update_category_uses_mysql_primary_write_repo_when_enabled(self):
        service = CategoryService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.update_category.return_value = {"status": "updated", "category_id": 501}

        with mock.patch(
            "services.category_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            updated = service.update_category(77, name="Trips")

        self.assertTrue(updated)
        self.assertTrue(conn.committed)
        repo.update_category.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_category_id=77,
            name="Trips",
        )

    def test_delete_category_uses_mysql_primary_write_repo_when_enabled(self):
        service = CategoryService()
        conn = _Connection()
        repo = mock.MagicMock()
        repo.connect.return_value.__enter__.return_value = conn
        repo.delete_category.return_value = {"status": "updated", "category_id": 501}

        with mock.patch(
            "services.category_service._mysql_write_repo_for_current_user",
            return_value=(repo, 12, "data/users/12/finance.db"),
        ):
            deleted = service.delete_category(77)

        self.assertTrue(deleted)
        self.assertTrue(conn.committed)
        repo.delete_category.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_category_id=77,
        )


if __name__ == "__main__":
    unittest.main()
