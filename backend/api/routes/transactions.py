import calendar
from datetime import date as date_cls
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status

import core
from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.common import MessageResponse
from backend.schemas.transactions import (
    TransactionCreateRequest,
    TransactionCreateResponse,
    TransactionPageResponse,
    TransactionResponse,
    TransactionUpdateRequest,
)
from backend.services import category_service, row_to_transaction_response, transaction_service
from backend.storage.shadow_write import (
    mirror_created_transaction_shadow_write,
    mirror_deleted_transaction_shadow_write,
    mirror_updated_transaction_shadow_write,
)
from models import Transaction


router = APIRouter()


def _list_transactions_window(limit: int, offset: int, period: str, include_planned: bool) -> List[Transaction]:
    if include_planned:
        return transaction_service.get_transactions(limit=limit, offset=offset, period=period)

    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    batch_size = min(max(safe_limit * 3, 100), 500)
    raw_offset = 0
    skipped = 0
    collected: List[Transaction] = []

    while len(collected) < safe_limit:
        batch = transaction_service.get_transactions(limit=batch_size, offset=raw_offset, period=period)
        if not batch:
            break

        for item in batch:
            if item.status == "planned":
                continue
            if skipped < safe_offset:
                skipped += 1
                continue
            collected.append(item)
            if len(collected) >= safe_limit:
                break

        if len(batch) < batch_size:
            break
        raw_offset += len(batch)

    return collected


def _count_transactions(period: str, include_planned: bool) -> int:
    total = 0
    raw_offset = 0
    batch_size = 500

    while True:
        batch = transaction_service.get_transactions(limit=batch_size, offset=raw_offset, period=period)
        if not batch:
            break

        if include_planned:
            total += len(batch)
        else:
            total += sum(1 for item in batch if item.status != "planned")

        if len(batch) < batch_size:
            break
        raw_offset += len(batch)

    return total


def _resolve_category_name(payload: TransactionCreateRequest) -> str:
    if payload.category_name:
        return payload.category_name
    category = category_service.get_category_by_id(payload.category_id or 0)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    return category.name


def _month_range(date_value: str) -> Tuple[str, str]:
    year, month = map(int, date_value.split("-")[:2])
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _is_future_date(date_value: str) -> bool:
    return date_value > date_cls.today().isoformat()


def _current_workspace_mode(user_id: int) -> str:
    return str(auth_service.get_user_preferences(user_id).get("workspace_mode") or "personal")


def _primary_family_id(user_id: int) -> int:
    family = auth_service.get_primary_family(user_id)
    return int(family["id"]) if family else 0


def _run_in_user_db(user_id: int, action):
    db_path = auth_service.ensure_user_finance_db(user_id)
    token = core.push_db_name(db_path)
    try:
        return action()
    finally:
        core.pop_db_name(token)


def _get_active_capital_account(owner_user_id: int, capital_account_id: int):
    def _action():
        for account in core.get_capital_accounts(include_inactive=False):
            if int(account["id"]) == capital_account_id:
                return account
        return None

    return _run_in_user_db(owner_user_id, _action)


def _adjust_daily_account(user_id: int, money_source: str, amount_delta: float) -> None:
    def _action():
        account_id = 2 if money_source == "cash" else 1
        core.update_account_balance(account_id, amount_delta)

    _run_in_user_db(user_id, _action)


