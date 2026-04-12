def execute_planned_transaction(
    get_connection,
    app_logger,
    invalidate_cache_fn,
    transaction_id,
    auto_percent=0,
    capital_account_id=None,
):
    app_logger.info(
        f"Исполнение плановой транзакции ID={transaction_id}, "
        f"auto_percent={auto_percent}, capital_account_id={capital_account_id}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute(
                """
                SELECT id, type, category, amount, comment, date, template_id
                FROM transactions
                WHERE id = ? AND status = 'planned'
                """,
                (transaction_id,),
            )
            planned = cursor.fetchone()
            if not planned:
                app_logger.warning(f"Плановая транзакция {transaction_id} не найдена")
                return False

            cursor.execute(
                """
                UPDATE transactions
                SET status = 'actual', executed_at = datetime('now')
                WHERE id = ?
                """,
                (transaction_id,),
            )

            if planned["type"] == "income":
                apply_auto_capital = auto_percent > 0 and capital_account_id and planned["category"] != "Остаток"
                if apply_auto_capital:
                    capital_amount = planned["amount"] * (auto_percent / 100)
                    main_amount = planned["amount"] - capital_amount
                    cursor.execute(
                        "SELECT id, name FROM capital_accounts WHERE id = ? AND is_active = 1",
                        (capital_account_id,),
                    )
                    capital_account = cursor.fetchone()
                    if capital_account:
                        cursor.execute(
                            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
                            (main_amount,),
                        )
                        cursor.execute(
                            """
                            INSERT INTO transfers (
                                from_account_id, to_account_id, amount,
                                transaction_id, date, comment, is_active
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                            """,
                            (
                                1,
                                capital_account_id,
                                capital_amount,
                                transaction_id,
                                planned["date"],
                                f"Автоотчисление {auto_percent}% от планового дохода: {planned['comment']}",
                            ),
                        )
                        cursor.execute(
                            """
                            UPDATE capital_accounts
                            SET balance = balance + ?, updated_at = datetime("now")
                            WHERE id = ? AND is_active = 1
                            """,
                            (capital_amount, capital_account_id),
                        )
                    else:
                        app_logger.warning(
                            f"Счёт капитала ID={capital_account_id} не найден или неактивен, "
                            "плановый доход будет зачислен полностью на основной счёт"
                        )
                        cursor.execute(
                            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
                            (planned["amount"],),
                        )
                else:
                    cursor.execute(
                        "UPDATE accounts SET balance = balance + ? WHERE id = 1",
                        (planned["amount"],),
                    )
            else:
                cursor.execute(
                    "UPDATE accounts SET balance = balance - ? WHERE id = 1",
                    (planned["amount"],),
                )

            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} исполнена")
            return True
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка исполнения транзакции {transaction_id}: {e}", exc_info=True)
            return False


def execute_all_planned_transactions(
    app_logger,
    get_planned_transactions_due_fn,
    execute_planned_transaction_fn,
    auto_percent=0,
    capital_account_id=None,
):
    app_logger.info(
        "Исполнение просроченных плановых транзакций "
        f"(auto_percent={auto_percent}, capital_account_id={capital_account_id})"
    )
    due_transactions = get_planned_transactions_due_fn()
    count = 0
    for trans in due_transactions:
        if execute_planned_transaction_fn(trans["id"], auto_percent, capital_account_id):
            count += 1
    app_logger.info(f"Исполнено {count} плановых транзакций")
    return count
