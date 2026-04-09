from typing import List

from pydantic import BaseModel

from backend.schemas.budgets import BudgetStatusItem
from backend.schemas.forecast import ForecastResponse
from backend.schemas.transactions import TransactionResponse


class BalanceSummary(BaseModel):
    main_balance: float
    income: float
    expense: float
    difference: float


class DashboardResponse(BaseModel):
    balance: BalanceSummary
    forecast: ForecastResponse
    recent_transactions: List[TransactionResponse]
    budget_highlights: List[BudgetStatusItem]
