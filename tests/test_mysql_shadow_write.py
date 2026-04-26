import unittest
from types import SimpleNamespace
from unittest import mock

from backend.storage import shadow_write


class _Row(dict):
    def keys(self):
        return super().keys()


class MySqlShadowWriteTestCase(unittest.TestCase):
    def test_shadow_write_disabled_without_flag_or_database_url(self):
        disabled = SimpleNamespace(mysql_shadow_write_enabled=False, mysql_database_url="")
        enabled_without_url = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="")

        self.assertFalse(shadow_write.mysql_shadow_write_enabled(disabled))
        self.assertFalse(shadow_write.mysql_shadow_write_enabled(enabled_without_url))

    def test_strict_categories_budgets_recurring_requires_shadow_write_flag_and_url(self):
        disabled = SimpleNamespace(
            mysql_shadow_write_enabled=False,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_categories_budgets_recurring_enabled=True,
        )
        enabled = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_categories_budgets_recurring_enabled=True,
        )

        self.assertFalse(shadow_write.mysql_strict_categories_budgets_recurring_enabled(disabled))
        self.assertTrue(shadow_write.mysql_strict_categories_budgets_recurring_enabled(enabled))

    def test_strict_transactions_requires_shadow_write_flag_and_url(self):
        disabled = SimpleNamespace(
            mysql_shadow_write_enabled=False,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_transactions_enabled=True,
        )
        enabled = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_transactions_enabled=True,
        )

        self.assertFalse(shadow_write.mysql_strict_transactions_enabled(disabled))
        self.assertTrue(shadow_write.mysql_strict_transactions_enabled(enabled))

    def test_strict_accounts_capital_requires_shadow_write_flag_and_url(self):
        disabled = SimpleNamespace(
            mysql_shadow_write_enabled=False,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_accounts_capital_enabled=True,
        )
        enabled = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_accounts_capital_enabled=True,
        )

        self.assertFalse(shadow_write.mysql_strict_accounts_capital_enabled(disabled))
        self.assertTrue(shadow_write.mysql_strict_accounts_capital_enabled(enabled))

    def test_strict_reconciliation_requires_shadow_write_flag_and_url(self):
        disabled = SimpleNamespace(
            mysql_shadow_write_enabled=False,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_reconciliation_enabled=True,
        )
        enabled = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_reconciliation_enabled=True,
        )

        self.assertFalse(shadow_write.mysql_strict_reconciliation_enabled(disabled))
        self.assertTrue(shadow_write.mysql_strict_reconciliation_enabled(enabled))

    def test_require_mysql_shadow_write_success_is_noop_when_strict_flag_is_off(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_categories_budgets_recurring_enabled=False,
        )

        shadow_write.require_mysql_shadow_write_success(
            {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed"}}},
            "category_create",
            config=config,
        )

    def test_require_mysql_shadow_write_success_accepts_mysql_ok_when_strict_flag_is_on(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_categories_budgets_recurring_enabled=True,
        )

        shadow_write.require_mysql_shadow_write_success(
            {"enabled": True, "status": "ok", "results": {"mysql": {"status": "ok"}}},
            "category_create",
            config=config,
        )

    def test_require_mysql_shadow_write_success_raises_on_mysql_failure_when_strict_flag_is_on(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_categories_budgets_recurring_enabled=True,
        )

        with self.assertRaisesRegex(RuntimeError, "category_create"):
            shadow_write.require_mysql_shadow_write_success(
                {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed", "reason": "boom"}}},
                "category_create",
                config=config,
            )

    def test_require_mysql_transaction_shadow_write_success_raises_on_failure_when_strict_flag_is_on(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_transactions_enabled=True,
        )

        with self.assertRaisesRegex(RuntimeError, "transaction_create"):
            shadow_write.require_mysql_transaction_shadow_write_success(
                {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed", "reason": "boom"}}},
                "transaction_create",
                config=config,
            )

    def test_transaction_shadow_write_is_mysql_noop_when_mysql_is_runtime_primary(self):
        config = SimpleNamespace(
            storage_backend="mysql",
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
        )
        row = _Row(
            id=11,
            type="income",
            category="Salary",
            amount=1000.0,
            comment="April",
            date="2026-04-26",
            money_source="cashless",
            status="actual",
        )

        with mock.patch("backend.storage.shadow_write.MySqlWriteRepository") as repo_cls:
            result = shadow_write.mirror_created_transaction_shadow_write({"id": 12}, row, config=config)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"]["mysql"]["result"]["status"], "primary_runtime")
        repo_cls.assert_not_called()

    def test_require_mysql_accounts_capital_shadow_write_success_raises_on_failure_when_strict_flag_is_on(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_accounts_capital_enabled=True,
        )

        with self.assertRaisesRegex(RuntimeError, "transfer_create"):
            shadow_write.require_mysql_accounts_capital_shadow_write_success(
                {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed", "reason": "boom"}}},
                "transfer_create",
                config=config,
            )

    def test_require_mysql_reconciliation_shadow_write_success_raises_on_failure_when_strict_flag_is_on(self):
        config = SimpleNamespace(
            mysql_shadow_write_enabled=True,
            mysql_database_url="mysql+pymysql://example/db",
            mysql_strict_write_reconciliation_enabled=True,
        )

        with self.assertRaisesRegex(RuntimeError, "reconciliation_apply"):
            shadow_write.require_mysql_reconciliation_shadow_write_success(
                {"enabled": True, "status": "failed", "results": {"mysql": {"status": "failed", "reason": "boom"}}},
                "reconciliation_apply",
                config=config,
            )

    def test_category_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        category = _Row(id=7, name="Fuel", type="expense", color="#333333", icon="car", is_active=1)
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_category.return_value = {"status": "inserted", "category_id": 44}

            result = shadow_write.mirror_category_shadow_write({"id": 12}, category, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_category.assert_called_once_with(
            conn,
            12,
            "data/users/12/finance.db",
            dict(category),
        )
        conn.commit.assert_called_once_with()

    def test_budget_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        budget = _Row(id=9, category_id=7, amount=1250.0, period="monthly")
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_budget.return_value = {"status": "inserted", "budget_id": 55}

            result = shadow_write.mirror_budget_shadow_write({"id": 12}, budget, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_budget.assert_called_once_with(
            conn,
            12,
            "data/users/12/finance.db",
            dict(budget),
        )
        conn.commit.assert_called_once_with()

    def test_deleted_budget_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_delete_budget.return_value = {"status": "deleted", "budget_id": 55}

            result = shadow_write.mirror_deleted_budget_shadow_write({"id": 12}, 9, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_delete_budget.assert_called_once_with(conn, 12, 9)
        conn.commit.assert_called_once_with()

    def test_recurring_template_shadow_write_calls_mysql_repository_and_planned_rows(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        template = _Row(id=3, type="expense", name="Rent", category_id=7, amount=30000.0)
        planned = [{"id": 30, "status": "planned", "template_id": 3}]
        with (
            mock.patch.object(shadow_write, "_planned_transactions_for_template", return_value=planned),
            mock.patch.object(shadow_write, "MySqlWriteRepository") as repository,
        ):
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_recurring_template.return_value = {"status": "inserted", "template_id": 88}
            repo.delete_planned_transactions_for_template.return_value = {"status": "deleted", "deleted": 1}
            repo.mirror_planned_transaction.return_value = {"status": "inserted", "transaction_id": 99}

            result = shadow_write.mirror_recurring_template_shadow_write({"id": 12}, template, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_recurring_template.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            template=dict(template),
        )
        repo.delete_planned_transactions_for_template.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_template_id=3,
        )
        repo.mirror_planned_transaction.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            transaction=planned[0],
        )
        conn.commit.assert_called_once_with()

    def test_deleted_recurring_template_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_delete_recurring_template.return_value = {"status": "deleted", "template_id": 88}

            result = shadow_write.mirror_deleted_recurring_template_shadow_write({"id": 12}, 3, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_delete_recurring_template.assert_called_once_with(
            conn,
            legacy_user_id=12,
            legacy_template_id=3,
        )
        conn.commit.assert_called_once_with()

    def test_capital_accounts_shadow_write_calls_mysql_repository_for_each_account(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        accounts = [_Row(id=100, name="Reserve", balance=1000.0, is_active=1)]
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_capital_account.return_value = {"status": "inserted", "account_id": 77}

            result = shadow_write.mirror_capital_accounts_shadow_write({"id": 12}, accounts, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_capital_account.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            account=dict(accounts[0]),
        )
        conn.commit.assert_called_once_with()

    def test_transfer_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        transfer = _Row(id=11, from_account_id=1, to_account_id=100, amount=500.0, date="2026-04-26", comment="")
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_standalone_transfer.return_value = {"status": "inserted", "transfer_id": 88}

            result = shadow_write.mirror_transfer_shadow_write({"id": 12}, transfer, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_standalone_transfer.assert_called_once_with(
            conn,
            legacy_user_id=12,
            source_db_path="data/users/12/finance.db",
            transfer=dict(transfer),
        )
        conn.commit.assert_called_once_with()

    def test_reconciliation_source_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        source = _Row(id=5, name="Wallet", balance=1000.0, is_active=1)
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_reconciliation_source.return_value = {"status": "inserted", "source_id": 66}

            result = shadow_write.mirror_reconciliation_source_shadow_write({"id": 12}, source, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_reconciliation_source.assert_called_once_with(
            conn,
            12,
            "data/users/12/finance.db",
            dict(source),
        )
        conn.commit.assert_called_once_with()

    def test_reconciliation_shadow_write_calls_mysql_repository(self):
        config = SimpleNamespace(mysql_shadow_write_enabled=True, mysql_database_url="mysql+pymysql://example/db")
        reconciliation = _Row(id=6, real_balance=1000.0, program_balance=900.0, difference=100.0)
        with mock.patch.object(shadow_write, "MySqlWriteRepository") as repository:
            repo = repository.return_value
            conn = repo.connect.return_value.__enter__.return_value
            repo.mirror_reconciliation.return_value = {"status": "inserted", "reconciliation_id": 67}

            result = shadow_write.mirror_reconciliation_shadow_write({"id": 12}, reconciliation, config=config)

        self.assertEqual(result["status"], "ok")
        repo.mirror_reconciliation.assert_called_once_with(
            conn,
            12,
            "data/users/12/finance.db",
            dict(reconciliation),
        )
        conn.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
