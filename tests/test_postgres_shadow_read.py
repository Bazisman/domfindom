import unittest
from types import SimpleNamespace
from unittest import mock

from backend.storage import shadow_read


class _Balance:
    main_balance = 100.0
    income = 50.0
    expense = 25.0


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Repository:
    def __init__(self, database_url):
        self.database_url = database_url

    def connect(self):
        return _Connection()

    def get_balance(self, conn, legacy_user_id):
        return {"main_balance": 100.0, "income": 50.0, "expense": 25.0}

    def get_monthly_stats(self, conn, legacy_user_id, year, month):
        return {"income": 10.0, "expense": 5.0, "capital": 2.0, "year": year, "month": month}


class PostgresShadowReadTestCase(unittest.TestCase):
    def test_shadow_read_disabled_without_flag_or_database_url(self):
        disabled = SimpleNamespace(postgres_read_shadow_enabled=False, database_url="")
        enabled_without_url = SimpleNamespace(postgres_read_shadow_enabled=True, database_url="")

        self.assertFalse(shadow_read.postgres_shadow_read_enabled(disabled))
        self.assertFalse(shadow_read.postgres_shadow_read_enabled(enabled_without_url))

    def test_dashboard_compare_returns_disabled_without_postgres_import(self):
        config = SimpleNamespace(postgres_read_shadow_enabled=False, database_url="")
        with mock.patch.object(shadow_read, "PostgresReadRepository") as repository:
            result = shadow_read.compare_dashboard_shadow_read(
                {"id": 1},
                _Balance(),
                {"income": 10.0, "expense": 5.0, "capital": 2.0},
                2026,
                4,
                config=config,
            )

        self.assertEqual(result, {"enabled": False, "issues": []})
        repository.assert_not_called()

    def test_dashboard_compare_reports_match(self):
        config = SimpleNamespace(postgres_read_shadow_enabled=True, database_url="postgresql://example")
        with mock.patch.object(shadow_read, "PostgresReadRepository", _Repository):
            result = shadow_read.compare_dashboard_shadow_read(
                {"id": 1},
                _Balance(),
                {"income": 10.0, "expense": 5.0, "capital": 2.0},
                2026,
                4,
                config=config,
            )

        self.assertEqual(result, {"enabled": True, "issues": []})

    def test_dashboard_compare_reports_mismatch(self):
        config = SimpleNamespace(postgres_read_shadow_enabled=True, database_url="postgresql://example")
        with mock.patch.object(shadow_read, "PostgresReadRepository", _Repository):
            result = shadow_read.compare_dashboard_shadow_read(
                {"id": 1},
                _Balance(),
                {"income": 10.0, "expense": 6.0, "capital": 2.0},
                2026,
                4,
                config=config,
            )

        self.assertEqual(result["enabled"], True)
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(result["issues"][0]["section"], "monthly_stats")
        self.assertEqual(result["issues"][0]["field"], "expense")


if __name__ == "__main__":
    unittest.main()
