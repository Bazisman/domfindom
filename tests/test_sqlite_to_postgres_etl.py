import unittest

from pathlib import Path

from tools.sqlite_to_postgres_etl import classify_transfer_account, finance_user_hint, normalize_psycopg_url


class SqliteToPostgresEtlTestCase(unittest.TestCase):
    def test_classify_transfer_account_daily(self):
        result = classify_transfer_account(1, daily_ids={1, 2}, capital_ids={100})
        self.assertEqual(result["kind"], "daily")
        self.assertIsNone(result["issue"])

    def test_classify_transfer_account_capital(self):
        result = classify_transfer_account(100, daily_ids={1, 2}, capital_ids={100})
        self.assertEqual(result["kind"], "capital")
        self.assertIsNone(result["issue"])

    def test_classify_transfer_account_missing(self):
        result = classify_transfer_account(404, daily_ids={1, 2}, capital_ids={100})
        self.assertIsNone(result["kind"])
        self.assertEqual(result["issue"], "missing")

    def test_classify_transfer_account_ambiguous(self):
        result = classify_transfer_account(1, daily_ids={1, 2}, capital_ids={1, 100})
        self.assertIsNone(result["kind"])
        self.assertEqual(result["issue"], "ambiguous")

    def test_finance_user_hint_for_legacy_root(self):
        legacy_id, email = finance_user_hint(Path("finance.db"), "legacy_root_finance", Path("."), "data/users")
        self.assertEqual(legacy_id, 0)
        self.assertEqual(email, "legacy-root@local.invalid")

    def test_normalize_psycopg_url_accepts_sqlalchemy_driver_name(self):
        self.assertEqual(
            normalize_psycopg_url("postgresql+psycopg://user:pass@localhost/db"),
            "postgresql://user:pass@localhost/db",
        )


if __name__ == "__main__":
    unittest.main()
