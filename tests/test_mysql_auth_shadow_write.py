import unittest
from types import SimpleNamespace
from unittest import mock

from backend.storage import auth_shadow_write


class _Row(dict):
    def keys(self):
        return super().keys()


class _Connection:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True


class MySqlAuthShadowWriteTestCase(unittest.TestCase):
    def test_auth_shadow_write_requires_flag_and_url(self):
        disabled = SimpleNamespace(mysql_shadow_write_enabled=False, mysql_database_url="")
        enabled_without_url = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="")
        enabled = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")

        self.assertFalse(auth_shadow_write.mysql_auth_shadow_write_enabled(disabled))
        self.assertFalse(auth_shadow_write.mysql_auth_shadow_write_enabled(enabled_without_url))
        self.assertTrue(auth_shadow_write.mysql_auth_shadow_write_enabled(enabled))

    def test_strict_auth_requires_shadow_write_flag_and_url(self):
        disabled = SimpleNamespace(
            mysql_shadow_write_enabled=False,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_auth_enabled=True,
        )
        enabled = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_auth_enabled=True,
        )

        self.assertFalse(auth_shadow_write.mysql_strict_auth_write_enabled(disabled))
        self.assertTrue(auth_shadow_write.mysql_strict_auth_write_enabled(enabled))

    def test_require_mysql_auth_shadow_write_success_raises_only_when_strict(self):
        loose = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_auth_enabled=False,
        )
        strict = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_auth_enabled=True,
        )
        failed = {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed", "reason": "boom"}}}

        auth_shadow_write.require_mysql_auth_shadow_write_success(failed, "create_user", config=loose)
        with self.assertRaisesRegex(RuntimeError, "create_user"):
            auth_shadow_write.require_mysql_auth_shadow_write_success(failed, "create_user", config=strict)

    def test_mirror_session_upserts_user_before_session(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
        )
        conn = _Connection()
        user = _Row({"id": 7, "email": "User@Example.test", "password_hash": "hash", "email_verified": 1, "is_active": 1})

        with mock.patch.object(auth_shadow_write, "MySqlAuthWriteRepository") as repository:
            repo = repository.return_value
            repo.connect.return_value.__enter__.return_value = conn
            repo.mirror_user.return_value = {"status": "upserted"}
            repo.mirror_session.return_value = {"status": "upserted"}

            result = auth_shadow_write.mirror_auth_session_shadow_write(
                user,
                token_hash="token-hash",
                expires_at="2026-04-26 12:00:00",
                ip="127.0.0.1",
                user_agent="test",
                config=config,
            )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(conn.committed)
        repo.mirror_user.assert_called_once()
        repo.mirror_session.assert_called_once()

    def test_mirror_user_delete_uses_auth_repository(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
        )
        conn = _Connection()

        with mock.patch.object(auth_shadow_write, "MySqlAuthWriteRepository") as repository:
            repo = repository.return_value
            repo.connect.return_value.__enter__.return_value = conn
            repo.delete_user.return_value = {"status": "deleted", "affected": 1}

            result = auth_shadow_write.mirror_auth_user_delete_shadow_write(9, config=config)

        self.assertEqual(result["status"], "ok")
        repo.delete_user.assert_called_once_with(conn, 9)


if __name__ == "__main__":
    unittest.main()
