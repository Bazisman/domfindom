from fastapi import APIRouter

from backend.services import transaction_service
from backend.schemas.forecast import ForecastResponse


router = APIRouter()


@router.get("/month-end", response_model=ForecastResponse)
def month_end_forecast() -> ForecastResponse:
    return ForecastResponse(**transaction_service.get_projected_balance())
