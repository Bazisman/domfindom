from datetime import date as date_cls
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_user
from backend.schemas.common import MessageResponse
from backend.schemas.reconciliation import (
    ReconciliationApplyResponse,
    ReconciliationHistoryItemResponse,
    ReconciliationSourceCreateRequest,
    ReconciliationSourceResponse,
    ReconciliationSourceUpdateRequest,
    ReconciliationSummaryResponse,
)
from backend.services import transaction_service
from backend.storage.shadow_write import (
    mirror_created_transaction_shadow_write,
    mirror_reconciliation_shadow_write,
    mirror_reconciliation_source_shadow_write,
    require_mysql_reconciliation_shadow_write_success,
    require_mysql_transaction_shadow_write_success,
)


router = APIRouter()


def _serialize_source(row: Any) -> ReconciliationSourceResponse:
    return ReconciliationSourceResponse(
        id=int(row["id"]),
        name=str(row["name"]),
        balance=float(row["balance"] or 0),
        is_active=bool(row["is_active"]),
    )


def _serialize_history_item(row: Any) -> ReconciliationHistoryItemResponse:
    return ReconciliationHistoryItemResponse(
        id=int(row["id"]),
        real_balance=float(row["real_balance"] or 0),
        program_balance=float(row["program_balance"] or 0),
        difference=float(row["difference"] or 0),
        adjustment_transaction_id=row["adjustment_transaction_id"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]) if "updated_at" in row.keys() and row["updated_at"] else None,
    )


def _get_program_balance() -> float:
    return transaction_service.get_program_balance()


def _get_summary() -> ReconciliationSummaryResponse:
    sources = [_serialize_source(item) for item in transaction_service.get_reconciliation_sources()]
    history_rows = transaction_service.get_reconciliations_history(limit=20)
    history = [_serialize_history_item(item) for item in history_rows]
    last_row = transaction_service.get_last_reconciliation()
    real_balance = transaction_service.get_total_real_balance()
    program_balance = _get_program_balance()

    return ReconciliationSummaryResponse(
        program_balance=program_balance,
        real_balance=real_balance,
        difference=real_balance - program_balance,
        last_reconciliation=_serialize_history_item(last_row) if last_row else None,
        sources=sources,
        history=history,
    )


def _ensure_adjustment_category() -> None:
    transaction_service.ensure_category_exists("Корректировка", "both", "#9c27b0", "⚖️")


def _find_reconciliation_source(source_id: int, include_inactive_row=None):
    source = next((item for item in transaction_service.get_reconciliation_sources() if int(item["id"]) == int(source_id)), None)
    return source or include_inactive_row


@router.get("", response_model=ReconciliationSummaryResponse)
def get_reconciliation_summary() -> ReconciliationSummaryResponse:
    return _get_summary()


@router.post("/sources", response_model=ReconciliationSourceResponse, status_code=status.HTTP_201_CREATED)
def create_reconciliation_source(
    payload: ReconciliationSourceCreateRequest,
    current_user=Depends(require_user),
) -> ReconciliationSourceResponse:
    source_id = transaction_service.add_reconciliation_source(payload.name.strip(), payload.balance)
    sources = transaction_service.get_reconciliation_sources()
    source = next((item for item in sources if int(item["id"]) == int(source_id)), None)
    if not source:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Источник создан, но не найден")
    mirror_result = mirror_reconciliation_source_shadow_write(current_user, source)
    require_mysql_reconciliation_shadow_write_success(mirror_result, "reconciliation_source_create")
    return _serialize_source(source)


@router.patch("/sources/{source_id}", response_model=ReconciliationSourceResponse)
def update_reconciliation_source(
    source_id: int,
    payload: ReconciliationSourceUpdateRequest,
    current_user=Depends(require_user),
) -> ReconciliationSourceResponse:
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.balance is not None:
        updates["balance"] = payload.balance
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не переданы изменения")

    updated = transaction_service.update_reconciliation_source(source_id, **updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")

    sources = transaction_service.get_reconciliation_sources()
    source = next((item for item in sources if int(item["id"]) == source_id), None)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")
    mirror_result = mirror_reconciliation_source_shadow_write(current_user, source)
    require_mysql_reconciliation_shadow_write_success(mirror_result, "reconciliation_source_update")
    return _serialize_source(source)


@router.delete("/sources/{source_id}", response_model=MessageResponse)
def delete_reconciliation_source(
    source_id: int,
    current_user=Depends(require_user),
) -> MessageResponse:
    existing = _find_reconciliation_source(source_id)
    deleted = transaction_service.delete_reconciliation_source(source_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")
    if existing:
        disabled_source = dict(existing)
        disabled_source["is_active"] = 0
        mirror_result = mirror_reconciliation_source_shadow_write(current_user, disabled_source)
        require_mysql_reconciliation_shadow_write_success(mirror_result, "reconciliation_source_delete")
    return MessageResponse(message="Источник удален")


@router.post("/apply", response_model=ReconciliationApplyResponse)
def apply_reconciliation(current_user=Depends(require_user)) -> ReconciliationApplyResponse:
    real_balance = transaction_service.get_total_real_balance()
    program_balance = _get_program_balance()
    difference = real_balance - program_balance
    adjustment_transaction_id = None

    if difference != 0:
        _ensure_adjustment_category()
        today = date_cls.today().isoformat()
        comment = "Корректировка баланса"
        amount = abs(difference)
        if difference > 0:
            adjustment_transaction_id = transaction_service.add_income_with_capital(
                amount,
                "Корректировка",
                comment,
                today,
                0,
                None,
            )
        else:
            adjustment_transaction_id = transaction_service.add_expense(amount, "Корректировка", comment, today)
        adjustment_row = transaction_service.get_transaction_row_by_id(adjustment_transaction_id)
        mirror_result = mirror_created_transaction_shadow_write(current_user, adjustment_row)
        require_mysql_transaction_shadow_write_success(mirror_result, "reconciliation_adjustment_transaction")

    recon_id = transaction_service.save_reconciliation(
        real_balance,
        program_balance,
        difference,
        adjustment_transaction_id,
    )
    history = transaction_service.get_reconciliations_history(limit=20)
    reconciliation = next((item for item in history if int(item["id"]) == int(recon_id)), None)
    if not reconciliation:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Сверка сохранена, но не найдена")
    mirror_result = mirror_reconciliation_shadow_write(current_user, reconciliation)
    require_mysql_reconciliation_shadow_write_success(mirror_result, "reconciliation_apply")

    message = "Баланс сверен" if difference == 0 else "Создана корректировка и сохранена сверка"
    return ReconciliationApplyResponse(
        message=message,
        reconciliation=_serialize_history_item(reconciliation),
        adjustment_transaction_id=adjustment_transaction_id,
    )
