def get_expenses_by_category(get_connection, start_date=None, end_date=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'expense' AND (status = 'actual' OR status IS NULL)
        """
        params = []
        if start_date and end_date:
            query += " AND date BETWEEN ? AND ?"
            params = [start_date, end_date]
        elif start_date:
            query += " AND date >= ?"
            params = [start_date]
        elif end_date:
            query += " AND date <= ?"
            params = [end_date]
        query += " GROUP BY category ORDER BY total DESC"
        cursor.execute(query, params)
        return cursor.fetchall()


def get_income_by_category(get_connection, start_date=None, end_date=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'income' AND (status = 'actual' OR status IS NULL)
        """
        params = []
        if start_date and end_date:
            query += " AND date BETWEEN ? AND ?"
            params = [start_date, end_date]
        elif start_date:
            query += " AND date >= ?"
            params = [start_date]
        elif end_date:
            query += " AND date <= ?"
            params = [end_date]
        query += " GROUP BY category ORDER BY total DESC"
        cursor.execute(query, params)
        return cursor.fetchall()


def get_capital_contributions_for_period(get_connection, start_date=None, end_date=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE is_active = 1"
        params = []
        if start_date and end_date:
            query += " AND date BETWEEN ? AND ?"
            params = [start_date, end_date]
        elif start_date:
            query += " AND date >= ?"
            params = [start_date]
        elif end_date:
            query += " AND date <= ?"
            params = [end_date]
        cursor.execute(query, params)
        return cursor.fetchone()[0] or 0


def get_available_periods(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT strftime('%Y-%m', date) as month
            FROM transactions
            ORDER BY month DESC
            """
        )
        return [row["month"] for row in cursor.fetchall()]
