import sqlite3
import unittest
from contextlib import contextmanager
import calendar
import os
import shutil
from datetime import datetime, timedelta
from unittest import mock
from uuid import uuid4

import core
from fastapi.testclient import TestClient

from backend.auth.service import auth_service
from backend.auth.mailer import auth_mailer
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

    def test_register_maps_integrity_error_to_conflict(self):
        with mock.patch.object(auth_service, "create_user", side_effect=sqlite3.IntegrityError("UNIQUE constraint")):
            response = self.client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"race-{uuid4().hex[:8]}@example.com",
                    "password": "StrongPass123",
                },
            )
        self.assertEqual(response.status_code, 409)

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

    def test_password_reset_unavailable_without_email_channel(self):
        old_expose = settings.expose_reset_token_in_response
        old_smtp_host = auth_mailer.smtp_host
        old_smtp_from = auth_mailer.smtp_from
        try:
            settings.expose_reset_token_in_response = False
            auth_mailer.smtp_host = ""
            auth_mailer.smtp_from = ""
            response = self.client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": self._primary_email},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json().get("message"),
                "Восстановление через email временно недоступно. Обратитесь в поддержку.",
            )
        finally:
            settings.expose_reset_token_in_response = old_expose
            auth_mailer.smtp_host = old_smtp_host
            auth_mailer.smtp_from = old_smtp_from

    def test_account_delete_request_requires_email_channel(self):
        old_smtp_host = auth_mailer.smtp_host
        old_smtp_from = auth_mailer.smtp_from
        try:
            auth_mailer.smtp_host = ""
            auth_mailer.smtp_from = ""
            response = self.client.post("/api/v1/account/delete/request")
            self.assertEqual(response.status_code, 503)
        finally:
            auth_mailer.smtp_host = old_smtp_host
            auth_mailer.smtp_from = old_smtp_from

    def test_account_delete_confirm_deletes_user_and_revokes_session(self):
        user_id = self._current_user_id()
        token = auth_service.create_account_deletion_token(user_id)
        self.assertIsNotNone(token)

        confirmed = self.client.post(
            "/api/v1/auth/account-delete/confirm",
            json={"token": token},
        )
        self.assertEqual(confirmed.status_code, 200)

        me_after = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_after.status_code, 401)

        login_after = self.client.post(
            "/api/v1/auth/login",
            json={"email": self._primary_email, "password": "StrongPass123"},
        )
        self.assertEqual(login_after.status_code, 401)

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

    def test_account_preferences_can_be_read_and_updated(self):
        initial = self.client.get("/api/v1/account/preferences")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["theme_mode"], "system")

        updated = self.client.put("/api/v1/account/preferences", json={"theme_mode": "dark"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["theme_mode"], "dark")

        fetched = self.client.get("/api/v1/account/preferences")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["theme_mode"], "dark")

    def test_reconciliation_flow_creates_adjustment_transaction(self):
        initial_summary = self.client.get("/api/v1/reconciliation")
        self.assertEqual(initial_summary.status_code, 200)
        self.assertEqual(initial_summary.json()["program_balance"], 0)
        self.assertEqual(initial_summary.json()["real_balance"], 0)

        created_source = self.client.post(
            "/api/v1/reconciliation/sources",
            json={"name": "Наличные", "balance": 1500},
        )
        self.assertEqual(created_source.status_code, 201)
        source_id = created_source.json()["id"]

        updated_source = self.client.patch(
            f"/api/v1/reconciliation/sources/{source_id}",
            json={"balance": 1700},
        )
        self.assertEqual(updated_source.status_code, 200)
        self.assertEqual(updated_source.json()["balance"], 1700)

        applied = self.client.post("/api/v1/reconciliation/apply")
        self.assertEqual(applied.status_code, 200)
        payload = applied.json()
        self.assertEqual(payload["reconciliation"]["real_balance"], 1700)
        self.assertEqual(payload["reconciliation"]["program_balance"], 0)
        self.assertEqual(payload["reconciliation"]["difference"], 1700)
        self.assertIsNotNone(payload["adjustment_transaction_id"])

        transactions_response = self.client.get("/api/v1/transactions?limit=20&offset=0&period=all")
        self.assertEqual(transactions_response.status_code, 200)
        transactions = transactions_response.json()
        self.assertTrue(any(item["category"] == "Корректировка" and item["type"] == "income" for item in transactions))

        summary_after = self.client.get("/api/v1/reconciliation")
        self.assertEqual(summary_after.status_code, 200)
        summary_payload = summary_after.json()
        self.assertEqual(summary_payload["program_balance"], 1700)
        self.assertEqual(summary_payload["real_balance"], 1700)
        self.assertEqual(summary_payload["difference"], 0)
        self.assertEqual(len(summary_payload["history"]), 1)

        deleted = self.client.delete(f"/api/v1/reconciliation/sources/{source_id}")
        self.assertEqual(deleted.status_code, 200)

    def test_backup_restore_and_reset_all_flow(self):
        created = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": "РџСЂРѕРґСѓРєС‚С‹",
                "amount": 111.0,
                "comment": "before backup",
                "date": "2026-04-08",
            },
        )
        self.assertEqual(created.status_code, 201)

        saved = self.client.post("/api/v1/account/backup/save")
        self.assertEqual(saved.status_code, 200)

        created_after = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": "РџСЂРѕРґСѓРєС‚С‹",
                "amount": 222.0,
                "comment": "after backup",
                "date": "2026-04-09",
            },
        )
        self.assertEqual(created_after.status_code, 201)

        restored = self.client.post("/api/v1/account/backup/restore")
        self.assertEqual(restored.status_code, 200)

        transactions_after_restore = self.client.get("/api/v1/transactions?limit=100&period=all")
        self.assertEqual(transactions_after_restore.status_code, 200)
        comments = [item.get("comment") for item in transactions_after_restore.json()]
        self.assertIn("before backup", comments)
        self.assertNotIn("after backup", comments)

        invalid_reset = self.client.post("/api/v1/account/reset-all", json={"confirm_text": "NOPE"})
        self.assertEqual(invalid_reset.status_code, 422)

        valid_reset = self.client.post("/api/v1/account/reset-all", json={"confirm_text": "СБРОС"})
        self.assertEqual(valid_reset.status_code, 200)

        transactions_after_reset = self.client.get("/api/v1/transactions?limit=100&period=all")
        self.assertEqual(transactions_after_reset.status_code, 200)
        self.assertEqual(transactions_after_reset.json(), [])

        activity = self.client.get("/api/v1/account/activity?limit=20")
        self.assertEqual(activity.status_code, 200)
        events = activity.json()["events"]
        self.assertTrue(any(item["event_type"] == "backup_save" and item["status"] == "success" for item in events))
        self.assertTrue(any(item["event_type"] == "backup_restore" and item["status"] == "success" for item in events))
        self.assertTrue(any(item["event_type"] == "reset_all_data" and item["status"] == "success" for item in events))

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

    def test_family_budget_invite_accept_and_membership_flow(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья Ивановых"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"family-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={
                "email": second_email,
                "password": "AnotherPass123",
            },
        )
        self.assertEqual(second_register.status_code, 201)

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_payload = invite_response.json()
        self.assertIn("invite_token", invite_payload)
        invite_token = str(invite_payload["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)
        self.assertEqual(accept_response.json()["family_id"], family_id)

        my_families_owner = self.client.get("/api/v1/families/me")
        self.assertEqual(my_families_owner.status_code, 200)
        self.assertTrue(any(item["id"] == family_id for item in my_families_owner.json()["families"]))

        my_families_member = second_client.get("/api/v1/families/me")
        self.assertEqual(my_families_member.status_code, 200)
        self.assertTrue(any(item["id"] == family_id for item in my_families_member.json()["families"]))

        members_response = self.client.get(f"/api/v1/families/{family_id}/members")
        self.assertEqual(members_response.status_code, 200)
        members = members_response.json()["members"]
        members_by_email = {item["email"]: item for item in members}
        self.assertIn(self._primary_email, members_by_email)
        self.assertIn(second_email, members_by_email)
        self.assertEqual(members_by_email[self._primary_email]["role"], "owner")
        self.assertEqual(members_by_email[second_email]["role"], "member")

        duplicate_invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(duplicate_invite.status_code, 409)

        change_role_to_viewer = self.client.patch(
            f"/api/v1/families/{family_id}/members/{second_register.json()['user']['id']}/role",
            json={"role": "viewer"},
        )
        self.assertEqual(change_role_to_viewer.status_code, 200)

        members_after_update = self.client.get(f"/api/v1/families/{family_id}/members")
        self.assertEqual(members_after_update.status_code, 200)
        members_after_update_by_email = {item["email"]: item for item in members_after_update.json()["members"]}
        self.assertEqual(members_after_update_by_email[second_email]["role"], "viewer")

        third_email = f"family-{uuid4().hex[:8]}@example.com"

        non_admin_cannot_invite = second_client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": third_email, "role": "viewer"},
        )
        self.assertEqual(non_admin_cannot_invite.status_code, 403)

        remove_member = self.client.delete(f"/api/v1/families/{family_id}/members/{second_register.json()['user']['id']}")
        self.assertEqual(remove_member.status_code, 200)

        second_after_remove = second_client.get(f"/api/v1/families/{family_id}/members")
        self.assertEqual(second_after_remove.status_code, 404)
        second_client.close()

    def test_family_pending_invites_accept_and_decline(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья Тест"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"pending-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)
        self.assertEqual(second_client.post("/api/v1/auth/logout").status_code, 200)
        self.assertEqual(
            second_client.post("/api/v1/auth/login", json={"email": second_email, "password": "AnotherPass123"}).status_code,
            200,
        )

        invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "viewer"},
        )
        self.assertEqual(invite.status_code, 200)

        pending = second_client.get("/api/v1/families/invites/pending")
        self.assertEqual(pending.status_code, 200)
        invites = pending.json()["invites"]
        self.assertGreaterEqual(len(invites), 1)
        invite_id = int(invites[0]["invite_id"])

        accept = second_client.post(f"/api/v1/families/invites/{invite_id}/accept")
        self.assertEqual(accept.status_code, 200)
        self.assertEqual(int(accept.json()["family_id"]), family_id)

        third_client = TestClient(app)
        third_email = f"pending-{uuid4().hex[:8]}@example.com"
        third_register = third_client.post(
            "/api/v1/auth/register",
            json={"email": third_email, "password": "AnotherPass123"},
        )
        self.assertEqual(third_register.status_code, 201)
        decline_invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": third_email, "role": "member"},
        )
        self.assertEqual(decline_invite.status_code, 200)
        pending_third = third_client.get("/api/v1/families/invites/pending")
        self.assertEqual(pending_third.status_code, 200)
        third_invite_id = int(pending_third.json()["invites"][0]["invite_id"])
        decline = third_client.post(f"/api/v1/families/invites/{third_invite_id}/decline")
        self.assertEqual(decline.status_code, 200)
        pending_third_after = third_client.get("/api/v1/families/invites/pending")
        self.assertEqual(pending_third_after.status_code, 200)
        self.assertEqual(len(pending_third_after.json()["invites"]), 0)

        second_client.close()
        third_client.close()

    def test_family_dashboard_sums_each_member_balance_without_cache_bleed(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья баланс"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"balance-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_token = str(invite_response.json()["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]

        owner_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 100000.0,
                "comment": "Owner income",
                "date": "2026-04-01",
            },
        )
        self.assertEqual(owner_income.status_code, 201)

        owner_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 10000.0,
                "comment": "Owner expense",
                "date": "2026-04-02",
            },
        )
        self.assertEqual(owner_expense.status_code, 201)

        member_expense = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 20000.0,
                "comment": "Member expense",
                "date": "2026-04-11",
            },
        )
        self.assertEqual(member_expense.status_code, 201)

        dashboard_response = self.client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        payload = dashboard_response.json()

        self.assertEqual(payload["balance"]["main_balance"], 70000.0)
        self.assertEqual(payload["balance"]["income"], 100000.0)
        self.assertEqual(payload["balance"]["expense"], 30000.0)
        self.assertEqual(payload["balance"]["difference"], 70000.0)

        second_client.close()

    def test_personal_accounts_and_dashboard_do_not_leak_between_family_members(self):
        create_family = self.client.post("/api/v1/families", json={"name": "РЎРµРјСЊСЏ С‡СѓР¶РёРµ СЃС‡РµС‚Р°"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"accounts-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": str(invite_response.json()["invite_token"])},
        )
        self.assertEqual(accept_response.status_code, 200)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]

        self.assertEqual(
            self.client.post(
                "/api/v1/transactions",
                json={
                    "type": "income",
                    "category_name": income_category,
                    "amount": 1000.0,
                    "comment": "Owner personal income",
                    "date": "2026-04-18",
                },
            ).status_code,
            201,
        )
        self.assertEqual(
            second_client.post(
                "/api/v1/transactions",
                json={
                    "type": "income",
                    "category_name": income_category,
                    "amount": 500.0,
                    "comment": "Member personal income",
                    "date": "2026-04-18",
                },
            ).status_code,
            201,
        )

        owner_capital = self.client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Owner only account", "balance": 111.0, "color": "#123456"},
        )
        self.assertEqual(owner_capital.status_code, 201)
        member_capital = second_client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Member only account", "balance": 222.0, "color": "#654321"},
        )
        self.assertEqual(member_capital.status_code, 201)

        family_dashboard = self.client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(family_dashboard.status_code, 200)

        owner_accounts = self.client.get("/api/v1/accounts")
        self.assertEqual(owner_accounts.status_code, 200)
        owner_account_names = {item["name"] for item in owner_accounts.json()}
        self.assertIn("Owner only account", owner_account_names)
        self.assertNotIn("Member only account", owner_account_names)

        member_accounts = second_client.get("/api/v1/accounts")
        self.assertEqual(member_accounts.status_code, 200)
        member_account_names = {item["name"] for item in member_accounts.json()}
        self.assertIn("Member only account", member_account_names)
        self.assertNotIn("Owner only account", member_account_names)

        owner_dashboard = self.client.get("/api/v1/dashboard")
        self.assertEqual(owner_dashboard.status_code, 200)
        self.assertEqual(owner_dashboard.json()["balance"]["main_balance"], 1000.0)

        member_dashboard = second_client.get("/api/v1/dashboard")
        self.assertEqual(member_dashboard.status_code, 200)
        self.assertEqual(member_dashboard.json()["balance"]["main_balance"], 500.0)

        second_client.close()

    def test_family_capital_target_receives_member_auto_contribution(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья капитал"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        owner_capital = self.client.post(
            "/api/v1/accounts",
            json={
                "type": "capital",
                "name": "Сбер копилка",
                "balance": 0.0,
                "color": "#228b22",
            },
        )
        self.assertEqual(owner_capital.status_code, 201)
        owner_capital_id = int(owner_capital.json()["id"])

        publish_owner_capital = self.client.patch(
            f"/api/v1/accounts/{owner_capital_id}",
            json={"family_visible": True, "family_default_target": True},
        )
        self.assertEqual(publish_owner_capital.status_code, 200)
        self.assertTrue(publish_owner_capital.json()["family_visible"])
        self.assertTrue(publish_owner_capital.json()["family_default_target"])

        second_client = TestClient(app)
        second_email = f"family-capital-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": str(invite_response.json()["invite_token"])},
        )
        self.assertEqual(accept_response.status_code, 200)

        switch_workspace = second_client.put(
            "/api/v1/account/preferences",
            json={"workspace_mode": "family"},
        )
        self.assertEqual(switch_workspace.status_code, 200)

        family_dashboard_before = second_client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(family_dashboard_before.status_code, 200)
        self.assertEqual(
            family_dashboard_before.json()["current_member_capital_target"]["target_capital_account_id"],
            owner_capital_id,
        )

        income_category = second_client.get("/api/v1/categories?type=income").json()[0]["name"]
        create_income = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 1000.0,
                "comment": "Семейное автоотчисление",
                "date": "2026-04-18",
            },
        )
        self.assertEqual(create_income.status_code, 201)
        income_id = int(create_income.json()["id"])

        owner_accounts = self.client.get("/api/v1/accounts")
        self.assertEqual(owner_accounts.status_code, 200)
        owner_capital_after = next(item for item in owner_accounts.json() if item["id"] == owner_capital_id)
        self.assertEqual(owner_capital_after["balance"], 100.0)

        member_accounts = second_client.get("/api/v1/accounts")
        self.assertEqual(member_accounts.status_code, 200)
        member_main = next(item for item in member_accounts.json() if item["type"] == "main")
        self.assertEqual(member_main["balance"], 900.0)

        family_dashboard_after = self.client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(family_dashboard_after.status_code, 200)
        self.assertEqual(family_dashboard_after.json()["balance"]["capital_balance"], 100.0)

        deleted_income = second_client.delete(f"/api/v1/transactions/{income_id}")
        self.assertEqual(deleted_income.status_code, 200)

        owner_accounts_after_delete = self.client.get("/api/v1/accounts")
        self.assertEqual(owner_accounts_after_delete.status_code, 200)
        owner_capital_after_delete = next(item for item in owner_accounts_after_delete.json() if item["id"] == owner_capital_id)
        self.assertEqual(owner_capital_after_delete["balance"], 0.0)

        member_accounts_after_delete = second_client.get("/api/v1/accounts")
        self.assertEqual(member_accounts_after_delete.status_code, 200)
        member_main_after_delete = next(item for item in member_accounts_after_delete.json() if item["type"] == "main")
        self.assertEqual(member_main_after_delete["balance"], 0.0)
        second_client.close()

    def test_family_dashboard_shows_only_published_capital_accounts(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья публикация"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        first_capital = self.client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Копилка 1", "balance": 100.0, "color": "#111111"},
        )
        self.assertEqual(first_capital.status_code, 201)
        first_capital_id = int(first_capital.json()["id"])

        second_capital = self.client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Копилка 2", "balance": 200.0, "color": "#222222"},
        )
        self.assertEqual(second_capital.status_code, 201)
        second_capital_id = int(second_capital.json()["id"])

        published = self.client.patch(
            f"/api/v1/accounts/{first_capital_id}",
            json={"family_visible": True, "family_default_target": True},
        )
        self.assertEqual(published.status_code, 200)

        hidden = self.client.patch(
            f"/api/v1/accounts/{second_capital_id}",
            json={"family_visible": False},
        )
        self.assertEqual(hidden.status_code, 200)
        self.assertFalse(hidden.json()["family_visible"])
        self.assertFalse(hidden.json()["family_default_target"])

        dashboard = self.client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        capital_accounts = dashboard.json()["capital_accounts"]
        self.assertEqual(len(capital_accounts), 1)
        self.assertEqual(capital_accounts[0]["capital_account_id"], first_capital_id)

    def test_family_capital_contribution_appears_in_transfer_history(self):
        member_email = f"family-transfer-{uuid4().hex[:8]}@example.com"
        member_client = TestClient(app)
        register_member = member_client.post(
            "/api/v1/auth/register",
            json={"email": member_email, "password": "MemberPass123"},
        )
        self.assertEqual(register_member.status_code, 201)
        member_login = member_client.post(
            "/api/v1/auth/login",
            json={"email": member_email, "password": "MemberPass123"},
        )
        self.assertEqual(member_login.status_code, 200)

        create_family = self.client.post("/api/v1/families", json={"name": "Семья переводы"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])
        invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": member_email},
        )
        self.assertEqual(invite.status_code, 200)
        accept = member_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite.json()["invite_token"]},
        )
        self.assertEqual(accept.status_code, 200)

        capital = self.client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Семейная копилка", "balance": 0.0, "color": "#345678"},
        )
        self.assertEqual(capital.status_code, 201)
        capital_id = int(capital.json()["id"])

        published = self.client.patch(
            f"/api/v1/accounts/{capital_id}",
            json={"family_visible": True, "family_default_target": True},
        )
        self.assertEqual(published.status_code, 200)

        switch_workspace = member_client.put(
            "/api/v1/account/preferences",
            json={"workspace_mode": "family"},
        )
        self.assertEqual(switch_workspace.status_code, 200)

        member_income_category = member_client.get("/api/v1/categories?type=income").json()[0]["name"]
        member_income = member_client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": member_income_category,
                "amount": 1000.0,
                "comment": "Доход с семейным отчислением",
                "date": "2026-04-18",
            },
        )
        self.assertEqual(member_income.status_code, 201)

        member_transfers = member_client.get("/api/v1/transfers").json()
        self.assertTrue(any(item["to_account_id"] == capital_id and item["amount"] == 100.0 for item in member_transfers))

        owner_transfers = self.client.get(f"/api/v1/transfers?account_id={capital_id}").json()
        self.assertTrue(any(item["to_account_id"] == capital_id and item["amount"] == 100.0 for item in owner_transfers))
        member_client.close()

    def test_family_capital_target_can_use_another_members_account_and_history_is_shared(self):
        member_email = f"family-shared-{uuid4().hex[:8]}@example.com"
        member_client = TestClient(app)
        register_member = member_client.post(
            "/api/v1/auth/register",
            json={"email": member_email, "password": "MemberPass123"},
        )
        self.assertEqual(register_member.status_code, 201)

        create_family = self.client.post("/api/v1/families", json={"name": "РЎРµРјСЊСЏ РѕР±С‰РёР№ С‡С‘С‚"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": member_email},
        )
        self.assertEqual(invite.status_code, 200)
        accept = member_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite.json()["invite_token"]},
        )
        self.assertEqual(accept.status_code, 200)

        self.assertEqual(self.client.put("/api/v1/account/preferences", json={"workspace_mode": "family"}).status_code, 200)
        self.assertEqual(member_client.put("/api/v1/account/preferences", json={"workspace_mode": "family"}).status_code, 200)

        member_capital = member_client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Озон Насти", "balance": 0.0, "color": "#2255aa"},
        )
        self.assertEqual(member_capital.status_code, 201)
        member_capital_id = int(member_capital.json()["id"])

        publish_member_capital = member_client.patch(
            f"/api/v1/accounts/{member_capital_id}",
            json={"family_visible": True, "family_default_target": True},
        )
        self.assertEqual(publish_member_capital.status_code, 200)

        set_owner_target = self.client.put(
            f"/api/v1/families/{family_id}/capital-target",
            json={
                "target_owner_user_id": int(register_member.json()["user"]["id"]),
                "target_capital_account_id": member_capital_id,
            },
        )
        self.assertEqual(set_owner_target.status_code, 200)
        self.assertEqual(set_owner_target.json()["target_capital_account_id"], member_capital_id)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        owner_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 1000.0,
                "comment": "Р”РѕС…РѕРґ РІ РћР·РѕРЅ РќР°СЃС‚Рё",
                "date": "2026-04-18",
            },
        )
        self.assertEqual(owner_income.status_code, 201)

        member_accounts = member_client.get("/api/v1/accounts")
        self.assertEqual(member_accounts.status_code, 200)
        member_capital_after = next(item for item in member_accounts.json() if item["id"] == member_capital_id)
        self.assertEqual(member_capital_after["balance"], 100.0)

        owner_history = self.client.get(f"/api/v1/families/{family_id}/capital-history")
        self.assertEqual(owner_history.status_code, 200)
        owner_items = owner_history.json()["items"]
        self.assertTrue(any(item["target_capital_account_id"] == member_capital_id and item["target_account_name"] == "Озон Насти" for item in owner_items))

        member_history = member_client.get(f"/api/v1/families/{family_id}/capital-history")
        self.assertEqual(member_history.status_code, 200)
        member_items = member_history.json()["items"]
        self.assertTrue(any(item["target_capital_account_id"] == member_capital_id and item["source_transaction_id"] == int(owner_income.json()["id"]) for item in member_items))
        member_client.close()

    def test_family_member_can_clear_family_capital_target_and_use_personal_default(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья личная цель"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        owner_capital = self.client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Общий капитал", "balance": 0.0, "color": "#228b22"},
        )
        self.assertEqual(owner_capital.status_code, 201)
        owner_capital_id = int(owner_capital.json()["id"])

        publish_owner_capital = self.client.patch(
            f"/api/v1/accounts/{owner_capital_id}",
            json={"family_visible": True, "family_default_target": True},
        )
        self.assertEqual(publish_owner_capital.status_code, 200)

        member_client = TestClient(app)
        member_email = f"family-personal-{uuid4().hex[:8]}@example.com"
        register_member = member_client.post(
            "/api/v1/auth/register",
            json={"email": member_email, "password": "MemberPass123"},
        )
        self.assertEqual(register_member.status_code, 201)

        invite = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": member_email, "role": "member"},
        )
        self.assertEqual(invite.status_code, 200)
        accept = member_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite.json()["invite_token"]},
        )
        self.assertEqual(accept.status_code, 200)

        member_capital = member_client.post(
            "/api/v1/accounts",
            json={"type": "capital", "name": "Личная копилка", "balance": 0.0, "color": "#2255aa"},
        )
        self.assertEqual(member_capital.status_code, 201)
        member_capital_id = int(member_capital.json()["id"])

        set_default_personal = member_client.patch(
            f"/api/v1/accounts/{member_capital_id}",
            json={"is_default": True},
        )
        self.assertEqual(set_default_personal.status_code, 200)

        self.assertEqual(member_client.put("/api/v1/account/preferences", json={"workspace_mode": "family"}).status_code, 200)

        dashboard_before_clear = member_client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(dashboard_before_clear.status_code, 200)
        self.assertEqual(
            dashboard_before_clear.json()["current_member_capital_target"]["target_capital_account_id"],
            owner_capital_id,
        )

        clear_family_target = member_client.put(
            f"/api/v1/families/{family_id}/capital-target",
            json={"target_owner_user_id": None, "target_capital_account_id": None},
        )
        self.assertEqual(clear_family_target.status_code, 200)
        self.assertIsNone(clear_family_target.json()["target_owner_user_id"])
        self.assertIsNone(clear_family_target.json()["target_capital_account_id"])

        dashboard_after_clear = member_client.get(f"/api/v1/families/{family_id}/dashboard")
        self.assertEqual(dashboard_after_clear.status_code, 200)
        self.assertIsNone(dashboard_after_clear.json()["current_member_capital_target"]["target_owner_user_id"])
        self.assertIsNone(dashboard_after_clear.json()["current_member_capital_target"]["target_capital_account_id"])

        income_category = member_client.get("/api/v1/categories?type=income").json()[0]["name"]
        create_income = member_client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 1000.0,
                "comment": "Доход в личную копилку",
                "date": "2026-04-19",
            },
        )
        self.assertEqual(create_income.status_code, 201)

        owner_accounts = self.client.get("/api/v1/accounts")
        self.assertEqual(owner_accounts.status_code, 200)
        owner_capital_after = next(item for item in owner_accounts.json() if item["id"] == owner_capital_id)
        self.assertEqual(owner_capital_after["balance"], 0.0)

        member_accounts = member_client.get("/api/v1/accounts")
        self.assertEqual(member_accounts.status_code, 200)
        member_capital_after = next(item for item in member_accounts.json() if item["id"] == member_capital_id)
        self.assertEqual(member_capital_after["balance"], 100.0)

        family_history = member_client.get(f"/api/v1/families/{family_id}/capital-history")
        self.assertEqual(family_history.status_code, 200)
        self.assertFalse(
            any(item["source_transaction_id"] == int(create_income.json()["id"]) for item in family_history.json()["items"])
        )

        member_client.close()

    def test_family_transactions_support_period_offset_and_planned_toggle(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья лента"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"feed-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)
        second_user_id = int(second_register.json()["user"]["id"])

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_token = str(invite_response.json()["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]

        owner_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 5000.0,
                "comment": "Owner feed income",
                "date": "2026-04-05",
            },
        )
        self.assertEqual(owner_income.status_code, 201)

        member_expense = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 1200.0,
                "comment": "Member feed expense",
                "date": "2026-04-11",
            },
        )
        self.assertEqual(member_expense.status_code, 201)

        second_db_token = core.push_db_name(auth_service.get_user_db_path(second_user_id))
        try:
            core.add_planned_transaction(
                "expense",
                expense_category,
                700.0,
                "Member future planned",
                "2026-04-20",
            )
        finally:
            core.pop_db_name(second_db_token)

        current_month = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&limit=5&offset=0"
        )
        self.assertEqual(current_month.status_code, 200)
        current_payload = current_month.json()
        self.assertEqual(current_payload["total"], 2)
        current_comments = [item["comment"] for item in current_payload["transactions"]]
        self.assertIn("Owner feed income", current_comments)
        self.assertIn("Member feed expense", current_comments)
        self.assertNotIn("Member future planned", current_comments)

        paged = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&limit=1&offset=1"
        )
        self.assertEqual(paged.status_code, 200)
        self.assertEqual(len(paged.json()["transactions"]), 1)
        self.assertEqual(paged.json()["transactions"][0]["comment"], "Owner feed income")

        with_planned = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&limit=10&offset=0&include_planned=true"
        )
        self.assertEqual(with_planned.status_code, 200)
        self.assertEqual(with_planned.json()["total"], 3)
        planned_items = [item for item in with_planned.json()["transactions"] if item["comment"] == "Member future planned"]
        self.assertEqual(len(planned_items), 1)
        self.assertEqual(planned_items[0]["status"], "planned")

        personal_page = self.client.get("/api/v1/transactions/page?period=month&limit=10&offset=0")
        self.assertEqual(personal_page.status_code, 200)
        self.assertEqual(personal_page.json()["total"], 1)
        self.assertEqual(personal_page.json()["items"][0]["comment"], "Owner feed income")

        second_client.close()

    def test_family_transactions_can_be_filtered_by_owner(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья фильтр"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"member-filter-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)
        second_user_id = int(second_register.json()["user"]["id"])

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_token = str(invite_response.json()["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)

        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]

        owner_income = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "income",
                "category_name": income_category,
                "amount": 4000.0,
                "comment": "Owner only item",
                "date": "2026-04-05",
            },
        )
        self.assertEqual(owner_income.status_code, 201)

        member_expense = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 900.0,
                "comment": "Member only item",
                "date": "2026-04-06",
            },
        )
        self.assertEqual(member_expense.status_code, 201)

        owner_user_id = self._current_user_id()
        owner_filtered = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&owner_user_id={owner_user_id}"
        )
        self.assertEqual(owner_filtered.status_code, 200)
        owner_payload = owner_filtered.json()
        self.assertEqual(owner_payload["owner_user_id"], owner_user_id)
        self.assertEqual(owner_payload["total"], 1)
        self.assertEqual([item["comment"] for item in owner_payload["transactions"]], ["Owner only item"])

        member_filtered = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&owner_user_id={second_user_id}"
        )
        self.assertEqual(member_filtered.status_code, 200)
        member_payload = member_filtered.json()
        self.assertEqual(member_payload["owner_user_id"], second_user_id)
        self.assertEqual(member_payload["total"], 1)
        self.assertEqual([item["comment"] for item in member_payload["transactions"]], ["Member only item"])

        not_member_filtered = self.client.get(
            f"/api/v1/families/{family_id}/transactions?period=month&owner_user_id=999999"
        )
        self.assertEqual(not_member_filtered.status_code, 404)

        second_client.close()

    def test_category_summary_supports_personal_and_family_scope(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья сводка"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"summary-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)
        second_user_id = int(second_register.json()["user"]["id"])

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_token = str(invite_response.json()["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)

        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]["name"]

        owner_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 1000.0,
                "comment": "Owner summary expense",
                "date": "2026-04-05",
            },
        )
        self.assertEqual(owner_expense.status_code, 201)

        member_expense = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category,
                "amount": 500.0,
                "comment": "Member summary expense",
                "date": "2026-04-11",
            },
        )
        self.assertEqual(member_expense.status_code, 201)

        owner_db_token = core.push_db_name(auth_service.get_user_db_path(self._current_user_id()))
        try:
            core.add_planned_transaction(
                "expense",
                expense_category,
                700.0,
                "Owner future planned summary",
                "2026-04-20",
            )
        finally:
            core.pop_db_name(owner_db_token)

        personal_summary = self.client.get("/api/v1/reports/category-summary?type=expense&period=month")
        self.assertEqual(personal_summary.status_code, 200)
        self.assertEqual(personal_summary.json()["scope"], "personal")
        self.assertEqual(personal_summary.json()["total"], 1000.0)
        self.assertEqual(personal_summary.json()["categories_count"], 1)
        self.assertEqual(personal_summary.json()["items"][0]["category"], expense_category)

        family_summary = self.client.get(f"/api/v1/reports/category-summary?type=expense&period=month&family_id={family_id}")
        self.assertEqual(family_summary.status_code, 200)
        self.assertEqual(family_summary.json()["scope"], "family")
        self.assertEqual(family_summary.json()["total"], 1500.0)
        self.assertEqual(family_summary.json()["family_id"], family_id)
        self.assertEqual(family_summary.json()["items"][0]["category"], expense_category)

        second_client.close()

    def test_budget_status_supports_family_scope(self):
        create_family = self.client.post("/api/v1/families", json={"name": "Семья бюджет"})
        self.assertEqual(create_family.status_code, 201)
        family_id = int(create_family.json()["id"])

        second_client = TestClient(app)
        second_email = f"family-budget-{uuid4().hex[:8]}@example.com"
        second_register = second_client.post(
            "/api/v1/auth/register",
            json={"email": second_email, "password": "AnotherPass123"},
        )
        self.assertEqual(second_register.status_code, 201)

        invite_response = self.client.post(
            f"/api/v1/families/{family_id}/invites",
            json={"email": second_email, "role": "member"},
        )
        self.assertEqual(invite_response.status_code, 200)
        invite_token = str(invite_response.json()["invite_token"])

        accept_response = second_client.post(
            "/api/v1/families/invites/accept",
            json={"token": invite_token},
        )
        self.assertEqual(accept_response.status_code, 200)

        expense_category = self.client.get("/api/v1/categories?type=expense").json()[0]

        budget_created = self.client.post(
            "/api/v1/budgets",
            json={
                "category_id": expense_category["id"],
                "amount": 3000.0,
                "period": "monthly",
            },
        )
        self.assertEqual(budget_created.status_code, 201)

        owner_expense = self.client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category["name"],
                "amount": 1000.0,
                "comment": "Owner family budget expense",
                "date": "2026-04-05",
            },
        )
        self.assertEqual(owner_expense.status_code, 201)

        member_expense = second_client.post(
            "/api/v1/transactions",
            json={
                "type": "expense",
                "category_name": expense_category["name"],
                "amount": 700.0,
                "comment": "Member family budget expense",
                "date": "2026-04-12",
            },
        )
        self.assertEqual(member_expense.status_code, 201)

        personal_status = self.client.get("/api/v1/budgets/status")
        self.assertEqual(personal_status.status_code, 200)
        personal_item = next(
            item for item in personal_status.json() if item["category_id"] == expense_category["id"]
        )
        self.assertEqual(personal_item["spent"], 1000.0)
        self.assertEqual(personal_item["remaining"], 2000.0)

        family_status = self.client.get(f"/api/v1/budgets/status?family_id={family_id}")
        self.assertEqual(family_status.status_code, 200)
        family_item = next(
            item for item in family_status.json() if item["category_id"] == expense_category["id"]
        )
        self.assertEqual(family_item["spent"], 1700.0)
        self.assertEqual(family_item["remaining"], 1300.0)

        second_client.close()

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

    def test_dashboard_auto_executes_planned_transactions_scheduled_for_today(self):
        income_category = self.client.get("/api/v1/categories?type=income").json()[0]["name"]
        due_today = datetime.now().strftime("%Y-%m-%d")

        db_token = self._push_current_user_db()
        try:
            with core.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("income", income_category, 1700.0, "Auto today income", due_today, "planned", 502),
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
            any(item["comment"] == "Auto today income" and item["status"] == "actual" for item in transactions)
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
