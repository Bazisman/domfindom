import unittest
from pathlib import Path

from tools.sqlite_family_preflight import validate_auth


class SqliteFamilyPreflightTestCase(unittest.TestCase):
    def test_missing_auth_db_is_reported(self):
        report = validate_auth(Path("missing-root"), "auth.db", "data/users")

        self.assertEqual(report["issues"][0]["code"], "missing_auth_db")
        self.assertEqual(report["warnings"], [])

if __name__ == "__main__":
    unittest.main()
