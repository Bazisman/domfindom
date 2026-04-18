from datetime import date as date_cls
from typing import Any

from fastapi import APIRouter, HTTPException, status

import core
from backend.schemas.common import MessageResponse
from backend.schemas.reconciliation import (
    ReconciliationApplyResponse,
    ReconciliationHistoryItemResponse,
    ReconciliationSourceCreateRequest,
    ReconciliationSourceResponse,
    ReconciliationSourceUpdateRequest,
    ReconciliationSummaryResponse,
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
    main_balance, _, _ = core.get_balance(force_update=True)
    return float(main_balance or 0)


def _get_summary() -> ReconciliationSummaryResponse:
    sources = [_serialize_source(item) for item in core.get_reconciliation_sources()]
    history_rows = core.get_reconciliations_history(limit=20)
    history = [_serialize_history_item(item) for item in history_rows]
    last_row = core.get_last_reconciliation()
    real_balance = float(core.get_total_real_balance() or 0)
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
    category = core.get_category_by_name("Корректировка")
    if category:
        return
    core.add_category("Корректировка", "both", "#9c27b0", "⚖️")


@router.get("", response_model=ReconciliationSummaryResponse)
def get_reconciliation_summary() -> ReconciliationSummaryResponse:
    return _get_summary()


@router.post("/sources", response_model=ReconciliationSourceResponse, status_code=status.HTTP_201_CREATED)
def create_reconciliation_source(payload: ReconciliationSourceCreateRequest) -> ReconciliationSourceResponse:
    source_id = core.add_reconciliation_source(payload.name.strip(), payload.balance)
    sources = core.get_reconciliation_sources()
    source = next((item for item in sources if int(item["id"]) == int(source_id)), None)
    if not source:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Источник создан, но не найден")
    return _serialize_source(source)


@router.patch("/sources/{source_id}", response_model=ReconciliationSourceResponse)
def update_reconciliation_source(source_id: int, payload: ReconciliationSourceUpdateRequest) -> ReconciliationSourceResponse:
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.balance is not None:
        updates["balance"] = payload.balance
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не переданы изменения")

    updated = core.update_reconciliation_source(source_id, **updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")

    sources = core.get_reconciliation_sources()
    source = next((item for item in sources if int(item["id"]) == source_id), None)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")
    return _serialize_source(source)


@router.delete("/sources/{source_id}", response_model=MessageResponse)
def delete_reconciliation_source(source_id: int) -> MessageResponse:
    deleted = core.delete_reconciliation_source(source_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")
    return MessageResponse(message="Источник удален")


@router.post("/apply", response_model=ReconciliationApplyResponse)
def apply_reconciliation() -> ReconciliationApplyResponse:
    real_balance = float(core.get_total_real_balance() or 0)
    program_balance = _get_program_balance()
    difference = real_balance - program_balance
    adjustment_transaction_id = None

    if difference != 0:
        _ensure_adjustment_category()
        today = date_cls.today().isoformat()
        comment = "Корректировка баланса"
        amount = abs(difference)
        if difference > 0:
            adjustment_transaction_id = core.add_income_with_capital(amount, "Корректировка", comment, today, 0, None)
        else:
            adjustment_transaction_id = core.add_expense(amount, "Корректировка", comment, today)

    recon_id = core.save_reconciliation(real_balance, program_balance, difference, adjustment_transaction_id)
    history = core.get_reconciliations_history(limit=20)
    reconciliation = next((item for item in history if int(item["id"]) == int(recon_id)), None)
    if not reconciliation:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Сверка сохранена, но не найдена")

    message = "Баланс сверен" if difference == 0 else "Создана корректировка и сохранена сверка"
    return ReconciliationApplyResponse(
        message=message,
        reconciliation=_serialize_history_item(reconciliation),
        adjustment_transaction_id=adjustment_transaction_id,
    )
