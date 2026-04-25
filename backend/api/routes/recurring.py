from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

import core
from backend.schemas.common import MessageResponse
from backend.schemas.recurring import (
    ExecutePlannedResponse,
    PlannedTransactionDueResponse,
    RecurringTemplateCreateRequest,
    RecurringTemplateResponse,
    RecurringTemplateUpdateRequest,
)
from backend.services import transaction_service


router = APIRouter()


def _template_response(row) -> RecurringTemplateResponse:
    return RecurringTemplateResponse(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        amount=float(row["amount"]),
        day_of_month=int(row["day_of_month"]),
        category_id=row["category_id"],
        category_name=row["category_name"] if "category_name" in row.keys() else None,
        comment_template=row["comment_template"] or "",
        money_source=row["money_source"] if "money_source" in row.keys() else "cashless",
        months_ahead=int(row["months_ahead"]),
        working_days_only=bool(row["working_days_only"]),
        is_active=bool(row["is_active"]),
    )


@router.get("", response_model=List[RecurringTemplateResponse])
def list_recurring_templates(
    type: Optional[str] = Query(default=None),
) -> List[RecurringTemplateResponse]:
    rows = transaction_service.get_recurring_templates(type)
    return [_template_response(row) for row in rows]


@router.post("", response_model=RecurringTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_recurring_template(payload: RecurringTemplateCreateRequest) -> RecurringTemplateResponse:
    template_id = transaction_service.create_recurring_template(
        template_type=payload.type,
        name=payload.name,
        amount=payload.amount,
        day_of_month=payload.day_of_month,
        category_id=payload.category_id,
        comment_template=payload.comment_template,
        months_ahead=payload.months_ahead,
        working_days_only=payload.working_days_only,
        money_source=payload.money_source,
    )
    if not template_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось создать шаблон")

    row = core.get_recurring_template_by_id(template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Шаблон создан, но не найден")
    category_name = None
    if row["category_id"]:
        category = core.get_category_by_id(row["category_id"])
        category_name = category["name"] if category else None
    merged = dict(row)
    merged["category_name"] = category_name
    return _template_response(merged)


@router.patch("/{template_id}", response_model=RecurringTemplateResponse)
def update_recurring_template(template_id: int, payload: RecurringTemplateUpdateRequest) -> RecurringTemplateResponse:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не переданы изменения")

    updated = transaction_service.update_recurring_template(template_id, **update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обновить шаблон")

    row = core.get_recurring_template_by_id(template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    category_name = None
    if row["category_id"]:
        category = core.get_category_by_id(row["category_id"])
        category_name = category["name"] if category else None
    merged = dict(row)
    merged["category_name"] = category_name
    return _template_response(merged)


@router.delete("/{template_id}", response_model=MessageResponse)
def delete_recurring_template(template_id: int) -> MessageResponse:
    deleted = transaction_service.delete_recurring_template(template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    return MessageResponse(message="Шаблон удален")


@router.get("/due", response_model=List[PlannedTransactionDueResponse])
def list_due_planned_transactions() -> List[PlannedTransactionDueResponse]:
    rows = core.get_planned_transactions_due()
    return [
        PlannedTransactionDueResponse(
            id=row["id"],
            type=row["type"],
            category=row["category"],
            amount=float(row["amount"]),
            comment=row["comment"] or "",
            date=row["date"],
            money_source=row["money_source"] if "money_source" in row.keys() else "cashless",
            template_id=row["template_id"],
            template_name=row["template_name"],
        )
        for row in rows
    ]


@router.post("/execute-due", response_model=ExecutePlannedResponse)
def execute_due_planned_transactions() -> ExecutePlannedResponse:
    executed_count = transaction_service.execute_planned_transactions()
    return ExecutePlannedResponse(
        executed_count=executed_count,
        message=f"Исполнено запланированных операций: {executed_count}",
    )
