from fastapi import APIRouter

import core
from backend.schemas.forecast import ForecastResponse


router = APIRouter()


@router.get("/month-end", response_model=ForecastResponse)
def month_end_forecast() -> ForecastResponse:
    return ForecastResponse(**core.get_projected_balance())
