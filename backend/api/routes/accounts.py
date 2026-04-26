from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.accounts import AccountCreateRequest, AccountResponse, AccountUpdateRequest
from backend.schemas.common import MessageResponse
from backend.services import transaction_service
from backend.storage.shadow_write import (
    mirror_capital_accounts_shadow_write,
    mirror_family_snapshot_shadow_write,
    require_mysql_accounts_capital_shadow_write_success,
)


router = APIRouter()


def _row_value(row, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _current_family_id(user_id: int) -> int:
    family = auth_service.get_primary_family(user_id)
    return int(family["id"]) if family else 0


def _hide_family_capital_account_if_needed(family_id: int, owner_user_id: int, account_id: int) -> None:
    if family_id <= 0:
        return
    auth_service.hide_family_capital_account(
        family_id=family_id,
        owner_user_id=owner_user_id,
        capital_account_id=account_id,
    )


def _family_meta_map(family_id: int, owner_user_id: int):
    if family_id <= 0:
        return {}
    return {
        int(item["capital_account_id"]): item
        for item in auth_service.list_family_capital_accounts(family_id)
        if int(item["owner_user_id"]) == owner_user_id
    }


def _daily_account_response(row) -> AccountResponse:
    account_id = int(_row_value(row, "id", 0))
    account_type = str(_row_value(row, "type", "main") or "main")
    money_source = "cash" if account_id == 2 or account_type == "cash" else "cashless"
    return AccountResponse(
        id=account_id,
        name=_row_value(row, "name", ""),
        type=account_type if account_type in {"main", "cash", "cashless"} else "main",
        balance=float(_row_value(row, "balance", 0) or 0),
        currency=_row_value(row, "currency", "RUB"),
        is_active=bool(_row_value(row, "is_active", 1)),
        is_default=False,
        icon=None,
        color=None,
        family_visible=False,
        family_default_target=False,
        money_source=money_source,
    )


def _capital_account_response(row, family_meta=None) -> AccountResponse:
    family_meta = family_meta or {}
    return AccountResponse(
        id=_row_value(row, "id", 0),
        name=_row_value(row, "name", ""),
        type="capital",
        balance=float(_row_value(row, "balance", 0) or 0),
        currency=_row_value(row, "currency", "RUB"),
        is_active=bool(_row_value(row, "is_active", 1)),
        is_default=bool(_row_value(row, "is_default", 0)),
        icon=_row_value(row, "icon"),
        color=_row_value(row, "color"),
        family_visible=bool(family_meta.get("is_visible", False)),
        family_default_target=bool(family_meta.get("is_default_target", False)),
        money_source=None,
    )


def _find_account_row(account_id: int, include_inactive: bool = False):
    if account_id < 100:
        for account in transaction_service.get_all_accounts(include_inactive=include_inactive):
            if _row_value(account, "id") == account_id:
                return ("daily", account)
        return None

    for account in transaction_service.get_capital_accounts(include_inactive=include_inactive):
        if _row_value(account, "id") == account_id:
            return ("capital", account)
    return None


@router.get("", response_model=List[AccountResponse])
def list_accounts(
    include_inactive: bool = Query(default=False),
    current_user=Depends(require_user),
) -> List[AccountResponse]:
    family_id = _current_family_id(int(current_user["id"]))
    family_meta = _family_meta_map(family_id, int(current_user["id"]))
    daily_accounts = [
        _daily_account_response(account)
        for account in transaction_service.get_all_accounts(include_inactive=include_inactive)
    ]
    capital_accounts = [
        _capital_account_response(account, family_meta.get(int(_row_value(account, "id", 0))))
        for account in transaction_service.get_capital_accounts(include_inactive=include_inactive)
    ]
    return [*daily_accounts, *capital_accounts]


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, current_user=Depends(require_user)) -> AccountResponse:
    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    account_type, row = found
    if account_type == "daily":
        return _daily_account_response(row)

    family_id = _current_family_id(int(current_user["id"]))
    family_meta = _family_meta_map(family_id, int(current_user["id"]))
    return _capital_account_response(row, family_meta.get(account_id))


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreateRequest, current_user=Depends(require_user)) -> AccountResponse:
    account_id = transaction_service.add_capital_account(
        name=payload.name,
        balance=payload.balance,
        icon=payload.icon,
        color=payload.color,
    )
    if not account_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось создать счет")

    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Счет создан, но не найден")
    mirror_result = mirror_capital_accounts_shadow_write(
        current_user,
        transaction_service.get_capital_accounts(include_inactive=True),
    )
    require_mysql_accounts_capital_shadow_write_success(mirror_result, "capital_account_create")
    family_id = _current_family_id(int(current_user["id"]))
    family_meta = _family_meta_map(family_id, int(current_user["id"]))
    return _capital_account_response(found[1], family_meta.get(account_id))


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, payload: AccountUpdateRequest, current_user=Depends(require_user)) -> AccountResponse:
    current_user_id = int(current_user["id"])
    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    account_type, _ = found
    if account_type != "capital":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Через этот раздел можно изменять только счета капитала",
        )

    if payload.is_default is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Счет капитала по умолчанию можно изменить только назначив другой счет основным",
        )

    update_data = payload.model_dump(exclude_none=True)
    should_set_default = update_data.pop("is_default", False)
    family_visible = update_data.pop("family_visible", None)
    family_default_target = update_data.pop("family_default_target", None)

    updated = True
    if update_data:
        updated = transaction_service.update_capital_account(account_id, **update_data)
    if should_set_default:
        updated = transaction_service.set_default_capital_account(account_id) and updated

    family_id = _current_family_id(current_user_id)
    if family_id > 0 and (family_visible is not None or family_default_target is not None):
        existing_meta = auth_service.get_family_capital_account(family_id, current_user_id, account_id) or {}
        effective_family_visible = bool(existing_meta.get("is_visible", False) if family_visible is None else family_visible)
        effective_family_default = bool(
            existing_meta.get("is_default_target", False)
            if family_default_target is None
            else family_default_target
        )
        if not effective_family_visible:
            effective_family_default = False
        if effective_family_default:
            effective_family_visible = True
        auth_service.upsert_family_capital_account(
            family_id=family_id,
            owner_user_id=current_user_id,
            capital_account_id=account_id,
            is_visible=effective_family_visible,
            is_default_target=effective_family_default,
        )
        mirror_family_snapshot_shadow_write(family_id)

    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обновить счет")

    refreshed = _find_account_row(account_id, include_inactive=True)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Счет обновлен, но не найден")
    if not bool(_row_value(refreshed[1], "is_active", 1)):
        _hide_family_capital_account_if_needed(family_id, current_user_id, account_id)
        mirror_family_snapshot_shadow_write(family_id)
    mirror_result = mirror_capital_accounts_shadow_write(
        current_user,
        transaction_service.get_capital_accounts(include_inactive=True),
    )
    require_mysql_accounts_capital_shadow_write_success(mirror_result, "capital_account_update")
    family_meta = _family_meta_map(family_id, current_user_id)
    return _capital_account_response(refreshed[1], family_meta.get(account_id))


@router.delete("/{account_id}", response_model=MessageResponse)
def delete_account(account_id: int, current_user=Depends(require_user)) -> MessageResponse:
    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    account_type, _ = found
    if account_type != "capital":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Повседневные счета нельзя удалить через этот раздел",
        )

    deleted = transaction_service.delete_capital_account(account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось удалить счет")
    _hide_family_capital_account_if_needed(_current_family_id(int(current_user["id"])), int(current_user["id"]), account_id)
    family_id = _current_family_id(int(current_user["id"]))
    mirror_family_snapshot_shadow_write(family_id)
    mirror_result = mirror_capital_accounts_shadow_write(
        current_user,
        transaction_service.get_capital_accounts(include_inactive=True),
    )
    require_mysql_accounts_capital_shadow_write_success(mirror_result, "capital_account_delete")
    return MessageResponse(message="Счет отключен")
