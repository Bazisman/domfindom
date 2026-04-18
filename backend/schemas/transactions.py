from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


TransactionType = Literal["income", "expense"]
TransactionStatus = Literal["actual", "planned"]


class TransactionResponse(BaseModel):
    id: int
    type: TransactionType
    category: str
    amount: float
    comment: str
    date: str
    status: TransactionStatus


class TransactionPageResponse(BaseModel):
    items: list[TransactionResponse]
    limit: int
    offset: int
    total: int


class RecurringOptionsRequest(BaseModel):
    enabled: bool = False
    template_name: str = Field(default="", max_length=255)
    day_of_month: int = Field(ge=1, le=31)
    months_ahead: int = Field(default=12, ge=1, le=24)
    working_days_only: bool = True


class TransactionCreateRequest(BaseModel):
    type: TransactionType
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: float = Field(gt=0)
    comment: str = ""
    date: str
    auto_capital_percent: Optional[int] = Field(default=None, ge=0, le=100)
    capital_account_id: Optional[int] = None
    recurring: Optional[RecurringOptionsRequest] = None

    @model_validator(mode="after")
    def validate_category(self) -> "TransactionCreateRequest":
        if not self.category_id and not self.category_name:
            raise ValueError("Нужно указать категорию")
        return self


class TransactionCreateResponse(BaseModel):
    id: int
    message: str
    transaction: TransactionResponse
