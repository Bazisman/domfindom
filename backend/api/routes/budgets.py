import calendar
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status

import core
from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.budgets import (
    BudgetCreateRequest,
    BudgetReportItem,
    BudgetResponse,
    BudgetStatusItem,
    BudgetUpdateRequest,
)
from backend.services import transaction_service


router = APIRouter()


def _budget_response(row) -> BudgetResponse:
    return BudgetResponse(
        id=row["id"],
        category_id=row["category_id"],
        category_name=row["category"],
        amount=row["amount"],
        period=row["period"],
    )


def _get_budget_or_404(budget_id: int):
    budgets = transaction_service.get_budgets()
    for item in budgets:
        if item["id"] == budget_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Бюджет не найден")


def _normalize_budget_category_name(value: object) -> str:
    normalized = str(value or "").replace("\u00a0", " ").strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^[\s.,;:]+|[\s.,;:]+$", "", normalized)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    return normalized


def _personal_category_names_for_family(family_id: int) -> Set[str]:
    names: Set[str] = set()
    for item in auth_service.list_family_category_audit_resolutions(family_id):
        if str(item.get("action") or "") != "keep_personal":
            continue
        for category_name in item.get("category_names", []):
            normalized = _normalize_budget_category_name(category_name)
            if normalized:
                names.add(normalized)
    return names


def _build_family_budget_status(family_id: int) -> List[BudgetStatusItem]:
    personal_status = core.get_budget_status()
    budgets = {
        int(item["category_id"]): item
        for item in transaction_service.get_budgets()
    }
    members = auth_service.list_family_members(family_id)
    personal_category_names = _personal_category_names_for_family(family_id)
    spent_by_category_name: Dict[str, float] = defaultdict(float)

    today = datetime.now()
    start_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    end_of_month = today.strftime("%Y-%m-%d")
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    remaining_days_including_today = max(days_in_month - today.day + 1, 0)

    for member in members:
        user_id = int(member["user_id"])
        user_db_path = auth_service.ensure_user_finance_db(user_id)
        db_token = core.push_db_name(user_db_path)
        try:
            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT category, COALESCE(SUM(amount), 0) AS spent
                    FROM transactions
                    WHERE type = 'expense'
                      AND date >= ?
                      AND date <= ?
                      AND (status = 'actual' OR status IS NULL)
                    GROUP BY category
                    """,
                    (start_of_month, end_of_month),
                )
                for row in cursor.fetchall():
                    spent_by_category_name[str(row["category"])] += float(row["spent"] or 0.0)
        finally:
            core.pop_db_name(db_token)

    result: List[BudgetStatusItem] = []
    for item in personal_status:
        category_id = int(item["category_id"])
        category_name = str(item["category_name"])
        if _normalize_budget_category_name(category_name) in personal_category_names:
            continue
        spent = round(spent_by_category_name.get(category_name, 0.0), 2)
        budget_config = budgets.get(category_id)
        period = budget_config["period"] if budget_config and "period" in budget_config.keys() else "monthly"
        normalized_period = (period or "monthly").lower()
        if normalized_period == "daily":
            daily_amount = float(budget_config["amount"] or 0.0) if budget_config else 0.0
            budget_amount = spent + (daily_amount * remaining_days_including_today)
        else:
            budget_amount = float(item["budget_amount"])
        remaining = round(budget_amount - spent, 2)
        percent = round((spent / budget_amount * 100) if budget_amount > 0 else 0.0, 1)
        result.append(
            BudgetStatusItem(
                category_id=category_id,
                category_name=category_name,
                icon=str(item["icon"]),
                color=str(item["color"]),
                budget_amount=round(budget_amount, 2),
                spent=spent,
                remaining=remaining,
                percent=percent,
                over_budget=remaining < 0,
            )
        )
    return result


@router.get("", response_model=List[BudgetResponse])
def list_budgets() -> List[BudgetResponse]:
    return [_budget_response(item) for item in transaction_service.get_budgets()]


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(payload: BudgetCreateRequest) -> BudgetResponse:
    category = core.get_category_by_id(payload.category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")

    created = transaction_service.set_budget(
        category_id=payload.category_id,
        amount=payload.amount,
        period=payload.period,
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось создать бюджет")

    budgets = transaction_service.get_budgets()
    for item in budgets:
        if item["category_id"] == payload.category_id:
            return _budget_response(item)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Бюджет создан, но не найден")


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(budget_id: int, payload: BudgetUpdateRequest) -> BudgetResponse:
    budget = _get_budget_or_404(budget_id)
    amount = payload.amount if payload.amount is not None else budget["amount"]
    period = payload.period if payload.period is not None else budget["period"]

    updated = transaction_service.set_budget(
        category_id=budget["category_id"],
        amount=amount,
        period=period,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обновить бюджет")

    refreshed = _get_budget_or_404(budget_id)
    return _budget_response(refreshed)


@router.get("/report", response_model=List[BudgetReportItem])
def budget_report(month: Optional[str] = Query(default=None)) -> List[BudgetReportItem]:
    report = core.get_budget_report(month)
    return [BudgetReportItem(**item) for item in report]


@router.get("/status", response_model=List[BudgetStatusItem])
def budget_status(
    family_id: Optional[int] = Query(default=None, ge=1),
    current_user=Depends(require_user),
) -> List[BudgetStatusItem]:
    if family_id is not None:
        membership = auth_service.get_family_membership(family_id=family_id, user_id=int(current_user["id"]))
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семья не найдена или доступ запрещен.")
        return _build_family_budget_status(family_id)

    status_items = core.get_budget_status()
    return [BudgetStatusItem(**item) for item in status_items]


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(budget_id: int) -> BudgetResponse:
    return _budget_response(_get_budget_or_404(budget_id))


@router.delete("/{budget_id}")
def delete_budget(budget_id: int) -> Dict[str, str]:
    _get_budget_or_404(budget_id)
    deleted = transaction_service.delete_budget(budget_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось удалить бюджет")
    return {"message": "Бюджет удален"}
