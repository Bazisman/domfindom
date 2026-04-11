import sqlite3
import unittest
from contextlib import contextmanager
import calendar
import os
import shutil
from datetime import datetime, timedelta
from uuid import uuid4

import core
from fastapi.testclient import TestClient

from backend.auth.service import auth_service
from backend.config import settings
from backend.main import app


class WebApiTestCase(unittest.TestCase):
    def setUp(self):
        self._old_db_name = core.DB_NAME
        self._old_get_connection = core.get_connection
        self._old_auth_db_name = auth_service.auth_db_name
        self._old_users_data_dir = auth_service.users_data_dir
        self._old_login_rate_limit_attempts = settings.login_rate_limit_attempts
        self._old_login_rate_limit_window_minutes = settings.login_rate_limit_window_minutes
        self._old_expose_reset_token_in_response = settings.expose_reset_token_in_response
        self._old_csrf_protection_enabled = settings.csrf_protection_enabled
        settings.login_rate_limit_attempts = 2
        settings.login_rate_limit_window_minutes = 15
        settings.expose_reset_token_in_response = True
        settings.csrf_protection_enabled = False
        auth_service.close()
        auth_service.auth_db_name = ":memory:"
        auth_service.users_data_dir = os.path.join(os.getcwd(), "tests_user_data")
        self._connections = {}

        def _get_conn_for_key(key: str):
            if key not in self._connections:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._connections[key] = conn
            return self._connections[key]

        @contextmanager
        def _memory_connection():
            active_key = core._DB_NAME_CONTEXT.get()  # type: ignore[attr-defined]
            conn = _get_conn_for_key(active_key)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        core.get_connection = _memory_connection
        core._invalidate_cache()
        core.init_db()
        auth_service.init_auth_db()
        self._conn = _get_conn_for_key(core.DB_NAME)
        self.client = TestClient(app)
        self._register_and_login()

    def tearDown(self):
        self.client.close()
        core._invalidate_cache()
        core.DB_NAME = self._old_db_name
        core.get_connection = self._old_get_connection
        auth_service.close()
        auth_service.auth_db_name = self._old_auth_db_name
        auth_service.users_data_dir = self._old_users_data_dir
        settings.login_rate_limit_attempts = self._old_login_rate_limit_attempts
        settings.login_rate_limit_window_minutes = self._old_login_rate_limit_window_minutes
        settings.expose_reset_token_in_response = self._old_expose_reset_token_in_response
        settings.csrf_protection_enabled = self._old_csrf_protection_enabled
        for conn in self._connections.values():
            conn.close()
        shutil.rmtree(os.path.join(os.getcwd(), "tests_user_data"), ignore_errors=True)

    def _register_and_login(self):
        email = f"tester-{uuid4().hex[:10]}@example.com"
        self._primary_email = email
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123",
            },
        )
        self.assertEqual(response.status_code, 201)

    def _current_user_id(self) -> int:
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        return int(me.json()["id"])

    def _push_current_user_db(self):
        user_db_path = auth_service.get_user_db_path(self._current_user_id())
        return core.push_db_name(user_db_path)

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_protected_endpoint_requires_auth_after_logout(self):
        logout_response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout_response.status_code, 200)

        dashboard_response = self.client.get("/api/v1/dashboard")
        self.assertEqual(dashboard_response.status_code, 401)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": f"weak-{uuid4().hex[:8]}@example.com",
                "password": "weakpass",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_login_rate_limit_blocks_after_failed_attempts(self):
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)
        email = f"ratelimit-{uuid4().hex[:8]}@example.com"
        created = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)

        attempt1 = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": "WrongPass123",
            },
        )
        self.assertEqual(attempt1.status_code, 401)

        attempt2 = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": "WrongPass123",
            },
        )
        self.assertEqual(attempt2.status_code, 401)

        blocked = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": "WrongPass123",
            },
        )
        self.assertEqual(blocked.status_code, 429)

    def test_change_password_invalidates_session_and_requires_new_password(self):
        changed = self.client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "StrongPass123",
                "new_password": "NewStrong123",
            },
        )
        self.assertEqual(changed.status_code, 200)

        dashboard_after_change = self.client.get("/api/v1/dashboard")
        self.assertEqual(dashboard_after_change.status_code, 401)

        old_login = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self._primary_email,
                "password": "StrongPass123",
            },
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self._primary_email,
                "password": "NewStrong123",
            },
        )
        self.assertEqual(new_login.status_code, 200)

    def test_password_reset_flow_updates_password(self):
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)
        email = f"reset-{uuid4().hex[:8]}@example.com"
        created = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)

        requested = self.client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": email},
        )
        self.assertEqual(requested.status_code, 200)
        payload = requested.json()
        self.assertIn("reset_token", payload)
        reset_token = payload["reset_token"]

        confirmed = self.client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": reset_token,
                "new_password": "ResetStrong123",
            },
        )
        self.assertEqual(confirmed.status_code, 200)

        repeat_confirm = self.client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": reset_token,
                "new_password": "AnotherStrong123",
            },
        )
        self.assertEqual(repeat_confirm.status_code, 400)

        old_login = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongPass123"},
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "ResetStrong123"},
        )
        self.assertEqual(new_login.status_code, 200)

    def test_session_management_endpoints(self):
        sessions_response = self.client.get("/api/v1/auth/sessions")
        self.assertEqual(sessions_response.status_code, 200)
        sessions = sessions_response.json()["sessions"]
        self.assertGreaterEqual(len(sessions), 1)
        self.assertTrue(any(item["is_current"] for item in sessions))

        current_session = next(item for item in sessions if item["is_current"])
        revoke_current = self.client.delete(f"/api/v1/auth/sessions/{current_session['id']}")
        self.assertEqual(revoke_current.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

        relogin = self.client.post(
            "/api/v1/auth/login",
            json={"email": self._primary_email, "password": "StrongPass123"},
        )
        self.assertEqual(relogin.status_code, 200)

        second_client = TestClient(app)
        second_login = second_client.post(
            "/api/v1/auth/login",
            json={"email": self._primary_email, "password": "StrongPass123"},
        )
        self.assertEqual(second_login.status_code, 200)

        after_second = self.client.get("/api/v1/auth/sessions")
        self.assertEqual(after_second.status_code, 200)
        self.assertGreaterEqual(len(after_second.json()["sessions"]), 2)

        revoke_others = self.client.post("/api/v1/auth/sessions/revoke-others")
        self.assertEqual(revoke_others.status_code, 200)
        self.assertGreaterEqual(revoke_others.json()["revoked_count"], 1)

        self.assertEqual(second_client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)
        second_client.close()

    def test_csrf_blocks_state_changes_without_header_when_enabled(self):
        settings.csrf_protection_enabled = True
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]
        without_header = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 100.0,
                "comment": "csrf fail",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(without_header.status_code, 403)

        csrf_token = self.client.cookies.get(settings.csrf_cookie_name)
        self.assertTrue(csrf_token)
        with_header = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 200.0,
                "comment": "csrf ok",
                "date": "2026-04-08",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(with_header.status_code, 201)

    def test_data_isolation_between_users(self):
        created = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": "Продукты",
                "amount": 777.0,
                "comment": "Only user A",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(created.status_code, 201)

        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 200)

        second_email = f"userb-{uuid4().hex[:8]}@example.com"
        second_register = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": second_email,
                "password": "AnotherPass123",
            },
        )
        self.assertEqual(second_register.status_code, 201)

        second_transactions = self.client.get("/api/v1/transactions?period=all")
        self.assertEqual(second_transactions.status_code, 200)
        self.assertFalse(any(item["comment"] == "Only user A" for item in second_transactions.json()))

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

        db_token = self._push_current_user_db()
        try:
            with core.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("income", income_category, 1500.0, "Auto due income", due_date, "planned", 501),
                )
                conn.commit()
        finally:
            core.pop_db_name(db_token)

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

        db_token = self._push_current_user_db()
        try:
            planned_transactions = core.get_planned_transactions_by_template(template["id"])
        finally:
            core.pop_db_name(db_token)
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

    def test_future_recurring_working_day_shifts_weekend_date(self):
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]

        now = datetime.now()
        # Ищем ближайшую субботу в будущем
        for offset in range(1, 15):
            candidate = now + timedelta(days=offset)
            if candidate.weekday() == 5:
                saturday = candidate
                break
        else:
            self.fail("Could not find upcoming Saturday for test")

        expected_monday = saturday + timedelta(days=2)
        target_date = saturday.strftime("%Y-%m-%d")

        response = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_id": expense_category["id"],
                "amount": 1500.0,
                "comment": "Платёж выходного дня",
                "date": target_date,
                "recurring": {
                    "enabled": True,
                    "template_name": "Тест переноса рабочего дня",
                    "day_of_month": saturday.day,
                    "months_ahead": 3,
                    "working_days_only": True,
                },
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["transaction"]["status"], "planned")
        self.assertEqual(payload["transaction"]["date"], expected_monday.strftime("%Y-%m-%d"))

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
        db_token = self._push_current_user_db()
        try:
            with core.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("income", income_category["name"], 500.0, "Executed income", first_day, "actual", 101),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("income", income_category["name"], 800.0, "Pending income", current_month_pending_date, "planned", 102),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("expense", expense_category["name"], 150.0, "Executed expense", first_day, "actual", 103),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("expense", expense_category["name"], 200.0, "Pending expense", current_month_pending_date, "planned", 104),
                )
                conn.commit()
        finally:
            core.pop_db_name(db_token)

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

        db_token = self._push_current_user_db()
        try:
            planned_transactions = core.get_planned_transactions_by_template(template_id)
        finally:
            core.pop_db_name(db_token)
        self.assertGreaterEqual(len(planned_transactions), 1)

        due_transaction_id = planned_transactions[0]["id"]
        db_token = self._push_current_user_db()
        try:
            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE transactions SET date = ? WHERE id = ?",
                    ("2026-04-01", due_transaction_id),
                )
                conn.commit()
        finally:
            core.pop_db_name(db_token)

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
