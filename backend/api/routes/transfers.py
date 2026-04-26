from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.routes.accounts import _find_account_row, _row_value
from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.accounts import TransferCreateRequest, TransferResponse
from backend.services import run_in_user_finance_db, transaction_service
from backend.storage.shadow_write import (
    mirror_transfer_shadow_write,
    require_mysql_accounts_capital_shadow_write_success,
)


router = APIRouter()


def _transfer_response(row) -> TransferResponse:
    return TransferResponse(
        id=_row_value(row, "id", 0),
        from_account_id=_row_value(row, "from_account_id", 0),
        to_account_id=_row_value(row, "to_account_id", 0),
        amount=float(_row_value(row, "amount", 0) or 0),
        date=_row_value(row, "date", ""),
        comment=_row_value(row, "comment", ""),
        from_name=_row_value(row, "from_name", ""),
        to_name=_row_value(row, "to_name", ""),
        is_active=bool(_row_value(row, "is_active", 1)),
    )


def _account_money_source(account_id: int, account_type: str) -> str:
    return "cash" if account_id == 2 or account_type == "cash" else "cashless"


def _adjust_daily_account(money_source: str, amount_delta: float) -> None:
    transaction_service.adjust_daily_account_balance(money_source, amount_delta)


def _adjust_capital_account(owner_user_id: int, capital_account_id: int, amount_delta: float) -> bool:
    def _action():
        return transaction_service.adjust_capital_account_balance(capital_account_id, amount_delta)

    return bool(run_in_user_finance_db(owner_user_id, _action))


def _target_capital_account_name(owner_user_id: int, capital_account_id: int) -> str:
    def _action():
        for capital_account in transaction_service.get_capital_accounts(include_inactive=True):
            if int(_row_value(capital_account, "id", 0)) == capital_account_id:
                return str(_row_value(capital_account, "name", ""))
        return ""

    return run_in_user_finance_db(owner_user_id, _action)


def _create_family_capital_transfer(payload: TransferCreateRequest, current_user) -> TransferResponse:
    current_user_id = int(current_user["id"])
    family = auth_service.get_primary_family(current_user_id)
    if not family:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Семья не найдена")

    target_owner_user_id = int(payload.target_owner_user_id or 0)
    target_capital_account_id = int(payload.to_account_id)
    family_id = int(family["id"])
    published_meta = auth_service.get_family_capital_account(
        family_id,
        target_owner_user_id,
        target_capital_account_id,
    )
    if not published_meta or not bool(published_meta.get("is_visible")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семейная подушка не найдена")

    from_account = _find_account_row(payload.from_account_id, include_inactive=False)
    if not from_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Откуда списать деньги не найдено")
    from_account_type, from_row = from_account
    if from_account_type != "daily":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="В семейную подушку можно отложить только из денег на жизнь")
    if float(_row_value(from_row, "balance", 0) or 0) < float(payload.amount):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостаточно денег")

    money_source = _account_money_source(int(payload.from_account_id), str(_row_value(from_row, "type", "")))
    transfer_date = payload.date or datetime.now().strftime("%Y-%m-%d")
    daily_applied = False
    capital_applied = False
    try:
        _adjust_daily_account(money_source, -float(payload.amount))
        daily_applied = True
        capital_applied = _adjust_capital_account(target_owner_user_id, target_capital_account_id, float(payload.amount))
        if not capital_applied:
            raise RuntimeError("family_capital_target_update_failed")
        contribution = auth_service.create_manual_family_capital_contribution(
            family_id=family_id,
            source_user_id=current_user_id,
            target_owner_user_id=target_owner_user_id,
            target_capital_account_id=target_capital_account_id,
            amount=float(payload.amount),
            date=transfer_date,
            comment=payload.comment,
            source_money_source=money_source,
        )
    except Exception:
        if capital_applied:
            _adjust_capital_account(target_owner_user_id, target_capital_account_id, -float(payload.amount))
        if daily_applied:
            _adjust_daily_account(money_source, float(payload.amount))
        raise

    target_name = _target_capital_account_name(target_owner_user_id, target_capital_account_id) or "Семейная подушка"
    owner_label = str(published_meta.get("owner_display_name") or published_meta.get("owner_email") or "Семья")
    if target_owner_user_id != current_user_id:
        target_name = f"{target_name} ({owner_label})"
    return _transfer_response(
        {
            "id": -int(contribution["id"]),
            "from_account_id": payload.from_account_id,
            "to_account_id": target_capital_account_id,
            "amount": float(payload.amount),
            "date": transfer_date,
            "comment": payload.comment or "Отложили в семейную подушку",
            "from_name": "Наличные" if money_source == "cash" else "Для трат",
            "to_name": target_name,
            "is_active": True,
        }
    )


