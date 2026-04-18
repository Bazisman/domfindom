from typing import List, Literal, Optional

from pydantic import BaseModel


SummaryTransactionType = Literal["income", "expense"]
SummaryPeriodType = Literal["month", "last_month", "year", "all", "custom"]
SummaryScopeType = Literal["personal", "family"]


class CategorySummaryItemResponse(BaseModel):
    category: str
    total: float
    share_percent: float
    color: str
    icon: str


class CategorySummaryResponse(BaseModel):
    scope: SummaryScopeType
    family_id: Optional[int] = None
    family_name: Optional[str] = None
    type: SummaryTransactionType
    period: SummaryPeriodType
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total: float
    categories_count: int
    items: List[CategorySummaryItemResponse]
