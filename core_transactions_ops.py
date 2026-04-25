from core_money import MONEY_SOURCE_CASHLESS, normalize_money_source


def add_planned_transaction(
    get_connection,
    invalidate_cache_fn,
    app_logger,
    transaction_type,
    category,
    amount,
    comment,
    date,
    template_id=None,
    money_source=MONEY_SOURCE_CASHLESS,
):
    app_logger.info(
        f"Добавление planned-транзакции: type={transaction_type}, amount={amount}, date={date}, template_id={template_id}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id, money_source, created_at)
                VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, datetime('now'))
            """,
            (
                transaction_type,
                category,
                amount,
                comment,
                date,
                template_id,
                normalize_money_source(money_source),
            ),
        )
        conn.commit()
        transaction_id = cursor.lastrowid
        invalidate_cache_fn()
        return transaction_id


def assign_template_to_planned_transaction(
    get_connection,
    invalidate_cache_fn,
    transaction_id,
    template_id,
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                UPDATE transactions
                SET template_id = ?
                WHERE id = ? AND status = 'planned'
            """,
            (template_id, transaction_id),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            invalidate_cache_fn()
        return updated


def get_balance(get_connection, get_cached_fn, force_update=False):
    def fetch_balance():
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(balance), 0) FROM accounts WHERE id IN (1, 2) AND is_active = 1"
            )
            main_balance = cursor.fetchone()[0] or 0
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income' AND (status = 'actual' OR status IS NULL)"
            )
            income = cursor.fetchone()[0] or 0
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND (status = 'actual' OR status IS NULL)"
            )
            expense = cursor.fetchone()[0] or 0
            return round(main_balance, 2), round(income, 2), round(expense, 2)

    return get_cached_fn("balance", fetch_balance, force_update)


def get_last_transactions(get_connection, limit=10, offset=0):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, date, type, category, amount, comment, money_source, status, template_id
            FROM transactions
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return cursor.fetchall()


def get_all_transactions(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, date, type, category, amount, comment, money_source, status, template_id
            FROM transactions
            ORDER BY date DESC, id DESC
            """
        )
        return cursor.fetchall()


def get_transactions_count(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        return cursor.fetchone()[0]


def get_transactions_by_period(get_connection, start_date, end_date, limit=500, offset=0):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, date, type, category, amount, comment, money_source, status, template_id
            FROM transactions
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (start_date, end_date, limit, offset),
        )
        return cursor.fetchall()


def get_transaction_by_id(get_connection, transaction_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, date, type, category, amount, comment, money_source, status, template_id
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        return cursor.fetchone()
