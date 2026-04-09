from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

import core
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
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")


@router.get("", response_model=List[BudgetResponse])
def list_budgets() -> List[BudgetResponse]:
    return [_budget_response(item) for item in transaction_service.get_budgets()]


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(payload: BudgetCreateRequest) -> BudgetResponse:
    category = core.get_category_by_id(payload.category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    created = transaction_service.set_budget(
        category_id=payload.category_id,
        amount=payload.amount,
        period=payload.period,
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Budget was not created")

    budgets = transaction_service.get_budgets()
    for item in budgets:
        if item["category_id"] == payload.category_id:
            return _budget_response(item)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Budget created but not found")


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Budget was not updated")

    refreshed = _get_budget_or_404(budget_id)
    return _budget_response(refreshed)


@router.get("/report", response_model=List[BudgetReportItem])
def budget_report(month: Optional[str] = Query(default=None)) -> List[BudgetReportItem]:
    report = core.get_budget_report(month)
    return [BudgetReportItem(**item) for item in report]


@router.get("/status", response_model=List[BudgetStatusItem])
def budget_status() -> List[BudgetStatusItem]:
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Budget was not deleted")
    return {"message": "Budget deleted"}
