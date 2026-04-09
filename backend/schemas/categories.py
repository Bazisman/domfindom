from typing import Optional

from pydantic import BaseModel, model_validator


class CategoryResponse(BaseModel):
    id: int
    name: str
    type: str
    color: str
    icon: str
    is_active: bool


class CategoryCreateRequest(BaseModel):
    name: str
    type: str = "both"
    color: str = "#808080"
    icon: str = "📁"


class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "CategoryUpdateRequest":
        if all(
            value is None
            for value in (
                self.name,
                self.type,
                self.color,
                self.icon,
                self.is_active,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self
