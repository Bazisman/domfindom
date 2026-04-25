import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

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
        self._ensured_finance_dbs: Set[str] = set()
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
                    email_verified INTEGER NOT NULL DEFAULT 1,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor.execute("PRAGMA table_info(users)")
            user_columns = {str(row["name"]) for row in cursor.fetchall()}
            if "email_verified" not in user_columns:
                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
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
                CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user_id
                ON email_verification_tokens(user_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_expires_at
                ON email_verification_tokens(expires_at)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS account_deletion_tokens (
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
                CREATE INDEX IF NOT EXISTS idx_account_deletion_tokens_user_id
                ON account_deletion_tokens(user_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_account_deletion_tokens_expires_at
                ON account_deletion_tokens(expires_at)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    theme_mode TEXT NOT NULL DEFAULT 'system',
                    workspace_mode TEXT NOT NULL DEFAULT 'personal',
                    display_name TEXT NOT NULL DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute("PRAGMA table_info(user_preferences)")
            preference_columns = {str(row["name"]) for row in cursor.fetchall()}
            if "workspace_mode" not in preference_columns:
                cursor.execute(
                    """
                    ALTER TABLE user_preferences
                    ADD COLUMN workspace_mode TEXT NOT NULL DEFAULT 'personal'
                    """
                )
            if "display_name" not in preference_columns:
                cursor.execute(
                    """
                    ALTER TABLE user_preferences
                    ADD COLUMN display_name TEXT NOT NULL DEFAULT ''
                    """
                )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_backup_slot (
                    user_id INTEGER PRIMARY KEY,
                    backup_blob TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS families (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    archived_at TEXT,
                    FOREIGN KEY (owner_user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_owner ON families(owner_user_id)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    invited_by_user_id INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (invited_by_user_id) REFERENCES users(id),
                    UNIQUE(family_id, user_id)
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_memberships_family ON family_memberships(family_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_memberships_user ON family_memberships(user_id, status)")
            # Legacy role migration: collapse old roles into member.
            cursor.execute(
                """
                UPDATE family_memberships
                SET role = 'member', updated_at = datetime('now')
                WHERE role IN ('admin', 'accountant')
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    invited_by_user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    accepted_at TEXT,
                    revoked_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (invited_by_user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_invites_family ON family_invites(family_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_invites_email ON family_invites(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_family_invites_expires ON family_invites(expires_at)")
            cursor.execute(
                """
                UPDATE family_invites
                SET role = 'member'
                WHERE role IN ('admin', 'accountant')
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_capital_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    capital_account_id INTEGER NOT NULL,
                    is_visible INTEGER NOT NULL DEFAULT 0,
                    is_default_target INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (owner_user_id) REFERENCES users(id),
                    UNIQUE(family_id, owner_user_id, capital_account_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_family_capital_accounts_family
                ON family_capital_accounts(family_id, is_visible)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_capital_member_settings (
                    family_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    target_owner_user_id INTEGER,
                    target_capital_account_id INTEGER,
                    updated_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (family_id, user_id),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_capital_contributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    source_user_id INTEGER NOT NULL,
                    source_transaction_id INTEGER NOT NULL,
                    target_owner_user_id INTEGER NOT NULL,
                    target_capital_account_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    date TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    reversed_at TEXT,
                    UNIQUE(source_user_id, source_transaction_id),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (source_user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_family_capital_contributions_family
                ON family_capital_contributions(family_id, reversed_at)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    semantic_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'both',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by_user_id INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
                    UNIQUE(family_id, semantic_key)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_family_categories_family
                ON family_categories(family_id, is_active)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_category_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    family_category_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    local_category_id INTEGER NOT NULL,
                    local_category_name TEXT NOT NULL,
                    local_category_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    confirmed_by_user_id INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (family_category_id) REFERENCES family_categories(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (confirmed_by_user_id) REFERENCES users(id),
                    UNIQUE(family_id, user_id, local_category_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_family_category_bindings_family
                ON family_category_bindings(family_id, status)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS family_category_audit_resolutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    group_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    category_names_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    resolved_by_user_id INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (family_id) REFERENCES families(id),
                    FOREIGN KEY (resolved_by_user_id) REFERENCES users(id),
                    UNIQUE(family_id, code, group_key, action)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_family_category_audit_resolutions_family
                ON family_category_audit_resolutions(family_id, code, group_key)
                """
            )
            conn.commit()
        self.cleanup_expired_sessions()
        self.cleanup_password_reset_tokens()
        self.cleanup_email_verification_tokens()
        self.cleanup_account_deletion_tokens()

    def close(self) -> None:
        if self._shared_memory_conn is not None:
            self._shared_memory_conn.close()
            self._shared_memory_conn = None
        self._ensured_finance_dbs.clear()

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
            "email_verified": bool(user_row["email_verified"]) if "email_verified" in user_row.keys() else True,
            "is_active": bool(user_row["is_active"]),
        }

    def create_user(self, email: str, password: str, email_verified: bool = True) -> Dict[str, object]:
        normalized = self._normalize_email(email)
        password_hash = self.hash_password(password)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, email_verified, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (normalized, password_hash, 1 if email_verified else 0),
            )
            conn.commit()
            user_id = int(cursor.lastrowid)
        self.ensure_user_finance_db(user_id)
        user_row = self.get_user_by_id(user_id)
        if not user_row:
            raise RuntimeError("Пользователь создан, но запись не найдена")
        return self.get_user_public(user_row)

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, object]]:
        user_row = self.get_user_by_email(email)
        if not user_row or not bool(user_row["is_active"]):
            return None
        if settings.require_email_verification and not bool(user_row["email_verified"]):
            return None
        if not self.verify_password(password, str(user_row["password_hash"])):
            return None
        return self.get_user_public(user_row)

    def is_email_verified(self, user_row: sqlite3.Row) -> bool:
        if "email_verified" not in user_row.keys():
            return True
        return bool(user_row["email_verified"])

    def _token_hash(self, raw_token: str) -> str:
        return hmac.new(self.session_secret, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_csrf_token(self, raw_session_token: str) -> str:
        payload = f"csrf:{raw_session_token}"
        return hmac.new(self.session_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_csrf_token(self, raw_session_token: str, provided_token: str) -> bool:
        if not raw_session_token or not provided_token:
            return False
        expected = self.create_csrf_token(raw_session_token)
        return hmac.compare_digest(expected, provided_token)

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
                SELECT s.user_id, s.expires_at, s.revoked_at, u.id, u.email, u.email_verified, u.is_active
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
                "email_verified": bool(row["email_verified"]) if "email_verified" in row.keys() else True,
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

    def revoke_other_user_sessions(self, user_id: int, current_raw_token: str) -> int:
        current_token_hash = self._token_hash(current_raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = datetime('now')
                WHERE user_id = ?
                  AND revoked_at IS NULL
                  AND token_hash != ?
                """,
                (user_id, current_token_hash),
            )
            conn.commit()
            return int(cursor.rowcount)

    def revoke_user_session_by_id(self, user_id: int, session_id: int) -> bool:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = datetime('now')
                WHERE id = ?
                  AND user_id = ?
                  AND revoked_at IS NULL
                """,
                (session_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_active_user_sessions(self, user_id: int, current_raw_token: str, limit: int = 8) -> List[Dict[str, object]]:
        safe_limit = max(1, min(limit, 50))
        current_token_hash = self._token_hash(current_raw_token) if current_raw_token else ""
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, ip, user_agent, created_at, expires_at, token_hash
                FROM sessions
                WHERE user_id = ?
                  AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        now = _utcnow()
        sessions: List[Dict[str, object]] = []
        for row in rows:
            expires_at = _parse_utc(str(row["expires_at"]))
            if expires_at < now:
                continue
            sessions.append(
                {
                    "id": int(row["id"]),
                    "ip": str(row["ip"] or ""),
                    "user_agent": str(row["user_agent"] or ""),
                    "created_at": str(row["created_at"] or ""),
                    "expires_at": str(row["expires_at"] or ""),
                    "is_current": bool(current_token_hash and str(row["token_hash"]) == current_token_hash),
                }
            )
            if len(sessions) >= safe_limit:
                break
        return sessions

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

    def cleanup_email_verification_tokens(self) -> int:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM email_verification_tokens
                WHERE used_at IS NOT NULL OR expires_at < ?
                """,
                (_format_utc(_utcnow()),),
            )
            conn.commit()
            return int(cursor.rowcount)

    def cleanup_account_deletion_tokens(self) -> int:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM account_deletion_tokens
                WHERE used_at IS NOT NULL OR expires_at < ?
                """,
                (_format_utc(_utcnow()),),
            )
            conn.commit()
            return int(cursor.rowcount)

    def create_email_verification_token(self, user_id: int) -> Optional[str]:
        user = self.get_user_by_id(user_id)
        if not user or not bool(user["is_active"]):
            return None
        if self.is_email_verified(user):
            return None
        raw_token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(raw_token)
        expires_at = _format_utc(_utcnow() + timedelta(hours=settings.email_verification_token_ttl_hours))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE email_verification_tokens
                SET used_at = datetime('now')
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (user_id, token_hash, expires_at),
            )
            conn.commit()
        self.cleanup_email_verification_tokens()
        return raw_token

    def verify_email_by_token(self, raw_token: str) -> Optional[Dict[str, object]]:
        token_hash = self._token_hash(raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT evt.id AS verify_id, evt.user_id, evt.expires_at, evt.used_at, u.email, u.is_active, u.email_verified
                FROM email_verification_tokens evt
                JOIN users u ON u.id = evt.user_id
                WHERE evt.token_hash = ?
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
            cursor.execute(
                """
                UPDATE users
                SET email_verified = 1, updated_at = datetime('now')
                WHERE id = ?
                """,
                (user_id,),
            )
            cursor.execute(
                """
                UPDATE email_verification_tokens
                SET used_at = datetime('now')
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user_id,),
            )
            conn.commit()
        self.cleanup_email_verification_tokens()
        user_row = self.get_user_by_id(user_id)
        if not user_row:
            return None
        return self.get_user_public(user_row)

    def create_account_deletion_token(self, user_id: int) -> Optional[str]:
        user = self.get_user_by_id(user_id)
        if not user or not bool(user["is_active"]):
            return None
        raw_token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(raw_token)
        expires_at = _format_utc(_utcnow() + timedelta(minutes=settings.account_delete_token_ttl_minutes))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE account_deletion_tokens
                SET used_at = datetime('now')
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO account_deletion_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (user_id, token_hash, expires_at),
            )
            conn.commit()
        self.cleanup_account_deletion_tokens()
        return raw_token

    def _delete_user_account_by_id(self, user_id: int, user_email: str) -> bool:
        normalized_email = self._normalize_email(user_email)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id
                FROM families
                WHERE owner_user_id = ?
                """,
                (user_id,),
            )
            owned_family_ids = [int(row["id"]) for row in cursor.fetchall()]

            cursor.execute("BEGIN")
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM account_deletion_tokens WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_backup_slot WHERE user_id = ?", (user_id,))
            cursor.execute(
                "DELETE FROM auth_events WHERE user_id = ? OR lower(email) = ?",
                (user_id, normalized_email),
            )
            cursor.execute(
                "DELETE FROM login_attempts WHERE lower(email) = ? OR rate_key LIKE ?",
                (normalized_email, f"{normalized_email}|%"),
            )

            if owned_family_ids:
                marks = ",".join("?" for _ in owned_family_ids)
                cursor.execute(f"DELETE FROM family_category_audit_resolutions WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_category_bindings WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_categories WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_capital_contributions WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_capital_member_settings WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_capital_accounts WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_invites WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM family_memberships WHERE family_id IN ({marks})", owned_family_ids)
                cursor.execute(f"DELETE FROM families WHERE id IN ({marks})", owned_family_ids)

            cursor.execute("DELETE FROM family_category_bindings WHERE user_id = ? OR confirmed_by_user_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM family_category_audit_resolutions WHERE resolved_by_user_id = ?", (user_id,))
            cursor.execute("DELETE FROM family_capital_contributions WHERE source_user_id = ? OR target_owner_user_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM family_capital_member_settings WHERE user_id = ? OR target_owner_user_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM family_capital_accounts WHERE owner_user_id = ?", (user_id,))
            cursor.execute(
                "DELETE FROM family_invites WHERE invited_by_user_id = ? OR lower(email) = ?",
                (user_id, normalized_email),
            )
            cursor.execute("DELETE FROM family_memberships WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

        user_dir = Path(self.users_data_dir) / str(user_id)
        if user_dir.exists():
            try:
                import shutil

                shutil.rmtree(str(user_dir), ignore_errors=True)
            except Exception:
                pass
        return True

    def delete_account_by_token(self, raw_token: str) -> Optional[str]:
        token_hash = self._token_hash(raw_token)
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT adt.id AS delete_id, adt.user_id, adt.expires_at, adt.used_at, u.email, u.is_active
                FROM account_deletion_tokens adt
                JOIN users u ON u.id = adt.user_id
                WHERE adt.token_hash = ?
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
            user_email = str(row["email"] or "")
            cursor.execute(
                """
                UPDATE account_deletion_tokens
                SET used_at = datetime('now')
                WHERE user_id = ? AND used_at IS NULL
                """,
                (user_id,),
            )
            conn.commit()

        self._delete_user_account_by_id(user_id, user_email)
        self.cleanup_account_deletion_tokens()
        return user_email

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
                SELECT prt.id AS reset_id, prt.user_id, prt.expires_at, prt.used_at, u.email, u.email_verified, u.is_active
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
            "email_verified": bool(row["email_verified"]) if "email_verified" in row.keys() else True,
            "is_active": bool(row["is_active"]),
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

    def list_user_auth_events(self, user_id: int, limit: int = 20) -> List[Dict[str, str]]:
        safe_limit = max(1, min(limit, 100))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_type, status, detail, ip, user_agent, created_at
                FROM auth_events
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            )
            rows = cursor.fetchall()

        return [
            {
                "event_type": str(row["event_type"] or ""),
                "status": str(row["status"] or ""),
                "detail": str(row["detail"] or ""),
                "ip": str(row["ip"] or ""),
                "user_agent": str(row["user_agent"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

    def get_user_db_path(self, user_id: int) -> str:
        base_dir = Path(self.users_data_dir)
        return str((base_dir / str(user_id) / "finance.db").resolve())

    def ensure_user_finance_db(self, user_id: int) -> str:
        db_path = self.get_user_db_path(user_id)
        user_dir = os.path.dirname(db_path)
        os.makedirs(user_dir, exist_ok=True)
        if db_path in self._ensured_finance_dbs:
            return db_path
        token = core.push_db_name(db_path)
        try:
            core.init_db()
        finally:
            core.pop_db_name(token)
        self._ensured_finance_dbs.add(db_path)
        return db_path

    def get_user_preferences(self, user_id: int) -> Dict[str, str]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT theme_mode, workspace_mode, display_name
                FROM user_preferences
                WHERE user_id = ?
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            return {"theme_mode": "system", "workspace_mode": "personal", "display_name": ""}
        theme_mode = str(row["theme_mode"] or "system")
        if theme_mode not in {"light", "dark", "system"}:
            theme_mode = "system"
        workspace_mode = str(row["workspace_mode"] or "personal")
        if workspace_mode not in {"personal", "family"}:
            workspace_mode = "personal"
        display_name = str(row["display_name"] or "").strip()
        if len(display_name) > 80:
            display_name = display_name[:80].strip()
        return {"theme_mode": theme_mode, "workspace_mode": workspace_mode, "display_name": display_name}

    def update_user_preferences(
        self,
        user_id: int,
        theme_mode: str = "",
        workspace_mode: str = "",
        display_name: Optional[str] = None,
    ) -> Dict[str, str]:
        current = self.get_user_preferences(user_id)
        normalized_theme = theme_mode if theme_mode in {"light", "dark", "system"} else str(current.get("theme_mode", "system"))
        normalized_workspace = (
            workspace_mode if workspace_mode in {"personal", "family"} else str(current.get("workspace_mode", "personal"))
        )
        normalized_display_name = str(display_name).strip() if display_name is not None else str(current.get("display_name", "")).strip()
        if len(normalized_display_name) > 80:
            normalized_display_name = normalized_display_name[:80].strip()
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_preferences (user_id, theme_mode, workspace_mode, display_name, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    theme_mode = excluded.theme_mode,
                    workspace_mode = excluded.workspace_mode,
                    display_name = excluded.display_name,
                    updated_at = datetime('now')
                """,
                (user_id, normalized_theme, normalized_workspace, normalized_display_name),
            )
            conn.commit()
        return {
            "theme_mode": normalized_theme,
            "workspace_mode": normalized_workspace,
            "display_name": normalized_display_name,
        }

    def create_family(self, owner_user_id: int, name: str) -> Dict[str, object]:
        clean_name = (name or "").strip()
        if len(clean_name) < 2:
            raise ValueError("Название семьи слишком короткое")

        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO families (name, owner_user_id, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                """,
                (clean_name, owner_user_id),
            )
            family_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO family_memberships (family_id, user_id, role, status, created_at, updated_at)
                VALUES (?, ?, 'owner', 'active', datetime('now'), datetime('now'))
                """,
                (family_id, owner_user_id),
            )
            conn.commit()

        return {
            "id": family_id,
            "name": clean_name,
            "role": "owner",
            "status": "active",
            "created_at": _format_utc(_utcnow()),
        }

    def list_user_families(self, user_id: int) -> List[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT f.id, f.name, fm.role, fm.status, f.created_at
                FROM family_memberships fm
                JOIN families f ON f.id = fm.family_id
                WHERE fm.user_id = ?
                  AND fm.status = 'active'
                  AND f.archived_at IS NULL
                ORDER BY f.created_at DESC, f.id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": str(row["name"] or ""),
                "role": str(row["role"] or "member"),
                "status": str(row["status"] or "active"),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

    def get_primary_family(self, user_id: int) -> Optional[Dict[str, object]]:
        families = self.list_user_families(user_id)
        return families[0] if families else None

    def get_family_membership(self, family_id: int, user_id: int) -> Optional[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fm.family_id, fm.user_id, fm.role, fm.status, fm.created_at, f.name
                FROM family_memberships fm
                JOIN families f ON f.id = fm.family_id
                WHERE fm.family_id = ?
                  AND fm.user_id = ?
                  AND fm.status = 'active'
                  AND f.archived_at IS NULL
                LIMIT 1
                """,
                (family_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "family_id": int(row["family_id"]),
            "user_id": int(row["user_id"]),
            "role": str(row["role"] or "member"),
            "status": str(row["status"] or "active"),
            "joined_at": str(row["created_at"] or ""),
            "family_name": str(row["name"] or ""),
        }

    def list_family_members(self, family_id: int) -> List[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fm.user_id, u.email, COALESCE(up.display_name, '') AS display_name, fm.role, fm.status, fm.created_at
                FROM family_memberships fm
                JOIN users u ON u.id = fm.user_id
                LEFT JOIN user_preferences up ON up.user_id = fm.user_id
                WHERE fm.family_id = ?
                  AND fm.status = 'active'
                ORDER BY
                  CASE fm.role
                    WHEN 'owner' THEN 1
                    WHEN 'member' THEN 2
                    WHEN 'viewer' THEN 3
                    ELSE 4
                  END,
                  fm.created_at ASC
                """,
                (family_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "user_id": int(row["user_id"]),
                "email": str(row["email"] or ""),
                "display_name": str(row["display_name"] or "").strip(),
                "role": str(row["role"] or "member"),
                "status": str(row["status"] or "active"),
                "joined_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

    def ensure_family_category(
        self,
        family_id: int,
        semantic_key: str,
        display_name: str,
        category_type: str,
        created_by_user_id: int,
    ) -> Dict[str, object]:
        clean_semantic_key = (semantic_key or "").strip().lower()
        clean_display_name = (display_name or clean_semantic_key).strip()
        clean_type = (category_type or "both").strip().lower()
        if clean_type not in {"income", "expense", "both"}:
            clean_type = "both"
        if not clean_semantic_key:
            raise ValueError("semantic_key_required")

        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO family_categories (
                    family_id,
                    semantic_key,
                    display_name,
                    type,
                    is_active,
                    created_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'))
                ON CONFLICT(family_id, semantic_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    type = excluded.type,
                    is_active = 1,
                    updated_at = datetime('now')
                """,
                (family_id, clean_semantic_key, clean_display_name, clean_type, created_by_user_id),
            )
            conn.commit()
        category = self.get_family_category_by_semantic_key(family_id, clean_semantic_key)
        if not category:
            raise RuntimeError("family_category_not_found_after_upsert")
        return category

    def get_family_category_by_semantic_key(self, family_id: int, semantic_key: str) -> Optional[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, family_id, semantic_key, display_name, type, is_active, created_by_user_id, created_at, updated_at
                FROM family_categories
                WHERE family_id = ?
                  AND semantic_key = ?
                LIMIT 1
                """,
                (family_id, semantic_key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "family_id": int(row["family_id"]),
            "semantic_key": str(row["semantic_key"] or ""),
            "display_name": str(row["display_name"] or ""),
            "type": str(row["type"] or "both"),
            "is_active": bool(row["is_active"]),
            "created_by_user_id": int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def list_family_category_bindings(self, family_id: int) -> List[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fcb.id,
                       fcb.family_id,
                       fcb.family_category_id,
                       fcb.user_id,
                       fcb.local_category_id,
                       fcb.local_category_name,
                       fcb.local_category_type,
                       fcb.status,
                       fcb.confirmed_by_user_id,
                       fcb.updated_at,
                       fc.semantic_key,
                       fc.display_name AS family_category_name,
                       fc.type AS family_category_type,
                       u.email,
                       COALESCE(up.display_name, '') AS display_name
                FROM family_category_bindings fcb
                JOIN family_categories fc ON fc.id = fcb.family_category_id
                JOIN users u ON u.id = fcb.user_id
                LEFT JOIN user_preferences up ON up.user_id = fcb.user_id
                WHERE fcb.family_id = ?
                  AND fcb.status = 'confirmed'
                  AND fc.is_active = 1
                ORDER BY fc.display_name, fcb.user_id, fcb.local_category_name
                """,
                (family_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "family_id": int(row["family_id"]),
                "family_category_id": int(row["family_category_id"]),
                "user_id": int(row["user_id"]),
                "local_category_id": int(row["local_category_id"]),
                "local_category_name": str(row["local_category_name"] or ""),
                "local_category_type": str(row["local_category_type"] or ""),
                "status": str(row["status"] or "confirmed"),
                "confirmed_by_user_id": int(row["confirmed_by_user_id"]) if row["confirmed_by_user_id"] is not None else None,
                "updated_at": str(row["updated_at"] or ""),
                "semantic_key": str(row["semantic_key"] or ""),
                "family_category_name": str(row["family_category_name"] or ""),
                "family_category_type": str(row["family_category_type"] or "both"),
                "owner_email": str(row["email"] or ""),
                "owner_display_name": str(row["display_name"] or "").strip(),
            }
            for row in rows
        ]

    def upsert_family_category_binding(
        self,
        family_id: int,
        family_category_id: int,
        user_id: int,
        local_category_id: int,
        local_category_name: str,
        local_category_type: str,
        confirmed_by_user_id: int,
    ) -> Dict[str, object]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO family_category_bindings (
                    family_id,
                    family_category_id,
                    user_id,
                    local_category_id,
                    local_category_name,
                    local_category_type,
                    status,
                    confirmed_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?, datetime('now'), datetime('now'))
                ON CONFLICT(family_id, user_id, local_category_id) DO UPDATE SET
                    family_category_id = excluded.family_category_id,
                    local_category_name = excluded.local_category_name,
                    local_category_type = excluded.local_category_type,
                    status = 'confirmed',
                    confirmed_by_user_id = excluded.confirmed_by_user_id,
                    updated_at = datetime('now')
                """,
                (
                    family_id,
                    family_category_id,
                    user_id,
                    local_category_id,
                    local_category_name,
                    local_category_type,
                    confirmed_by_user_id,
                ),
            )
            conn.commit()
            binding_id = int(cursor.lastrowid or 0)

        bindings = self.list_family_category_bindings(family_id)
        if binding_id:
            for binding in bindings:
                if int(binding["id"]) == binding_id:
                    return binding
        for binding in bindings:
            if int(binding["user_id"]) == user_id and int(binding["local_category_id"]) == local_category_id:
                return binding
        return {}

    def list_family_category_audit_resolutions(self, family_id: int) -> List[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id,
                       family_id,
                       code,
                       group_key,
                       action,
                       category_names_json,
                       note,
                       resolved_by_user_id,
                       created_at,
                       updated_at
                FROM family_category_audit_resolutions
                WHERE family_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (family_id,),
            )
            rows = cursor.fetchall()
        resolutions: List[Dict[str, object]] = []
        for row in rows:
            try:
                category_names = json.loads(str(row["category_names_json"] or "[]"))
            except json.JSONDecodeError:
                category_names = []
            if not isinstance(category_names, list):
                category_names = []
            resolutions.append(
                {
                    "id": int(row["id"]),
                    "family_id": int(row["family_id"]),
                    "code": str(row["code"] or ""),
                    "group_key": str(row["group_key"] or ""),
                    "action": str(row["action"] or ""),
                    "category_names": [str(item) for item in category_names],
                    "note": str(row["note"] or ""),
                    "resolved_by_user_id": int(row["resolved_by_user_id"]) if row["resolved_by_user_id"] is not None else None,
                    "created_at": str(row["created_at"] or ""),
                    "updated_at": str(row["updated_at"] or ""),
                }
            )
        return resolutions

    def upsert_family_category_audit_resolution(
        self,
        family_id: int,
        code: str,
        group_key: str,
        action: str,
        category_names: List[str],
        note: str,
        resolved_by_user_id: int,
    ) -> Dict[str, object]:
        clean_code = (code or "").strip()
        clean_group_key = (group_key or "").strip()
        clean_action = (action or "").strip()
        clean_names = [str(name).strip() for name in category_names if str(name).strip()]
        if not clean_code or not clean_group_key or not clean_action:
            raise ValueError("audit_resolution_required")
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO family_category_audit_resolutions (
                    family_id,
                    code,
                    group_key,
                    action,
                    category_names_json,
                    note,
                    resolved_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(family_id, code, group_key, action) DO UPDATE SET
                    category_names_json = excluded.category_names_json,
                    note = excluded.note,
                    resolved_by_user_id = excluded.resolved_by_user_id,
                    updated_at = datetime('now')
                """,
                (
                    family_id,
                    clean_code,
                    clean_group_key,
                    clean_action,
                    json.dumps(clean_names, ensure_ascii=False),
                    (note or "").strip(),
                    resolved_by_user_id,
                ),
            )
            conn.commit()
        for resolution in self.list_family_category_audit_resolutions(family_id):
            if (
                str(resolution["code"]) == clean_code
                and str(resolution["group_key"]) == clean_group_key
                and str(resolution["action"]) == clean_action
            ):
                return resolution
        return {}

    def delete_family_category_audit_resolution(
        self,
        family_id: int,
        code: str,
        group_key: str,
        action: str,
    ) -> bool:
        clean_code = (code or "").strip()
        clean_group_key = (group_key or "").strip()
        clean_action = (action or "").strip()
        if not clean_code or not clean_group_key or not clean_action:
            return False
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM family_category_audit_resolutions
                WHERE family_id = ?
                  AND code = ?
                  AND group_key = ?
                  AND action = ?
                """,
                (family_id, clean_code, clean_group_key, clean_action),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_family_capital_accounts(self, family_id: int) -> List[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fca.family_id,
                       fca.owner_user_id,
                       fca.capital_account_id,
                       fca.is_visible,
                       fca.is_default_target,
                       fca.updated_at,
                       u.email,
                       COALESCE(up.display_name, '') AS display_name
                FROM family_capital_accounts fca
                JOIN users u ON u.id = fca.owner_user_id
                LEFT JOIN user_preferences up ON up.user_id = fca.owner_user_id
                WHERE fca.family_id = ?
                ORDER BY fca.is_default_target DESC, fca.owner_user_id ASC, fca.capital_account_id ASC
                """,
                (family_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "family_id": int(row["family_id"]),
                "owner_user_id": int(row["owner_user_id"]),
                "capital_account_id": int(row["capital_account_id"]),
                "is_visible": bool(row["is_visible"]),
                "is_default_target": bool(row["is_default_target"]),
                "updated_at": str(row["updated_at"] or ""),
                "owner_email": str(row["email"] or ""),
                "owner_display_name": str(row["display_name"] or "").strip(),
            }
            for row in rows
        ]

    def get_family_capital_account(
        self,
        family_id: int,
        owner_user_id: int,
        capital_account_id: int,
    ) -> Optional[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT family_id, owner_user_id, capital_account_id, is_visible, is_default_target, updated_at
                FROM family_capital_accounts
                WHERE family_id = ?
                  AND owner_user_id = ?
                  AND capital_account_id = ?
                LIMIT 1
                """,
                (family_id, owner_user_id, capital_account_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "family_id": int(row["family_id"]),
            "owner_user_id": int(row["owner_user_id"]),
            "capital_account_id": int(row["capital_account_id"]),
            "is_visible": bool(row["is_visible"]),
            "is_default_target": bool(row["is_default_target"]),
            "updated_at": str(row["updated_at"] or ""),
        }

    def upsert_family_capital_account(
        self,
        family_id: int,
        owner_user_id: int,
        capital_account_id: int,
        is_visible: bool,
        is_default_target: bool,
    ) -> Dict[str, object]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            if is_default_target:
                cursor.execute(
                    """
                    UPDATE family_capital_accounts
                    SET is_default_target = 0, updated_at = datetime('now')
                    WHERE family_id = ?
                      AND owner_user_id = ?
                    """,
                    (family_id, owner_user_id),
                )
            cursor.execute(
                """
                INSERT INTO family_capital_accounts (
                    family_id,
                    owner_user_id,
                    capital_account_id,
                    is_visible,
                    is_default_target,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(family_id, owner_user_id, capital_account_id) DO UPDATE SET
                    is_visible = excluded.is_visible,
                    is_default_target = excluded.is_default_target,
                    updated_at = datetime('now')
                """,
                (
                    family_id,
                    owner_user_id,
                    capital_account_id,
                    1 if is_visible else 0,
                    1 if is_default_target else 0,
                ),
            )
            conn.commit()
        return self.get_family_capital_account(family_id, owner_user_id, capital_account_id) or {}

    def hide_family_capital_account(
        self,
        family_id: int,
        owner_user_id: int,
        capital_account_id: int,
    ) -> None:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE family_capital_accounts
                SET is_visible = 0,
                    is_default_target = 0,
                    updated_at = datetime('now')
                WHERE family_id = ?
                  AND owner_user_id = ?
                  AND capital_account_id = ?
                """,
                (family_id, owner_user_id, capital_account_id),
            )
            cursor.execute(
                """
                UPDATE family_capital_member_settings
                SET target_owner_user_id = NULL,
                    target_capital_account_id = NULL,
                    updated_at = datetime('now')
                WHERE family_id = ?
                  AND target_owner_user_id = ?
                  AND target_capital_account_id = ?
                """,
                (family_id, owner_user_id, capital_account_id),
            )
            conn.commit()

    def get_family_default_capital_target(self, family_id: int) -> Optional[Dict[str, int]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT owner_user_id, capital_account_id
                FROM family_capital_accounts
                WHERE family_id = ?
                  AND is_visible = 1
                ORDER BY is_default_target DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                (family_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "owner_user_id": int(row["owner_user_id"]),
            "capital_account_id": int(row["capital_account_id"]),
        }

    def get_family_member_capital_target(self, family_id: int, user_id: int) -> Optional[Dict[str, int]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT target_owner_user_id, target_capital_account_id
                FROM family_capital_member_settings
                WHERE family_id = ?
                  AND user_id = ?
                LIMIT 1
                """,
                (family_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        owner_user_id = row["target_owner_user_id"]
        capital_account_id = row["target_capital_account_id"]
        if owner_user_id is None or capital_account_id is None:
            return None
        return {
            "owner_user_id": int(owner_user_id),
            "capital_account_id": int(capital_account_id),
        }

    def set_family_member_capital_target(
        self,
        family_id: int,
        user_id: int,
        target_owner_user_id: Optional[int],
        target_capital_account_id: Optional[int],
    ) -> Dict[str, object]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO family_capital_member_settings (
                    family_id,
                    user_id,
                    target_owner_user_id,
                    target_capital_account_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(family_id, user_id) DO UPDATE SET
                    target_owner_user_id = excluded.target_owner_user_id,
                    target_capital_account_id = excluded.target_capital_account_id,
                    updated_at = datetime('now')
                """,
                (family_id, user_id, target_owner_user_id, target_capital_account_id),
            )
            conn.commit()
        return {
            "family_id": family_id,
            "user_id": user_id,
            "target_owner_user_id": target_owner_user_id,
            "target_capital_account_id": target_capital_account_id,
        }

    def ensure_family_member_capital_target(self, family_id: int, user_id: int) -> Optional[Dict[str, int]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT target_owner_user_id, target_capital_account_id
                FROM family_capital_member_settings
                WHERE family_id = ?
                  AND user_id = ?
                LIMIT 1
                """,
                (family_id, user_id),
            )
            row = cursor.fetchone()
        if row:
            owner_user_id = row["target_owner_user_id"]
            capital_account_id = row["target_capital_account_id"]
            if owner_user_id is None or capital_account_id is None:
                return None
            return {
                "owner_user_id": int(owner_user_id),
                "capital_account_id": int(capital_account_id),
            }
        default_target = self.get_family_default_capital_target(family_id)
        if not default_target:
            return None
        self.set_family_member_capital_target(
            family_id=family_id,
            user_id=user_id,
            target_owner_user_id=int(default_target["owner_user_id"]),
            target_capital_account_id=int(default_target["capital_account_id"]),
        )
        return default_target

    def create_family_capital_contribution(
        self,
        family_id: int,
        source_user_id: int,
        source_transaction_id: int,
        target_owner_user_id: int,
        target_capital_account_id: int,
        amount: float,
        date: str,
        comment: str = "",
    ) -> Dict[str, object]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO family_capital_contributions (
                    family_id,
                    source_user_id,
                    source_transaction_id,
                    target_owner_user_id,
                    target_capital_account_id,
                    amount,
                    date,
                    comment,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    family_id,
                    source_user_id,
                    source_transaction_id,
                    target_owner_user_id,
                    target_capital_account_id,
                    amount,
                    date,
                    comment,
                ),
            )
            contribution_id = int(cursor.lastrowid)
            conn.commit()
        return {
            "id": contribution_id,
            "family_id": family_id,
            "source_user_id": source_user_id,
            "source_transaction_id": source_transaction_id,
            "target_owner_user_id": target_owner_user_id,
            "target_capital_account_id": target_capital_account_id,
            "amount": amount,
            "date": date,
            "comment": comment,
        }

    def get_family_capital_contribution(
        self,
        source_user_id: int,
        source_transaction_id: int,
    ) -> Optional[Dict[str, object]]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM family_capital_contributions
                WHERE source_user_id = ?
                  AND source_transaction_id = ?
                  AND reversed_at IS NULL
                LIMIT 1
                """,
                (source_user_id, source_transaction_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "family_id": int(row["family_id"]),
            "source_user_id": int(row["source_user_id"]),
            "source_transaction_id": int(row["source_transaction_id"]),
            "target_owner_user_id": int(row["target_owner_user_id"]),
            "target_capital_account_id": int(row["target_capital_account_id"]),
            "amount": float(row["amount"] or 0),
            "date": str(row["date"] or ""),
            "comment": str(row["comment"] or ""),
        }

    def reverse_family_capital_contribution(self, contribution_id: int) -> bool:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE family_capital_contributions
                SET reversed_at = datetime('now')
                WHERE id = ?
                  AND reversed_at IS NULL
                """,
                (contribution_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_family_capital_contributions_for_user(
        self,
        user_id: int,
        limit: int = 50,
    ) -> List[Dict[str, object]]:
        safe_limit = max(1, min(limit, 200))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fcc.id,
                       fcc.family_id,
                       f.name AS family_name,
                       fcc.source_user_id,
                       fcc.source_transaction_id,
                       fcc.target_owner_user_id,
                       fcc.target_capital_account_id,
                       fcc.amount,
                       fcc.date,
                       fcc.comment,
                       src.email AS source_email,
                       COALESCE(src_up.display_name, '') AS source_display_name,
                       tgt.email AS target_owner_email,
                       COALESCE(tgt_up.display_name, '') AS target_owner_display_name
                FROM family_capital_contributions fcc
                JOIN families f ON f.id = fcc.family_id
                JOIN users src ON src.id = fcc.source_user_id
                LEFT JOIN user_preferences src_up ON src_up.user_id = fcc.source_user_id
                JOIN users tgt ON tgt.id = fcc.target_owner_user_id
                LEFT JOIN user_preferences tgt_up ON tgt_up.user_id = fcc.target_owner_user_id
                WHERE fcc.reversed_at IS NULL
                  AND (fcc.source_user_id = ? OR fcc.target_owner_user_id = ?)
                ORDER BY fcc.date DESC, fcc.id DESC
                LIMIT ?
                """,
                (user_id, user_id, safe_limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "family_id": int(row["family_id"]),
                "family_name": str(row["family_name"] or ""),
                "source_user_id": int(row["source_user_id"]),
                "source_transaction_id": int(row["source_transaction_id"]),
                "target_owner_user_id": int(row["target_owner_user_id"]),
                "target_capital_account_id": int(row["target_capital_account_id"]),
                "amount": float(row["amount"] or 0),
                "date": str(row["date"] or ""),
                "comment": str(row["comment"] or ""),
                "source_email": str(row["source_email"] or ""),
                "source_display_name": str(row["source_display_name"] or "").strip(),
                "target_owner_email": str(row["target_owner_email"] or ""),
                "target_owner_display_name": str(row["target_owner_display_name"] or "").strip(),
            }
            for row in rows
        ]

    def list_family_capital_contributions_for_family(
        self,
        family_id: int,
        limit: int = 100,
    ) -> List[Dict[str, object]]:
        safe_limit = max(1, min(limit, 300))
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fcc.id,
                       fcc.family_id,
                       fcc.source_user_id,
                       fcc.source_transaction_id,
                       fcc.target_owner_user_id,
                       fcc.target_capital_account_id,
                       fcc.amount,
                       fcc.date,
                       fcc.comment,
                       src.email AS source_email,
                       COALESCE(src_up.display_name, '') AS source_display_name,
                       tgt.email AS target_owner_email,
                       COALESCE(tgt_up.display_name, '') AS target_owner_display_name
                FROM family_capital_contributions fcc
                JOIN users src ON src.id = fcc.source_user_id
                LEFT JOIN user_preferences src_up ON src_up.user_id = fcc.source_user_id
                JOIN users tgt ON tgt.id = fcc.target_owner_user_id
                LEFT JOIN user_preferences tgt_up ON tgt_up.user_id = fcc.target_owner_user_id
                WHERE fcc.family_id = ?
                  AND fcc.reversed_at IS NULL
                ORDER BY fcc.date DESC, fcc.id DESC
                LIMIT ?
                """,
                (family_id, safe_limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "family_id": int(row["family_id"]),
                "source_user_id": int(row["source_user_id"]),
                "source_transaction_id": int(row["source_transaction_id"]),
                "target_owner_user_id": int(row["target_owner_user_id"]),
                "target_capital_account_id": int(row["target_capital_account_id"]),
                "amount": float(row["amount"] or 0),
                "date": str(row["date"] or ""),
                "comment": str(row["comment"] or ""),
                "source_email": str(row["source_email"] or ""),
                "source_display_name": str(row["source_display_name"] or "").strip(),
                "target_owner_email": str(row["target_owner_email"] or ""),
                "target_owner_display_name": str(row["target_owner_display_name"] or "").strip(),
            }
            for row in rows
        ]

    def update_family_member_role(self, family_id: int, user_id: int, role: str) -> bool:
        normalized_role = role if role in {"member", "viewer"} else "member"
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role
                FROM family_memberships
                WHERE family_id = ?
                  AND user_id = ?
                  AND status = 'active'
                LIMIT 1
                """,
                (family_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return False
            if str(row["role"] or "") == "owner":
                raise ValueError("owner_role_locked")
            cursor.execute(
                """
                UPDATE family_memberships
                SET role = ?, updated_at = datetime('now')
                WHERE family_id = ?
                  AND user_id = ?
                  AND status = 'active'
                """,
                (normalized_role, family_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def remove_family_member(self, family_id: int, user_id: int) -> bool:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role
                FROM family_memberships
                WHERE family_id = ?
                  AND user_id = ?
                  AND status = 'active'
                LIMIT 1
                """,
                (family_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return False
            if str(row["role"] or "") == "owner":
                raise ValueError("owner_cannot_be_removed")
            cursor.execute(
                """
                UPDATE family_memberships
                SET status = 'revoked', updated_at = datetime('now')
                WHERE family_id = ?
                  AND user_id = ?
                  AND status = 'active'
                """,
                (family_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_family_invite(
        self,
        family_id: int,
        invited_by_user_id: int,
        email: str,
        role: str = "member",
    ) -> Dict[str, str]:
        normalized_email = self._normalize_email(email)
        invite_role = role if role in {"member", "viewer"} else "member"

        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id
                FROM family_memberships
                WHERE family_id = ?
                  AND user_id = (SELECT id FROM users WHERE email = ? LIMIT 1)
                  AND status = 'active'
                LIMIT 1
                """,
                (family_id, normalized_email),
            )
            existing_member = cursor.fetchone()
            if existing_member:
                raise ValueError("user_already_member")

            cursor.execute(
                """
                UPDATE family_invites
                SET revoked_at = datetime('now')
                WHERE family_id = ?
                  AND email = ?
                  AND accepted_at IS NULL
                  AND revoked_at IS NULL
                  AND expires_at >= datetime('now')
                """,
                (family_id, normalized_email),
            )

            raw_token = secrets.token_urlsafe(36)
            token_hash = self._token_hash(raw_token)
            expires_at = _format_utc(_utcnow() + timedelta(hours=72))
            cursor.execute(
                """
                INSERT INTO family_invites (family_id, email, role, token_hash, invited_by_user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (family_id, normalized_email, invite_role, token_hash, invited_by_user_id, expires_at),
            )
            conn.commit()

        return {"token": raw_token, "expires_at": expires_at}

    def list_pending_family_invites(self, user_id: int) -> List[Dict[str, object]]:
        user = self.get_user_by_id(user_id)
        if not user:
            return []
        user_email = str(user["email"] or "").lower()
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fi.id,
                       fi.family_id,
                       f.name AS family_name,
                       fi.role,
                       fi.expires_at,
                       fi.created_at,
                       inviter.email AS invited_by_email
                FROM family_invites fi
                JOIN families f ON f.id = fi.family_id
                JOIN users inviter ON inviter.id = fi.invited_by_user_id
                WHERE fi.email = ?
                  AND fi.accepted_at IS NULL
                  AND fi.revoked_at IS NULL
                  AND fi.expires_at >= datetime('now')
                  AND f.archived_at IS NULL
                ORDER BY fi.created_at DESC, fi.id DESC
                """,
                (user_email,),
            )
            rows = cursor.fetchall()
        return [
            {
                "invite_id": int(row["id"]),
                "family_id": int(row["family_id"]),
                "family_name": str(row["family_name"] or ""),
                "role": str(row["role"] or "member"),
                "invited_by_email": str(row["invited_by_email"] or ""),
                "expires_at": str(row["expires_at"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

    def accept_family_invite_by_id(self, invite_id: int, user_id: int) -> Optional[Dict[str, object]]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        user_email = str(user["email"] or "").lower()

        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fi.id, fi.family_id, fi.email, fi.role, fi.expires_at, fi.accepted_at, fi.revoked_at, f.name
                FROM family_invites fi
                JOIN families f ON f.id = fi.family_id
                WHERE fi.id = ?
                LIMIT 1
                """,
                (invite_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["accepted_at"] or row["revoked_at"]:
                return None
            if _parse_utc(str(row["expires_at"])) < _utcnow():
                return None
            if str(row["email"] or "").lower() != user_email:
                return None

            family_id = int(row["family_id"])
            role = str(row["role"] or "member")
            family_name = str(row["name"] or "")

            cursor.execute(
                """
                INSERT INTO family_memberships (family_id, user_id, role, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', datetime('now'), datetime('now'))
                ON CONFLICT(family_id, user_id) DO UPDATE SET
                    role = excluded.role,
                    status = 'active',
                    updated_at = datetime('now')
                """,
                (family_id, user_id, role),
            )
            cursor.execute(
                """
                UPDATE family_invites
                SET accepted_at = datetime('now')
                WHERE id = ?
                """,
                (invite_id,),
            )
            conn.commit()
        self.ensure_family_member_capital_target(family_id, user_id)
        return {
            "family_id": family_id,
            "family_name": family_name,
            "role": role,
        }

    def decline_family_invite_by_id(self, invite_id: int, user_id: int) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        user_email = str(user["email"] or "").lower()
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE family_invites
                SET revoked_at = datetime('now')
                WHERE id = ?
                  AND email = ?
                  AND accepted_at IS NULL
                  AND revoked_at IS NULL
                  AND expires_at >= datetime('now')
                """,
                (invite_id, user_email),
            )
            conn.commit()
            return cursor.rowcount > 0

    def accept_family_invite(self, token: str, user_id: int) -> Optional[Dict[str, object]]:
        token_hash = self._token_hash(token)
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        user_email = str(user["email"] or "").lower()

        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fi.id, fi.family_id, fi.email, fi.role, fi.expires_at, fi.accepted_at, fi.revoked_at, f.name
                FROM family_invites fi
                JOIN families f ON f.id = fi.family_id
                WHERE fi.token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["accepted_at"] or row["revoked_at"]:
                return None
            if _parse_utc(str(row["expires_at"])) < _utcnow():
                return None
            if str(row["email"] or "").lower() != user_email:
                return None

            family_id = int(row["family_id"])
            role = str(row["role"] or "member")
            family_name = str(row["name"] or "")

            cursor.execute(
                """
                INSERT INTO family_memberships (family_id, user_id, role, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', datetime('now'), datetime('now'))
                ON CONFLICT(family_id, user_id) DO UPDATE SET
                    role = excluded.role,
                    status = 'active',
                    updated_at = datetime('now')
                """,
                (family_id, user_id, role),
            )
            cursor.execute(
                """
                UPDATE family_invites
                SET accepted_at = datetime('now')
                WHERE id = ?
                """,
                (int(row["id"]),),
            )
            conn.commit()
        self.ensure_family_member_capital_target(family_id, user_id)

        return {
            "family_id": family_id,
            "family_name": family_name,
            "role": role,
        }

    def _drop_all_user_tables(self) -> None:
        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
            table_names = [str(row["name"]) for row in cursor.fetchall()]
            for table_name in table_names:
                safe_name = table_name.replace('"', '""')
                cursor.execute(f'DROP TABLE IF EXISTS "{safe_name}"')
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    def _dump_current_user_db_sql(self, user_id: int) -> str:
        db_path = self.ensure_user_finance_db(user_id)
        token = core.push_db_name(db_path)
        try:
            with core.get_connection() as conn:
                dump_lines = list(conn.iterdump())
            return "\n".join(dump_lines)
        finally:
            core.pop_db_name(token)

    def save_user_backup_slot(self, user_id: int) -> Dict[str, str]:
        dump_sql = self._dump_current_user_db_sql(user_id)
        compressed = zlib.compress(dump_sql.encode("utf-8"), level=9)
        backup_blob = base64.b64encode(compressed).decode("ascii")
        checksum = hashlib.sha256(dump_sql.encode("utf-8")).hexdigest()
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_backup_slot (user_id, backup_blob, checksum, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    backup_blob = excluded.backup_blob,
                    checksum = excluded.checksum,
                    updated_at = datetime('now')
                """,
                (user_id, backup_blob, checksum),
            )
            conn.commit()
            cursor.execute(
                """
                SELECT created_at, updated_at, checksum
                FROM user_backup_slot
                WHERE user_id = ?
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return {
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "checksum": str(row["checksum"] or ""),
        }

    def get_user_backup_slot_info(self, user_id: int) -> Dict[str, object]:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, updated_at, checksum
                FROM user_backup_slot
                WHERE user_id = ?
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            return {"has_backup": False, "created_at": "", "updated_at": "", "checksum": ""}
        return {
            "has_backup": True,
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "checksum": str(row["checksum"] or ""),
        }

    def restore_user_backup_slot(self, user_id: int) -> bool:
        with self._auth_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT backup_blob, checksum
                FROM user_backup_slot
                WHERE user_id = ?
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            return False
        try:
            compressed = base64.b64decode(str(row["backup_blob"]).encode("ascii"))
            dump_sql = zlib.decompress(compressed).decode("utf-8")
        except Exception:
            return False
        checksum = hashlib.sha256(dump_sql.encode("utf-8")).hexdigest()
        if checksum != str(row["checksum"]):
            return False

        db_path = self.ensure_user_finance_db(user_id)
        token = core.push_db_name(db_path)
        try:
            self._drop_all_user_tables()
            with core.get_connection() as conn:
                conn.executescript(dump_sql)
                conn.commit()
            core.init_db()
            core._invalidate_cache()
        finally:
            core.pop_db_name(token)
        return True

    def reset_user_finance_data(self, user_id: int) -> None:
        db_path = self.ensure_user_finance_db(user_id)
        token = core.push_db_name(db_path)
        try:
            self._drop_all_user_tables()
            core.init_db()
            core._invalidate_cache()
        finally:
            core.pop_db_name(token)


auth_service = AuthService(
    auth_db_name=settings.auth_db_name,
    users_data_dir=settings.users_data_dir,
    session_secret=settings.session_secret,
)
