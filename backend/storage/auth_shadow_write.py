from __future__ import annotations

from typing import Any, Dict, Optional

from backend.config import settings
from backend.storage.mysql_auth_write import MySqlAuthWriteRepository
from utils.logger import app_logger


def mysql_auth_shadow_write_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "mysql_shadow_write_enabled", False)
        and getattr(config, "mysql_database_url", "")
    )


def mysql_strict_auth_write_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "mysql_strict_write_auth_enabled", False)
        and mysql_auth_shadow_write_enabled(config)
    )


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    keys = row.keys() if hasattr(row, "keys") else []
    return {key: row[key] for key in keys}


def _result_ok(result: Dict[str, Any]) -> bool:
    mysql_result = (result.get("results") or {}).get("mysql") or {}
    return result.get("status") == "ok" and mysql_result.get("status") == "ok"


def require_mysql_auth_shadow_write_success(
    result: Dict[str, Any],
    operation: str,
    config=settings,
) -> None:
    if not mysql_strict_auth_write_enabled(config):
        return
    if _result_ok(result):
        return
    mysql_result = (result.get("results") or {}).get("mysql") or {}
    reason = mysql_result.get("reason") or result.get("reason") or result.get("status") or "unknown"
    raise RuntimeError(f"MySQL strict auth shadow-write failed for {operation}: {reason}")


def _mysql_auth_write(operation: str, callback, config=settings) -> Dict[str, Any]:
    if not mysql_auth_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    results: Dict[str, Any] = {}
    try:
        repo = MySqlAuthWriteRepository(config.mysql_database_url)
        with repo.connect() as conn:
            result = callback(repo, conn)
            conn.commit()
        results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok", "results": results}
    except Exception as exc:
        app_logger.warning("MySQL auth shadow-write failed for %s: %s", operation, exc)
        results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_auth_user_shadow_write(user_row: Any, config=settings) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    if not user:
        return {"enabled": True, "status": "skipped", "reason": "missing_user"}
    return _mysql_auth_write("user", lambda repo, conn: repo.mirror_user(conn, user), config=config)


def mirror_auth_session_shadow_write(
    user_row: Any,
    token_hash: str,
    expires_at: str,
    ip: str = "",
    user_agent: str = "",
    revoked_at: Optional[str] = None,
    config=settings,
) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    if not user:
        return {"enabled": True, "status": "skipped", "reason": "missing_user"}
    session = {
        "token_hash": token_hash,
        "expires_at": expires_at,
        "ip": ip or "",
        "user_agent": user_agent or "",
        "revoked_at": revoked_at,
    }

    def _write(repo: MySqlAuthWriteRepository, conn):
        repo.mirror_user(conn, user)
        return repo.mirror_session(conn, int(user["id"]), session)

    return _mysql_auth_write("session", _write, config=config)


def mirror_auth_preferences_shadow_write(
    user_row: Any,
    preferences: Dict[str, Any],
    config=settings,
) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    if not user:
        return {"enabled": True, "status": "skipped", "reason": "missing_user"}

    def _write(repo: MySqlAuthWriteRepository, conn):
        repo.mirror_user(conn, user)
        return repo.mirror_user_preferences(conn, int(user["id"]), preferences)

    return _mysql_auth_write("user_preferences", _write, config=config)


def mirror_auth_login_attempt_shadow_write(
    email: str,
    rate_key: str,
    ip: str = "",
    success: bool = False,
    config=settings,
) -> Dict[str, Any]:
    attempt = {"email": email, "rate_key": rate_key, "ip": ip or "", "success": success}
    return _mysql_auth_write(
        "login_attempt",
        lambda repo, conn: repo.mirror_login_attempt(conn, attempt),
        config=config,
    )


def mirror_auth_event_shadow_write(
    event_type: str,
    status: str,
    user_row: Any = None,
    user_id: Optional[int] = None,
    email: str = "",
    ip: str = "",
    user_agent: str = "",
    detail: str = "",
    config=settings,
) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    legacy_user_id = int(user["id"]) if user else (int(user_id) if user_id is not None else None)
    event = {
        "email": email,
        "event_type": event_type,
        "status": status,
        "ip": ip or "",
        "user_agent": user_agent or "",
        "detail": detail or "",
    }

    def _write(repo: MySqlAuthWriteRepository, conn):
        if user:
            repo.mirror_user(conn, user)
        return repo.mirror_auth_event(conn, legacy_user_id, event)

    return _mysql_auth_write("auth_event", _write, config=config)


def mirror_auth_token_shadow_write(
    user_row: Any,
    table: str,
    token_hash: str,
    expires_at: str,
    used_at: Optional[str] = None,
    config=settings,
) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    if not user:
        return {"enabled": True, "status": "skipped", "reason": "missing_user"}
    token = {"token_hash": token_hash, "expires_at": expires_at, "used_at": used_at}

    def _write(repo: MySqlAuthWriteRepository, conn):
        repo.mirror_user(conn, user)
        return repo.mirror_token(conn, int(user["id"]), table, token)

    return _mysql_auth_write(f"{table}_token", _write, config=config)


def mirror_auth_session_revoke_shadow_write(token_hash: str, config=settings) -> Dict[str, Any]:
    return _mysql_auth_write(
        "session_revoke",
        lambda repo, conn: repo.revoke_session_by_token_hash(conn, token_hash),
        config=config,
    )


def mirror_auth_user_sessions_revoke_shadow_write(
    legacy_user_id: int,
    except_token_hash: str = "",
    config=settings,
) -> Dict[str, Any]:
    return _mysql_auth_write(
        "user_sessions_revoke",
        lambda repo, conn: repo.revoke_user_sessions(conn, int(legacy_user_id), except_token_hash or ""),
        config=config,
    )


def mirror_auth_user_delete_shadow_write(legacy_user_id: int, config=settings) -> Dict[str, Any]:
    return _mysql_auth_write(
        "user_delete",
        lambda repo, conn: repo.delete_user(conn, int(legacy_user_id)),
        config=config,
    )
