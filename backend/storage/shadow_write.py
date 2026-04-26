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


def _planned_transactions_for_template(template_id: int) -> List[Dict[str, Any]]:
    return [_row_to_dict(row) for row in core.get_planned_transactions_by_template(int(template_id))]


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
    status = str(transaction.get("status") or "actual")
    if status not in {"actual", "planned"}:
        return {"enabled": True, "status": "skipped", "reason": "non_actual_transaction"}

    legacy_user_id = int(current_user["id"])
    legacy_transaction_id = int(transaction["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            if status == "planned":
                result = repo.mirror_planned_transaction(
                    conn,
                    legacy_user_id=legacy_user_id,
                    source_db_path=source_db_path,
                    transaction=transaction,
                )
            else:
                transfers = _active_transfers_for_transaction(legacy_transaction_id)
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


def mirror_updated_transaction_shadow_write(
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
    status = str(transaction.get("status") or "actual")
    if status not in {"actual", "planned"}:
        return {"enabled": True, "status": "skipped", "reason": "non_actual_transaction"}

    legacy_user_id = int(current_user["id"])
    legacy_transaction_id = int(transaction["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    try:
        transfers = [] if status == "planned" else _active_transfers_for_transaction(legacy_transaction_id)
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_update_transaction(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                transaction=transaction,
                transfers=transfers,
            )
            conn.commit()
        app_logger.info(
            "PostgreSQL shadow-write mirrored update user_id=%s transaction_id=%s status=%s",
            legacy_user_id,
            legacy_transaction_id,
            result.get("status"),
        )
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write update failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            legacy_transaction_id,
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_recurring_template_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_template_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}

    template = _row_to_dict(sqlite_template_row)
    if not template:
        return {"enabled": True, "status": "skipped", "reason": "missing_template"}

    legacy_user_id = int(current_user["id"])
    legacy_template_id = int(template["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    try:
        planned_transactions = _planned_transactions_for_template(legacy_template_id)
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            template_result = repo.mirror_recurring_template(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                template=template,
            )
            delete_result = repo.delete_planned_transactions_for_template(
                conn,
                legacy_user_id=legacy_user_id,
                legacy_template_id=legacy_template_id,
            )
            planned_results = [
                repo.mirror_planned_transaction(
                    conn,
                    legacy_user_id=legacy_user_id,
                    source_db_path=source_db_path,
                    transaction=transaction,
                )
                for transaction in planned_transactions
            ]
            conn.commit()
        app_logger.info(
            "PostgreSQL shadow-write mirrored recurring template user_id=%s template_id=%s status=%s planned=%s",
            legacy_user_id,
            legacy_template_id,
            template_result.get("status"),
            len(planned_results),
        )
        return {
            "enabled": True,
            "status": "ok",
            "result": {
                "template": template_result,
                "stale_planned": delete_result,
                "planned": planned_results,
            },
        }
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write recurring template failed for user_id=%s template_id=%s: %s",
            legacy_user_id,
            legacy_template_id,
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_deleted_recurring_template_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_template_id: int,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}

    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_delete_recurring_template(
                conn,
                legacy_user_id=legacy_user_id,
                legacy_template_id=int(legacy_template_id),
            )
            conn.commit()
        app_logger.info(
            "PostgreSQL shadow-write mirrored recurring template delete user_id=%s template_id=%s status=%s",
            legacy_user_id,
            int(legacy_template_id),
            result.get("status"),
        )
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write recurring template delete failed for user_id=%s template_id=%s: %s",
            legacy_user_id,
            int(legacy_template_id),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_category_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_category_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    category = _row_to_dict(sqlite_category_row)
    if not category:
        return {"enabled": True, "status": "skipped", "reason": "missing_category"}

    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_category(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=f"data/users/{legacy_user_id}/finance.db",
                category=category,
            )
            conn.commit()
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write category failed for user_id=%s category_id=%s: %s",
            legacy_user_id,
            category.get("id"),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_budget_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_budget_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    budget = _row_to_dict(sqlite_budget_row)
    if not budget:
        return {"enabled": True, "status": "skipped", "reason": "missing_budget"}

    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_budget(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=f"data/users/{legacy_user_id}/finance.db",
                budget=budget,
            )
            conn.commit()
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write budget failed for user_id=%s budget_id=%s: %s",
            legacy_user_id,
            budget.get("id"),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_deleted_budget_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_budget_id: int,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_delete_budget(conn, legacy_user_id, int(legacy_budget_id))
            conn.commit()
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write budget delete failed for user_id=%s budget_id=%s: %s",
            legacy_user_id,
            int(legacy_budget_id),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}


def mirror_capital_accounts_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_account_rows: List[Any],
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    accounts = [_row_to_dict(row) for row in sqlite_account_rows]
    legacy_user_id = int(current_user["id"])
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            results = [
                repo.mirror_capital_account(
                    conn,
                    legacy_user_id=legacy_user_id,
                    source_db_path=f"data/users/{legacy_user_id}/finance.db",
                    account=account,
                )
                for account in accounts
                if account
            ]
            conn.commit()
        return {"enabled": True, "status": "ok", "result": {"accounts": results}}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write capital accounts failed for user_id=%s: %s",
            legacy_user_id,
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}
