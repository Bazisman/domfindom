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

    def test_legacy_account_id_prefers_stored_legacy_values(self):
        repo = PostgresWriteRepository("postgresql://example")

        self.assertEqual(
            repo._legacy_account_id_from_transfer_row(
                {
                    "to_account_kind": "daily",
                    "legacy_to_account_id": 2,
                    "to_daily_account_id": 10,
                    "to_capital_account_id": None,
                    "to_daily_legacy_local_id": 2,
                    "to_capital_legacy_local_id": None,
                },
                "to",
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
