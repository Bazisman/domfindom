import unittest

from tools.postgres_read_compare import compare_values, from_minor


class PostgresReadCompareTestCase(unittest.TestCase):
    def test_from_minor_returns_float_rubles(self):
        self.assertEqual(from_minor(12345), 123.45)

    def test_compare_values_reports_difference(self):
        issues = compare_values("balance", {"a": 1}, {"a": 2})
        self.assertEqual(issues[0]["section"], "balance")
        self.assertEqual(issues[0]["expected"], {"a": 1})
        self.assertEqual(issues[0]["actual"], {"a": 2})

    def test_compare_values_ignores_equal_values(self):
        self.assertEqual(compare_values("balance", {"a": 1}, {"a": 1}), [])


if __name__ == "__main__":
    unittest.main()
