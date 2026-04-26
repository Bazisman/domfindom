from datetime import datetime

from fastapi import APIRouter, Request

import core
from backend.auth.service import auth_service
from backend.schemas.dashboard import BalanceSummary, DashboardResponse
from backend.schemas.budgets import BudgetStatusItem
from backend.schemas.forecast import ForecastResponse
from backend.schemas.transactions import TransactionResponse
from backend.services import row_to_transaction_response, transaction_service
from backend.storage.shadow_read import compare_dashboard_mysql_shadow_read, compare_dashboard_shadow_read


router = APIRouter()


def _family_capital_outflow_for_user(user_id: int, start_date: str, end_date: str) -> float:
    total = 0.0
    for item in auth_service.list_family_capital_contributions_for_user(user_id=user_id, limit=300):
        if int(item["source_user_id"]) != user_id:
            continue
        item_date = str(item["date"] or "")
        if start_date <= item_date <= end_date:
            total += float(item["amount"] or 0.0)
    return total


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(request: Request) -> DashboardResponse:
    now = datetime.now()
    start_date = now.replace(day=1).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    balance = transaction_service.get_balance()
    current_month_stats = transaction_service.get_monthly_stats(now.year, now.month)
    direct_capital_outflow = float(transaction_service.get_capital_outflow_for_period(start_date, today) or 0.0)
    family_capital_outflow = 0.0
    current_user = getattr(request.state, "current_user", None)
    if current_user:
        family_capital_outflow = _family_capital_outflow_for_user(int(current_user["id"]), start_date, today)
    capital_outflow = direct_capital_outflow + family_capital_outflow

    forecast = transaction_service.get_projected_balance()
    forecast["executed_planned_expense"] = round(
        float(forecast.get("executed_planned_expense", 0.0) or 0.0) + family_capital_outflow,
        2,
    )
    forecast["combined_executed_expense"] = round(
        float(forecast.get("combined_executed_expense", 0.0) or 0.0) + family_capital_outflow,
        2,
    )
    adjusted_projected = float(forecast.get("projected_balance", 0.0) or 0.0) - family_capital_outflow
    forecast["projected_balance"] = round(adjusted_projected, 2)
    forecast["projected"] = round(adjusted_projected, 2)
    # Dashboard should show recent executed operations, not future planned items.
    recent_transactions = [
        item
        for item in transaction_service.get_transactions(limit=100, period="all", offset=0)
        if item.status != "planned"
    ][:10]
    budgets = core.get_budget_status()[:5]
    compare_dashboard_shadow_read(current_user, balance, current_month_stats, now.year, now.month)
    compare_dashboard_mysql_shadow_read(current_user, balance, current_month_stats, now.year, now.month)

    return DashboardResponse(
        balance=BalanceSummary(
            main_balance=balance.main_balance,
            income=current_month_stats["income"],
            expense=round(float(current_month_stats["expense"] or 0.0) + capital_outflow, 2),
            difference=round(
                float(current_month_stats["income"] or 0.0)
                - (float(current_month_stats["expense"] or 0.0) + capital_outflow),
                2,
            ),
        ),
        forecast=ForecastResponse(**forecast),
        recent_transactions=[
            TransactionResponse(**row_to_transaction_response(item))
            for item in recent_transactions
        ],
        budget_highlights=[BudgetStatusItem(**item) for item in budgets],
    )
