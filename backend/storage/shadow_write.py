from __future__ import annotations

from typing import Any, Dict, List, Optional

import core
from backend.config import settings
from backend.storage.mysql_write import MySqlWriteRepository
from backend.storage.postgres_write import PostgresWriteRepository
from utils.logger import app_logger


def postgres_shadow_write_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "postgres_shadow_write_enabled", False)
        and getattr(config, "database_url", "")
    )


def mysql_shadow_write_enabled(config=settings) -> bool:
    return bool(
        getattr(config, "mysql_shadow_write_enabled", False)
        and getattr(config, "mysql_database_url", "")
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
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
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
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
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
                "MySQL shadow-write mirrored transaction user_id=%s transaction_id=%s status=%s",
                legacy_user_id,
                legacy_transaction_id,
                result.get("status"),
            )
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write failed for user_id=%s transaction_id=%s: %s",
                legacy_user_id,
                legacy_transaction_id,
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}

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
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            legacy_transaction_id,
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_deleted_transaction_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_transaction_id: int,
    config=settings,
    skip_reason: str = "",
) -> Dict[str, Any]:
    if skip_reason:
        return {"enabled": False, "status": "skipped", "reason": skip_reason}
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}

    legacy_user_id = int(current_user["id"])
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_delete_transaction(
                    conn,
                    legacy_user_id=legacy_user_id,
                    legacy_transaction_id=int(legacy_transaction_id),
                )
                conn.commit()
            app_logger.info(
                "MySQL shadow-write mirrored delete user_id=%s transaction_id=%s status=%s",
                legacy_user_id,
                int(legacy_transaction_id),
                result.get("status"),
            )
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write delete failed for user_id=%s transaction_id=%s: %s",
                legacy_user_id,
                int(legacy_transaction_id),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
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
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write delete failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            int(legacy_transaction_id),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_updated_transaction_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_transaction_row: Any,
    config=settings,
    skip_reason: str = "",
) -> Dict[str, Any]:
    if skip_reason:
        return {"enabled": False, "status": "skipped", "reason": skip_reason}
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
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
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
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
                    result = repo.mirror_update_transaction(
                        conn,
                        legacy_user_id=legacy_user_id,
                        source_db_path=source_db_path,
                        transaction=transaction,
                        transfers=transfers,
                    )
                conn.commit()
            app_logger.info(
                "MySQL shadow-write mirrored update user_id=%s transaction_id=%s status=%s",
                legacy_user_id,
                legacy_transaction_id,
                result.get("status"),
            )
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write update failed for user_id=%s transaction_id=%s: %s",
                legacy_user_id,
                legacy_transaction_id,
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
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
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write update failed for user_id=%s transaction_id=%s: %s",
            legacy_user_id,
            legacy_transaction_id,
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_recurring_template_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_template_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}

    template = _row_to_dict(sqlite_template_row)
    if not template:
        return {"enabled": True, "status": "skipped", "reason": "missing_template"}

    legacy_user_id = int(current_user["id"])
    legacy_template_id = int(template["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    planned_transactions = _planned_transactions_for_template(legacy_template_id)
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
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
                "MySQL shadow-write mirrored recurring template user_id=%s template_id=%s status=%s planned=%s",
                legacy_user_id,
                legacy_template_id,
                template_result.get("status"),
                len(planned_results),
            )
            results["mysql"] = {
                "enabled": True,
                "status": "ok",
                "result": {"template": template_result, "stale_planned": delete_result, "planned": planned_results},
            }
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write recurring template failed for user_id=%s template_id=%s: %s",
                legacy_user_id,
                legacy_template_id,
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
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
        results["postgres"] = {
            "enabled": True,
            "status": "ok",
            "result": {
                "template": template_result,
                "stale_planned": delete_result,
                "planned": planned_results,
            },
        }
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write recurring template failed for user_id=%s template_id=%s: %s",
            legacy_user_id,
            legacy_template_id,
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_deleted_recurring_template_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_template_id: int,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}

    legacy_user_id = int(current_user["id"])
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_delete_recurring_template(
                    conn,
                    legacy_user_id=legacy_user_id,
                    legacy_template_id=int(legacy_template_id),
                )
                conn.commit()
            app_logger.info(
                "MySQL shadow-write mirrored recurring template delete user_id=%s template_id=%s status=%s",
                legacy_user_id,
                int(legacy_template_id),
                result.get("status"),
            )
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write recurring template delete failed for user_id=%s template_id=%s: %s",
                legacy_user_id,
                int(legacy_template_id),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
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
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write recurring template delete failed for user_id=%s template_id=%s: %s",
            legacy_user_id,
            int(legacy_template_id),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_category_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_category_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}
    category = _row_to_dict(sqlite_category_row)
    if not category:
        return {"enabled": True, "status": "skipped", "reason": "missing_category"}

    legacy_user_id = int(current_user["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_category(conn, legacy_user_id, source_db_path, category)
                conn.commit()
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write category failed for user_id=%s category_id=%s: %s",
                legacy_user_id,
                category.get("id"),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_category(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                category=category,
            )
            conn.commit()
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write category failed for user_id=%s category_id=%s: %s",
            legacy_user_id,
            category.get("id"),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_budget_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_budget_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}
    budget = _row_to_dict(sqlite_budget_row)
    if not budget:
        return {"enabled": True, "status": "skipped", "reason": "missing_budget"}

    legacy_user_id = int(current_user["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_budget(conn, legacy_user_id, source_db_path, budget)
                conn.commit()
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write budget failed for user_id=%s budget_id=%s: %s",
                legacy_user_id,
                budget.get("id"),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_budget(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                budget=budget,
            )
            conn.commit()
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write budget failed for user_id=%s budget_id=%s: %s",
            legacy_user_id,
            budget.get("id"),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_deleted_budget_shadow_write(
    current_user: Optional[Dict[str, Any]],
    legacy_budget_id: int,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}
    legacy_user_id = int(current_user["id"])
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_delete_budget(conn, legacy_user_id, int(legacy_budget_id))
                conn.commit()
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write budget delete failed for user_id=%s budget_id=%s: %s",
                legacy_user_id,
                int(legacy_budget_id),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_delete_budget(conn, legacy_user_id, int(legacy_budget_id))
            conn.commit()
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write budget delete failed for user_id=%s budget_id=%s: %s",
            legacy_user_id,
            int(legacy_budget_id),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_capital_accounts_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_account_rows: List[Any],
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}
    accounts = [_row_to_dict(row) for row in sqlite_account_rows]
    legacy_user_id = int(current_user["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                mirrored = [
                    repo.mirror_capital_account(
                        conn,
                        legacy_user_id=legacy_user_id,
                        source_db_path=source_db_path,
                        account=account,
                    )
                    for account in accounts
                    if account
                ]
                conn.commit()
            results["mysql"] = {"enabled": True, "status": "ok", "result": {"accounts": mirrored}}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write capital accounts failed for user_id=%s: %s",
                legacy_user_id,
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            mirrored = [
                repo.mirror_capital_account(
                    conn,
                    legacy_user_id=legacy_user_id,
                    source_db_path=source_db_path,
                    account=account,
                )
                for account in accounts
                if account
            ]
            conn.commit()
        results["postgres"] = {"enabled": True, "status": "ok", "result": {"accounts": mirrored}}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write capital accounts failed for user_id=%s: %s",
            legacy_user_id,
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def mirror_transfer_shadow_write(
    current_user: Optional[Dict[str, Any]],
    sqlite_transfer_row: Any,
    config=settings,
) -> Dict[str, Any]:
    if not current_user or not (postgres_shadow_write_enabled(config) or mysql_shadow_write_enabled(config)):
        return {"enabled": False, "status": "disabled"}
    transfer = _row_to_dict(sqlite_transfer_row)
    if not transfer:
        return {"enabled": True, "status": "skipped", "reason": "missing_transfer"}

    legacy_user_id = int(current_user["id"])
    source_db_path = f"data/users/{legacy_user_id}/finance.db"
    results: Dict[str, Any] = {}
    if mysql_shadow_write_enabled(config):
        try:
            repo = MySqlWriteRepository(config.mysql_database_url)
            with repo.connect() as conn:
                result = repo.mirror_standalone_transfer(
                    conn,
                    legacy_user_id=legacy_user_id,
                    source_db_path=source_db_path,
                    transfer=transfer,
                )
                conn.commit()
            results["mysql"] = {"enabled": True, "status": "ok", "result": result}
        except Exception as exc:
            app_logger.warning(
                "MySQL shadow-write transfer failed for user_id=%s transfer_id=%s: %s",
                legacy_user_id,
                transfer.get("id"),
                exc,
            )
            results["mysql"] = {"enabled": True, "status": "failed", "reason": str(exc)}
    if not postgres_shadow_write_enabled(config):
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_standalone_transfer(
                conn,
                legacy_user_id=legacy_user_id,
                source_db_path=source_db_path,
                transfer=transfer,
            )
            conn.commit()
        results["postgres"] = {"enabled": True, "status": "ok", "result": result}
        return {"enabled": True, "status": "ok" if all(item.get("status") != "failed" for item in results.values()) else "failed", "results": results}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write transfer failed for user_id=%s transfer_id=%s: %s",
            legacy_user_id,
            transfer.get("id"),
            exc,
        )
        results["postgres"] = {"enabled": True, "status": "failed", "reason": str(exc)}
        return {"enabled": True, "status": "failed", "results": results}


def _auth_rows_for_family(family_id: int) -> Dict[str, Any]:
    from backend.auth.service import auth_service

    def _rows(cursor, sql: str, params=()):
        cursor.execute(sql, params)
        return [_row_to_dict(row) for row in cursor.fetchall()]

    with auth_service._auth_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, owner_user_id, created_at, updated_at, archived_at FROM families WHERE id = ?",
            (int(family_id),),
        )
        family = _row_to_dict(cursor.fetchone())
        if not family:
            return {}
        return {
            "family": family,
            "memberships": _rows(
                cursor,
                """
                SELECT id, family_id, user_id, role, status, invited_by_user_id, created_at, updated_at
                FROM family_memberships
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "invites": _rows(
                cursor,
                """
                SELECT id, family_id, email, role, token_hash, invited_by_user_id,
                       expires_at, accepted_at, revoked_at, created_at
                FROM family_invites
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "capital_accounts": _rows(
                cursor,
                """
                SELECT id, family_id, owner_user_id, capital_account_id, is_visible,
                       is_default_target, created_at, updated_at
                FROM family_capital_accounts
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "capital_member_settings": _rows(
                cursor,
                """
                SELECT family_id, user_id, target_owner_user_id, target_capital_account_id, updated_at
                FROM family_capital_member_settings
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "categories": _rows(
                cursor,
                """
                SELECT id, family_id, semantic_key, display_name, type, is_active,
                       created_by_user_id, created_at, updated_at
                FROM family_categories
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "category_bindings": _rows(
                cursor,
                """
                SELECT id, family_id, family_category_id, user_id, local_category_id,
                       local_category_name, local_category_type, status,
                       confirmed_by_user_id, created_at, updated_at
                FROM family_category_bindings
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
            "category_audit_resolutions": _rows(
                cursor,
                """
                SELECT id, family_id, code, group_key, action, category_names_json,
                       note, resolved_by_user_id, created_at, updated_at
                FROM family_category_audit_resolutions
                WHERE family_id = ?
                """,
                (int(family_id),),
            ),
        }


def mirror_family_snapshot_shadow_write(
    family_id: int,
    config=settings,
) -> Dict[str, Any]:
    if not postgres_shadow_write_enabled(config):
        return {"enabled": False, "status": "disabled"}
    snapshot = _auth_rows_for_family(int(family_id))
    if not snapshot:
        return {"enabled": True, "status": "skipped", "reason": "missing_family"}
    try:
        repo = PostgresWriteRepository(config.database_url)
        with repo.connect() as conn:
            result = repo.mirror_family_snapshot(
                conn,
                source_db_path="auth.db",
                snapshot=snapshot,
            )
            conn.commit()
        return {"enabled": True, "status": "ok", "result": result}
    except Exception as exc:
        app_logger.warning(
            "PostgreSQL shadow-write family snapshot failed for family_id=%s: %s",
            int(family_id),
            exc,
        )
        return {"enabled": True, "status": "failed", "reason": str(exc)}
