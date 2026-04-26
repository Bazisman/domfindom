from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import core
from backend.api.routes.accounts import _find_account_row, _row_value
from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.accounts import TransferCreateRequest, TransferResponse
from backend.services import transaction_service
from backend.storage.shadow_write import mirror_transfer_shadow_write


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
        db_path = auth_service.ensure_user_finance_db(target_owner_user_id)
        token = core.push_db_name(db_path)
        try:
            for capital_account in core.get_capital_accounts(include_inactive=True):
                if int(_row_value(capital_account, "id", 0)) == target_capital_account_id:
                    target_account_name = str(_row_value(capital_account, "name", ""))
                    break
        finally:
            core.pop_db_name(token)

        source_name = "Безнал"
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
            mirror_transfer_shadow_write(current_user, item)
            return _transfer_response(item)

    fallback = transaction_service.get_transfers_history(limit=1, include_inactive=True)
    if not fallback:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Перевод создан, но не найден")
    mirror_transfer_shadow_write(current_user, fallback[0])
    return _transfer_response(fallback[0])
