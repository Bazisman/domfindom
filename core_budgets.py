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
            period = budget["period"] if "period" in budget.keys() else "monthly"
            normalized_period = normalize_budget_period(period)
            if normalized_period == "daily":
                budget_amount = float(budget["budget_amount"] or 0) * today.day
            else:
                budget_amount = get_budget_monthly_limit_fn(
                    budget["budget_amount"] or 0,
                    period,
                )
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
            remaining = budget_amount - spent
            percent = (spent / budget_amount * 100) if budget_amount > 0 else 0
            result.append(
                {
                    "category_id": budget["category_id"],
                    "category_name": budget["category_name"],
                    "icon": budget["icon"],
                    "color": budget["color"],
                    "budget_amount": round(budget_amount, 2),
                    "spent": round(spent, 2),
                    "remaining": round(remaining, 2),
                    "percent": round(percent, 1),
                    "over_budget": remaining < 0,
                }
            )
        if category_id is not None:
            result = [item for item in result if item["category_id"] == category_id]
        return result
