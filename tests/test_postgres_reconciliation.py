import sqlite3
import unittest

from pathlib import Path

from tools.postgres_reconciliation import (
    build_sqlite_family_summary,
    compare_dicts,
    sqlite_group_sum,
    sqlite_monthly_transaction_sum,
)


class PostgresReconciliationTestCase(unittest.TestCase):
    def test_compare_dicts_reports_only_differences(self):
        issues = compare_dicts("counts", {"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})

        self.assertEqual(
            issues,
            [
                {"section": "counts", "key": "b", "expected": 2, "actual": 3, "delta": 1},
                {"section": "counts", "key": "c", "expected": 0, "actual": 4, "delta": 4},
            ],
        )

    def test_sqlite_group_sum_defaults_missing_money_source_to_cashless(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE transactions (type TEXT, status TEXT, money_source TEXT, amount REAL)")
        conn.execute(
            "INSERT INTO transactions (type, status, money_source, amount) VALUES (?, ?, ?, ?)",
            ("expense", "actual", None, 10.25),
        )

        result = sqlite_group_sum(conn, "transactions", ("type", "status", "money_source"), "amount")

        self.assertEqual(result, {"expense|actual|cashless": 1025})

    def test_sqlite_group_sum_defaults_absent_money_source_column(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE transactions (type TEXT, status TEXT, amount REAL)")
        conn.execute(
            "INSERT INTO transactions (type, status, amount) VALUES (?, ?, ?)",
            ("expense", "actual", 10.25),
        )

        result = sqlite_group_sum(conn, "transactions", ("type", "status", "money_source"), "amount")

        self.assertEqual(result, {"expense|actual|cashless": 1025})

    def test_sqlite_monthly_transaction_sum_uses_date_month(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE transactions (type TEXT, status TEXT, money_source TEXT, date TEXT, amount REAL)"
        )
        conn.execute(
            "INSERT INTO transactions (type, status, money_source, date, amount) VALUES (?, ?, ?, ?, ?)",
            ("income", "actual", "cash", "2026-04-26", 12),
        )

        result = sqlite_monthly_transaction_sum(conn)

        self.assertEqual(result, {"income|actual|cash|2026-04": 1200})

    def test_sqlite_monthly_transaction_sum_defaults_missing_money_source(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE transactions (type TEXT, status TEXT, date TEXT, amount REAL)")
        conn.execute(
            "INSERT INTO transactions (type, status, date, amount) VALUES (?, ?, ?, ?)",
            ("expense", "actual", "2026-04-26", 7),
        )

        result = sqlite_monthly_transaction_sum(conn)

        self.assertEqual(result, {"expense|actual|cashless|2026-04": 700})

    def test_build_sqlite_family_summary_defaults_missing_auth_tables_to_zero(self):
        result = build_sqlite_family_summary(Path("missing-auth.db"))

        self.assertEqual(result["counts"]["families"], 0)
        self.assertEqual(result["counts"]["family_memberships"], 0)
        self.assertEqual(result["counts"]["family_invites"], 0)


if __name__ == "__main__":
    unittest.main()
