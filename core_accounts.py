from core_money import CASH_ACCOUNT_ID, CASHLESS_ACCOUNT_ID, DAILY_ACCOUNT_IDS


def get_all_accounts(get_connection, include_inactive=False):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, name, type, balance, currency, is_active FROM accounts"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += """
            ORDER BY
                CASE id
                    WHEN 1 THEN 1
                    WHEN 2 THEN 2
                    ELSE 3
                END,
                name
        """
        cursor.execute(query)
        return cursor.fetchall()


def get_account_balance(get_connection, account_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        if account_id < 100:
            cursor.execute("SELECT balance FROM accounts WHERE id = ? AND is_active = 1", (account_id,))
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
        if account_id < 100:
            cursor.execute(
                """
                UPDATE accounts
                SET balance = balance + ?, updated_at = datetime('now')
                WHERE id = ? AND is_active = 1
                """,
                (amount, account_id),
            )
            if cursor.rowcount > 0:
                conn.commit()
                app_logger.info(
                    f"Баланс повседневного счёта {account_id} обновлён: изменение={amount}"
                )
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
        balances = {CASHLESS_ACCOUNT_ID: 0.0, CASH_ACCOUNT_ID: 0.0}

        cursor.execute(
            """
            SELECT money_source, type, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE status = 'actual' OR status IS NULL
            GROUP BY money_source, type
            """
        )
        for row in cursor.fetchall():
            account_id = CASH_ACCOUNT_ID if row["money_source"] == "cash" else CASHLESS_ACCOUNT_ID
            direction = 1 if row["type"] == "income" else -1
            balances[account_id] += direction * float(row["total"] or 0)

        cursor.execute("SELECT from_account_id, to_account_id, amount FROM transfers WHERE is_active = 1")
        for row in cursor.fetchall():
            amount = float(row["amount"] or 0)
            from_id = int(row["from_account_id"])
            to_id = int(row["to_account_id"])
            if from_id in DAILY_ACCOUNT_IDS:
                balances[from_id] -= amount
            if to_id in DAILY_ACCOUNT_IDS:
                balances[to_id] += amount

        cursor.execute(
            "UPDATE accounts SET balance = ?, updated_at = datetime('now') WHERE id = ?",
            (balances[CASHLESS_ACCOUNT_ID], CASHLESS_ACCOUNT_ID),
        )
        cursor.execute(
            "UPDATE accounts SET balance = ?, updated_at = datetime('now') WHERE id = ?",
            (balances[CASH_ACCOUNT_ID], CASH_ACCOUNT_ID),
        )

        cursor.execute("SELECT id FROM capital_accounts WHERE is_active = 1")
        for row in cursor.fetchall():
            balance = get_capital_balance_from_transfers_fn(row["id"])
            cursor.execute(
                "UPDATE capital_accounts SET balance = ? WHERE id = ?",
                (balance, row["id"]),
            )
        conn.commit()
        daily_total = balances[CASHLESS_ACCOUNT_ID] + balances[CASH_ACCOUNT_ID]
        app_logger.info(f"Синхронизация завершена: повседневные деньги={daily_total:.2f}")
        return daily_total
