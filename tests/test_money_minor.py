import unittest
from decimal import Decimal

from tools.money_minor import MoneyConversionError, from_minor, from_minor_float, to_minor


class MoneyMinorTestCase(unittest.TestCase):
    def test_to_minor_converts_rubles_to_kopecks(self):
        self.assertEqual(to_minor("1000.50"), 100050)
        self.assertEqual(to_minor(1000), 100000)
        self.assertEqual(to_minor(1000.5), 100050)

    def test_to_minor_rounds_half_up_to_kopecks(self):
        self.assertEqual(to_minor("10.004"), 1000)
        self.assertEqual(to_minor("10.005"), 1001)
        self.assertEqual(to_minor("10.995"), 1100)

    def test_to_minor_keeps_sign_for_migration_values(self):
        self.assertEqual(to_minor("-1.23"), -123)

    def test_from_minor_returns_decimal_major_units(self):
        self.assertEqual(from_minor(100050), Decimal("1000.50"))
        self.assertEqual(from_minor(-123), Decimal("-1.23"))

    def test_from_minor_float_is_boundary_adapter(self):
        self.assertEqual(from_minor_float(100050), 1000.5)

    def test_rejects_invalid_values(self):
        for value in ("", "abc", True):
            with self.subTest(value=value):
                with self.assertRaises(MoneyConversionError):
                    to_minor(value)

        with self.assertRaises(MoneyConversionError):
            from_minor(True)

    def test_rejects_unknown_currency(self):
        with self.assertRaises(MoneyConversionError):
            to_minor("1.00", currency="USD")


if __name__ == "__main__":
    unittest.main()
