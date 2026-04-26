from __future__ import annotations

from typing import Any, Dict, List, Optional

import core
from backend.config import settings
from backend.storage.postgres_write import PostgresWriteRepository
from utils.logger import app_logger


def postgres_shadow_write_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "postgres_shadow_write_enabled", False)
        and getattr(config, "database_url", "")
    )


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    keys = row.keys() if hasattr(row, "keys") else []
    return {key: row[key] for key in keys}


def _active_transfers_for_transaction(transaction_id: int) -> List[Dict[str, Any]]:
    with core.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, from_account_id, to_account_id, amount, transaction_id, date, comment, is_active
            FROM transfers
            WHERE transaction_id = ? AND is_active = 1
            ORDER BY id
            """,
            (int(transaction_id),),
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]


def mirror_created_transaction_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_transaction_row: Any,
    config=settings,
    skip_reason: str = "",
) -> Dict[str, Any]:
    if skip_reason:
        return {"enabled": False, "status": "skipped", "reason": skip_reason}
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}

    transaction = _row_to_dict(sqlite_transaction_row)
    if not transaction:
        return {"enabled": True, "status": "skipped", "reason": "missing_transaction"}
    if str(transaction.get("status") or "actual") != "actual":
        return {"enabled": True, "status": "skipped", "reason": "non_actual_transaction"}

    legacy_user_id = int(current_user["id"])
    legacy_transaction_id = int(transaction["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    try:
        transfers = _active_transfers_for_transaction(legacy_transaction_id)
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_actual_transaction(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                transaction=transaction,
                transfers=transfers,
            )
            conn.commit()
        app_logger.info(
            "PostgreSQL shadow-write mirrored transaction user_id=%s transaction_id=%s status=%s",
            legacy_user_id,
            legacy_transaction_id,
            result.get("status"),
        )
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            legacy_transaction_id,
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_deleted_transaction_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_transaction_id: int,
    config=settings,
    skip_reason: str = "",
) -> Dict[str, Any]:
    if skip_reason:
        return {"enabled": False, "status": "skipped", "reason": skip_reason}
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}

    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_delete_transaction(
                conn,
                legacy_user_id=legacy_user_id,
                legacy_transaction_id=int(legacy_transaction_id),
            )
            conn.commit()
        app_logger.info(
            "PostgreSQL shadow-write mirrored delete user_id=%s transaction_id=%s status=%s",
            legacy_user_id,
            int(legacy_transaction_id),
            result.get("status"),
        )
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write delete failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            int(legacy_transaction_id),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}
