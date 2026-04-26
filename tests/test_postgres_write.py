import unittest

from backend.storage.postgres_write import PostgresWriteRepository


class PostgresWriteRepositoryTestCase(unittest.TestCase):
    def test_daily_account_refs_are_classified(self):
        repo = PostgresWriteRepository("postgresql://example")

        self.assertEqual(
            repo._account_ref(1),
            {"kind": "daily", "daily_legacy_id": 1, "capital_legacy_id": None},
        )
        self.assertEqual(
            repo._account_ref(2),
            {"kind": "daily", "daily_legacy_id": 2, "capital_legacy_id": None},
        )

    def test_capital_account_refs_are_classified(self):
        repo = PostgresWriteRepository("postgresql://example")

        self.assertEqual(
            repo._account_ref(100),
            {"kind": "capital", "daily_legacy_id": None, "capital_legacy_id": 100},
        )


if __name__ == "__main__":
    unittest.main()
