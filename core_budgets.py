import calendar
from datetime import date, datetime


def normalize_budget_period(period):
    normalized = (period or "monthly").lower()
    if normalized in {"daily", "weekly", "monthly", "yearly"}:
        return normalized
    return "monthly"


def _coerce_reference_date(reference_date=None):
    if reference_date is None:
        return datetime.now()
    if isinstance(reference_date, datetime):
        return reference_date
    if isinstance(reference_date, date):
        return datetime.combine(reference_date, datetime.min.time())
    if isinstance(reference_date, str):
        return datetime.strptime(reference_date[:10], "%Y-%m-%d")
    return datetime.now()


def get_budget_monthly_limit(amount, period, reference_date=None):
    normalized_period = normalize_budget_period(period)
    if normalized_period == "daily":
        reference = _coerce_reference_date(reference_date)
        return amount * calendar.monthrange(reference.year, reference.month)[1]
    if normalized_period == "weekly":
        return amount * 4
    if normalized_period == "yearly":
        return amount / 12
    return amount


def get_budget_status_metrics(amount, period, spent, reference_date=None):
    reference = _coerce_reference_date(reference_date)
    normalized_period = normalize_budget_period(period)
    budget_amount = float(get_budget_monthly_limit(amount or 0, period, reference))
    spent_value = float(spent or 0)
    plan_remaining = budget_amount - spent_value
    percent = (spent_value / budget_amount * 100) if budget_amount > 0 else 0.0
    forecast_remaining = None
    forecast_mode = "none"

    if normalized_period == "daily":
        days_in_month = calendar.monthrange(reference.year, reference.month)[1]
        remaining_days = max(days_in_month - reference.day, 0)
        future_limit = float(amount or 0) * remaining_days
        forecast_remaining = max(budget_amount - (spent_value + future_limit), 0.0)
        forecast_mode = "daily_tempo"

    return {
        "budget_amount": round(budget_amount, 2),
        "spent": round(spent_value, 2),
        "remaining": round(plan_remaining, 2),
        "plan_remaining": round(plan_remaining, 2),
        "forecast_remaining": round(forecast_remaining, 2) if forecast_remaining is not None else None,
        "forecast_mode": forecast_mode,
        "percent": round(percent, 1),
        "over_budget": plan_remaining < 0,
    }


def set_budget(get_connection, app_logger, category_id, amount, period="monthly"):
    app_logger.info(
        f"Установка бюджета: category_id={category_id}, amount={amount}, period={period}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE budgets SET amount = ?, period = ?
            WHERE category_id = ?
            """,
            (amount, period, category_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO budgets (category_id, amount, period)
                VALUES (?, ?, ?)
                """,
                (category_id, amount, period),
            )
        conn.commit()
        return True


def get_budgets(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT b.id, b.category_id, c.name as category, b.amount, b.period
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            ORDER BY c.name
            """
        )
        return cursor.fetchall()


def delete_budget(get_connection, app_logger, budget_id):
    app_logger.info(f"Удаление бюджета ID={budget_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_budget_report(get_connection, get_budgets_fn, get_budget_monthly_limit_fn, month=None):
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    start_date = month + "-01"
    year, month_num = map(int, month.split("-"))
    if month_num == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month_num + 1:02d}-01"

    with get_connection() as conn:
        cursor = conn.cursor()
        budgets = get_budgets_fn()
        report = []
        for budget in budgets:
            category_id = budget["category_id"]
            category_name = budget["category"]
            budget_amount = get_budget_monthly_limit_fn(
                budget["amount"] or 0,
                budget["period"] if "period" in budget.keys() else "monthly",
                start_date,
            )
            cursor.execute(
                """
                SELECT SUM(amount) as total
                FROM transactions
                WHERE type = 'expense'
                AND category = ?
                AND (status = 'actual' OR status IS NULL)
                AND date >= ? AND date < ?
                """,
                (category_name, start_date, end_date),
            )
            spent = cursor.fetchone()["total"] or 0
            percent = (spent / budget_amount * 100) if budget_amount > 0 else 0
            report.append(
                {
                    "category_id": category_id,
                    "category": category_name,
                    "budget": budget_amount,
                    "spent": spent,
                    "remaining": budget_amount - spent,
                    "percent": percent,
                    "status": "OK" if spent <= budget_amount else "ПРЕВЫШЕНИЕ",
                }
            )
        return report


def check_budget(get_connection, get_budget_monthly_limit_fn, category_id, amount, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT amount, period FROM budgets
            WHERE category_id = ?
            """,
            (category_id,),
        )
        budget = cursor.fetchone()
        if not budget:
            return None

        budget_amount = get_budget_monthly_limit_fn(
            budget["amount"] or 0,
            budget["period"] if "period" in budget.keys() else "monthly",
            date,
        )
        start_date = date[:8] + "01"
        cursor.execute(
            """
            SELECT SUM(amount) as total
            FROM transactions
            WHERE type = 'expense'
            AND category = (SELECT name FROM categories WHERE id = ?)
            AND (status = 'actual' OR status IS NULL)
            AND date >= ?
            """,
            (category_id, start_date),
        )
        spent = cursor.fetchone()["total"] or 0
        total_with_new = spent + amount
        return (total_with_new > budget_amount, spent, budget_amount)


def get_budget_status(get_connection, get_budget_monthly_limit_fn, category_id: int = None):
    today = datetime.now()
    start_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    end_of_month = today.strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT b.id, b.category_id, c.name as category_name, c.icon, c.color, b.amount as budget_amount, b.period
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            """
        )
        budgets = cursor.fetchall()
        result = []
        for budget in budgets:
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0) as spent
                FROM transactions
                WHERE type = 'expense'
                  AND category = ?
                  AND date >= ?
                  AND date <= ?
                  AND (status = 'actual' OR status IS NULL)
                """,
                (budget["category_name"], start_of_month, end_of_month),
            )
            spent = cursor.fetchone()[0] or 0
            metrics = get_budget_status_metrics(
                budget["budget_amount"] or 0,
                budget["period"] if "period" in budget.keys() else "monthly",
                spent,
                today,
            )
            result.append(
                {
                    "category_id": budget["category_id"],
                    "category_name": budget["category_name"],
                    "icon": budget["icon"],
                    "color": budget["color"],
                    **metrics,
                }
            )
        if category_id is not None:
            result = [item for item in result if item["category_id"] == category_id]
        return result
