from datetime import datetime
import calendar


def get_projected_balance(get_connection, get_budget_monthly_limit_fn, app_logger, end_date=None):
    if not end_date:
        today = datetime.now()
        last_day = datetime(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        end_date = last_day.strftime("%Y-%m-%d")

    today = datetime.now().strftime("%Y-%m-%d")
    reference = datetime.strptime(today, "%Y-%m-%d")
    days_in_month = calendar.monthrange(reference.year, reference.month)[1]
    remaining_days_including_today = max(days_in_month - reference.day + 1, 0)
    start_of_month = today[:8] + "01"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM accounts WHERE id = 1")
        current_balance = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE (status = 'actual' OR status IS NULL)
              AND type = 'income'
              AND date >= ?
              AND date <= ?
            """,
            (start_of_month, today),
        )
        actual_income = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE (status = 'actual' OR status IS NULL)
              AND type = 'expense'
              AND date >= ?
              AND date <= ?
            """,
            (start_of_month, today),
        )
        actual_expense = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE status = 'planned' AND type = 'income' AND date <= ?
            """,
            (end_date,),
        )
        planned_income = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE status = 'planned' AND type = 'expense' AND date <= ?
            """,
            (end_date,),
        )
        planned_expense = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT b.amount, b.period, c.name as category_name
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            """
        )
        budgets = cursor.fetchall()

        total_budgets = 0
        current_expenses = 0
        budget_remaining = 0
        for budget in budgets:
            period = budget["period"] if "period" in budget.keys() else "monthly"
            monthly_amount = get_budget_monthly_limit_fn(
                budget["amount"] or 0,
                period,
                today,
            )
            total_budgets += monthly_amount
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
                (budget["category_name"], start_of_month, today),
            )
            spent = cursor.fetchone()[0] or 0
            current_expenses += spent

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0) as planned
                FROM transactions
                WHERE type = 'expense'
                  AND status = 'planned'
                  AND category = ?
                  AND date <= ?
                """,
                (budget["category_name"], end_date),
            )
            planned_category_expense = cursor.fetchone()[0] or 0

            normalized_period = str(period or "monthly").lower()
            if normalized_period == "daily":
                future_budget_expense = float(budget["amount"] or 0) * remaining_days_including_today
                budget_remaining += max(future_budget_expense - planned_category_expense, 0.0)
            else:
                budget_remaining += max(monthly_amount - spent - planned_category_expense, 0.0)

        combined_pending_expense = planned_expense + budget_remaining
        combined_executed_expense = actual_expense
        projected_balance = actual_income + planned_income - actual_expense - planned_expense - budget_remaining

        app_logger.debug(
            "Forecast calc: current=%s planned_income=%s planned_expense=%s "
            "executed_planned_income=%s executed_planned_expense=%s total_budgets=%s "
            "current_expenses=%s budget_remaining=%s combined_pending_expense=%s "
            "combined_executed_expense=%s projected=%s end_date=%s",
            round(current_balance, 2),
            round(planned_income, 2),
            round(planned_expense, 2),
            round(actual_income, 2),
            round(actual_expense, 2),
            round(total_budgets, 2),
            round(current_expenses, 2),
            round(budget_remaining, 2),
            round(combined_pending_expense, 2),
            round(combined_executed_expense, 2),
            round(projected_balance, 2),
            end_date,
        )

        return {
            "current_balance": round(current_balance, 2),
            "planned_income": round(planned_income, 2),
            "planned_expense": round(planned_expense, 2),
            "executed_planned_income": round(actual_income, 2),
            "executed_planned_expense": round(actual_expense, 2),
            "monthly_budget": round(total_budgets, 2),
            "total_budgets": round(total_budgets, 2),
            "current_expenses": round(current_expenses, 2),
            "budget_remaining": round(budget_remaining, 2),
            "combined_pending_expense": round(combined_pending_expense, 2),
            "combined_executed_expense": round(combined_executed_expense, 2),
            "projected": round(projected_balance, 2),
            "projected_balance": round(projected_balance, 2),
            "end_date": end_date,
        }
