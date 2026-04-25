from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SettingsResponse(BaseModel):
    auto_capital_enabled: bool
    auto_capital_percent: int = Field(ge=0, le=100)
    default_capital_account_id: Optional[int] = None
    default_money_source: Literal["cashless", "cash"] = "cashless"


class SettingsUpdateRequest(BaseModel):
    auto_capital_enabled: Optional[bool] = None
    auto_capital_percent: Optional[int] = Field(default=None, ge=0, le=100)
    default_money_source: Optional[Literal["cashless", "cash"]] = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "SettingsUpdateRequest":
        if (
            self.auto_capital_enabled is None
            and self.auto_capital_percent is None
            and self.default_money_source is None
        ):
            raise ValueError("Нужно передать хотя бы одно поле для изменения")
        return self
