def get_all_accounts(get_connection, include_inactive=False):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, name, type, balance, currency, is_active FROM accounts"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY type, name"
        cursor.execute(query)
        return cursor.fetchall()


def get_account_balance(get_connection, account_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        if account_id == 1:
            cursor.execute("SELECT balance FROM accounts WHERE id = 1")
            result = cursor.fetchone()
            return result["balance"] if result else 0
        if account_id >= 100:
            cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
            result = cursor.fetchone()
            return result["balance"] if result else 0
        return 0


def update_account_balance(
    get_connection,
    app_logger,
    invalidate_capital_cache_fn,
    account_id,
    amount,
):
    app_logger.debug(f"update_account_balance: account_id={account_id}, amount={amount}")
    with get_connection() as conn:
        cursor = conn.cursor()
        if account_id == 1:
            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance + ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (amount,),
            )
            conn.commit()
            app_logger.info(f"Баланс основного счёта обновлён: изменение={amount}")
            return True
        if account_id >= 100:
            cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
            result = cursor.fetchone()
            if result:
                cursor.execute(
                    """
                    UPDATE capital_accounts
                    SET balance = balance + ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (amount, account_id),
                )
                conn.commit()
                invalidate_capital_cache_fn()
                app_logger.info(
                    f"Баланс счёта капитала {account_id} обновлён: изменение={amount}"
                )
                return True
        app_logger.error(f"Счёт {account_id} не найден")
        return False


def sync_accounts_with_transactions(
    get_connection,
    app_logger,
    get_capital_balance_from_transfers_fn,
):
    app_logger.info("Синхронизация счетов с транзакциями")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE type='income' AND (status = 'actual' OR status IS NULL)"
        )
        total_income = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE type='expense' AND (status = 'actual' OR status IS NULL)"
        )
        total_expense = cursor.fetchone()[0] or 0
        total_balance = total_income - total_expense

        cursor.execute(
            "SELECT SUM(amount) FROM transfers WHERE to_account_id IN (SELECT id FROM capital_accounts) AND is_active = 1"
        )
        total_to_capital = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT SUM(amount) FROM transfers WHERE from_account_id IN (SELECT id FROM capital_accounts) AND is_active = 1"
        )
        total_from_capital = cursor.fetchone()[0] or 0

        main_balance = total_balance - total_to_capital + total_from_capital
        cursor.execute("UPDATE accounts SET balance = ? WHERE type = 'main'", (main_balance,))

        cursor.execute("SELECT id FROM capital_accounts WHERE is_active = 1")
        for row in cursor.fetchall():
            balance = get_capital_balance_from_transfers_fn(row["id"])
            cursor.execute(
                "UPDATE capital_accounts SET balance = ? WHERE id = ?",
                (balance, row["id"]),
            )
        conn.commit()
        app_logger.info(f"Синхронизация завершена: основной счёт={main_balance:.2f}")
        return main_balance
