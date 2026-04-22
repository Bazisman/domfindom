import calendar
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime

import core
from services.transaction_service import TransactionService


class FinancialLogicTestCase(unittest.TestCase):
    def setUp(self):
        self._old_db_name = core.DB_NAME
        self._old_get_connection = core.get_connection
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

        @contextmanager
        def _memory_connection():
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        core.get_connection = _memory_connection
        core._invalidate_cache()
        core.init_db()

    def tearDown(self):
        core._invalidate_cache()
        core.DB_NAME = self._old_db_name
        core.get_connection = self._old_get_connection
        self._conn.close()

    def test_execute_planned_income_applies_auto_capital(self):
        account_id = core.add_capital_account("Test Capital", balance=0)

        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions
                (type, category, amount, comment, date, created_at, status)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                ("income", "Зарплата", 1000.0, "Плановый доход", "2026-04-05", "planned"),
            )
            transaction_id = cursor.lastrowid
            conn.commit()

        result = core.execute_planned_transaction(
            transaction_id,
            auto_percent=10,
            capital_account_id=account_id,
        )
        self.assertTrue(result)

        main_balance, _, _ = core.get_balance(force_update=True)
        capital_balance = core.get_capital_balance(account_id)

        self.assertEqual(main_balance, 900.0)
        self.assertEqual(capital_balance, 100.0)

        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM transactions WHERE id = ?",
                (transaction_id,),
            )
            self.assertEqual(cursor.fetchone()["status"], "actual")

            cursor.execute(
                "SELECT amount, to_account_id, is_active FROM transfers WHERE transaction_id = ?",
                (transaction_id,),
            )
            transfer = cursor.fetchone()

        self.assertIsNotNone(transfer)
        self.assertEqual(transfer["amount"], 100.0)
        self.assertEqual(transfer["to_account_id"], account_id)
        self.assertEqual(transfer["is_active"], 1)

    def test_projected_balance_uses_budget_remaining_not_full_budget(self):
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 5000.0, "monthly")
        core.add_expense(3000.0, "Продукты", "Факт", "2026-04-05")

        forecast = core.get_projected_balance(end_date="2026-04-30")

        self.assertEqual(forecast["current_balance"], -3000.0)
        self.assertEqual(forecast["total_budgets"], 5000.0)
        self.assertEqual(forecast["current_expenses"], 3000.0)
        self.assertEqual(forecast["budget_remaining"], 2000.0)
        self.assertEqual(forecast["projected_balance"], -5000.0)

    def test_export_path_returns_all_transactions_without_ui_limit(self):
        with core.get_connection() as conn:
            cursor = conn.cursor()
            rows = [
                ("expense", "Тест", float(i + 1), f"item {i}", "2026-04-05")
                for i in range(600)
            ]
            cursor.executemany(
                """
                INSERT INTO transactions
                (type, category, amount, comment, date, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                rows,
            )
            conn.commit()

        service = TransactionService()
        exported = service.get_transactions_for_export()

        self.assertEqual(len(exported), 600)

    def test_budget_report_ignores_planned_expenses(self):
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 5000.0, "monthly")

        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions
                (type, category, amount, comment, date, created_at, status)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                ("expense", "Продукты", 2500.0, "Плановый расход", "2026-04-10", "planned"),
            )
            conn.commit()

        core.add_expense(1000.0, "Продукты", "Фактический расход", "2026-04-05")
        report = core.get_budget_report("2026-04")
        products = next(item for item in report if item["category"] == "Продукты")

        self.assertEqual(products["spent"], 1000.0)
        self.assertEqual(products["remaining"], 4000.0)

    def test_check_budget_ignores_planned_expenses(self):
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 5000.0, "monthly")

        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions
                (type, category, amount, comment, date, created_at, status)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                ("expense", "Продукты", 4500.0, "Плановый расход", "2026-04-15", "planned"),
            )
            conn.commit()

        result = core.check_budget(category_id, 1000.0, date="2026-04-05")

        self.assertIsNotNone(result)
        over, spent, budget = result
        self.assertFalse(over)
        self.assertEqual(spent, 0)
        self.assertEqual(budget, 5000.0)


    def test_update_recurring_template_preserves_category_and_regenerates_once(self):
        category = core.get_category_by_name("Зарплата")
        category_id = category["id"] if category else core.add_category("Зарплата", "income")
        template_id = core.create_recurring_template(
            template_type="income",
            name="Основная зарплата",
            amount=120000.0,
            day_of_month=1,
            category_id=category_id,
            comment_template="Зарплата",
            months_ahead=3,
            working_days_only=0,
        )

        planned_before = core.get_planned_transactions_by_template(template_id)
        self.assertGreater(len(planned_before), 0)
        self.assertTrue(all(item["category"] == "Зарплата" for item in planned_before))

        updated = core.update_recurring_template(template_id, amount=125000.0)
        self.assertTrue(updated)

        planned_after = core.get_planned_transactions_by_template(template_id)
        self.assertEqual(len(planned_after), len(planned_before))
        self.assertTrue(all(item["category"] == "Зарплата" for item in planned_after))
        self.assertTrue(all(item["amount"] == 125000.0 for item in planned_after))


    def test_update_recurring_template_executes_when_moved_to_today_or_past(self):
        today = datetime.now().date()
        last_day = calendar.monthrange(today.year, today.month)[1]
        initial_day = today.day + 1 if today.day < last_day else today.day
        target_day = today.day if initial_day != today.day else max(today.day - 1, 1)

        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        template_id = core.create_recurring_template(
            template_type="expense",
            name="Тест переноса",
            amount=500.0,
            day_of_month=initial_day,
            category_id=category_id,
            comment_template="Перенесенная операция",
            months_ahead=2,
            working_days_only=0,
        )

        service = TransactionService()
        updated = service.update_recurring_template(template_id, day_of_month=target_day)
        self.assertTrue(updated)

        today_str = today.strftime("%Y-%m-%d")
        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, date
                FROM transactions
                WHERE template_id = ?
                ORDER BY date
                """,
                (template_id,),
            )
            rows = cursor.fetchall()

        self.assertTrue(any(row["status"] == "actual" and row["date"] <= today_str for row in rows))
        self.assertFalse(any(row["status"] == "planned" and row["date"] <= today_str for row in rows))

        main_balance, _, _ = core.get_balance(force_update=True)
        self.assertEqual(main_balance, -500.0)

    def test_create_recurring_template_generates_current_day_planned_transaction(self):
        today = datetime.now().date()
        category = core.get_category_by_name("Интернет/связь")
        category_id = category["id"] if category else core.add_category("Интернет/связь", "expense")

        template_id = core.create_recurring_template(
            template_type="expense",
            name="Тест шаблона на сегодня",
            amount=449.0,
            day_of_month=today.day,
            category_id=category_id,
            comment_template="Подписка на сегодня",
            months_ahead=2,
            working_days_only=0,
        )

        planned = core.get_planned_transactions_by_template(template_id)
        today_str = today.strftime("%Y-%m-%d")

        self.assertTrue(any(item["date"] == today_str and item["status"] == "planned" for item in planned))

    def test_budget_status_uses_monthly_equivalent_for_daily_budget(self):
        days_in_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 100.0, "daily")
        core.add_expense(1000.0, "Продукты", "Факт", "2026-04-05")

        status_items = core.get_budget_status(category_id)
        products = next(item for item in status_items if item["category_id"] == category_id)

        self.assertEqual(products["budget_amount"], float(days_in_month * 100))
        self.assertEqual(products["spent"], 1000.0)
        self.assertEqual(products["remaining"], float(days_in_month * 100 - 1000))
        self.assertEqual(products["plan_remaining"], float(days_in_month * 100 - 1000))
        self.assertEqual(products["forecast_mode"], "daily_tempo")

    def test_check_budget_uses_monthly_equivalent_for_daily_budget(self):
        days_in_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 100.0, "daily")
        core.add_expense(2500.0, "Продукты", "Факт", "2026-04-05")

        result = core.check_budget(category_id, 600.0, date="2026-04-06")

        self.assertIsNotNone(result)
        over, spent, budget = result
        self.assertTrue(over)
        self.assertEqual(spent, 2500.0)
        self.assertEqual(budget, float(days_in_month * 100))

    def test_daily_budget_status_includes_forecast_remaining(self):
        today = datetime.now()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 100.0, "daily")
        core.add_expense(1000.0, "Продукты", "Факт", today.strftime("%Y-%m-05"))

        status_items = core.get_budget_status(category_id)
        products = next(item for item in status_items if item["category_id"] == category_id)
        expected_forecast_remaining = max((days_in_month * 100) - (1000 + (days_in_month - today.day) * 100), 0)

        self.assertEqual(products["forecast_remaining"], float(expected_forecast_remaining))

    def test_projected_balance_uses_daily_forecast_remaining(self):
        today = datetime.now()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 100.0, "daily")
        core.add_expense(1000.0, "Продукты", "Факт", today.strftime("%Y-%m-05"))

        forecast = core.get_projected_balance()
        expected_plan_remaining = max(days_in_month * 100 - 1000, 0)
        expected_forecast_remaining = max((days_in_month * 100) - (1000 + (days_in_month - today.day) * 100), 0)

        self.assertEqual(forecast["budget_plan_remaining"], float(expected_plan_remaining))
        self.assertEqual(forecast["budget_remaining"], float(expected_forecast_remaining))
        self.assertEqual(forecast["budget_forecast_remaining"], float(expected_forecast_remaining))

    def test_projected_balance_does_not_double_count_planned_budget_expense(self):
        today = datetime.now()
        end_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1]).strftime("%Y-%m-%d")
        category = core.get_category_by_name("Продукты")
        category_id = category["id"] if category else core.add_category("Продукты", "expense")
        core.set_budget(category_id, 5000.0, "monthly")
        core.add_expense(3000.0, "Продукты", "Факт", today.strftime("%Y-%m-05"))

        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions
                (type, category, amount, comment, date, created_at, status)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
                """,
                ("expense", "Продукты", 700.0, "План по продуктам", end_of_month, "planned"),
            )
            conn.commit()

        forecast = core.get_projected_balance(end_date=end_of_month)

        self.assertEqual(forecast["planned_expense"], 700.0)
        self.assertEqual(forecast["budget_plan_remaining"], 2000.0)
        self.assertEqual(forecast["budget_remaining"], 1300.0)
        self.assertEqual(forecast["combined_pending_expense"], 2000.0)
        self.assertEqual(forecast["projected_balance"], -5000.0)

    def test_adjust_to_workday_moves_weekend_dates(self):
        # 2026-04-11 = суббота -> перенос на понедельник
        self.assertEqual(core._adjust_to_workday("2026-04-11"), "2026-04-13")
        # 2026-04-12 = воскресенье -> перенос на понедельник
        self.assertEqual(core._adjust_to_workday("2026-04-12"), "2026-04-13")
        # Рабочий день не должен изменяться
        self.assertEqual(core._adjust_to_workday("2026-04-14"), "2026-04-14")


if __name__ == "__main__":
    unittest.main()
