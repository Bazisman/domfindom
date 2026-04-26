from fastapi import APIRouter

import core
from backend.schemas.settings import SettingsResponse, SettingsUpdateRequest
from backend.services import transaction_service


router = APIRouter()


def _build_settings_response() -> SettingsResponse:
    enabled, percent = transaction_service.get_auto_capital_settings()
    default_account = transaction_service.get_default_capital_account()
    return SettingsResponse(
        auto_capital_enabled=enabled,
        auto_capital_percent=percent,
        default_capital_account_id=default_account["id"] if default_account else None,
        default_money_source=core.get_default_money_source(),
    )


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _build_settings_response()


@router.patch("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
    current_enabled, current_percent = transaction_service.get_auto_capital_settings()
    transaction_service.set_auto_capital_settings(
        enabled=payload.auto_capital_enabled if payload.auto_capital_enabled is not None else current_enabled,
        percent=payload.auto_capital_percent if payload.auto_capital_percent is not None else current_percent,
    )
    if payload.default_money_source is not None:
        core.set_default_money_source(payload.default_money_source)
    return _build_settings_response()
