from __future__ import annotations

from typing import Any, Dict, Optional

from tools.mysql_schema import mysql_connect


class MySqlAuthWriteRepository:
    """MySQL auth write adapter for guarded auth/session migration probes."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return mysql_connect(self.database_url)

    def _user_id_by_legacy(self, conn, legacy_user_id: int) -> Optional[int]:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM auth_users WHERE legacy_sqlite_user_id = %s",
                (int(legacy_user_id),),
            )
            row = cursor.fetchone()
        return int(row["id"]) if row else None

    def mirror_user(self, conn, user: Dict[str, Any]) -> Dict[str, Any]:
        legacy_user_id = int(user["id"])
        email = str(user["email"]).strip().lower()
        values = (
            email,
            str(user.get("password_hash") or "migration-placeholder"),
            bool(user.get("email_verified", True)),
            bool(user.get("is_active", True)),
            legacy_user_id,
        )
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_users (
                    email, password_hash, email_verified, is_active, legacy_sqlite_user_id
                )
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    email = VALUES(email),
                    password_hash = VALUES(password_hash),
                    email_verified = VALUES(email_verified),
                    is_active = VALUES(is_active),
                    legacy_sqlite_user_id = VALUES(legacy_sqlite_user_id)
                """,
                values,
            )
        user_id = self._user_id_by_legacy(conn, legacy_user_id)
        return {"status": "upserted", "user_id": user_id}

    def mirror_session(self, conn, legacy_user_id: int, session: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_sessions (
                    user_id, token_hash, expires_at, ip, user_agent, revoked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    user_id = VALUES(user_id),
                    expires_at = VALUES(expires_at),
                    ip = VALUES(ip),
                    user_agent = VALUES(user_agent),
                    revoked_at = VALUES(revoked_at)
                """,
                (
                    user_id,
                    str(session["token_hash"]),
                    str(session["expires_at"]),
                    session.get("ip") or "",
                    session.get("user_agent") or "",
                    session.get("revoked_at"),
                ),
            )
            cursor.execute("SELECT id FROM auth_sessions WHERE token_hash = %s", (str(session["token_hash"]),))
            row = cursor.fetchone()
        return {"status": "upserted", "session_id": int(row["id"]) if row else None}

    def mirror_user_preferences(self, conn, legacy_user_id: int, preferences: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_user_preferences (user_id, theme_mode, workspace_mode, display_name)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    theme_mode = VALUES(theme_mode),
                    workspace_mode = VALUES(workspace_mode),
                    display_name = VALUES(display_name)
                """,
                (
                    user_id,
                    preferences.get("theme_mode") or "system",
                    preferences.get("workspace_mode") or "personal",
                    preferences.get("display_name") or "",
                ),
            )
        return {"status": "upserted", "user_id": user_id}

    def mirror_login_attempt(self, conn, attempt: Dict[str, Any]) -> Dict[str, Any]:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_login_attempts (rate_key, email, ip, success)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    str(attempt["rate_key"]),
                    str(attempt["email"]).strip().lower(),
                    attempt.get("ip") or "",
                    bool(attempt.get("success", False)),
                ),
            )
            attempt_id = int(cursor.lastrowid)
        return {"status": "inserted", "attempt_id": attempt_id}

    def mirror_auth_event(self, conn, legacy_user_id: Optional[int], event: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._user_id_by_legacy(conn, legacy_user_id) if legacy_user_id is not None else None
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_auth_events (user_id, email, event_type, status, ip, user_agent, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    str(event.get("email") or "").strip().lower() or None,
                    str(event["event_type"]),
                    str(event["status"]),
                    event.get("ip") or "",
                    event.get("user_agent") or "",
                    event.get("detail") or "",
                ),
            )
            event_id = int(cursor.lastrowid)
        return {"status": "inserted", "event_id": event_id}

    def mirror_token(self, conn, legacy_user_id: int, table: str, token: Dict[str, Any]) -> Dict[str, Any]:
        if table not in {"password_reset_tokens", "email_verification_tokens", "account_deletion_tokens"}:
            raise ValueError(f"Unsupported auth token table: {table}")
        user_id = self._user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            raise RuntimeError(f"MySQL user for legacy user {legacy_user_id} was not found")
        target_table = f"auth_{table}"
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {target_table} (user_id, token_hash, expires_at, used_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    user_id = VALUES(user_id),
                    expires_at = VALUES(expires_at),
                    used_at = VALUES(used_at)
                """,
                (
                    user_id,
                    str(token["token_hash"]),
                    str(token["expires_at"]),
                    token.get("used_at"),
                ),
            )
            cursor.execute(f"SELECT id FROM {target_table} WHERE token_hash = %s", (str(token["token_hash"]),))
            row = cursor.fetchone()
        return {"status": "upserted", "token_id": int(row["id"]) if row else None}
