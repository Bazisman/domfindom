from typing import Literal, Optional

from pydantic import BaseModel, Field


RecurringType = Literal["income", "expense"]
MoneySource = Literal["cashless", "cash"]


class RecurringTemplateResponse(BaseModel):
    id: int
    type: RecurringType
    name: str
    amount: float
    day_of_month: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    comment_template: str = ""
    money_source: MoneySource = "cashless"
    months_ahead: int = Field(ge=1, le=24)
    working_days_only: bool = True
    is_active: bool = True


class RecurringTemplateCreateRequest(BaseModel):
    type: RecurringType
    name: str = Field(min_length=1)
    amount: float = Field(gt=0)
    day_of_month: int = Field(ge=1, le=31)
    category_id: Optional[int] = None
    comment_template: str = ""
    money_source: MoneySource = "cashless"
    months_ahead: int = Field(default=12, ge=1, le=24)
    working_days_only: bool = True


class RecurringTemplateUpdateRequest(BaseModel):
    type: Optional[RecurringType] = None
    name: Optional[str] = Field(default=None, min_length=1)
    amount: Optional[float] = Field(default=None, gt=0)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
    category_id: Optional[int] = None
    comment_template: Optional[str] = None
    money_source: Optional[MoneySource] = None
    months_ahead: Optional[int] = Field(default=None, ge=1, le=24)
    working_days_only: Optional[bool] = None
    is_active: Optional[bool] = None


class PlannedTransactionDueResponse(BaseModel):
    id: int
    type: RecurringType
    category: str
    amount: float
    comment: str
    date: str
    money_source: MoneySource = "cashless"
    template_id: Optional[int] = None
    template_name: Optional[str] = None


class ExecutePlannedResponse(BaseModel):
    executed_count: int
    message: str