def _adjust_capital_account(owner_user_id: int, capital_account_id: int, amount_delta: float) -> bool:
    def _action():
        with core.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE capital_accounts
                SET balance = balance + ?, updated_at = datetime("now")
                WHERE id = ? AND is_active = 1
                """,
                (amount_delta, capital_account_id),
            )
            conn.commit()
            core._invalidate_cache()
            return cursor.rowcount > 0

    return bool(_run_in_user_db(owner_user_id, _action))


def _create_income_with_family_capital(
    current_user_id: int,
    payload: TransactionCreateRequest,
    category_name: str,
    auto_capital_percent: int,
) -> Optional[int]:
    if auto_capital_percent <= 0 or _current_workspace_mode(current_user_id) != "family":
        return None

    family_id = _primary_family_id(current_user_id)
    if family_id <= 0:
        return None

    target = auth_service.ensure_family_member_capital_target(family_id, current_user_id)
    if not target:
        return None

    target_owner_user_id = int(target["owner_user_id"])
    target_capital_account_id = int(target["capital_account_id"])
    published_meta = auth_service.get_family_capital_account(
        family_id,
        target_owner_user_id,
        target_capital_account_id,
    )
    if not published_meta or not bool(published_meta.get("is_visible")):
        return None

    target_account = _get_active_capital_account(target_owner_user_id, target_capital_account_id)
    if not target_account:
        return None

    contribution_amount = payload.amount * (auto_capital_percent / 100)
    created_id = core.add_income_with_capital(
        payload.amount,
        category_name,
        payload.comment,
        payload.date,
        0,
        None,
        money_source=payload.money_source,
    )

    capital_applied = False
    try:
        _adjust_daily_account(current_user_id, payload.money_source, -contribution_amount)
        capital_applied = _adjust_capital_account(target_owner_user_id, target_capital_account_id, contribution_amount)
        if not capital_applied:
            raise RuntimeError("family_capital_target_update_failed")
        auth_service.create_family_capital_contribution(
            family_id=family_id,
            source_user_id=current_user_id,
            source_transaction_id=created_id,
            target_owner_user_id=target_owner_user_id,
            target_capital_account_id=target_capital_account_id,
            amount=contribution_amount,
            date=payload.date,
            comment=payload.comment,
        )
        return created_id
    except Exception:
        if capital_applied:
            _adjust_capital_account(target_owner_user_id, target_capital_account_id, -contribution_amount)
        core.delete_transaction(created_id)
        raise


def _rollback_family_capital_contribution(source_user_id: int, transaction_id: int, money_source: str = "cashless") -> None:
    contribution = auth_service.get_family_capital_contribution(source_user_id, transaction_id)
    if not contribution:
        return

    amount = float(contribution["amount"] or 0)
    target_owner_user_id = int(contribution["target_owner_user_id"])
    target_capital_account_id = int(contribution["target_capital_account_id"])

    _adjust_daily_account(source_user_id, money_source, amount)
    _adjust_capital_account(target_owner_user_id, target_capital_account_id, -amount)
    auth_service.reverse_family_capital_contribution(int(contribution["id"]))


@router.get("", response_model=List[TransactionResponse])
def list_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default="all"),
    include_planned: bool = Query(default=True),
) -> List[TransactionResponse]:
    transactions = _list_transactions_window(limit=limit, offset=offset, period=period, include_planned=include_planned)
    return [TransactionResponse(**row_to_transaction_response(item)) for item in transactions]


@router.get("/page", response_model=TransactionPageResponse)
def list_transactions_page(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default="all"),
    include_planned: bool = Query(default=True),
) -> TransactionPageResponse:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)
    transactions = _list_transactions_window(
        limit=safe_limit,
        offset=safe_offset,
        period=period,
        include_planned=include_planned,
    )
    total = _count_transactions(period=period, include_planned=include_planned)
    return TransactionPageResponse(
        items=[TransactionResponse(**row_to_transaction_response(item)) for item in transactions],
        limit=safe_limit,
        offset=safe_offset,
        total=total,
    )


@router.post("", response_model=TransactionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreateRequest, current_user=Depends(require_user)) -> TransactionCreateResponse:
    category_name = _resolve_category_name(payload)
    category = core.get_category_by_name(category_name)
    is_future = _is_future_date(payload.date)
    recurring_payload = payload.recurring if payload.recurring and payload.recurring.enabled else None
    planned_date = payload.date
    shadow_write_skip_reason = ""

    if is_future and recurring_payload and recurring_payload.working_days_only:
        planned_date = core._adjust_to_workday(payload.date)

    if is_future:
        shadow_write_skip_reason = "recurring_planned_transaction" if recurring_payload else ""
        created_id = core.add_planned_transaction(
            payload.type,
            category_name,
            payload.amount,
            payload.comment,
            planned_date,
            template_id=None,
            money_source=payload.money_source,
        )
    else:
        if payload.type == "income":
            settings_enabled, settings_percent = transaction_service.get_auto_capital_settings()
            default_capital_account = core.get_default_capital_account()
            auto_capital_percent = payload.auto_capital_percent
            capital_account_id = payload.capital_account_id

            if auto_capital_percent is None:
                auto_capital_percent = settings_percent if settings_enabled else 0

            family_created_id = _create_income_with_family_capital(
                current_user_id=int(current_user["id"]),
                payload=payload,
                category_name=category_name,
                auto_capital_percent=int(auto_capital_percent or 0),
            )
            if family_created_id is not None:
                created_id = family_created_id
                shadow_write_skip_reason = "family_capital_contribution"
            else:
                if capital_account_id is None and default_capital_account:
                    capital_account_id = default_capital_account["id"]
                created_id = core.add_income_with_capital(
                    payload.amount,
                    category_name,
                    payload.comment,
                    payload.date,
                    auto_capital_percent,
                    capital_account_id,
                    money_source=payload.money_source,
                )
        else:
            created_id = core.add_expense(
                payload.amount,
                category_name,
                payload.comment,
                payload.date,
                money_source=payload.money_source,
            )

    if recurring_payload:
        template_name = recurring_payload.template_name.strip() or payload.comment.strip() or category_name
        template_id = core.create_recurring_template(
            template_type=payload.type,
            name=template_name,
            amount=payload.amount,
            day_of_month=recurring_payload.day_of_month,
            category_id=category["id"] if category else payload.category_id,
            comment_template=payload.comment,
            months_ahead=recurring_payload.months_ahead,
            working_days_only=recurring_payload.working_days_only,
            money_source=payload.money_source,
        )
        month_start, month_end = _month_range(planned_date if is_future else payload.date)
        core.delete_planned_transactions_in_period(template_id, month_start, month_end)
        if is_future:
            core.assign_template_to_planned_transaction(created_id, template_id)

    row = core.get_transaction_by_id(created_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Транзакция создана, но не найдена")

    transaction = Transaction(
        id=row["id"],
        type=row["type"],
        category=row["category"],
        amount=row["amount"],
        comment=row["comment"],
        date=row["date"],
        status=row["status"] if "status" in row.keys() else "actual",
        money_source=row["money_source"] if "money_source" in row.keys() else "cashless",
    )
    mirror_created_transaction_shadow_write(current_user, row, skip_reason=shadow_write_skip_reason)
    return TransactionCreateResponse(
        id=created_id,
        message="Транзакция создана",
        transaction=TransactionResponse(**row_to_transaction_response(transaction)),
    )


@router.delete("/{transaction_id}", response_model=MessageResponse)
def delete_transaction(transaction_id: int, current_user=Depends(require_user)) -> MessageResponse:
    existing = transaction_service.get_transaction_by_id(transaction_id)
    family_contribution = auth_service.get_family_capital_contribution(int(current_user["id"]), transaction_id)
    deleted = transaction_service.delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена")
    _rollback_family_capital_contribution(
        int(current_user["id"]),
        transaction_id,
        existing.money_source if existing else "cashless",
    )
    mirror_deleted_transaction_shadow_write(
        current_user,
        transaction_id,
        skip_reason="family_capital_contribution" if family_contribution else "",
    )
    return MessageResponse(message="Транзакция удалена")


@router.patch("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdateRequest,
    current_user=Depends(require_user),
) -> TransactionResponse:
    existing = transaction_service.get_transaction_by_id(transaction_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена")

    update_data = payload.model_dump(exclude_unset=True)
    family_contribution = auth_service.get_family_capital_contribution(int(current_user["id"]), transaction_id)
    if family_contribution and any(field in update_data for field in ("amount", "type")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Операцию с семейным отчислением можно перенести между наличными и безналом, но сумму и тип сейчас нужно менять отдельной новой операцией.",
        )

    if "category_id" in update_data or "category_name" in update_data:
        update_data["category"] = _resolve_category_name(
            TransactionCreateRequest(
                type=payload.type or existing.type,
                category_id=payload.category_id,
                category_name=payload.category_name,
                amount=payload.amount or 1,
                comment=payload.comment or "",
                date=payload.date or date_cls.today().isoformat(),
                money_source=payload.money_source or existing.money_source,
            )
        )
        update_data.pop("category_id", None)
        update_data.pop("category_name", None)

    updated = core.update_transaction_fields(transaction_id, **update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена")

    if (
        family_contribution
        and payload.money_source is not None
        and payload.money_source != existing.money_source
    ):
        contribution_amount = float(family_contribution["amount"] or 0)
        _adjust_daily_account(int(current_user["id"]), existing.money_source, contribution_amount)
        _adjust_daily_account(int(current_user["id"]), payload.money_source, -contribution_amount)

    row = core.get_transaction_by_id(transaction_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Транзакция не найдена")
    transaction = Transaction(
        id=row["id"],
        type=row["type"],
        category=row["category"],
        amount=row["amount"],
        comment=row["comment"],
        date=row["date"],
        status=row["status"] if "status" in row.keys() else "actual",
        money_source=row["money_source"] if "money_source" in row.keys() else "cashless",
    )
    mirror_updated_transaction_shadow_write(
        current_user,
        row,
        skip_reason="family_capital_contribution" if family_contribution else "",
    )
    transaction_service.notify_listeners()
    return TransactionResponse(**row_to_transaction_response(transaction))
