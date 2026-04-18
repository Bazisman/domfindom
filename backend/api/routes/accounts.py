from typing import List

from fastapi import APIRouter, HTTPException, Query, status

import core
from backend.schemas.accounts import AccountCreateRequest, AccountResponse, AccountUpdateRequest
from backend.schemas.common import MessageResponse
from backend.services import transaction_service


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


def _main_account_response(row) -> AccountResponse:
    return AccountResponse(
        id=_row_value(row, "id", 0),
        name=_row_value(row, "name", ""),
        type="main",
        balance=float(_row_value(row, "balance", 0) or 0),
        currency=_row_value(row, "currency", "RUB"),
        is_active=bool(_row_value(row, "is_active", 1)),
        is_default=False,
        icon=None,
        color=None,
    )


def _capital_account_response(row) -> AccountResponse:
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
    )


def _find_account_row(account_id: int, include_inactive: bool = False):
    if account_id < 100:
        for account in transaction_service.get_all_accounts(include_inactive=include_inactive):
            if _row_value(account, "id") == account_id:
                return ("main", account)
        return None

    for account in core.get_capital_accounts(include_inactive=include_inactive):
        if _row_value(account, "id") == account_id:
            return ("capital", account)
    return None


@router.get("", response_model=List[AccountResponse])
def list_accounts(
    include_inactive: bool = Query(default=False),
) -> List[AccountResponse]:
    main_accounts = [
        _main_account_response(account)
        for account in transaction_service.get_all_accounts(include_inactive=include_inactive)
    ]
    capital_accounts = [
        _capital_account_response(account)
        for account in core.get_capital_accounts(include_inactive=include_inactive)
    ]
    return [*main_accounts, *capital_accounts]


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int) -> AccountResponse:
    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    account_type, row = found
    if account_type == "main":
        return _main_account_response(row)
    return _capital_account_response(row)


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreateRequest) -> AccountResponse:
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
    return _capital_account_response(found[1])


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, payload: AccountUpdateRequest) -> AccountResponse:
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

    updated = True
    if update_data:
        updated = transaction_service.update_capital_account(account_id, **update_data)
    if should_set_default:
        updated = transaction_service.set_default_capital_account(account_id) and updated

    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обновить счет")

    refreshed = _find_account_row(account_id, include_inactive=True)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Счет обновлен, но не найден")
    return _capital_account_response(refreshed[1])


@router.delete("/{account_id}", response_model=MessageResponse)
def delete_account(account_id: int) -> MessageResponse:
    found = _find_account_row(account_id, include_inactive=True)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")

    account_type, _ = found
    if account_type != "capital":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Основной счет нельзя удалить через этот раздел",
        )

    deleted = transaction_service.delete_capital_account(account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось удалить счет")
    return MessageResponse(message="Счет отключен")
