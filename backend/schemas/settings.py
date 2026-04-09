from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SettingsResponse(BaseModel):
    auto_capital_enabled: bool
    auto_capital_percent: int = Field(ge=0, le=100)
    default_capital_account_id: Optional[int] = None


class SettingsUpdateRequest(BaseModel):
    auto_capital_enabled: Optional[bool] = None
    auto_capital_percent: Optional[int] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_has_changes(self) -> "SettingsUpdateRequest":
        if self.auto_capital_enabled is None and self.auto_capital_percent is None:
            raise ValueError("At least one field must be provided")
        return self
