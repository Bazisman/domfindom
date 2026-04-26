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


if __name__ == "__main__":
    unittest.main()
