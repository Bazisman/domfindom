import sqlite3
import unittest
from contextlib import contextmanager
import calendar
from datetime import datetime, timedelta

import core
from fastapi.testclient import TestClient

from backend.main import app


class WebApiTestCase(unittest.TestCase):
    def setUp(self):
        self._old_db_name = core.DB_NAME
        self._old_get_connection = core.get_connection
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
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
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        core._invalidate_cache()
        core.DB_NAME = self._old_db_name
        core.get_connection = self._old_get_connection
        self._conn.close()

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_dashboard_endpoint_returns_core_sections(self):
        response = self.client.get("/api/v1/dashboard")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("balance", payload)
        self.assertIn("forecast", payload)
        self.assertIn("recent_transactions", payload)
        self.assertIn("budget_highlights", payload)

    def test_dashboard_recent_transactions_exclude_planned_items(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]

        created_actual = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 1200.0,
                "comment": "Actual for dashboard",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(created_actual.status_code, 201)

        template_id = core.create_recurring_template(
            template_type="income",
            name="Future Salary",
            amount=99999.0,
            day_of_month=1,
            category_id=core.get_category_by_name(income_category)["id"],
            comment_template="Planned salary",
            months_ahead=2,
            working_days_only=True,
        )
        self.assertIsNotNone(template_id)

        response = self.client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200)
        recent_transactions = response.json()["recent_transactions"]

        self.assertTrue(any(item["comment"] == "Actual for dashboard" for item in recent_transactions))
        self.assertTrue(all(item["status"] != "planned" for item in recent_transactions))

    def test_dashboard_auto_executes_overdue_planned_transactions(self):
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        due_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("income", income_category, 1500.0, "Auto due income", due_date, "planned", 501),
            )

        dashboard_response = self.client.get("/api/v1/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)

        transactions_response = self.client.get("/api/v1/transactions?period=all")
        self.assertEqual(transactions_response.status_code, 200)
        transactions = transactions_response.json()

        self.assertTrue(
            any(item["comment"] == "Auto due income" and item["status"] == "actual" for item in transactions)
        )

    def test_dashboard_balance_income_and_expense_use_current_month_only(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        now = datetime.now()
        current_month_date = now.strftime("%Y-%m-08")
        previous_month_date = f"{now.year - 1}-12-08" if now.month == 1 else f"{now.year}-{now.month - 1:02d}-08"

        current_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 10000.0,
                "comment": "Current month income",
                "date": current_month_date,
            },
        )
        self.assertEqual(current_income.status_code, 201)

        current_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 2500.0,
                "comment": "Current month expense",
                "date": current_month_date,
            },
        )
        self.assertEqual(current_expense.status_code, 201)

        previous_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 99000.0,
                "comment": "Previous month expense",
                "date": previous_month_date,
            },
        )
        self.assertEqual(previous_expense.status_code, 201)

        response = self.client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["balance"]["income"], 10000.0)
        self.assertEqual(payload["balance"]["expense"], 2500.0)

    def test_dashboard_balance_income_and_expense_exclude_next_month_boundary(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        now = datetime.now()
        current_month_date = now.strftime("%Y-%m-08")
        if now.month == 12:
            next_month_date = f"{now.year + 1}-01-01"
        else:
            next_month_date = f"{now.year}-{now.month + 1:02d}-01"

        current_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 10000.0,
                "comment": "Current month income",
                "date": current_month_date,
            },
        )
        self.assertEqual(current_income.status_code, 201)

        next_month_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 5000.0,
                "comment": "Next month income",
                "date": next_month_date,
            },
        )
        self.assertEqual(next_month_income.status_code, 201)

        next_month_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 1500.0,
                "comment": "Next month expense",
                "date": next_month_date,
            },
        )
        self.assertEqual(next_month_expense.status_code, 201)

        response = self.client.get("/api/v1/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["balance"]["income"], 10000.0)
        self.assertEqual(payload["balance"]["expense"], 0.0)

    def test_categories_endpoint_returns_seed_categories(self):
        response = self.client.get("/api/v1/categories")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(payload), 0)
        self.assertIn("name", payload[0])
        self.assertIn("type", payload[0])

    def test_category_crud_via_api(self):
        created = self.client.post(
            "/api/v1/categories",
            json={
                "name": "Web Category",
                "type": "expense",
                "color": "#112233",
                "icon": "web",
            },
        )
        self.assertEqual(created.status_code, 201)
        category_id = created.json()["id"]

        fetched = self.client.get(f"/api/v1/categories/{category_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["name"], "Web Category")

        updated = self.client.patch(
            f"/api/v1/categories/{category_id}",
            json={
                "name": "Web Category Updated",
                "color": "#445566",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Web Category Updated")
        self.assertEqual(updated.json()["color"], "#445566")

        deleted = self.client.delete(f"/api/v1/categories/{category_id}")
        self.assertEqual(deleted.status_code, 200)

        inactive_list = self.client.get("/api/v1/categories?include_inactive=true")
        self.assertEqual(inactive_list.status_code, 200)
        restored = next(item for item in inactive_list.json() if item["id"] == category_id)
        self.assertFalse(restored["is_active"])

    def test_create_and_delete_expense_transaction_via_api(self):
        response = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": "Продукты",
                "amount": 1234.0,
                "comment": "API test",
                "date": "2026-04-08",
            },
        )

        self.assertEqual(response.status_code, 201)
        created = response.json()
        transaction_id = created["id"]
        self.assertEqual(created["transaction"]["category"], "Продукты")
        self.assertEqual(created["transaction"]["amount"], 1234.0)

        transactions = self.client.get("/api/v1/transactions?limit=20")
        self.assertEqual(transactions.status_code, 200)
        items = transactions.json()
        self.assertTrue(any(item["id"] == transaction_id for item in items))

        deleted = self.client.delete(f"/api/v1/transactions/{transaction_id}")
        self.assertEqual(deleted.status_code, 200)

    def test_create_transaction_with_recurring_creates_template(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]

        response = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_id": expense_category["id"],
                "amount": 2100.0,
                "comment": "Интернет дома",
                "date": "2026-04-12",
                "recurring": {
                    "enabled": True,
                    "template_name": "Домашний интернет",
                    "day_of_month": 12,
                    "months_ahead": 6,
                    "working_days_only": True,
                },
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["transaction"]["status"], "planned")

        templates = self.client.get("/api/v1/recurring-templates")
        self.assertEqual(templates.status_code, 200)
        self.assertTrue(any(item["name"] == "Домашний интернет" for item in templates.json()))

    def test_create_transaction_with_recurring_skips_same_month_planned_duplicate(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]
        now = datetime.now()
        if now.month == 12:
            target_year = now.year + 1
            target_month = 1
        else:
            target_year = now.year
            target_month = now.month + 1
        target_day = min(15, calendar.monthrange(target_year, target_month)[1])
        target_date = f"{target_year}-{target_month:02d}-{target_day:02d}"
        target_month_prefix = target_date[:7]

        response = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_id": expense_category["id"],
                "amount": 2100.0,
                "comment": "Интернет дома",
                "date": target_date,
                "recurring": {
                    "enabled": True,
                    "template_name": "Домашний интернет без дубля",
                    "day_of_month": target_day,
                    "months_ahead": 6,
                    "working_days_only": True,
                },
            },
        )

        self.assertEqual(response.status_code, 201)

        templates = self.client.get("/api/v1/recurring-templates")
        self.assertEqual(templates.status_code, 200)
        template = next(item for item in templates.json() if item["name"] == "Домашний интернет без дубля")

        planned_transactions = core.get_planned_transactions_by_template(template["id"])
        self.assertTrue(planned_transactions)
        same_month_items = [item for item in planned_transactions if item["date"].startswith(target_month_prefix)]
        self.assertEqual(len(same_month_items), 1)
        self.assertEqual(same_month_items[0]["date"], target_date)

    def test_future_dated_recurring_income_is_created_as_planned_and_does_not_change_balance(self):
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]

        now = datetime.now()
        if now.day < 15:
            target_year = now.year
            target_month = now.month
        elif now.month == 12:
            target_year = now.year + 1
            target_month = 1
        else:
            target_year = now.year
            target_month = now.month + 1

        target_day = min(15, calendar.monthrange(target_year, target_month)[1])
        target_date = f"{target_year}-{target_month:02d}-{target_day:02d}"

        before_accounts = self.client.get("/api/v1/accounts")
        self.assertEqual(before_accounts.status_code, 200)
        before_main_balance = next(item for item in before_accounts.json() if item["type"] == "main")["balance"]

        response = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_id": income_category["id"],
                "amount": 50000.0,
                "comment": "Будущая зарплата",
                "date": target_date,
                "recurring": {
                    "enabled": True,
                    "template_name": "Зарплата тест",
                    "day_of_month": target_day,
                    "months_ahead": 6,
                    "working_days_only": True,
                },
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["transaction"]["status"], "planned")
        self.assertEqual(payload["transaction"]["date"], target_date)

        after_accounts = self.client.get("/api/v1/accounts")
        self.assertEqual(after_accounts.status_code, 200)
        after_main_balance = next(item for item in after_accounts.json() if item["type"] == "main")["balance"]
        self.assertEqual(after_main_balance, before_main_balance)

    def test_forecast_endpoint_returns_projected_balance(self):
        response = self.client.get("/api/v1/forecast/month-end")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("projected_balance", payload)
        self.assertIn("current_balance", payload)
        self.assertIn("budget_remaining", payload)

    def test_forecast_tracks_executed_and_pending_planned_amounts(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]
        today = datetime.now()
        first_day = today.strftime("%Y-%m-01")

        budget_created = self.client.post(
            "/api/v1/budgets",
            json={
                "category_id": expense_category["id"],
                "amount": 1000.0,
                "period": "monthly",
            },
        )
        self.assertEqual(budget_created.status_code, 201)

        actual_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_id": expense_category["id"],
                "amount": 300.0,
                "comment": "Budget expense",
                "date": first_day,
            },
        )
        self.assertEqual(actual_expense.status_code, 201)

        current_month_pending_date = today.strftime("%Y-%m-25")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("income", income_category["name"], 500.0, "Executed income", first_day, "actual", 101),
            )
            self._conn.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("income", income_category["name"], 800.0, "Pending income", current_month_pending_date, "planned", 102),
            )
            self._conn.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("expense", expense_category["name"], 150.0, "Executed expense", first_day, "actual", 103),
            )
            self._conn.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("expense", expense_category["name"], 200.0, "Pending expense", current_month_pending_date, "planned", 104),
            )

        response = self.client.get("/api/v1/forecast/month-end")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["planned_income"], 800.0)
        self.assertEqual(payload["executed_planned_income"], 500.0)
        self.assertEqual(payload["planned_expense"], 200.0)
        self.assertEqual(payload["executed_planned_expense"], 150.0)
        self.assertEqual(payload["current_expenses"], 450.0)
        self.assertEqual(payload["budget_remaining"], 550.0)
        self.assertEqual(payload["combined_pending_expense"], 750.0)
        self.assertEqual(payload["combined_executed_expense"], 600.0)

    def test_accounts_endpoint_returns_main_account(self):
        response = self.client.get("/api/v1/accounts")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["type"] == "main" for item in payload))
        main_account = next(item for item in payload if item["type"] == "main")
        self.assertEqual(main_account["id"], 1)

    def test_capital_account_crud_and_default_switch_via_api(self):
        first = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Reserve",
                "balance": 2500.0,
                "icon": "safe",
                "color": "#111111",
            },
        )
        self.assertEqual(first.status_code, 201)
        first_id = first.json()["id"]
        self.assertTrue(first.json()["is_default"])

        second = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Invest",
                "balance": 500.0,
                "icon": "chart",
                "color": "#222222",
            },
        )
        self.assertEqual(second.status_code, 201)
        second_id = second.json()["id"]
        self.assertFalse(second.json()["is_default"])

        switched = self.client.patch(
            f"/api/v1/accounts/{second_id}",
            json={
                "is_default": True,
                "color": "#333333",
            },
        )
        self.assertEqual(switched.status_code, 200)
        self.assertTrue(switched.json()["is_default"])
        self.assertEqual(switched.json()["color"], "#333333")

        first_refetched = self.client.get(f"/api/v1/accounts/{first_id}")
        self.assertEqual(first_refetched.status_code, 200)
        self.assertFalse(first_refetched.json()["is_default"])

        deleted = self.client.delete(f"/api/v1/accounts/{first_id}")
        self.assertEqual(deleted.status_code, 200)

        inactive = self.client.get("/api/v1/accounts?include_inactive=true")
        self.assertEqual(inactive.status_code, 200)
        deleted_account = next(item for item in inactive.json() if item["id"] == first_id)
        self.assertFalse(deleted_account["is_active"])

    def test_capital_account_update_persists_name_balance_and_color(self):
        created = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Editable",
                "balance": 100.0,
                "icon": "bank",
                "color": "#111111",
            },
        )
        self.assertEqual(created.status_code, 201)
        account_id = created.json()["id"]

        updated = self.client.patch(
            f"/api/v1/accounts/{account_id}",
            json={
                "name": "Editable Updated",
                "balance": 2500.0,
                "color": "#abcdef",
            },
        )
        self.assertEqual(updated.status_code, 200)
        payload = updated.json()
        self.assertEqual(payload["name"], "Editable Updated")
        self.assertEqual(payload["balance"], 2500.0)
        self.assertEqual(payload["color"], "#abcdef")

        fetched = self.client.get(f"/api/v1/accounts/{account_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["name"], "Editable Updated")
        self.assertEqual(fetched.json()["balance"], 2500.0)
        self.assertEqual(fetched.json()["color"], "#abcdef")

    def test_transfer_via_api_updates_account_balances(self):
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 5000.0,
                "comment": "Seed main balance",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(income.status_code, 201)

        capital = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Web Capital",
                "balance": 0.0,
                "icon": "bank",
                "color": "#123456",
            },
        )
        self.assertEqual(capital.status_code, 201)
        capital_id = capital.json()["id"]

        transfer = self.client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": 1,
                "to_account_id": capital_id,
                "amount": 1000.0,
                "date": "2026-04-08",
                "comment": "Move to capital",
            },
        )
        self.assertEqual(transfer.status_code, 201)
        payload = transfer.json()
        self.assertEqual(payload["from_account_id"], 1)
        self.assertEqual(payload["to_account_id"], capital_id)
        self.assertEqual(payload["amount"], 1000.0)

        accounts = self.client.get("/api/v1/accounts").json()
        main_account = next(item for item in accounts if item["id"] == 1)
        capital_account = next(item for item in accounts if item["id"] == capital_id)
        self.assertEqual(main_account["balance"], 4000.0)
        self.assertEqual(capital_account["balance"], 1000.0)

        history = self.client.get(f"/api/v1/transfers?account_id={capital_id}")
        self.assertEqual(history.status_code, 200)
        self.assertTrue(any(item["to_account_id"] == capital_id for item in history.json()))

    def test_settings_endpoint_and_income_auto_capital_flow(self):
        initial_settings = self.client.get("/api/v1/settings")
        self.assertEqual(initial_settings.status_code, 200)
        self.assertIn("auto_capital_enabled", initial_settings.json())
        self.assertIn("auto_capital_percent", initial_settings.json())

        capital = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Auto Capital",
                "balance": 0.0,
                "icon": "bank",
                "color": "#12ab34",
            },
        )
        self.assertEqual(capital.status_code, 201)
        capital_id = capital.json()["id"]

        updated_settings = self.client.patch(
            "/api/v1/settings",
            json={
                "auto_capital_enabled": True,
                "auto_capital_percent": 15,
            },
        )
        self.assertEqual(updated_settings.status_code, 200)
        self.assertEqual(updated_settings.json()["auto_capital_percent"], 15)
        self.assertEqual(updated_settings.json()["default_capital_account_id"], capital_id)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 10000.0,
                "comment": "Auto capital income",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(income.status_code, 201)

        accounts = self.client.get("/api/v1/accounts").json()
        main_account = next(item for item in accounts if item["id"] == 1)
        capital_account = next(item for item in accounts if item["id"] == capital_id)
        self.assertEqual(main_account["balance"], 8500.0)
        self.assertEqual(capital_account["balance"], 1500.0)

        transfers = self.client.get(f"/api/v1/transfers?account_id={capital_id}").json()
        self.assertTrue(any(item["amount"] == 1500.0 for item in transfers))

    def test_budget_crud_via_api(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]

        created = self.client.post(
            "/api/v1/budgets",
            json={
                "category_id": expense_category["id"],
                "amount": 15000.0,
                "period": "monthly",
            },
        )
        self.assertEqual(created.status_code, 201)
        budget_id = created.json()["id"]
        self.assertEqual(created.json()["category_id"], expense_category["id"])

        fetched = self.client.get(f"/api/v1/budgets/{budget_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["amount"], 15000.0)

        updated = self.client.patch(
            f"/api/v1/budgets/{budget_id}",
            json={
                "amount": 18000.0,
                "period": "yearly",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["amount"], 18000.0)
        self.assertEqual(updated.json()["period"], "yearly")

        report = self.client.get("/api/v1/budgets/report")
        self.assertEqual(report.status_code, 200)
        self.assertTrue(any(item["category_id"] == expense_category["id"] for item in report.json()))

        deleted = self.client.delete(f"/api/v1/budgets/{budget_id}")
        self.assertEqual(deleted.status_code, 200)

    def test_recurring_template_crud_and_execute_due_via_api(self):
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]
        capital = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Recurring Capital",
                "balance": 0.0,
                "color": "#654321",
            },
        )
        self.assertEqual(capital.status_code, 201)

        created = self.client.post(
            "/api/v1/recurring-templates",
            json={
                "type": "income",
                "name": "Salary",
                "amount": 12000.0,
                "day_of_month": 1,
                "category_id": income_category["id"],
                "comment_template": "Monthly salary",
                "months_ahead": 3,
                "working_days_only": True,
            },
        )
        self.assertEqual(created.status_code, 201)
        template_id = created.json()["id"]
        self.assertEqual(created.json()["name"], "Salary")

        listed = self.client.get("/api/v1/recurring-templates")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(item["id"] == template_id for item in listed.json()))

        updated = self.client.patch(
            f"/api/v1/recurring-templates/{template_id}",
            json={
                "amount": 15000.0,
                "comment_template": "Salary updated",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["amount"], 15000.0)
        self.assertEqual(updated.json()["comment_template"], "Salary updated")

        planned_transactions = core.get_planned_transactions_by_template(template_id)
        self.assertGreaterEqual(len(planned_transactions), 1)

        due_transaction_id = planned_transactions[0]["id"]
        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE transactions SET date = ? WHERE id = ?",
                ("2026-04-01", due_transaction_id),
            )
            conn.commit()

        due_before = self.client.get("/api/v1/recurring-templates/due")
        self.assertEqual(due_before.status_code, 200)
        self.assertEqual(len(due_before.json()), 0)

        refreshed_transactions = self.client.get("/api/v1/transactions?period=all")
        self.assertEqual(refreshed_transactions.status_code, 200)
        self.assertTrue(
            any(item["id"] == due_transaction_id and item["status"] == "actual" for item in refreshed_transactions.json())
        )

        executed = self.client.post("/api/v1/recurring-templates/execute-due")
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["executed_count"], 0)

        due_after = self.client.get("/api/v1/recurring-templates/due")
        self.assertEqual(due_after.status_code, 200)
        self.assertEqual(len(due_after.json()), 0)

        deleted = self.client.delete(f"/api/v1/recurring-templates/{template_id}")
        self.assertEqual(deleted.status_code, 200)
        listed_after_delete = self.client.get("/api/v1/recurring-templates")
        self.assertEqual(listed_after_delete.status_code, 200)
        self.assertFalse(any(item["id"] == template_id for item in listed_after_delete.json()))


if __name__ == "__main__":
    unittest.main()
