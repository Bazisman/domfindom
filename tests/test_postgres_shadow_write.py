import unittest
from types import SimpleNamespace
from unittest import mock

from backend.storage import shadow_write


class _Row(dict):
    def keys(self):
        return super().keys()


class PostgresShadowWriteTestCase(unittest.TestCase):
    def test_shadow_write_disabled_without_flag_or_database_url(self):
        disabled = SimpleNamespace(postgres_shadow_write_enabled=False, database_url="")
        enabled_without_url = SimpleNamespace(postgres_shadow_write_enabled=True, database_url="")

        self.assertFalse(shadow_write.postgres_shadow_write_enabled(disabled))
        self.assertFalse(shadow_write.postgres_shadow_write_enabled(enabled_without_url))

    def test_shadow_write_skip_reason_does_not_call_repository(self):
        config = SimpleNamespace(postgres_shadow_write_enabled=True, database_url="postgresql://example")
        with mock.patch.object(shadow_write, "PostgresWriteRepository") as repository:
            result = shadow_write.mirror_created_transaction_shadow_write(
                {"id": 12},
                _Row(id=1, status="actual"),
                config=config,
                skip_reason="planned_transaction",
            )

        self.assertEqual(result, {"enabled": False, "status": "skipped", "reason": "planned_transaction"})
        repository.assert_not_called()

    def test_shadow_write_disabled_does_not_call_repository(self):
        config = SimpleNamespace(postgres_shadow_write_enabled=False, database_url="")
        with mock.patch.object(shadow_write, "PostgresWriteRepository") as repository:
            result = shadow_write.mirror_created_transaction_shadow_write(
                {"id": 12},
                _Row(id=1, status="actual"),
                config=config,
            )

        self.assertEqual(result, {"enabled": False, "status": "disabled"})
        repository.assert_not_called()

    def test_shadow_write_delete_disabled_does_not_call_repository(self):
        config = SimpleNamespace(postgres_shadow_write_enabled=False, database_url="")
        with mock.patch.object(shadow_write, "PostgresWriteRepository") as repository:
            result = shadow_write.mirror_deleted_transaction_shadow_write(
                {"id": 12},
                1,
                config=config,
            )

        self.assertEqual(result, {"enabled": False, "status": "disabled"})
        repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
