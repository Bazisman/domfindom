import calendar
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.budgets import (
    BudgetCreateRequest,
    BudgetReportItem,
    BudgetResponse,
    BudgetStatusItem,
    BudgetUpdateRequest,
)
from backend.services import category_service, run_in_user_finance_db, transaction_service
from backend.storage.shadow_write import (
    mirror_budget_shadow_write,
    mirror_deleted_budget_shadow_write,
)


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
    members = auth_service.list_family_members(family_id)
    personal_category_names = _personal_category_names_for_family(family_id)
    spent_by_category_name: Dict[str, float] = defaultdict(float)
    budgets_by_category_name: Dict[str, Dict[str, object]] = {}

    today = datetime.now()
    start_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    end_of_month = today.strftime("%Y-%m-%d")
    remaining_days_including_today = max(calendar.monthrange(today.year, today.month)[1] - today.day + 1, 0)

    for member in members:
        user_id = int(member["user_id"])
        def _action():
            for row in transaction_service.get_expenses_by_category(start_of_month, end_of_month):
                normalized = _normalize_budget_category_name(row["category"])
                if normalized:
                    spent_by_category_name[normalized] += float(row["total"] or 0.0)

            for row in transaction_service.get_budgets():
                category_id = int(row["category_id"] or 0)
                category = category_service.get_category_by_id(category_id)
                category_name = str(row["category"] or (category.name if category else ""))
                normalized = _normalize_budget_category_name(category_name)
                if not normalized or normalized in personal_category_names:
                    continue
                period = str(row["period"] or "monthly").strip().lower()
                amount = float(row["amount"] or 0.0)
                row_keys = row.keys() if hasattr(row, "keys") else []
                row_icon = row["icon"] if "icon" in row_keys else ""
                row_color = row["color"] if "color" in row_keys else ""
                bucket = budgets_by_category_name.setdefault(
                    normalized,
                    {
                        "category_id": category_id,
                        "category_name": category_name,
                        "icon": str((category.icon if category else row_icon) or ""),
                        "color": str((category.color if category else row_color) or ""),
                        "monthly_amount": 0.0,
                        "daily_amount": 0.0,
                        "has_non_daily": False,
                    },
                )
                bucket["monthly_amount"] = float(bucket["monthly_amount"]) + float(
                    transaction_service.get_budget_monthly_limit(amount, period, today)
                )
                if period == "daily":
                    bucket["daily_amount"] = float(bucket["daily_amount"]) + amount
                else:
                    bucket["has_non_daily"] = True

        run_in_user_finance_db(user_id, _action)

    result: List[BudgetStatusItem] = []
    for normalized_name, budget_meta in sorted(
        budgets_by_category_name.items(),
        key=lambda item: str(item[1]["category_name"]).lower(),
    ):
        spent = round(spent_by_category_name.get(normalized_name, 0.0), 2)
        daily_amount = float(budget_meta["daily_amount"])
        has_non_daily = bool(budget_meta["has_non_daily"])
        if daily_amount > 0 and not has_non_daily:
            budget_amount = spent + (daily_amount * remaining_days_including_today)
        else:
            budget_amount = float(budget_meta["monthly_amount"])
        remaining = round(budget_amount - spent, 2)
        percent = round((spent / budget_amount * 100) if budget_amount > 0 else 0.0, 1)
        result.append(
            BudgetStatusItem(
                category_id=int(budget_meta["category_id"]),
                category_name=str(budget_meta["category_name"]),
                icon=str(budget_meta["icon"]),
                color=str(budget_meta["color"]),
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
def create_budget(payload: BudgetCreateRequest, current_user=Depends(require_user)) -> BudgetResponse:
    category = category_service.get_category_by_id(payload.category_id)
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
            mirror_budget_shadow_write(current_user, item)
            return _budget_response(item)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Бюджет создан, но не найден")


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int,
    payload: BudgetUpdateRequest,
    current_user=Depends(require_user),
) -> BudgetResponse:
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
    mirror_budget_shadow_write(current_user, refreshed)
    return _budget_response(refreshed)


@router.get("/report", response_model=List[BudgetReportItem])
def budget_report(month: Optional[str] = Query(default=None)) -> List[BudgetReportItem]:
    report = transaction_service.get_budget_report(month)
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

    status_items = transaction_service.get_budget_status()
    return [BudgetStatusItem(**item) for item in status_items]


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(budget_id: int) -> BudgetResponse:
    return _budget_response(_get_budget_or_404(budget_id))


@router.delete("/{budget_id}")
def delete_budget(budget_id: int, current_user=Depends(require_user)) -> Dict[str, str]:
    _get_budget_or_404(budget_id)
    deleted = transaction_service.delete_budget(budget_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось удалить бюджет")
    mirror_deleted_budget_shadow_write(current_user, budget_id)
    return {"message": "Бюджет удален"}
