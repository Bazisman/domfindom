from pydantic import BaseModel


class ForecastResponse(BaseModel):
    current_balance: float
    planned_income: float
    planned_expense: float
    executed_planned_income: float
    executed_planned_expense: float
    monthly_budget: float
    total_budgets: float
    current_expenses: float
    budget_plan_remaining: float
    budget_remaining: float
    budget_forecast_remaining: float
    combined_pending_expense: float
    combined_executed_expense: float
    projected: float
    projected_balance: float
    end_date: str
