import calendar
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

import core
from core_budgets import get_budget_status_metrics
from backend.auth.dependencies import require_user
from backend.auth.mailer import auth_mailer
from backend.auth.service import auth_service
from backend.schemas.families import (
    FamilyActionResponse,
    FamilyCapitalAccountItemResponse,
    FamilyCapitalContributionItemResponse,
    FamilyCapitalContributionListResponse,
    FamilyCapitalSelectionResponse,
    FamilyCapitalTargetUpdatePayload,
    FamilyCreatePayload,
    FamilyDashboardBalanceResponse,
    FamilyDashboardResponse,
    FamilyDashboardTransactionResponse,
    FamilyInviteAcceptPayload,
    FamilyInviteAcceptResponse,
    FamilyInviteCreatePayload,
    FamilyInviteCreateResponse,
    FamilyItemResponse,
    FamilyListResponse,
    FamilyMemberItemResponse,
    FamilyMemberListResponse,
    FamilyMemberRoleUpdatePayload,
    FamilyPendingInviteItemResponse,
    FamilyPendingInviteListResponse,
    FamilyTransactionListResponse,
)
from backend.schemas.forecast import ForecastResponse
from backend.services import row_to_transaction_response, transaction_service


router = APIRouter()


def _collect_family_forecast(
    members: List[Dict[str, object]],
    now: datetime,
    current_balance: float,
    planned_income: float,
    planned_expense: float,
    executed_planned_income: float,
    executed_planned_expense: float,
) -> ForecastResponse:
    start_of_month = now.replace(day=1).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    end_date = now.replace(day=calendar.monthrange(now.year, now.month)[1]).strftime("%Y-%m-%d")
    spent_by_category: Dict[str, float] = {}
    planned_expense_by_category: Dict[str, float] = {}
    budget_by_category: Dict[str, Dict[str, float | bool]] = {}

    for member in members:
        user_id = int(member["user_id"])

        def _action():
            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT category, COALESCE(SUM(amount), 0) as total
                    FROM transactions
                    WHERE status = 'planned' AND type = 'expense' AND date <= ?
                    GROUP BY category
                    """,
                    (end_date,),
                )
                planned_expenses = cursor.fetchall()
            return core.get_expenses_by_category(start_of_month, today), core.get_budgets(), planned_expenses

        expenses, budgets, planned_expenses = _run_in_user_db(user_id, _action)
        for item in expenses:
            category_name = str(item["category"] or "")
            spent_by_category[category_name] = spent_by_category.get(category_name, 0.0) + float(item["total"] or 0.0)
        for item in planned_expenses:
            category_name = str(item["category"] or "")
            planned_expense_by_category[category_name] = planned_expense_by_category.get(category_name, 0.0) + float(item["total"] or 0.0)
        for budget in budgets:
            category_name = str(budget["category"] or "")
            period = budget["period"] if "period" in budget.keys() else "monthly"
            monthly_amount = float(core._get_budget_monthly_limit(budget["amount"] or 0, period, today))
            category_bucket = budget_by_category.setdefault(
                category_name,
                {
                    "monthly_amount": 0.0,
                    "daily_amount": 0.0,
                    "has_non_daily": False,
                },
            )
            category_bucket["monthly_amount"] += monthly_amount
            if str(period).lower() == "daily":
                category_bucket["daily_amount"] += float(budget["amount"] or 0.0)
            else:
                category_bucket["has_non_daily"] = True

    total_budgets = 0.0
    current_expenses = 0.0
    budget_plan_remaining = 0.0
    budget_forecast_remaining = 0.0
    for category_name, budget_meta in budget_by_category.items():
        monthly_amount = float(budget_meta["monthly_amount"])
        total_budgets += monthly_amount
        spent = float(spent_by_category.get(category_name, 0.0))
        current_expenses += min(spent, monthly_amount)
        plan_remaining = max(monthly_amount - spent, 0.0)
        budget_plan_remaining += plan_remaining
        daily_amount = float(budget_meta["daily_amount"])
        has_non_daily = bool(budget_meta["has_non_daily"])
        planned_category_expense = float(planned_expense_by_category.get(category_name, 0.0))
        if daily_amount > 0 and not has_non_daily:
            metrics = get_budget_status_metrics(daily_amount, "daily", spent, today)
            budget_forecast_remaining += max(float(metrics["forecast_remaining"]) - planned_category_expense, 0.0)
        else:
            budget_forecast_remaining += max(plan_remaining - planned_category_expense, 0.0)

    combined_pending_expense = planned_expense + budget_forecast_remaining
    combined_executed_expense = executed_planned_expense + current_expenses
    projected_balance = current_balance + planned_income - planned_expense - budget_forecast_remaining

    return ForecastResponse(
        current_balance=round(current_balance, 2),
        planned_income=round(planned_income, 2),
        planned_expense=round(planned_expense, 2),
        executed_planned_income=round(executed_planned_income, 2),
        executed_planned_expense=round(executed_planned_expense, 2),
        monthly_budget=round(total_budgets, 2),
        total_budgets=round(total_budgets, 2),
        current_expenses=round(current_expenses, 2),
        budget_plan_remaining=round(budget_plan_remaining, 2),
        budget_remaining=round(budget_forecast_remaining, 2),
        budget_forecast_remaining=round(budget_forecast_remaining, 2),
        combined_pending_expense=round(combined_pending_expense, 2),
        combined_executed_expense=round(combined_executed_expense, 2),
        projected=round(projected_balance, 2),
        projected_balance=round(projected_balance, 2),
        end_date=end_date,
    )


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or "." not in normalized.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный email")
    return normalized


def _require_family_role(family_id: int, user_id: int):
    membership = auth_service.get_family_membership(family_id=family_id, user_id=user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семья не найдена или доступ запрещен")
    return membership


def _require_family_admin_access(family_id: int, user_id: int):
    membership = _require_family_role(family_id=family_id, user_id=user_id)
    if membership["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return membership


def _run_in_user_db(user_id: int, action):
    user_db_path = auth_service.ensure_user_finance_db(user_id)
    token = core.push_db_name(user_db_path)
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


def _collect_family_capital_accounts(family_id: int) -> List[Dict[str, object]]:
    result: List[Dict[str, object]] = []
    for item in auth_service.list_family_capital_accounts(family_id):
        if not bool(item.get("is_visible")):
            continue
        owner_user_id = int(item["owner_user_id"])
        capital_account_id = int(item["capital_account_id"])

        def _action():
            for account in core.get_capital_accounts(include_inactive=False):
                if int(account["id"]) == capital_account_id:
                    return account
            return None

        account = _run_in_user_db(owner_user_id, _action)
        if not account:
            continue
        result.append(
            {
                "owner_user_id": owner_user_id,
                "owner_email": str(item.get("owner_email") or ""),
                "owner_display_name": str(item.get("owner_display_name") or "").strip(),
                "capital_account_id": capital_account_id,
                "name": str(account["name"] or ""),
                "balance": float(account["balance"] or 0),
                "color": account["color"] if "color" in account.keys() else None,
                "icon": account["icon"] if "icon" in account.keys() else None,
                "is_visible": True,
                "is_default_target": bool(item.get("is_default_target")),
            }
        )
    return result


def _collect_family_dashboard(family_id: int, family_name: str, current_user_id: int) -> FamilyDashboardResponse:
    members = auth_service.list_family_members(family_id)
    now = datetime.now()

    main_balance = 0.0
    capital_balance = 0.0
    income = 0.0
    expense = 0.0
    forecast_planned_income = 0.0
    forecast_planned_expense = 0.0
    forecast_executed_planned_income = 0.0
    forecast_executed_planned_expense = 0.0
    recent_transactions: List[Dict[str, object]] = []
    capital_accounts = _collect_family_capital_accounts(family_id)
    capital_balance = sum(float(item["balance"] or 0) for item in capital_accounts)

    for member in members:
        user_id = int(member["user_id"])
        user_email = str(member["email"] or "")
        user_display_name = str(member.get("display_name") or "").strip()

        def _action():
            balance = transaction_service.get_balance(force_update=True)
            stats = transaction_service.get_monthly_stats(now.year, now.month)
            items = transaction_service.get_transactions(limit=100, period="all", offset=0)
            forecast = core.get_projected_balance()
            return balance, stats, items, forecast

        balance, stats, items, forecast = _run_in_user_db(user_id, _action)
        main_balance += float(balance.main_balance)
        income += float(stats.get("income", 0.0) or 0.0)
        expense += float(stats.get("expense", 0.0) or 0.0)
        forecast_planned_income += float(forecast.get("planned_income", 0.0) or 0.0)
        forecast_planned_expense += float(forecast.get("planned_expense", 0.0) or 0.0)
        forecast_executed_planned_income += float(forecast.get("executed_planned_income", 0.0) or 0.0)
        forecast_executed_planned_expense += float(forecast.get("executed_planned_expense", 0.0) or 0.0)

        for item in items:
            if item.status == "planned":
                continue
            mapped = row_to_transaction_response(item)
            recent_transactions.append(
                {
                    **mapped,
                    "owner_user_id": user_id,
                    "owner_email": user_email,
                    "owner_display_name": user_display_name,
                }
            )

    recent_transactions.sort(key=lambda item: (str(item["date"]), int(item["id"])), reverse=True)
    top_transactions = recent_transactions[:20]
    current_target = auth_service.ensure_family_member_capital_target(family_id, current_user_id)
    if current_target and not any(
        int(item["owner_user_id"]) == int(current_target["owner_user_id"])
        and int(item["capital_account_id"]) == int(current_target["capital_account_id"])
        for item in capital_accounts
    ):
        current_target = None
    family_forecast = _collect_family_forecast(
        members=members,
        now=now,
        current_balance=main_balance,
        planned_income=forecast_planned_income,
        planned_expense=forecast_planned_expense,
        executed_planned_income=forecast_executed_planned_income,
        executed_planned_expense=forecast_executed_planned_expense,
    )

    return FamilyDashboardResponse(
        family_id=family_id,
        family_name=family_name,
        members_count=len(members),
        balance=FamilyDashboardBalanceResponse(
            main_balance=round(main_balance, 2),
            capital_balance=round(capital_balance, 2),
            income=round(income, 2),
            expense=round(expense, 2),
            difference=round(income - expense, 2),
        ),
        forecast=family_forecast,
        capital_accounts=[FamilyCapitalAccountItemResponse(**item) for item in capital_accounts],
        current_member_capital_target=FamilyCapitalSelectionResponse(
            target_owner_user_id=int(current_target["owner_user_id"]) if current_target else None,
            target_capital_account_id=int(current_target["capital_account_id"]) if current_target else None,
        ),
        recent_transactions=[FamilyDashboardTransactionResponse(**item) for item in top_transactions],
    )


def _collect_family_capital_history(family_id: int) -> FamilyCapitalContributionListResponse:
    items = auth_service.list_family_capital_contributions_for_family(family_id=family_id, limit=120)
    response_items = []
    for item in items:
        target_account = _get_active_capital_account(
            int(item["target_owner_user_id"]),
            int(item["target_capital_account_id"]),
        )
        response_items.append(
            FamilyCapitalContributionItemResponse(
                **item,
                target_account_name=str(target_account["name"] or "") if target_account else "",
            )
        )
    return FamilyCapitalContributionListResponse(
        family_id=family_id,
        items=response_items,
    )


def _collect_family_transactions(
    family_id: int,
    family_name: str,
    owner_user_id: int = 0,
    limit: int = 50,
    offset: int = 0,
    period: str = "all",
    include_planned: bool = False,
) -> FamilyTransactionListResponse:
    members = auth_service.list_family_members(family_id)
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)
    member_map: Dict[int, Dict[str, str]] = {
        int(item["user_id"]): {
            "email": str(item["email"] or ""),
            "display_name": str(item.get("display_name") or "").strip(),
        }
        for item in members
    }

    if owner_user_id > 0 and owner_user_id not in member_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник семьи не найден")

    target_user_ids: List[int] = [owner_user_id] if owner_user_id > 0 else list(member_map.keys())
    items: List[Dict[str, object]] = []

    for user_id in target_user_ids:
        def _action():
            return transaction_service.get_transactions(limit=500, period=period, offset=0)

        rows = _run_in_user_db(user_id, _action)
        for row in rows:
            if not include_planned and row.status == "planned":
                continue
            mapped = row_to_transaction_response(row)
            items.append(
                {
                    **mapped,
                    "owner_user_id": user_id,
                    "owner_email": member_map.get(user_id, {}).get("email", ""),
                    "owner_display_name": member_map.get(user_id, {}).get("display_name", ""),
                }
            )

    items.sort(key=lambda item: (str(item["date"]), int(item["id"])), reverse=True)

    return FamilyTransactionListResponse(
        family_id=family_id,
        family_name=family_name,
        owner_user_id=owner_user_id if owner_user_id > 0 else None,
        limit=safe_limit,
        offset=safe_offset,
        total=len(items),
        transactions=[
            FamilyDashboardTransactionResponse(**item)
            for item in items[safe_offset:safe_offset + safe_limit]
        ],
    )


def _validate_member_management_rules(
    actor_user_id: int,
    actor_role: str,
    target_user_id: int,
    target_role: str,
    next_role: str = "",
) -> None:
    if target_role == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя изменить владельца семьи")
    if actor_role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    if actor_user_id == target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя изменить собственную роль этим действием")


@router.post("", response_model=FamilyItemResponse, status_code=status.HTTP_201_CREATED)
def create_family(payload: FamilyCreatePayload, current_user=Depends(require_user)) -> FamilyItemResponse:
    family = auth_service.create_family(owner_user_id=int(current_user["id"]), name=payload.name.strip())
    return FamilyItemResponse(**family)


@router.get("/me", response_model=FamilyListResponse)
def list_my_families(current_user=Depends(require_user)) -> FamilyListResponse:
    items = auth_service.list_user_families(int(current_user["id"]))
    return FamilyListResponse(families=[FamilyItemResponse(**item) for item in items])


@router.get("/{family_id}/members", response_model=FamilyMemberListResponse)
def list_family_members(family_id: int, current_user=Depends(require_user)) -> FamilyMemberListResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    members = auth_service.list_family_members(family_id=family_id)
    return FamilyMemberListResponse(members=[FamilyMemberItemResponse(**item) for item in members])


@router.get("/{family_id}/dashboard", response_model=FamilyDashboardResponse)
def get_family_dashboard(family_id: int, current_user=Depends(require_user)) -> FamilyDashboardResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    membership = _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    family_name = str(membership.get("family_name") or "Семья")
    return _collect_family_dashboard(
        family_id=family_id,
        family_name=family_name,
        current_user_id=int(current_user["id"]),
    )


@router.put("/{family_id}/capital-target", response_model=FamilyCapitalSelectionResponse)
def update_family_capital_target(
    family_id: int,
    payload: FamilyCapitalTargetUpdatePayload,
    current_user=Depends(require_user),
) -> FamilyCapitalSelectionResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_role(family_id=family_id, user_id=int(current_user["id"]))

    if payload.target_owner_user_id is None or payload.target_capital_account_id is None:
        auth_service.set_family_member_capital_target(
            family_id=family_id,
            user_id=int(current_user["id"]),
            target_owner_user_id=None,
            target_capital_account_id=None,
        )
        return FamilyCapitalSelectionResponse()

    published_meta = auth_service.get_family_capital_account(
        family_id=family_id,
        owner_user_id=int(payload.target_owner_user_id),
        capital_account_id=int(payload.target_capital_account_id),
    )
    if not published_meta or not bool(published_meta.get("is_visible")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семейный счет для отчислений не найден")

    auth_service.set_family_member_capital_target(
        family_id=family_id,
        user_id=int(current_user["id"]),
        target_owner_user_id=int(payload.target_owner_user_id),
        target_capital_account_id=int(payload.target_capital_account_id),
    )
    return FamilyCapitalSelectionResponse(
        target_owner_user_id=int(payload.target_owner_user_id),
        target_capital_account_id=int(payload.target_capital_account_id),
    )


@router.get("/{family_id}/transactions", response_model=FamilyTransactionListResponse)
def list_family_transactions(
    family_id: int,
    owner_user_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default="all"),
    include_planned: bool = Query(default=False),
    current_user=Depends(require_user),
) -> FamilyTransactionListResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    membership = _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    family_name = str(membership.get("family_name") or "Семья")
    return _collect_family_transactions(
        family_id=family_id,
        family_name=family_name,
        owner_user_id=owner_user_id,
        limit=limit,
        offset=offset,
        period=period,
        include_planned=include_planned,
    )


@router.get("/{family_id}/capital-history", response_model=FamilyCapitalContributionListResponse)
def list_family_capital_history(family_id: int, current_user=Depends(require_user)) -> FamilyCapitalContributionListResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    return _collect_family_capital_history(family_id)


@router.post("/{family_id}/invites", response_model=FamilyInviteCreateResponse)
def create_family_invite(
    family_id: int,
    payload: FamilyInviteCreatePayload,
    request: Request,
    current_user=Depends(require_user),
) -> FamilyInviteCreateResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    actor_membership = _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))

    invited_email = _normalize_email(payload.email)
    try:
        invite = auth_service.create_family_invite(
            family_id=family_id,
            invited_by_user_id=int(current_user["id"]),
            email=invited_email,
            role=payload.role,
        )
    except ValueError as exc:
        if str(exc) == "user_already_member":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь уже состоит в семейном бюджете",
            ) from exc
        raise

    sent_email = False
    if auth_mailer.is_configured():
        try:
            role_label = "Помощник" if payload.role == "member" else "Только просмотр"
            auth_mailer.send_family_invite_email(
                to_email=invited_email,
                family_name=str(actor_membership.get("family_name") or "Семья"),
                invited_by_email=str(current_user["email"]),
                role_label=role_label,
                token=str(invite["token"]),
            )
            sent_email = True
        except Exception:
            sent_email = False

    auth_service.log_auth_event(
        event_type="family_invite_create",
        status="success",
        user_id=int(current_user["id"]),
        email=str(current_user["email"]),
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        detail="sent_via_email_and_cabinet" if sent_email else "saved_to_cabinet_only",
    )

    return FamilyInviteCreateResponse(
        message="Приглашение отправлено на почту и добавлено в личный кабинет." if sent_email else "Приглашение добавлено в личный кабинет.",
        family_id=family_id,
        email=invited_email,
        role=payload.role,
        expires_at=invite["expires_at"],
        invite_token=invite["token"],
    )


@router.post("/invites/accept", response_model=FamilyInviteAcceptResponse)
def accept_family_invite(payload: FamilyInviteAcceptPayload, current_user=Depends(require_user)) -> FamilyInviteAcceptResponse:
    accepted = auth_service.accept_family_invite(token=payload.token, user_id=int(current_user["id"]))
    if not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Инвайт недействителен или истек")

    return FamilyInviteAcceptResponse(
        message="Вы подключены к семейному бюджету.",
        family_id=int(accepted["family_id"]),
        family_name=str(accepted["family_name"]),
        role=str(accepted["role"]),
    )


@router.get("/invites/pending", response_model=FamilyPendingInviteListResponse)
def list_pending_family_invites(current_user=Depends(require_user)) -> FamilyPendingInviteListResponse:
    invites = auth_service.list_pending_family_invites(int(current_user["id"]))
    return FamilyPendingInviteListResponse(invites=[FamilyPendingInviteItemResponse(**item) for item in invites])


@router.post("/invites/{invite_id}/accept", response_model=FamilyInviteAcceptResponse)
def accept_family_invite_by_id(invite_id: int, current_user=Depends(require_user)) -> FamilyInviteAcceptResponse:
    if invite_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор приглашения")
    accepted = auth_service.accept_family_invite_by_id(invite_id=invite_id, user_id=int(current_user["id"]))
    if not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение недействительно или истекло")
    return FamilyInviteAcceptResponse(
        message="Вы подключены к семейному бюджету.",
        family_id=int(accepted["family_id"]),
        family_name=str(accepted["family_name"]),
        role=str(accepted["role"]),
    )


@router.post("/invites/{invite_id}/decline", response_model=FamilyActionResponse)
def decline_family_invite_by_id(invite_id: int, current_user=Depends(require_user)) -> FamilyActionResponse:
    if invite_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор приглашения")
    declined = auth_service.decline_family_invite_by_id(invite_id=invite_id, user_id=int(current_user["id"]))
    if not declined:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение недействительно или уже обработано")
    return FamilyActionResponse(message="Приглашение отклонено.")


@router.patch("/{family_id}/members/{member_user_id}/role", response_model=FamilyActionResponse)
def update_family_member_role(
    family_id: int,
    member_user_id: int,
    payload: FamilyMemberRoleUpdatePayload,
    current_user=Depends(require_user),
) -> FamilyActionResponse:
    if family_id <= 0 or member_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректные параметры")

    actor = _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    target = _require_family_role(family_id=family_id, user_id=member_user_id)
    _validate_member_management_rules(
        actor_user_id=int(current_user["id"]),
        actor_role=str(actor["role"]),
        target_user_id=member_user_id,
        target_role=str(target["role"]),
        next_role=payload.role,
    )

    try:
        updated = auth_service.update_family_member_role(
            family_id=family_id,
            user_id=member_user_id,
            role=payload.role,
        )
    except ValueError as exc:
        if str(exc) == "owner_role_locked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя изменить роль владельца") from exc
        raise

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return FamilyActionResponse(message="Роль участника обновлена.")


@router.delete("/{family_id}/members/{member_user_id}", response_model=FamilyActionResponse)
def remove_family_member(
    family_id: int,
    member_user_id: int,
    current_user=Depends(require_user),
) -> FamilyActionResponse:
    if family_id <= 0 or member_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректные параметры")

    actor = _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    target = _require_family_role(family_id=family_id, user_id=member_user_id)
    _validate_member_management_rules(
        actor_user_id=int(current_user["id"]),
        actor_role=str(actor["role"]),
        target_user_id=member_user_id,
        target_role=str(target["role"]),
    )

    try:
        removed = auth_service.remove_family_member(family_id=family_id, user_id=member_user_id)
    except ValueError as exc:
        if str(exc) == "owner_cannot_be_removed":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя удалить владельца семьи") from exc
        raise

    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return FamilyActionResponse(message="Участник исключен из семьи.")
