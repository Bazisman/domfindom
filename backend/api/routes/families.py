import calendar
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

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
    FamilyCategoryAuditFindingResponse,
    FamilyCategoryAuditGroupResponse,
    FamilyCategoryAuditMemberResponse,
    FamilyCategoryAuditResponse,
    FamilyCategoryAuditResolutionPayload,
    FamilyCategoryAuditResolutionResponse,
    FamilyCategoryAuditSummaryResponse,
    FamilyCategoryBindingApplyResponse,
    FamilyCategoryBindingCandidateResponse,
    FamilyCategoryBindingPreviewPayload,
    FamilyCategoryBindingPreviewResponse,
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
from backend.services import row_to_transaction_response, run_in_user_finance_db, transaction_service
from backend.storage.shadow_write import mirror_family_snapshot_shadow_write


router = APIRouter()


_SEMANTIC_CATEGORY_TEMPLATES = {
    "groceries": {
        "display_name": "Продукты",
        "aliases": ["продукты", "еда", "магазин", "продуктовый", "пятерочка", "пятёрочка"],
    },
    "household": {
        "display_name": "Хозтовары",
        "aliases": ["хозтовары", "хоз товары", "товары для дома", "бытовая химия"],
    },
    "utilities": {
        "display_name": "Коммунальные",
        "aliases": ["коммунальные", "жкх", "квартплата"],
    },
    "internet_mobile": {
        "display_name": "Интернет/связь",
        "aliases": ["интернет/связь", "интернет", "связь", "мобильная связь"],
    },
    "subscriptions": {
        "display_name": "Подписки",
        "aliases": ["подписки", "сервисы"],
    },
    "transport": {
        "display_name": "Проезд/транспорт",
        "aliases": ["проезд", "транспорт", "общественный транспорт"],
    },
    "transport.parking": {
        "display_name": "Парковка",
        "aliases": ["парковка", "парковка на работе"],
    },
    "transport.fuel": {
        "display_name": "Топливо",
        "aliases": ["топливо", "бензин", "заправка"],
    },
    "car": {
        "display_name": "Автомобиль",
        "aliases": ["автомобиль", "машина", "авто"],
    },
    "credit": {
        "display_name": "Кредиты",
        "aliases": ["кредит", "кредиты", "ипотека"],
    },
    "taxes": {
        "display_name": "Налоги",
        "aliases": ["налоги", "налог"],
    },
    "clothing": {
        "display_name": "Одежда",
        "aliases": ["одежда", "обувь"],
    },
    "health": {
        "display_name": "Здоровье",
        "aliases": ["здоровье", "аптека", "лекарства", "врач"],
    },
    "beauty": {
        "display_name": "Красота/уход",
        "aliases": ["красота", "уход", "парикмахерская", "стрижка"],
    },
    "children.school": {
        "display_name": "Школа",
        "aliases": ["школа", "детская школа"],
    },
    "children.clubs": {
        "display_name": "Доп. занятия",
        "aliases": ["доп. школа", "доп школа", "кружки", "секции"],
    },
    "entertainment": {
        "display_name": "Развлечения",
        "aliases": ["развлечения", "развлечение", "досуг"],
    },
    "gifts": {
        "display_name": "Подарки",
        "aliases": ["подарки", "подарок"],
    },
    "salary": {
        "display_name": "Зарплата",
        "aliases": ["зарплата", "основная зарплата"],
    },
    "salary.advance": {
        "display_name": "Аванс",
        "aliases": ["аванс"],
    },
    "benefits": {
        "display_name": "Соц.выплаты",
        "aliases": ["соц.выплаты", "соц выплаты", "детские", "пособия"],
    },
    "side_job": {
        "display_name": "Подработка",
        "aliases": ["подработка", "доп.подработка", "доп подработка"],
    },
    "business_project": {
        "display_name": "Бизнес/проект",
        "aliases": ["проектирование", "проект", "бизнес"],
    },
    "sale": {
        "display_name": "Продажа вещей",
        "aliases": ["продажа ненужного", "продажа вещей", "продажа"],
    },
    "interest_cashback": {
        "display_name": "Проценты/кэшбэк",
        "aliases": ["проценты по карте", "кэшбэк", "кешбэк", "проценты"],
    },
    "opening_balance": {
        "display_name": "Остаток",
        "aliases": ["остаток", "входящий остаток"],
    },
}


_ALIAS_TO_SEMANTIC_KEY: Dict[str, str] = {}
for semantic_key, template in _SEMANTIC_CATEGORY_TEMPLATES.items():
    for alias in template["aliases"]:
        normalized_alias = re.sub(r"\s+", " ", alias.strip().lower().replace("ё", "е"))
        normalized_alias = re.sub(r"^[\s.,;:]+|[\s.,;:]+$", "", normalized_alias)
        normalized_alias = re.sub(r"\s*/\s*", "/", normalized_alias)
        _ALIAS_TO_SEMANTIC_KEY[normalized_alias] = semantic_key


def _normalize_category_name(value: object) -> str:
    normalized = str(value or "").replace("\u00a0", " ").strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^[\s.,;:]+|[\s.,;:]+$", "", normalized)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    return normalized


def _personal_category_names_for_family(family_id: int) -> Set[str]:
    names: Set[str] = set()
    for item in auth_service.list_family_category_audit_resolutions(family_id):
        if str(item.get("action") or "") != "keep_personal":
            continue
        for category_name in item.get("category_names", []):
            normalized = _normalize_category_name(category_name)
            if normalized:
                names.add(normalized)
    return names


def _semantic_key_for_category_name(value: object) -> Optional[str]:
    normalized = _normalize_category_name(value)
    return _ALIAS_TO_SEMANTIC_KEY.get(normalized)


def _semantic_display_name(semantic_key: Optional[str], fallback: str) -> str:
    if semantic_key and semantic_key in _SEMANTIC_CATEGORY_TEMPLATES:
        return str(_SEMANTIC_CATEGORY_TEMPLATES[semantic_key]["display_name"])
    return fallback


