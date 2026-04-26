from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


MoneySource = Literal["cashless", "cash"]
AccountType = Literal["main", "cash", "cashless", "capital"]


class AccountResponse(BaseModel):
    id: int
    name: str
    type: AccountType
    balance: float
    currency: str
    is_active: bool
    is_default: bool = False
    icon: Optional[str] = None
    color: Optional[str] = None
    family_visible: bool = False
    family_default_target: bool = False
    money_source: Optional[MoneySource] = None


class AccountCreateRequest(BaseModel):
    type: Literal["capital"] = "capital"
    name: str
    balance: float = 0
    icon: str = "💰"
    color: str = "#ff9800"


class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    balance: Optional[float] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    family_visible: Optional[bool] = None
    family_default_target: Optional[bool] = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "AccountUpdateRequest":
        if all(
            value is None
            for value in (
                self.name,
                self.balance,
                self.icon,
                self.color,
                self.is_active,
                self.is_default,
                self.family_visible,
                self.family_default_target,
            )
        ):
            raise ValueError("Нужно передать хотя бы одно поле для изменения")
        return self


class TransferResponse(BaseModel):
    id: int
    from_account_id: int
    to_account_id: int
    amount: float
    date: str
    comment: str
    from_name: str
    to_name: str
    is_active: bool = True


class TransferCreateRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    target_owner_user_id: Optional[int] = None
    amount: float = Field(gt=0)
    date: Optional[str] = None
    comment: str = ""

    @model_validator(mode="after")
    def validate_accounts(self) -> "TransferCreateRequest":
        if self.target_owner_user_id is None and self.from_account_id == self.to_account_id:
            raise ValueError("Счет списания и счет зачисления должны отличаться")
        return self
