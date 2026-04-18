from typing import List, Optional

from pydantic import BaseModel, Field


class ReconciliationSourceResponse(BaseModel):
    id: int
    name: str
    balance: float
    is_active: bool


class ReconciliationSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    balance: float = 0


class ReconciliationSourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    balance: Optional[float] = None


class ReconciliationHistoryItemResponse(BaseModel):
    id: int
    real_balance: float
    program_balance: float
    difference: float
    adjustment_transaction_id: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None


class ReconciliationSummaryResponse(BaseModel):
    program_balance: float
    real_balance: float
    difference: float
    last_reconciliation: Optional[ReconciliationHistoryItemResponse] = None
    sources: List[ReconciliationSourceResponse]
    history: List[ReconciliationHistoryItemResponse]


class ReconciliationApplyResponse(BaseModel):
    message: str
    reconciliation: ReconciliationHistoryItemResponse
    adjustment_transaction_id: Optional[int] = None