def _semantic_type(semantic_key: str, fallback: str = "both") -> str:
    if semantic_key.startswith(("salary", "benefits", "side_job", "business_project", "sale", "interest_cashback", "opening_balance")):
        return "income"
    if semantic_key == "gifts":
        return "both"
    return fallback if fallback in {"income", "expense", "both"} else "both"


def _category_type_label(category_type: object) -> str:
    labels = {
        "income": "доход",
        "expense": "расход",
        "both": "доход и расход",
    }
    return labels.get(str(category_type or "").strip().lower(), str(category_type or "не указано"))


def _category_type_list_label(category_types: Set[str]) -> str:
    return ", ".join(_category_type_label(item) for item in sorted(category_types))


def _display_owner_name(member: Dict[str, object]) -> str:
    display_name = str(member.get("display_name") or "").strip()
    if display_name:
        return display_name
    return str(member.get("email") or "")


def _collect_family_forecast(
    members: List[Dict[str, object]],
    now: datetime,
    current_balance: float,
    actual_income: float,
    actual_expense: float,
    planned_income: float,
    planned_expense: float,
    executed_planned_income: float,
    executed_planned_expense: float,
    personal_category_names: Optional[Set[str]] = None,
) -> ForecastResponse:
    personal_category_names = personal_category_names or set()
    start_of_month = now.replace(day=1).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    end_date = now.replace(day=calendar.monthrange(now.year, now.month)[1]).strftime("%Y-%m-%d")
    remaining_days_including_today = max(calendar.monthrange(now.year, now.month)[1] - now.day + 1, 0)
    remaining_days_after_today = max(calendar.monthrange(now.year, now.month)[1] - now.day, 0)
    spent_by_category: Dict[str, float] = {}
    spent_today_by_category: Dict[str, float] = {}
    planned_expense_by_category: Dict[str, float] = {}
    budget_by_category: Dict[str, Dict[str, Any]] = {}

    for member in members:
        user_id = int(member["user_id"])

        def _action():
            expenses = transaction_service.get_expenses_by_category(start_of_month, today)
            budgets = transaction_service.get_budgets()
            today_expense_rows = transaction_service.get_expenses_by_category(today, today)
            planned_rows = transaction_service.get_planned_expenses_by_category(end_date)
            return expenses, budgets, today_expense_rows, planned_rows

        expenses, budgets, today_expense_rows, planned_rows = _run_in_user_db(user_id, _action)
        for item in expenses:
            category_name = str(item["category"] or "")
            spent_by_category[category_name] = spent_by_category.get(category_name, 0.0) + float(item["total"] or 0.0)
        for item in today_expense_rows:
            category_name = str(item["category"] or "")
            spent_today_by_category[category_name] = spent_today_by_category.get(category_name, 0.0) + float(item["total"] or 0.0)
        for item in planned_rows:
            category_name = str(item["category"] or "")
            planned_expense_by_category[category_name] = planned_expense_by_category.get(category_name, 0.0) + float(item["total"] or 0.0)
        for budget in budgets:
            period = budget["period"] if "period" in budget.keys() else "monthly"
            monthly_amount = float(
                transaction_service.get_budget_monthly_limit(
                    budget["amount"] or 0,
                    period,
                    today,
                )
            )
            category_name = str(budget["category"] or "")
            if _normalize_category_name(category_name) in personal_category_names:
                continue
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
    budget_remaining = 0.0
    for category_name, budget_meta in budget_by_category.items():
        monthly_amount = float(budget_meta["monthly_amount"])
        total_budgets += monthly_amount
        spent = float(spent_by_category.get(category_name, 0.0))
        current_expenses += spent
        daily_amount = float(budget_meta["daily_amount"])
        has_non_daily = bool(budget_meta["has_non_daily"])
        if daily_amount > 0 and not has_non_daily:
            spent_today = float(spent_today_by_category.get(category_name, 0.0))
            days_to_reserve = remaining_days_after_today if spent_today > 0 else remaining_days_including_today
            future_budget_expense = daily_amount * days_to_reserve
            budget_remaining += max(future_budget_expense, 0.0)
        else:
            budget_remaining += max(monthly_amount - spent, 0.0)

    combined_pending_expense = planned_expense + budget_remaining
    combined_executed_expense = actual_expense
    projected_balance = actual_income + planned_income - actual_expense - planned_expense - budget_remaining

    return ForecastResponse(
        current_balance=round(current_balance, 2),
        planned_income=round(planned_income, 2),
        planned_expense=round(planned_expense, 2),
        executed_planned_income=round(actual_income, 2),
        executed_planned_expense=round(actual_expense, 2),
        monthly_budget=round(total_budgets, 2),
        total_budgets=round(total_budgets, 2),
        current_expenses=round(current_expenses, 2),
        budget_remaining=round(budget_remaining, 2),
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
    return run_in_user_finance_db(user_id, action)


def _get_active_capital_account(owner_user_id: int, capital_account_id: int):
    def _action():
        for account in transaction_service.get_capital_accounts(include_inactive=False):
            if int(account["id"]) == capital_account_id:
                return account
        return None

    return _run_in_user_db(owner_user_id, _action)


def _capital_purpose(value) -> str:
    value = str(value or "").strip()
    if value in {"investment", "personal"}:
        return value
    return "cushion"


def _counts_as_cushion(account) -> bool:
    try:
        value = account["counts_as_cushion"]
    except (KeyError, IndexError, TypeError):
        value = None
    if value is None:
        try:
            purpose = account["purpose"]
        except (KeyError, IndexError, TypeError):
            purpose = "cushion"
        return _capital_purpose(purpose) == "cushion"
    return bool(value)


def _collect_family_capital_accounts(family_id: int) -> List[Dict[str, object]]:
    result: List[Dict[str, object]] = []
    for item in auth_service.list_family_capital_accounts(family_id):
        if not bool(item.get("is_visible")):
            continue
        owner_user_id = int(item["owner_user_id"])
        capital_account_id = int(item["capital_account_id"])

        def _action():
            for account in transaction_service.get_capital_accounts(include_inactive=False):
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
                "purpose": _capital_purpose(account["purpose"] if "purpose" in account.keys() else "cushion"),
                "counts_as_cushion": _counts_as_cushion(account),
                "is_visible": True,
                "is_default_target": bool(item.get("is_default_target")),
            }
        )
    return result


