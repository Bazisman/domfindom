from datetime import datetime

from fastapi import APIRouter

import core
from backend.schemas.dashboard import BalanceSummary, DashboardResponse
from backend.schemas.budgets import BudgetStatusItem
from backend.schemas.forecast import ForecastResponse
from backend.schemas.transactions import TransactionResponse
from backend.services import row_to_transaction_response, transaction_service


router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard() -> DashboardResponse:
    balance = transaction_service.get_balance()
    current_month_stats = transaction_service.get_monthly_stats(datetime.now().year, datetime.now().month)
    forecast = core.get_projected_balance()
    # Dashboard should show recent executed operations, not future planned items.
    recent_transactions = [
        item
        for item in transaction_service.get_transactions(limit=100, period="all", offset=0)
        if item.status != "planned"
    ][:10]
    budgets = core.get_budget_status()[:5]

    return DashboardResponse(
        balance=BalanceSummary(
            main_balance=balance.main_balance,
            income=current_month_stats["income"],
            expense=current_month_stats["expense"],
            difference=round(current_month_stats["income"] - current_month_stats["expense"], 2),
        ),
        forecast=ForecastResponse(**forecast),
        recent_transactions=[
            TransactionResponse(**row_to_transaction_response(item))
            for item in recent_transactions
        ],
        budget_highlights=[BudgetStatusItem(**item) for item in budgets],
    )
