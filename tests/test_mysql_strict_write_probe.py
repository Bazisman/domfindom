import unittest
from unittest import mock

from tools import mysql_strict_write_probe


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return {"legacy_sqlite_user_id": 12}


class _Connection:
    def __init__(self):
        self.rollback_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _Cursor()

    def rollback(self):
        self.rollback_called = True


class MySqlStrictWriteProbeTestCase(unittest.TestCase):
    def test_probe_rolls_back_after_successful_adapter_calls(self):
        conn = _Connection()
        with mock.patch.object(mysql_strict_write_probe, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            repo.connect.return_value.__enter__.return_value = conn
            repo.mirror_category.return_value = {"status": "inserted"}
            repo.mirror_budget.return_value = {"status": "inserted"}
            repo.mirror_recurring_template.return_value = {"status": "inserted"}
            repo.mirror_planned_transaction.return_value = {"status": "inserted"}
            repo.mirror_actual_transaction.return_value = {"status": "inserted"}
            repo.mirror_update_transaction.return_value = {"status": "updated"}
            repo.mirror_delete_transaction.return_value = {"status": "deleted"}
            repo.mirror_delete_budget.return_value = {"status": "deleted"}
            repo.mirror_delete_recurring_template.return_value = {"status": "deleted"}

            report = mysql_strict_write_probe.run_probe("mysql+pymysql://example/db")

        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["rolled_back"])
        self.assertTrue(conn.rollback_called)
        repo.mirror_category.assert_called_once()
        repo.mirror_budget.assert_called_once()
        repo.mirror_recurring_template.assert_called_once()
        repo.mirror_planned_transaction.assert_called_once()
        repo.mirror_actual_transaction.assert_called_once()
        repo.mirror_update_transaction.assert_called_once()
        repo.mirror_delete_transaction.assert_called_once()


if __name__ == "__main__":
    unittest.main()