def _collect_family_dashboard(family_id: int, family_name: str, current_user_id: int) -> FamilyDashboardResponse:
    members = auth_service.list_family_members(family_id)
    now = datetime.now()
    start_of_month = now.replace(day=1).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    main_balance = 0.0
    capital_balance = 0.0
    income = 0.0
    expense = 0.0
    forecast_planned_income = 0.0
    forecast_planned_expense = 0.0
    forecast_executed_planned_income = 0.0
    forecast_executed_planned_expense = 0.0
    recent_transactions: List[Dict[str, object]] = []
    member_money: List[Dict[str, object]] = []
    capital_accounts = _collect_family_capital_accounts(family_id)
    capital_balance = sum(float(item["balance"] or 0) for item in capital_accounts)
    cushion_balance = sum(
        float(item["balance"] or 0)
        for item in capital_accounts
        if bool(item.get("counts_as_cushion", str(item.get("purpose") or "cushion") == "cushion"))
    )
    investment_balance = sum(
        float(item["balance"] or 0)
        for item in capital_accounts
        if str(item.get("purpose") or "cushion") == "investment"
    )
    personal_category_names = _personal_category_names_for_family(family_id)
    family_capital_outflow_by_source_user: Dict[int, float] = {}
    for item in auth_service.list_family_capital_contributions_for_family(family_id=family_id, limit=300):
        item_date = str(item["date"] or "")
        if not (start_of_month <= item_date <= today):
            continue
        source_user_id = int(item["source_user_id"])
        family_capital_outflow_by_source_user[source_user_id] = (
            family_capital_outflow_by_source_user.get(source_user_id, 0.0) + float(item["amount"] or 0.0)
        )

    for member in members:
        user_id = int(member["user_id"])
        user_email = str(member["email"] or "")
        user_display_name = str(member.get("display_name") or "").strip()

        def _action():
            balance = transaction_service.get_balance(force_update=True)
            stats = transaction_service.get_monthly_stats(now.year, now.month)
            capital_outflow = transaction_service.get_capital_outflow_for_period(start_of_month, today)
            items = transaction_service.get_transactions(limit=100, period="all", offset=0)
            forecast = transaction_service.get_projected_balance()
            return balance, stats, capital_outflow, items, forecast

        balance, stats, direct_capital_outflow, items, forecast = _run_in_user_db(user_id, _action)
        family_capital_outflow = float(family_capital_outflow_by_source_user.get(user_id, 0.0))
        capital_outflow = float(direct_capital_outflow or 0.0) + family_capital_outflow
        member_main_balance = float(balance.main_balance)
        main_balance += member_main_balance
        member_money.append(
            {
                "user_id": user_id,
                "email": user_email,
                "display_name": user_display_name,
                "main_balance": round(member_main_balance, 2),
            }
        )
        income += float(stats.get("income", 0.0) or 0.0)
        expense += float(stats.get("expense", 0.0) or 0.0) + capital_outflow
        forecast_planned_income += float(forecast.get("planned_income", 0.0) or 0.0)
        forecast_planned_expense += float(forecast.get("planned_expense", 0.0) or 0.0)
        forecast_executed_planned_income += float(forecast.get("executed_planned_income", 0.0) or 0.0)
        forecast_executed_planned_expense += float(forecast.get("executed_planned_expense", 0.0) or 0.0) + family_capital_outflow

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
        actual_income=income,
        actual_expense=expense,
        planned_income=forecast_planned_income,
        planned_expense=forecast_planned_expense,
        executed_planned_income=forecast_executed_planned_income,
        executed_planned_expense=forecast_executed_planned_expense,
        personal_category_names=personal_category_names,
    )

    return FamilyDashboardResponse(
        family_id=family_id,
        family_name=family_name,
        members_count=len(members),
        balance=FamilyDashboardBalanceResponse(
            main_balance=round(main_balance, 2),
            capital_balance=round(capital_balance, 2),
            cushion_balance=round(cushion_balance, 2),
            investment_balance=round(investment_balance, 2),
            income=round(income, 2),
            expense=round(expense, 2),
            difference=round(income - expense, 2),
        ),
        member_money=member_money,
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


def _collect_member_category_audit_snapshot(member: Dict[str, object]) -> Dict[str, object]:
    user_id = int(member["user_id"])

    def _action():
        return transaction_service.get_category_audit_snapshot()

    snapshot = _run_in_user_db(user_id, _action)
    return {
        "user_id": user_id,
        "email": str(member.get("email") or ""),
        "display_name": str(member.get("display_name") or ""),
        "owner_name": _display_owner_name(member),
        "categories": snapshot["categories"],
        "transactions": snapshot["transactions"],
        "budgets": snapshot["budgets"],
        "recurring_templates": snapshot["recurring_templates"],
    }


def _category_audit_finding(
    severity: str,
    code: str,
    title: str,
    description: str,
    recommended_action: str,
    group_key: Optional[str] = None,
    semantic_key: Optional[str] = None,
    display_name: Optional[str] = None,
    category_names: Optional[List[str]] = None,
    owner_names: Optional[List[str]] = None,
    affected_transaction_count: int = 0,
    affected_budget_count: int = 0,
    affected_recurring_count: int = 0,
    can_apply_automatically: bool = False,
) -> Dict[str, object]:
    return {
        "severity": severity,
        "code": code,
        "title": title,
        "description": description,
        "group_key": group_key,
        "semantic_key": semantic_key,
        "display_name": display_name,
        "category_names": sorted(set(category_names or [])),
        "owner_names": sorted(set(owner_names or [])),
        "affected_transaction_count": affected_transaction_count,
        "affected_budget_count": affected_budget_count,
        "affected_recurring_count": affected_recurring_count,
        "recommended_action": recommended_action,
        "can_apply_automatically": can_apply_automatically,
    }


def _collect_family_category_audit(family_id: int, family_name: str) -> FamilyCategoryAuditResponse:
    members = auth_service.list_family_members(family_id)
    snapshots = [_collect_member_category_audit_snapshot(member) for member in members]
    member_ids = {int(snapshot["user_id"]) for snapshot in snapshots}
    existing_bindings = auth_service.list_family_category_bindings(family_id)
    resolved_items = auth_service.list_family_category_audit_resolutions(family_id)
    resolved_keys = {
        (str(item.get("code") or ""), str(item.get("group_key") or ""))
        for item in resolved_items
        if str(item.get("action") or "") in {"ignore", "keep_personal"}
    }
    resolved_group_keys = {group_key for _, group_key in resolved_keys if group_key}
    bindings_by_local_category = {
        (int(item["user_id"]), int(item["local_category_id"])): item
        for item in existing_bindings
    }
    bindings_by_local_name = {
        (int(item["user_id"]), _normalize_category_name(item["local_category_name"])): item
        for item in existing_bindings
    }

    category_names_by_user: Dict[int, Set[str]] = {}
    active_category_names_by_user: Dict[int, Set[str]] = {}
    transaction_usage_by_user: Dict[int, Dict[str, Dict[str, Any]]] = {}
    budget_usage_by_user: Dict[int, Dict[str, Dict[str, Any]]] = {}
    recurring_usage_by_user: Dict[int, Dict[str, int]] = {}
    groups: Dict[str, Dict[str, Any]] = {}
    findings: List[Dict[str, object]] = []

    def _group_for(name: str, binding: Optional[Dict[str, object]] = None) -> Dict[str, Any]:
        normalized = _normalize_category_name(name)
        semantic_key = str(binding.get("semantic_key") or "") if binding else ""
        if not semantic_key:
            semantic_key = _semantic_key_for_category_name(normalized) or ""
        semantic_key_or_none = semantic_key or None
        group_key = semantic_key or f"name:{normalized}"
        if group_key not in groups:
            groups[group_key] = {
                "group_key": group_key,
                "semantic_key": semantic_key_or_none,
                "display_name": str(binding.get("family_category_name") or "") if binding else _semantic_display_name(semantic_key_or_none, name),
                "category_names": set(),
                "normalized_names": set(),
                "owner_names": set(),
                "user_ids": set(),
                "types": set(),
                "family_category_types": set(),
                "confirmed_bindings_count": 0,
                "transaction_count": 0,
                "planned_transaction_count": 0,
                "transaction_total": 0.0,
                "budget_count": 0,
                "budget_total": 0.0,
                "recurring_count": 0,
            }
        if binding:
            groups[group_key]["family_category_types"].add(str(binding.get("family_category_type") or "both"))
        return groups[group_key]

    for snapshot in snapshots:
        user_id = int(snapshot["user_id"])
        category_names_by_user[user_id] = set()
        active_category_names_by_user[user_id] = set()
        transaction_usage_by_user[user_id] = {}
        budget_usage_by_user[user_id] = {}
        recurring_usage_by_user[user_id] = {}
        owner_name = str(snapshot["owner_name"])

        for category in snapshot["categories"]:
            category_name = str(category.get("name") or "")
            normalized = _normalize_category_name(category_name)
            if not normalized:
                continue
            binding = bindings_by_local_category.get((user_id, int(category.get("id") or 0)))
            category_names_by_user[user_id].add(normalized)
            if bool(category.get("is_active")):
                active_category_names_by_user[user_id].add(normalized)
            group = _group_for(category_name, binding)
            group["category_names"].add(category_name)
            group["normalized_names"].add(normalized)
            group["owner_names"].add(owner_name)
            group["user_ids"].add(user_id)
            group["types"].add(str(category.get("type") or ""))
            if binding:
                group["confirmed_bindings_count"] += 1

        for item in snapshot["transactions"]:
            category_name = str(item.get("category") or "")
            normalized = _normalize_category_name(category_name)
            if not normalized:
                continue
            usage = transaction_usage_by_user[user_id].setdefault(
                normalized,
                {"count": 0, "planned_count": 0, "total": 0.0},
            )
            count = int(item.get("count") or 0)
            total = float(item.get("total") or 0.0)
            usage["count"] = int(usage["count"]) + count
            usage["total"] = float(usage["total"]) + total
            if str(item.get("status") or "actual") == "planned":
                usage["planned_count"] = int(usage["planned_count"]) + count
            group = _group_for(category_name, bindings_by_local_name.get((user_id, normalized)))
            group["category_names"].add(category_name)
            group["normalized_names"].add(normalized)
            group["owner_names"].add(owner_name)
            group["user_ids"].add(user_id)
            group["types"].add(str(item.get("type") or ""))
            group["transaction_count"] += count
            group["transaction_total"] += total
            if str(item.get("status") or "actual") == "planned":
                group["planned_transaction_count"] += count

        for budget in snapshot["budgets"]:
            category_name = str(budget.get("category") or "")
            normalized = _normalize_category_name(category_name)
            if not normalized:
                findings.append(
                    _category_audit_finding(
                        severity="critical",
                        code="budget_without_category",
                        title="Бюджет без категории",
                        description=f"У участника {owner_name} найден бюджет, который ссылается на отсутствующую категорию.",
                        recommended_action="Перед синхронизацией нужно восстановить категорию или перенести бюджет на корректную категорию.",
                        owner_names=[owner_name],
                        affected_budget_count=1,
                    )
                )
                continue
            budget_usage = budget_usage_by_user[user_id].setdefault(normalized, {"count": 0, "total": 0.0})
            budget_usage["count"] = int(budget_usage["count"]) + 1
            budget_usage["total"] = float(budget_usage["total"]) + float(budget.get("amount") or 0.0)
            group = _group_for(category_name, bindings_by_local_category.get((user_id, int(budget.get("category_id") or 0))))
            group["category_names"].add(category_name)
            group["normalized_names"].add(normalized)
            group["owner_names"].add(owner_name)
            group["user_ids"].add(user_id)
            group["budget_count"] += 1
            group["budget_total"] += float(budget.get("amount") or 0.0)
            if budget.get("category_is_active") is not None and not bool(budget.get("category_is_active")):
                findings.append(
                    _category_audit_finding(
                        severity="warning",
                        code="budget_on_inactive_category",
                        title="Бюджет на отключенной категории",
                        description=f"У участника {owner_name} бюджет привязан к отключенной категории `{category_name}`.",
                        recommended_action="Перед слиянием нужно решить: включить категорию обратно или перенести бюджет.",
                        category_names=[category_name],
                        owner_names=[owner_name],
                        affected_budget_count=1,
                    )
                )

        for template in snapshot["recurring_templates"]:
            if not bool(template.get("is_active")):
                continue
            category_name = str(template.get("category") or "")
            normalized = _normalize_category_name(category_name)
            if not normalized:
                findings.append(
                    _category_audit_finding(
                        severity="critical",
                        code="recurring_without_category",
                        title="Регулярный шаблон без категории",
                        description=f"У участника {owner_name} активный регулярный шаблон `{template.get('name')}` ссылается на отсутствующую категорию.",
                        recommended_action="Нужно выбрать корректную категорию для шаблона до включения синхронизации.",
                        owner_names=[owner_name],
                        affected_recurring_count=1,
                    )
                )
                continue
            recurring_usage_by_user[user_id][normalized] = recurring_usage_by_user[user_id].get(normalized, 0) + 1
            group = _group_for(category_name, bindings_by_local_category.get((user_id, int(template.get("category_id") or 0))))
            group["category_names"].add(category_name)
            group["normalized_names"].add(normalized)
            group["owner_names"].add(owner_name)
            group["user_ids"].add(user_id)
            group["recurring_count"] += 1
            if template.get("category_is_active") is not None and not bool(template.get("category_is_active")):
                findings.append(
                    _category_audit_finding(
                        severity="warning",
                        code="recurring_on_inactive_category",
                        title="Регулярный шаблон на отключенной категории",
                        description=f"У участника {owner_name} активный шаблон `{template.get('name')}` привязан к отключенной категории `{category_name}`.",
                        recommended_action="Перед слиянием нужно включить категорию или перенести шаблон.",
                        category_names=[category_name],
                        owner_names=[owner_name],
                        affected_recurring_count=1,
                    )
                )

    for snapshot in snapshots:
        user_id = int(snapshot["user_id"])
        owner_name = str(snapshot["owner_name"])
        for normalized, usage in transaction_usage_by_user[user_id].items():
            if normalized not in category_names_by_user[user_id]:
                category_name = next(
                    (
                        str(item.get("category") or "")
                        for item in snapshot["transactions"]
                        if _normalize_category_name(item.get("category")) == normalized
                    ),
                    normalized,
                )
                findings.append(
                    _category_audit_finding(
                        severity="critical",
                        code="orphan_transaction_category",
                        title="Операции без категории в справочнике",
                        description=f"У участника {owner_name} есть операции с категорией `{category_name}`, но такой категории нет в его справочнике.",
                        recommended_action="Создать категорию, связать ее со смыслом или перенести операции через будущий merge-preview.",
                        category_names=[category_name],
                        owner_names=[owner_name],
                        affected_transaction_count=int(usage["count"]),
                    )
                )

        for category in snapshot["categories"]:
            if bool(category.get("is_active")):
                continue
            category_name = str(category.get("name") or "")
            normalized = _normalize_category_name(category_name)
            usage = transaction_usage_by_user[user_id].get(normalized, {"count": 0})
            budget_usage = budget_usage_by_user[user_id].get(normalized, {"count": 0})
            recurring_count = recurring_usage_by_user[user_id].get(normalized, 0)
            if int(usage.get("count", 0)) or int(budget_usage.get("count", 0)) or recurring_count:
                findings.append(
                    _category_audit_finding(
                        severity="warning",
                        code="inactive_category_with_usage",
                        title="Отключенная категория все еще используется",
                        description=f"Участник {owner_name} отключил категорию `{category_name}`, но по ней есть история, бюджет или шаблон.",
                        recommended_action="Не удалять такую категорию физически; сначала решить, как она должна мапиться в семейном справочнике.",
                        category_names=[category_name],
                        owner_names=[owner_name],
                        affected_transaction_count=int(usage.get("count", 0)),
                        affected_budget_count=int(budget_usage.get("count", 0)),
                        affected_recurring_count=recurring_count,
                    )
                )

    for group in groups.values():
        names = sorted(group["category_names"])
        owner_names = sorted(group["owner_names"])
        semantic_key = group["semantic_key"]
        types = {item for item in group["types"] if item}
        concrete_types = {item for item in types if item != "both"}
        confirmed_as_both = "both" in {str(item) for item in group["family_category_types"]}
        if len(concrete_types) > 1 and not confirmed_as_both:
            findings.append(
                _category_audit_finding(
                    severity="warning",
                    code="category_type_conflict",
                    title="Разные типы у одного смысла",
                    description=f"Категории `{', '.join(names)}` похожи на один смысл, но используются как разные типы: {_category_type_list_label(types)}.",
                    recommended_action="Перед синхронизацией нужно вручную решить, это одна категория с типом `доход и расход` или разные категории.",
                    group_key=str(group["group_key"]),
                    semantic_key=semantic_key,
                    display_name=str(group["display_name"]),
                    category_names=names,
                    owner_names=owner_names,
                    affected_transaction_count=int(group["transaction_count"]),
                )
            )
        if semantic_key and len(group["normalized_names"]) > 1 and int(group["confirmed_bindings_count"]) == 0:
            severity = "warning" if int(group["transaction_count"]) or int(group["budget_count"]) else "info"
            findings.append(
                _category_audit_finding(
                    severity=severity,
                    code="semantic_duplicate_candidate",
                    title="Похожие категории можно связать по смыслу",
                    description=f"Категории `{', '.join(names)}` похожи на общий смысл `{_semantic_display_name(semantic_key, names[0])}`.",
                    recommended_action="Показать пользователю preview и подтвердить связь; автоматически не сливать, если есть бюджеты или шаблоны.",
                    group_key=str(group["group_key"]),
                    semantic_key=semantic_key,
                    display_name=str(group["display_name"]),
                    category_names=names,
                    owner_names=owner_names,
                    affected_transaction_count=int(group["transaction_count"]),
                    affected_budget_count=int(group["budget_count"]),
                    affected_recurring_count=int(group["recurring_count"]),
                    can_apply_automatically=not bool(group["budget_count"] or group["recurring_count"]),
                )
            )
        if int(group["budget_count"]) > 1:
            findings.append(
                _category_audit_finding(
                    severity="warning",
                    code="multiple_budgets_same_semantic",
                    title="Несколько бюджетов попадают в один смысл",
                    description=f"В группе `{group['display_name']}` найдено несколько бюджетов. Это может быть нормально, но для слияния нужна явная политика.",
                    recommended_action="Перед merge выбрать: сложить бюджеты, оставить один, перенести или разделить на дочерние категории.",
                    group_key=str(group["group_key"]),
                    semantic_key=semantic_key,
                    display_name=str(group["display_name"]),
                    category_names=names,
                    owner_names=owner_names,
                    affected_budget_count=int(group["budget_count"]),
                )
            )
        if group["user_ids"] and set(group["user_ids"]) != member_ids and int(group["confirmed_bindings_count"]) == 0:
            missing_count = len(member_ids - set(group["user_ids"]))
            if int(group["transaction_count"]) or int(group["budget_count"]) or int(group["recurring_count"]) or semantic_key:
                findings.append(
                    _category_audit_finding(
                        severity="info",
                        code="missing_member_category",
                        title="Категория есть не у всех участников",
                        description=f"Категория `{group['display_name']}` есть у части семьи, но отсутствует у {missing_count} участника(ов).",
                        recommended_action="В будущем мастер синхронизации должен предложить создать недостающую локальную категорию или оставить ее личной.",
                        group_key=str(group["group_key"]),
                        semantic_key=semantic_key,
                        display_name=str(group["display_name"]),
                        category_names=names,
                        owner_names=owner_names,
                        affected_transaction_count=int(group["transaction_count"]),
                        affected_budget_count=int(group["budget_count"]),
                        affected_recurring_count=int(group["recurring_count"]),
                    )
                )

    semantic_groups = {str(group["semantic_key"]): group for group in groups.values() if group["semantic_key"]}
    for semantic_key, group in semantic_groups.items():
        child_groups = [
            item for key, item in semantic_groups.items()
            if key.startswith(f"{semantic_key}.") and key != semantic_key
        ]
        if not child_groups:
            continue
        child_names = sorted({str(child["display_name"]) for child in child_groups})
        severity = "warning" if int(group["budget_count"]) or any(int(child["budget_count"]) for child in child_groups) else "info"
        findings.append(
            _category_audit_finding(
                severity=severity,
                code="parent_child_category_overlap",
                title="Есть общая и детальная категория одного направления",
                description=f"У семьи есть общий смысл `{group['display_name']}` и детализация: {', '.join(child_names)}.",
                recommended_action="Перед бюджетированием решить, считать все вместе или вести отдельные дочерние бюджеты.",
                group_key=str(group["group_key"]),
                semantic_key=semantic_key,
                display_name=str(group["display_name"]),
                category_names=sorted(set(group["category_names"])),
                owner_names=sorted(set(group["owner_names"])),
                affected_transaction_count=int(group["transaction_count"]),
                affected_budget_count=int(group["budget_count"]),
            )
        )

    findings = [
        item for item in findings
        if (str(item.get("code") or ""), str(item.get("group_key") or "")) not in resolved_keys
    ]
    unresolved_group_keys = {str(item.get("group_key") or "") for item in findings if item.get("group_key")}

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (severity_order.get(str(item["severity"]), 9), str(item["code"]), str(item["title"])))

    category_groups = []
    for group in groups.values():
        group_key = str(group["group_key"])
        if group_key in resolved_group_keys and group_key not in unresolved_group_keys and int(group["confirmed_bindings_count"]) == 0:
            continue
        concrete_types = {item for item in group["types"] if item and item != "both"}
        confirmed_as_both = "both" in {str(item) for item in group["family_category_types"]}
        has_conflict = len(concrete_types) > 1 and not confirmed_as_both
        if has_conflict:
            status_value = "conflict"
        elif int(group["confirmed_bindings_count"]) > 0:
            status_value = "confirmed"
        else:
            status_value = "suggested" if group["semantic_key"] else "unlinked"
        category_groups.append(
            FamilyCategoryAuditGroupResponse(
                group_key=group_key,
                semantic_key=group["semantic_key"],
                display_name=str(group["display_name"]),
                category_names=sorted(group["category_names"]),
                owner_names=sorted(group["owner_names"]),
                types=sorted(item for item in group["types"] if item),
                confirmed_bindings_count=int(group["confirmed_bindings_count"]),
                transaction_count=int(group["transaction_count"]),
                planned_transaction_count=int(group["planned_transaction_count"]),
                transaction_total=round(float(group["transaction_total"]), 2),
                budget_count=int(group["budget_count"]),
                budget_total=round(float(group["budget_total"]), 2),
                recurring_count=int(group["recurring_count"]),
                status=status_value,
            )
        )
    category_groups.sort(
        key=lambda item: (
            0 if item.status == "conflict" else 1 if item.status == "suggested" else 2 if item.status == "confirmed" else 3,
            -(item.transaction_count + item.budget_count + item.recurring_count),
            item.display_name,
        )
    )

    response_findings = [FamilyCategoryAuditFindingResponse(**item) for item in findings]
    summary = FamilyCategoryAuditSummaryResponse(
        members_count=len(snapshots),
        active_categories_count=sum(
            1
            for snapshot in snapshots
            for category in snapshot["categories"]
            if bool(category.get("is_active"))
        ),
        transaction_categories_count=sum(len(transaction_usage_by_user.get(int(snapshot["user_id"]), {})) for snapshot in snapshots),
        findings_count=len(response_findings),
        critical_count=sum(1 for item in response_findings if item.severity == "critical"),
        warning_count=sum(1 for item in response_findings if item.severity == "warning"),
        info_count=sum(1 for item in response_findings if item.severity == "info"),
        duplicate_candidates_count=sum(1 for item in response_findings if item.code == "semantic_duplicate_candidate"),
        orphan_transaction_categories_count=sum(1 for item in response_findings if item.code == "orphan_transaction_category"),
        missing_member_categories_count=sum(1 for item in response_findings if item.code == "missing_member_category"),
    )
    member_responses = [
        FamilyCategoryAuditMemberResponse(
            user_id=int(snapshot["user_id"]),
            email=str(snapshot["email"]),
            display_name=str(snapshot["display_name"]),
            active_categories_count=sum(1 for item in snapshot["categories"] if bool(item.get("is_active"))),
            inactive_categories_count=sum(1 for item in snapshot["categories"] if not bool(item.get("is_active"))),
            transaction_categories_count=len(transaction_usage_by_user.get(int(snapshot["user_id"]), {})),
            budget_count=len(snapshot["budgets"]),
            recurring_template_count=sum(1 for item in snapshot["recurring_templates"] if bool(item.get("is_active"))),
        )
        for snapshot in snapshots
    ]

    return FamilyCategoryAuditResponse(
        family_id=family_id,
        family_name=family_name,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=summary,
        members=member_responses,
        category_groups=category_groups,
        findings=response_findings,
        resolutions=[
            {
                "family_id": family_id,
                "code": str(item.get("code") or ""),
                "group_key": str(item.get("group_key") or ""),
                "action": str(item.get("action") or ""),
                "category_names": [str(name) for name in item.get("category_names", [])],
                "note": str(item.get("note") or ""),
            }
            for item in resolved_items
            if str(item.get("action") or "") in {"ignore", "keep_personal"}
        ],
    )


