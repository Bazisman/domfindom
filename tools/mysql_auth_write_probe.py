from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.mysql_auth_write import MySqlAuthWriteRepository


def run_probe(database_url: str) -> Dict[str, Any]:
    repo = MySqlAuthWriteRepository(database_url)
    legacy_user_id = 910_000_901
    with repo.connect() as conn:
        try:
            user = {
                "id": legacy_user_id,
                "email": f"mysql-auth-probe-{legacy_user_id}@example.invalid",
                "password_hash": "probe-hash",
                "email_verified": True,
                "is_active": True,
            }
            session = {
                "token_hash": f"probe-session-{legacy_user_id}",
                "expires_at": "2099-01-01 00:00:00",
                "ip": "127.0.0.1",
                "user_agent": "mysql-auth-probe",
            }
            preferences = {
                "theme_mode": "system",
                "workspace_mode": "personal",
                "display_name": "MySQL Auth Probe",
            }
            login_attempt = {
                "rate_key": f"{user['email']}|127.0.0.1",
                "email": user["email"],
                "ip": "127.0.0.1",
                "success": True,
            }
            event = {
                "email": user["email"],
                "event_type": "mysql_auth_probe",
                "status": "ok",
                "ip": "127.0.0.1",
                "user_agent": "mysql-auth-probe",
                "detail": "rollback probe",
            }
            token = {
                "token_hash": f"probe-token-{legacy_user_id}",
                "expires_at": "2099-01-01 00:00:00",
                "used_at": None,
            }

            results = {
                "user": repo.mirror_user(conn, user),
                "session": repo.mirror_session(conn, legacy_user_id, session),
                "preferences": repo.mirror_user_preferences(conn, legacy_user_id, preferences),
                "login_attempt": repo.mirror_login_attempt(conn, login_attempt),
                "auth_event": repo.mirror_auth_event(conn, legacy_user_id, event),
                "password_reset_token": repo.mirror_token(conn, legacy_user_id, "password_reset_tokens", token),
                "email_verification_token": repo.mirror_token(conn, legacy_user_id, "email_verification_tokens", token),
                "account_deletion_token": repo.mirror_token(conn, legacy_user_id, "account_deletion_tokens", token),
            }
            return {"status": "ok", "legacy_user_id": legacy_user_id, "rolled_back": True, "results": results}
        finally:
            conn.rollback()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Rollback probe for MySQL auth/session writes.")
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    report = run_probe(args.database_url)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
