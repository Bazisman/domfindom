from typing import Optional

from pydantic import BaseModel, Field, model_validator


class BudgetResponse(BaseModel):
    id: int
    category_id: int
    category_name: str
    amount: float
    period: str


class BudgetCreateRequest(BaseModel):
    category_id: int
    amount: float = Field(gt=0)
    period: str = "monthly"


class BudgetUpdateRequest(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    period: Optional[str] = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "BudgetUpdateRequest":
        if self.amount is None and self.period is None:
            raise ValueError("Нужно передать хотя бы одно поле для изменения")
        return self


class BudgetReportItem(BaseModel):
    category_id: int
    category: str
    budget: float
    spent: float
    remaining: float
    percent: float
    status: str


class BudgetStatusItem(BaseModel):
    category_id: int
    category_name: str
    icon: str
    color: str
    budget_amount: float
    spent: float
    remaining: float
    plan_remaining: float
    forecast_remaining: Optional[float] = None
    forecast_mode: str = "none"
    percent: float
    over_budget: bool
