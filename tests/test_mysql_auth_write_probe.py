import unittest
from unittest import mock

from tools import mysql_auth_write_probe


class _Connection:
    def __init__(self):
        self.rollback_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def rollback(self):
        self.rollback_called = True


class MySqlAuthWriteProbeTestCase(unittest.TestCase):
    def test_probe_rolls_back_after_successful_auth_adapter_calls(self):
        conn = _Connection()
        with mock.patch.object(mysql_auth_write_probe, "MySqlAuthWriteRepository") as repository:
            repo = repository.return_value
            repo.connect.return_value.__enter__.return_value = conn
            repo.mirror_user.return_value = {"status": "upserted"}
            repo.mirror_session.return_value = {"status": "upserted"}
            repo.mirror_user_preferences.return_value = {"status": "upserted"}
            repo.mirror_login_attempt.return_value = {"status": "inserted"}
            repo.mirror_auth_event.return_value = {"status": "inserted"}
            repo.mirror_token.return_value = {"status": "upserted"}

            report = mysql_auth_write_probe.run_probe("mysql+pymysql://example/db")

        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["rolled_back"])
        self.assertTrue(conn.rollback_called)
        repo.mirror_user.assert_called_once()
        repo.mirror_session.assert_called_once()
        repo.mirror_user_preferences.assert_called_once()
        repo.mirror_login_attempt.assert_called_once()
        repo.mirror_auth_event.assert_called_once()
        self.assertEqual(repo.mirror_token.call_count, 3)


if __name__ == "__main__":
    unittest.main()