def _build_family_category_binding_preview(
    family_id: int,
    payload: FamilyCategoryBindingPreviewPayload,
) -> FamilyCategoryBindingPreviewResponse:
    semantic_key = payload.semantic_key.strip().lower()
    category_names = [name.strip() for name in payload.category_names if name.strip()]
    normalized_targets = {_normalize_category_name(name) for name in category_names if _normalize_category_name(name)}
    display_name = (payload.display_name or "").strip() or _semantic_display_name(semantic_key, category_names[0] if category_names else semantic_key)
    requested_type = (payload.category_type or "").strip().lower()
    if requested_type not in {"income", "expense", "both"}:
        requested_type = ""
    members = auth_service.list_family_members(family_id)
    snapshots = [_collect_member_category_audit_snapshot(member) for member in members]
    existing_bindings = auth_service.list_family_category_bindings(family_id)
    bindings_by_local_category = {
        (int(item["user_id"]), int(item["local_category_id"])): item
        for item in existing_bindings
    }

    candidates: List[FamilyCategoryBindingCandidateResponse] = []
    local_types: Set[str] = set()
    blocks: List[str] = []

    for snapshot in snapshots:
        user_id = int(snapshot["user_id"])
        owner_name = str(snapshot["owner_name"])
        transaction_metrics: Dict[str, Dict[str, Any]] = {}
        for item in snapshot["transactions"]:
            normalized = _normalize_category_name(item.get("category"))
            if not normalized:
                continue
            bucket = transaction_metrics.setdefault(
                normalized,
                {"count": 0, "planned_count": 0, "total": 0.0},
            )
            count = int(item.get("count") or 0)
            bucket["count"] = int(bucket["count"]) + count
            bucket["total"] = float(bucket["total"]) + float(item.get("total") or 0.0)
            if str(item.get("status") or "actual") == "planned":
                bucket["planned_count"] = int(bucket["planned_count"]) + count

        budget_counts: Dict[int, int] = {}
        for budget in snapshot["budgets"]:
            category_id = int(budget.get("category_id") or 0)
            budget_counts[category_id] = budget_counts.get(category_id, 0) + 1

        recurring_counts: Dict[int, int] = {}
        for template in snapshot["recurring_templates"]:
            if not bool(template.get("is_active")):
                continue
            category_id = int(template.get("category_id") or 0)
            recurring_counts[category_id] = recurring_counts.get(category_id, 0) + 1

        for category in snapshot["categories"]:
            if not bool(category.get("is_active")):
                continue
            category_name = str(category.get("name") or "")
            normalized = _normalize_category_name(category_name)
            if normalized not in normalized_targets:
                continue
            local_category_id = int(category.get("id") or 0)
            local_category_type = str(category.get("type") or "both")
            local_types.add(local_category_type)
            binding = bindings_by_local_category.get((user_id, local_category_id))
            if binding and str(binding.get("semantic_key") or "") != semantic_key:
                blocks.append(
                    f"{owner_name}: `{category_name}` уже связана с `{binding.get('family_category_name')}`"
                )
            metrics = transaction_metrics.get(normalized, {"count": 0, "planned_count": 0, "total": 0.0})
            candidates.append(
                FamilyCategoryBindingCandidateResponse(
                    user_id=user_id,
                    owner_name=owner_name,
                    local_category_id=local_category_id,
                    local_category_name=category_name,
                    local_category_type=local_category_type,
                    transaction_count=int(metrics["count"]),
                    planned_transaction_count=int(metrics["planned_count"]),
                    transaction_total=round(float(metrics["total"]), 2),
                    budget_count=budget_counts.get(local_category_id, 0),
                    recurring_count=recurring_counts.get(local_category_id, 0),
                    already_bound=bool(binding and str(binding.get("semantic_key") or "") == semantic_key),
                )
            )

    concrete_types = {item for item in local_types if item != "both"}
    inferred_type = requested_type or _semantic_type(semantic_key, next(iter(concrete_types), "both"))
    if inferred_type != "both" and any(item not in {inferred_type, "both"} for item in local_types):
        blocks.append("У выбранных категорий разные типы. Для такой связи нужен отдельный ручной разбор.")

    candidate_count = len(candidates)
    already_bound_count = sum(1 for item in candidates if item.already_bound)
    can_apply = bool(candidate_count) and not blocks
    if not candidate_count:
        message = "Не найдено активных локальных категорий для выбранных названий."
    elif blocks:
        message = "Связь нельзя применить автоматически: " + "; ".join(blocks)
    elif already_bound_count == candidate_count:
        message = "Все найденные категории уже связаны с этим смыслом."
    else:
        message = "Можно подтвердить связь. История, бюджеты и шаблоны не будут переписаны."

    return FamilyCategoryBindingPreviewResponse(
        family_id=family_id,
        semantic_key=semantic_key,
        display_name=display_name,
        type=inferred_type,
        candidates=candidates,
        candidate_count=candidate_count,
        already_bound_count=already_bound_count,
        new_binding_count=candidate_count - already_bound_count,
        affected_transaction_count=sum(item.transaction_count for item in candidates),
        affected_budget_count=sum(item.budget_count for item in candidates),
        affected_recurring_count=sum(item.recurring_count for item in candidates),
        can_apply=can_apply,
        message=message,
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
    mirror_family_snapshot_shadow_write(int(family["id"]))
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


@router.get("/{family_id}/categories/audit", response_model=FamilyCategoryAuditResponse)
def get_family_category_audit(family_id: int, current_user=Depends(require_user)) -> FamilyCategoryAuditResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    membership = _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    family_name = str(membership.get("family_name") or "Семья")
    return _collect_family_category_audit(family_id=family_id, family_name=family_name)


@router.post("/{family_id}/categories/audit/resolutions", response_model=FamilyCategoryAuditResolutionResponse)
def resolve_family_category_audit_item(
    family_id: int,
    payload: FamilyCategoryAuditResolutionPayload,
    current_user=Depends(require_user),
) -> FamilyCategoryAuditResolutionResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    auth_service.upsert_family_category_audit_resolution(
        family_id=family_id,
        code=payload.code,
        group_key=payload.group_key,
        action=payload.action,
        category_names=payload.category_names,
        note=payload.note or "",
        resolved_by_user_id=int(current_user["id"]),
    )
    mirror_family_snapshot_shadow_write(family_id)
    action_label = "оставлено личным" if payload.action == "keep_personal" else "скрыто из проверки"
    return FamilyCategoryAuditResolutionResponse(
        message=f"Решение сохранено: {action_label}.",
        family_id=family_id,
        code=payload.code,
        group_key=payload.group_key,
        action=payload.action,
    )


@router.delete("/{family_id}/categories/audit/resolutions", response_model=FamilyActionResponse)
def delete_family_category_audit_resolution(
    family_id: int,
    payload: FamilyCategoryAuditResolutionPayload,
    current_user=Depends(require_user),
) -> FamilyActionResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    deleted = auth_service.delete_family_category_audit_resolution(
        family_id=family_id,
        code=payload.code,
        group_key=payload.group_key,
        action=payload.action,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Решение аудита не найдено")
    mirror_family_snapshot_shadow_write(family_id)
    return FamilyActionResponse(message="Решение отменено. Пункт снова появится в аудите.", family_id=family_id)


@router.post("/{family_id}/categories/bindings/preview", response_model=FamilyCategoryBindingPreviewResponse)
def preview_family_category_binding(
    family_id: int,
    payload: FamilyCategoryBindingPreviewPayload,
    current_user=Depends(require_user),
) -> FamilyCategoryBindingPreviewResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    return _build_family_category_binding_preview(family_id=family_id, payload=payload)


@router.post("/{family_id}/categories/bindings", response_model=FamilyCategoryBindingApplyResponse)
def apply_family_category_binding(
    family_id: int,
    payload: FamilyCategoryBindingPreviewPayload,
    current_user=Depends(require_user),
) -> FamilyCategoryBindingApplyResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    preview = _build_family_category_binding_preview(family_id=family_id, payload=payload)
    if not preview.can_apply:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=preview.message)

    family_category = auth_service.ensure_family_category(
        family_id=family_id,
        semantic_key=preview.semantic_key,
        display_name=preview.display_name,
        category_type=preview.type,
        created_by_user_id=int(current_user["id"]),
    )
    applied_count = 0
    for candidate in preview.candidates:
        if candidate.already_bound:
            continue
        auth_service.upsert_family_category_binding(
            family_id=family_id,
            family_category_id=int(family_category["id"]),
            user_id=candidate.user_id,
            local_category_id=candidate.local_category_id,
            local_category_name=candidate.local_category_name,
            local_category_type=candidate.local_category_type,
            confirmed_by_user_id=int(current_user["id"]),
        )
        applied_count += 1

    refreshed_preview = _build_family_category_binding_preview(family_id=family_id, payload=payload)
    mirror_family_snapshot_shadow_write(family_id)
    if applied_count == 0 and refreshed_preview.already_bound_count == refreshed_preview.candidate_count:
        message = "Категория уже добавлена в семейный учет."
    else:
        message = f"Связи категорий подтверждены: {applied_count}. История операций не изменялась."
    return FamilyCategoryBindingApplyResponse(
        message=message,
        preview=refreshed_preview,
        applied_bindings_count=applied_count,
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
        mirror_family_snapshot_shadow_write(family_id)
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
    mirror_family_snapshot_shadow_write(family_id)
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
    mirror_family_snapshot_shadow_write(family_id)

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
    mirror_family_snapshot_shadow_write(int(accepted["family_id"]))

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
    mirror_family_snapshot_shadow_write(int(accepted["family_id"]))
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
    invite_family_id = 0
    for invite in auth_service.list_pending_family_invites(int(current_user["id"])):
        if int(invite["invite_id"]) == invite_id:
            invite_family_id = int(invite["family_id"])
            break
    declined = auth_service.decline_family_invite_by_id(invite_id=invite_id, user_id=int(current_user["id"]))
    if not declined:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение недействительно или уже обработано")
    if invite_family_id > 0:
        mirror_family_snapshot_shadow_write(invite_family_id)
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
    mirror_family_snapshot_shadow_write(family_id)
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
    mirror_family_snapshot_shadow_write(family_id)
    return FamilyActionResponse(message="Участник исключен из семьи.")