def _family_transfer_rows(user_id: int, account_id: Optional[int], limit: int) -> List[dict]:
    rows = auth_service.list_family_capital_contributions_for_user(user_id=user_id, limit=limit)
    mapped: List[dict] = []
    for item in rows:
        source_user_id = int(item["source_user_id"])
        target_owner_user_id = int(item["target_owner_user_id"])
        target_capital_account_id = int(item["target_capital_account_id"])

        if account_id is not None and account_id not in {1, target_capital_account_id}:
            continue

        target_account_name = ""
        def _action():
            for capital_account in transaction_service.get_capital_accounts(include_inactive=True):
                if int(_row_value(capital_account, "id", 0)) == target_capital_account_id:
                    return str(_row_value(capital_account, "name", ""))
            return ""

        target_account_name = run_in_user_finance_db(target_owner_user_id, _action)

        source_name = "Наличные" if item.get("source_money_source") == "cash" else "Для трат"
        if user_id == target_owner_user_id and user_id != source_user_id:
            source_name = f"Семейное отчисление: {item['source_display_name'] or item['source_email']}"
        to_name = target_account_name or "Семейный счет"
        if user_id == source_user_id and user_id != target_owner_user_id:
            to_name = f"{to_name} ({item['target_owner_display_name'] or item['target_owner_email']})"

        mapped.append(
            {
                "id": -int(item["id"]),
                "from_account_id": 1,
                "to_account_id": target_capital_account_id,
                "amount": float(item["amount"] or 0),
                "date": str(item["date"] or ""),
                "comment": str(item["comment"] or "") or "Семейное автоотчисление",
                "from_name": source_name,
                "to_name": to_name,
                "is_active": True,
            }
        )
    return mapped


@router.get("", response_model=List[TransferResponse])
def list_transfers(
    account_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    include_inactive: bool = Query(default=False),
    current_user=Depends(require_user),
) -> List[TransferResponse]:
    direct_transfers = transaction_service.get_transfers_history(
        account_id=account_id,
        limit=limit,
        include_inactive=include_inactive,
    )
    family_transfers = _family_transfer_rows(int(current_user["id"]), account_id, limit) if not include_inactive else []
    combined = [*direct_transfers, *family_transfers]
    combined.sort(key=lambda item: (str(_row_value(item, "date", "")), int(_row_value(item, "id", 0))), reverse=True)
    return [_transfer_response(item) for item in combined[:limit]]


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(payload: TransferCreateRequest, current_user=Depends(require_user)) -> TransferResponse:
    if payload.target_owner_user_id is not None:
        return _create_family_capital_transfer(payload, current_user)

    from_account = _find_account_row(payload.from_account_id, include_inactive=False)
    to_account = _find_account_row(payload.to_account_id, include_inactive=False)
    if not from_account or not to_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет списания или зачисления не найден")

    created = transaction_service.transfer_money(
        payload.from_account_id,
        payload.to_account_id,
        payload.amount,
        payload.date,
        payload.comment,
    )
    if not created:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось создать перевод. Проверьте балансы и параметры счетов.",
        )

    latest = transaction_service.get_transfers_history(
        account_id=payload.from_account_id,
        limit=20,
        include_inactive=True,
    )
    for item in latest:
        if (
            _row_value(item, "from_account_id") == payload.from_account_id
            and _row_value(item, "to_account_id") == payload.to_account_id
            and float(_row_value(item, "amount", 0) or 0) == float(payload.amount)
            and _row_value(item, "comment", "") == payload.comment
        ):
            mirror_result = mirror_transfer_shadow_write(current_user, item)
            require_mysql_accounts_capital_shadow_write_success(mirror_result, "transfer_create")
            return _transfer_response(item)

    fallback = transaction_service.get_transfers_history(limit=1, include_inactive=True)
    if not fallback:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Перевод создан, но не найден")
    mirror_result = mirror_transfer_shadow_write(current_user, fallback[0])
    require_mysql_accounts_capital_shadow_write_success(mirror_result, "transfer_create")
    return _transfer_response(fallback[0])
