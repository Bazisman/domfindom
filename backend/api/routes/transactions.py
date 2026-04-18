import calendar
from datetime import date as date_cls
from typing import List, Tuple

from fastapi import APIRouter, HTTPException, Query, status

import core
from backend.schemas.common import MessageResponse
from backend.schemas.transactions import (
    TransactionCreateRequest,
    TransactionCreateResponse,
    TransactionResponse,
)
from backend.services import category_service, row_to_transaction_response, transaction_service
from models import Transaction


router = APIRouter()


def _list_transactions_window(limit: int, offset: int, period: str, include_planned: bool) -> List[Transaction]:
    if include_planned:
        return transaction_service.get_transactions(limit=limit, offset=offset, period=period)

    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    batch_size = min(max(safe_limit * 3, 100), 500)
    raw_offset = 0
    skipped = 0
    collected: List[Transaction] = []

    while len(collected) < safe_limit:
        batch = transaction_service.get_transactions(limit=batch_size, offset=raw_offset, period=period)
        if not batch:
            break

        for item in batch:
            if item.status == "planned":
                continue
            if skipped < safe_offset:
                skipped += 1
                continue
            collected.append(item)
            if len(collected) >= safe_limit:
                break

        if len(batch) < batch_size:
            break
        raw_offset += len(batch)

    return collected


def _resolve_category_name(payload: TransactionCreateRequest) -> str:
    if payload.category_name:
        return payload.category_name
    category = category_service.get_category_by_id(payload.category_id or 0)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    return category.name


def _month_range(date_value: str) -> Tuple[str, str]:
    year, month = map(int, date_value.split("-")[:2])
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _is_future_date(date_value: str) -> bool:
    return date_value > date_cls.today().isoformat()


@router.get("", response_model=List[TransactionResponse])
def list_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default="all"),
    include_planned: bool = Query(default=True),
) -> List[TransactionResponse]:
    transactions = _list_transactions_window(limit=limit, offset=offset, period=period, include_planned=include_planned)
    return [TransactionResponse(**row_to_transaction_response(item)) for item in transactions]


@router.post("", response_model=TransactionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreateRequest) -> TransactionCreateResponse:
    category_name = _resolve_category_name(payload)
    category = core.get_category_by_name(category_name)
    is_future = _is_future_date(payload.date)
    recurring_payload = payload.recurring if payload.recurring and payload.recurring.enabled else None
    planned_date = payload.date

    if (
        is_future
        and recurring_payload
        and recurring_payload.working_days_only
    ):
        planned_date = core._adjust_to_workday(payload.date)

    if is_future:
        created_id = core.add_planned_transaction(
            payload.type,
            category_name,
            payload.amount,
            payload.comment,
            planned_date,
            template_id=None,
        )
    else:
        if payload.type == "income":
            settings_enabled, settings_percent = transaction_service.get_auto_capital_settings()
            default_capital_account = core.get_default_capital_account()
            auto_capital_percent = payload.auto_capital_percent
            capital_account_id = payload.capital_account_id

            if auto_capital_percent is None:
                auto_capital_percent = settings_percent if settings_enabled else 0
            if capital_account_id is None and default_capital_account:
                capital_account_id = default_capital_account["id"]

            created_id = core.add_income_with_capital(
                payload.amount,
                category_name,
                payload.comment,
                payload.date,
                auto_capital_percent,
                capital_account_id,
            )
        else:
            created_id = core.add_expense(
                payload.amount,
                category_name,
                payload.comment,
                payload.date,
            )

    if recurring_payload:
        template_name = recurring_payload.template_name.strip() or payload.comment.strip() or category_name
        template_id = core.create_recurring_template(
            template_type=payload.type,
            name=template_name,
            amount=payload.amount,
            day_of_month=recurring_payload.day_of_month,
            category_id=category["id"] if category else payload.category_id,
            comment_template=payload.comment,
            months_ahead=recurring_payload.months_ahead,
            working_days_only=recurring_payload.working_days_only,
        )
        month_start, month_end = _month_range(planned_date if is_future else payload.date)
        core.delete_planned_transactions_in_period(template_id, month_start, month_end)
        if is_future:
            core.assign_template_to_planned_transaction(created_id, template_id)

    row = core.get_transaction_by_id(created_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Транзакция создана, но не найдена")

    transaction = Transaction(
        id=row["id"],
        type=row["type"],
        category=row["category"],
        amount=row["amount"],
        comment=row["comment"],
        date=row["date"],
        status=row["status"] if "status" in row.keys() else "actual",
    )
    return TransactionCreateResponse(
        id=created_id,
        message="Транзакция создана",
        transaction=TransactionResponse(**row_to_transaction_response(transaction)),
    )


@router.delete("/{transaction_id}", response_model=MessageResponse)
def delete_transaction(transaction_id: int) -> MessageResponse:
    deleted = transaction_service.delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена")
    return MessageResponse(message="Транзакция удалена")
