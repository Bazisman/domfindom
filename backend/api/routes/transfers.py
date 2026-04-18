from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

import core
from backend.api.routes.accounts import _find_account_row, _row_value
from backend.schemas.accounts import TransferCreateRequest, TransferResponse
from backend.services import transaction_service


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


@router.get("", response_model=List[TransferResponse])
def list_transfers(
    account_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    include_inactive: bool = Query(default=False),
) -> List[TransferResponse]:
    transfers = core.get_transfers_history(
        account_id=account_id,
        limit=limit,
        include_inactive=include_inactive,
    )
    return [_transfer_response(item) for item in transfers]


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(payload: TransferCreateRequest) -> TransferResponse:
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

    latest = core.get_transfers_history(
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
            return _transfer_response(item)

    fallback = core.get_transfers_history(limit=1, include_inactive=True)
    if not fallback:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Перевод создан, но не найден")
    return _transfer_response(fallback[0])
