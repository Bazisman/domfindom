from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


TransactionType = Literal["income", "expense"]
TransactionStatus = Literal["actual", "planned"]
MoneySource = Literal["cashless", "cash"]


class TransactionResponse(BaseModel):
    id: int
    type: TransactionType
    category: str
    amount: float
    comment: str
    date: str
    status: TransactionStatus
    money_source: MoneySource = "cashless"


class TransactionPageResponse(BaseModel):
    items: List[TransactionResponse]
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
    money_source: MoneySource = "cashless"
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


class TransactionUpdateRequest(BaseModel):
    type: Optional[TransactionType] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    comment: Optional[str] = None
    date: Optional[str] = None
    money_source: Optional[MoneySource] = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "TransactionUpdateRequest":
        if all(
            value is None
            for value in (
                self.type,
                self.category_id,
                self.category_name,
                self.amount,
                self.comment,
                self.date,
                self.money_source,
            )
        ):
            raise ValueError("Нужно передать хотя бы одно поле для изменения")
        return self
