from collections import defaultdict
from datetime import date as date_cls, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.reports import (
    CategorySummaryItemResponse,
    CategorySummaryResponse,
)
from backend.services import category_service, run_in_user_finance_db, transaction_service


router = APIRouter()


def _resolve_period_bounds(
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    today = date_cls.today()

    if period == "custom":
        if not start_date or not end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Для произвольного периода укажите даты начала и конца.",
            )
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Дата начала не может быть позже даты конца.",
            )
        return start_date, end_date

    if period == "month":
        return today.replace(day=1).isoformat(), today.isoformat()

    if period == "last_month":
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)
        return first_day_previous_month.isoformat(), last_day_previous_month.isoformat()

    if period == "year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()

    return None, None


def _load_personal_category_rows(
    summary_type: str,
    start_date: Optional[str],
    end_date: Optional[str],
):
    if summary_type == "income":
        return transaction_service.get_income_by_category(start_date, end_date)
    return transaction_service.get_expenses_by_category(start_date, end_date)


def _map_category_meta(category_name: str) -> Dict[str, str]:
    category = category_service.get_category_by_name(category_name)
    if not category:
        return {"color": "#808080", "icon": "📁"}
    return {
        "color": str(category.color or "#808080"),
        "icon": str(category.icon or "📁"),
    }


def _build_summary_response(
    rows,
    summary_type: str,
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
    scope: str,
    family_id: Optional[int] = None,
    family_name: Optional[str] = None,
) -> CategorySummaryResponse:
    items_payload: List[CategorySummaryItemResponse] = []
    total_sum = round(sum(float(row["total"] or 0.0) for row in rows), 2)

    for row in rows:
        category_name = str(row["category"] or "Без категории")
        category_total = round(float(row["total"] or 0.0), 2)
        meta = _map_category_meta(category_name)
        share_percent = round((category_total / total_sum) * 100, 2) if total_sum > 0 else 0.0
        items_payload.append(
            CategorySummaryItemResponse(
                category=category_name,
                total=category_total,
                share_percent=share_percent,
                color=meta["color"],
                icon=meta["icon"],
            )
        )

    return CategorySummaryResponse(
        scope=scope,
        family_id=family_id,
        family_name=family_name,
        type=summary_type,
        period=period,
        start_date=start_date,
        end_date=end_date,
        total=total_sum,
        categories_count=len(items_payload),
        items=items_payload,
    )


def _build_family_category_summary(
    family_id: int,
    family_name: str,
    summary_type: str,
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> CategorySummaryResponse:
    members = auth_service.list_family_members(family_id)
    totals: Dict[str, float] = defaultdict(float)
    meta_map: Dict[str, Dict[str, str]] = {}

    for member in members:
        user_id = int(member["user_id"])
        def _action():
            rows = _load_personal_category_rows(summary_type, start_date, end_date)
            for row in rows:
                category_name = str(row["category"] or "Без категории")
                totals[category_name] += float(row["total"] or 0.0)
                if category_name not in meta_map:
                    meta_map[category_name] = _map_category_meta(category_name)

        run_in_user_finance_db(user_id, _action)

    sorted_rows = [
        {
            "category": category_name,
            "total": round(total, 2),
            "color": meta_map.get(category_name, {}).get("color", "#808080"),
            "icon": meta_map.get(category_name, {}).get("icon", "📁"),
        }
        for category_name, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]

    total_sum = round(sum(item["total"] for item in sorted_rows), 2)
    items_payload = [
        CategorySummaryItemResponse(
            category=item["category"],
            total=item["total"],
            share_percent=round((item["total"] / total_sum) * 100, 2) if total_sum > 0 else 0.0,
            color=item["color"],
            icon=item["icon"],
        )
        for item in sorted_rows
    ]

    return CategorySummaryResponse(
        scope="family",
        family_id=family_id,
        family_name=family_name,
        type=summary_type,
        period=period,
        start_date=start_date,
        end_date=end_date,
        total=total_sum,
        categories_count=len(items_payload),
        items=items_payload,
    )


@router.get("/category-summary", response_model=CategorySummaryResponse)
def get_category_summary(
    summary_type: str = Query(default="expense", alias="type"),
    period: str = Query(default="month"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    family_id: Optional[int] = Query(default=None, ge=1),
    current_user=Depends(require_user),
) -> CategorySummaryResponse:
    if summary_type not in {"income", "expense"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный тип сводки.")
    if period not in {"month", "last_month", "year", "all", "custom"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный период.")

    resolved_start, resolved_end = _resolve_period_bounds(period, start_date, end_date)

    if family_id is not None:
        membership = auth_service.get_family_membership(family_id=family_id, user_id=int(current_user["id"]))
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семья не найдена или доступ запрещен.")
        family_name = str(membership.get("family_name") or "Семья")
        return _build_family_category_summary(
            family_id=family_id,
            family_name=family_name,
            summary_type=summary_type,
            period=period,
            start_date=resolved_start,
            end_date=resolved_end,
        )

    rows = _load_personal_category_rows(summary_type, resolved_start, resolved_end)
    return _build_summary_response(
        rows=rows,
        summary_type=summary_type,
        period=period,
        start_date=resolved_start,
        end_date=resolved_end,
        scope="personal",
    )
