import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import core
from backend.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


class AuthService:
    def __init__(self, auth_db_name: str, users_data_dir: str, session_secret: str):
        self.auth_db_name = str(Path(auth_db_name).resolve())
        self.users_data_dir = str(Path(users_data_dir).resolve())
        self.session_secret = session_secret.encode("utf-8")
        self._shared_memory_conn: Optional[sqlite3.Connection] = None
        os.makedirs(os.path.dirname(self.auth_db_name), exist_ok=True)

    def _auth_connection(self):
        if self.auth_db_name == ":memory:":
            if self._shared_memory_conn is None:
                self._shared_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._shared_memory_conn.row_factory = sqlite3.Row
            return self._shared_memory_conn

        os.makedirs(os.path.dirname(self.auth_db_name), exist_ok=True)
        conn = sqlite3.connect(self.auth_db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def init_auth_db(self) -> None:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    ip TEXT,
                    user_agent TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    revoked_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rate_key TEXT NOT NULL,
                    email TEXT NOT NULL,
                    ip TEXT,
                    success INTEGER NOT NULL,
                    attempted_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_login_attempts_rate_key_time ON login_attempts(rate_key, attempted_at)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    email TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ip TEXT,
                    user_agent TEXT,
                    detail TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_events_created_at ON auth_events(created_at)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id
                ON password_reset_tokens(user_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at
                ON password_reset_tokens(expires_at)
                """
            )
            conn.commit()
        self.cleanup_expired_sessions()

    def close(self) -> None:
        if self._shared_memory_conn is not None:
            self._shared_memory_conn.close()
            self._shared_memory_conn = None

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        n = 2 ** 14
        r = 8
        p = 1
        derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        hash_b64 = base64.b64encode(derived).decode("ascii")
        return f"scrypt${n}${r}${p}${salt_b64}${hash_b64}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            algorithm, n_raw, r_raw, p_raw, salt_b64, hash_b64 = password_hash.split("$", 5)
            if algorithm != "scrypt":
                return False
            n = int(n_raw)
            r = int(r_raw)
            p = int(p_raw)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(hash_b64.encode("ascii"))
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def get_user_by_email(self, email: str) -> Optional[sqlite3.Row]:
        normalized = self._normalize_email(email)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (normalized,))
            return cursor.fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[sqlite3.Row]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,))
            return cursor.fetchone()

    def get_user_public(self, user_row: sqlite3.Row) -> Dict[str, object]:
        return {
            "id": int(user_row["id"]),
            "email": str(user_row["email"]),
            "is_active": bool(user_row["is_active"]),
        }

    def create_user(self, email: str, password: str) -> Dict[str, object]:
        normalized = self._normalize_email(email)
        password_hash = self.hash_password(password)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                (normalized, password_hash),
            )
            conn.commit()
            user_id = int(cursor.lastrowid)
        self.ensure_user_finance_db(user_id)
        user_row = self.get_user_by_id(user_id)
        if not user_row:
            raise RuntimeError("User creation succeeded but user not found")
        return self.get_user_public(user_row)

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, object]]:
        user_row = self.get_user_by_email(email)
        if not user_row or not bool(user_row["is_active"]):
            return None
        if not self.verify_password(password, str(user_row["password_hash"])):
            return None
        return self.get_user_public(user_row)

    def _token_hash(self, raw_token: str) -> str:
        return hmac.new(self.session_secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_session(self, user_id: int, ip: str = "", user_agent: str = "") -> str:
        raw_token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(raw_token)
        expires_at = _format_utc(_utcnow() + timedelta(hours=settings.session_ttl_hours))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (user_id, token_hash, expires_at, ip, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (user_id, token_hash, expires_at, ip or "", user_agent or ""),
            )
            conn.commit()
        self.cleanup_expired_sessions()
        return raw_token

    def resolve_session(self, raw_token: str) -> Optional[Dict[str, object]]:
        token_hash = self._token_hash(raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.user_id, s.expires_at, s.revoked_at, u.id, u.email, u.is_active
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["revoked_at"]:
                return None
            if _parse_utc(str(row["expires_at"])) < _utcnow():
                self.revoke_session(raw_token)
                return None
            if not bool(row["is_active"]):
                return None
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "is_active": bool(row["is_active"]),
            }

    def revoke_session(self, raw_token: str) -> None:
        token_hash = self._token_hash(raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = datetime('now')
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (token_hash,),
            )
            conn.commit()

    def revoke_all_user_sessions(self, user_id: int) -> int:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = datetime('now')
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (user_id,),
            )
            conn.commit()
            return int(cursor.rowcount)

    def cleanup_expired_sessions(self) -> int:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM sessions
                WHERE revoked_at IS NOT NULL OR expires_at < ?
                """,
                (_format_utc(_utcnow()),),
            )
            conn.commit()
            return int(cursor.rowcount)

    def update_user_password(self, user_id: int, new_password: str) -> bool:
        password_hash = self.hash_password(new_password)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (password_hash, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_password_reset_tokens(self) -> int:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM password_reset_tokens
                WHERE used_at IS NOT NULL OR expires_at < ?
                """,
                (_format_utc(_utcnow()),),
            )
            conn.commit()
            return int(cursor.rowcount)

    def create_password_reset_token(self, email: str) -> Optional[str]:
        user = self.get_user_by_email(email)
        if not user or not bool(user["is_active"]):
            return None
        raw_token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(raw_token)
        expires_at = _format_utc(_utcnow() + timedelta(minutes=30))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (int(user["id"]), token_hash, expires_at),
            )
            conn.commit()
        self.cleanup_password_reset_tokens()
        return raw_token

    def reset_password_by_token(self, raw_token: str, new_password: str) -> Optional[Dict[str, object]]:
        token_hash = self._token_hash(raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT prt.id AS reset_id, prt.user_id, prt.expires_at, prt.used_at, u.email, u.is_active
                FROM password_reset_tokens prt
                JOIN users u ON u.id = prt.user_id
                WHERE prt.token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["used_at"] or _parse_utc(str(row["expires_at"])) < _utcnow() or not bool(row["is_active"]):
                return None
            user_id = int(row["user_id"])
            password_hash = self.hash_password(new_password)
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (password_hash, user_id),
            )
            cursor.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = datetime('now')
                WHERE id = ?
                """,
                (int(row["reset_id"]),),
            )
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = datetime('now')
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (user_id,),
            )
            conn.commit()
        self.cleanup_password_reset_tokens()
        return {
            "id": user_id,
            "email": str(row["email"]),
        }

    def _rate_limit_key(self, email: str, ip: str = "") -> str:
        return f"{self._normalize_email(email)}|{(ip or '').strip()}"

    def _cleanup_old_login_attempts(self) -> None:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            retention_minutes = max(settings.login_rate_limit_window_minutes * 4, 60)
            cursor.execute(
                "DELETE FROM login_attempts WHERE attempted_at < datetime('now', ?)",
                (f"-{retention_minutes} minutes",),
            )
            conn.commit()

    def record_login_attempt(self, email: str, ip: str = "", success: bool = False) -> None:
        rate_key = self._rate_limit_key(email, ip)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO login_attempts (rate_key, email, ip, success, attempted_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (rate_key, self._normalize_email(email), ip or "", 1 if success else 0),
            )
            conn.commit()
        self._cleanup_old_login_attempts()

    def is_login_rate_limited(self, email: str, ip: str = "") -> bool:
        rate_key = self._rate_limit_key(email, ip)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS attempts
                FROM login_attempts
                WHERE rate_key = ?
                  AND success = 0
                  AND attempted_at >= datetime('now', ?)
                """,
                (rate_key, f"-{settings.login_rate_limit_window_minutes} minutes"),
            )
            row = cursor.fetchone()
            attempts = int(row["attempts"]) if row else 0
            return attempts >= settings.login_rate_limit_attempts

    def log_auth_event(
        self,
        event_type: str,
        status: str,
        user_id: Optional[int] = None,
        email: str = "",
        ip: str = "",
        user_agent: str = "",
        detail: str = "",
    ) -> None:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO auth_events (user_id, email, event_type, status, ip, user_agent, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    user_id,
                    self._normalize_email(email) if email else None,
                    event_type,
                    status,
                    ip or "",
                    user_agent or "",
                    detail or "",
                ),
            )
            conn.commit()

    def get_user_db_path(self, user_id: int) -> str:
        base_dir = Path(self.users_data_dir)
        return str((base_dir / str(user_id) / "finance.db").resolve())

    def ensure_user_finance_db(self, user_id: int) -> str:
        db_path = self.get_user_db_path(user_id)
        user_dir = os.path.dirname(db_path)
        os.makedirs(user_dir, exist_ok=True)
        if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
            return db_path
        token = core.push_db_name(db_path)
        try:
            core.init_db()
        finally:
            core.pop_db_name(token)
        return db_path


auth_service = AuthService(
    auth_db_name=settings.auth_db_name,
    users_data_dir=settings.users_data_dir,
    session_secret=settings.session_secret,
)
