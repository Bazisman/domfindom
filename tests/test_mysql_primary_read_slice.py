import unittest

import core
from services import transaction_service as transaction_service_module


class MySqlPrimaryReadSliceTestCase(unittest.TestCase):
    def test_legacy_user_id_from_current_db_path(self):
        token = core.push_db_name("data/users/12/finance.db")
        try:
            self.assertEqual(transaction_service_module._legacy_user_id_from_current_db(), 12)
        finally:
            core.pop_db_name(token)

    def test_legacy_user_id_returns_none_for_root_db(self):
        token = core.push_db_name("finance.db")
        try:
            self.assertIsNone(transaction_service_module._legacy_user_id_from_current_db())
        finally:
            core.pop_db_name(token)


if __name__ == "__main__":
    unittest.main()
