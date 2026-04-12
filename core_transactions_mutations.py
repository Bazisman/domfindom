def add_income_with_capital(
    get_connection,
    app_logger,
    invalidate_cache_fn,
    amount,
    category,
    comment,
    date,
    auto_percent,
    capital_account_id,
):
    app_logger.info(
        f"Добавление дохода {amount} с отчислением {auto_percent}% на счёт {capital_account_id}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                ("income", category, amount, comment, date),
            )
            transaction_id = cursor.lastrowid

            if auto_percent > 0 and capital_account_id:
                capital_amount = amount * (auto_percent / 100)
                main_amount = amount - capital_amount
                cursor.execute(
                    'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                    (main_amount,),
                )
                cursor.execute(
                    "SELECT id, name FROM capital_accounts WHERE id = ? AND is_active = 1",
                    (capital_account_id,),
                )
                capital_account = cursor.fetchone()
                if capital_account:
                    app_logger.info(
                        f"Отчисление на счёт капитала: {capital_account['name']} (ID={capital_account['id']})"
                    )
                    cursor.execute(
                        """
                        INSERT INTO transfers (from_account_id, to_account_id, amount, transaction_id, date, comment, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            1,
                            capital_account_id,
                            capital_amount,
                            transaction_id,
                            date,
                            f"Автоотчисление {auto_percent}% от дохода: {comment}",
                        ),
                    )
                    cursor.execute(
                        """
                        UPDATE capital_accounts SET balance = balance + ?, updated_at = datetime("now")
                        WHERE id = ? AND is_active = 1
                        """,
                        (capital_amount, capital_account_id),
                    )
                else:
                    app_logger.warning(
                        f"Счёт капитала ID={capital_account_id} не найден или неактивен"
                    )
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (capital_amount,),
                    )
            else:
                cursor.execute(
                    'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                    (amount,),
                )

            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Доход добавлен: транзакция={transaction_id}")
            return transaction_id
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка добавления дохода: {e}", exc_info=True)
            raise


def add_expense(
    get_connection,
    app_logger,
    invalidate_cache_fn,
    amount,
    category,
    comment,
    date,
):
    app_logger.info(f"Добавление расхода {amount}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                ("expense", category, amount, comment, date),
            )
            transaction_id = cursor.lastrowid
            cursor.execute(
                'UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1',
                (amount,),
            )
            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Расход добавлен: транзакция={transaction_id}")
            return transaction_id
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка добавления расхода: {e}", exc_info=True)
            raise


def delete_transaction(get_connection, app_logger, invalidate_cache_fn, transaction_id):
    app_logger.info(f"Удаление транзакции {transaction_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if not transaction:
                app_logger.warning(f"Транзакция {transaction_id} не найдена")
                return False

            if transaction["type"] == "income":
                app_logger.info("Это доход, ищем связанный перевод...")
                cursor.execute(
                    "SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1",
                    (transaction_id,),
                )
                transfer = cursor.fetchone()
                if transfer:
                    app_logger.info(
                        f"Найден перевод ID={transfer['id']}, amount={transfer['amount']}, from={transfer['from_account_id']}, to={transfer['to_account_id']}"
                    )
                    target_account_id = transfer["to_account_id"]
                    cursor.execute(
                        "SELECT id, is_active FROM capital_accounts WHERE id = ?",
                        (target_account_id,),
                    )
                    target_account = cursor.fetchone()
                    if target_account and target_account["is_active"] == 1:
                        cursor.execute(
                            """
                            UPDATE capital_accounts
                            SET balance = balance - ?, updated_at = datetime("now")
                            WHERE id = ?
                            """,
                            (transfer["amount"], target_account_id),
                        )
                        app_logger.info(
                            f"Возврат {transfer['amount']} на счёт капитала {target_account_id}"
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE accounts
                            SET balance = balance + ?, updated_at = datetime("now")
                            WHERE id = 1
                            """,
                            (transfer["amount"],),
                        )
                        app_logger.info(
                            f"Счёт капитала {target_account_id} неактивен, возврат {transfer['amount']} на основной счёт"
                        )
                    cursor.execute(
                        "UPDATE transfers SET is_active = 0 WHERE id = ?",
                        (transfer["id"],),
                    )
                else:
                    app_logger.warning(
                        f"Перевод для транзакции {transaction_id} НЕ НАЙДЕН! (transaction_id может быть null или перевод уже неактивен)"
                    )
                    cursor.execute(
                        "SELECT id, transaction_id, amount, date, is_active FROM transfers ORDER BY id DESC LIMIT 10"
                    )
                    all_transfers = cursor.fetchall()
                    app_logger.warning(f"Последние переводы: {all_transfers}")

            if transaction["type"] == "income":
                capital_amount = transfer["amount"] if transfer else 0
                main_amount = transaction["amount"] - capital_amount
                app_logger.info(
                    f"Откат баланса: вычитаем {main_amount} (было зачислено) из основного счёта, отчисление было {capital_amount}"
                )
                cursor.execute(
                    "UPDATE accounts SET balance = balance - ? WHERE id = 1",
                    (main_amount,),
                )
            else:
                app_logger.info(
                    f"Откат баланса: прибавляем {transaction['amount']} к основному счёту"
                )
                cursor.execute(
                    "UPDATE accounts SET balance = balance + ? WHERE id = 1",
                    (transaction["amount"],),
                )

            app_logger.info(f"Удаление транзакции {transaction_id} из БД...")
            cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            deleted_rows = cursor.rowcount
            app_logger.info(f"Удалено строк: {deleted_rows}")
            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} удалена")
            return True
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка удаления транзакции {transaction_id}: {e}", exc_info=True)
            return False


def update_transaction(
    get_connection,
    app_logger,
    invalidate_cache_fn,
    transaction_id,
    field,
    value,
):
    allowed_fields = ["category", "amount", "comment", "date", "type"]
    if field not in allowed_fields:
        app_logger.warning(f"Поле {field} нельзя редактировать")
        return False

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            old_transaction = cursor.fetchone()
            if not old_transaction:
                app_logger.warning(f"Транзакция {transaction_id} не найдена")
                return False

            old_type = old_transaction["type"]
            old_amount = old_transaction["amount"]

            if field == "amount":
                new_amount = float(value)
                amount_diff = new_amount - old_amount
                app_logger.info(
                    f"Изменение суммы транзакции {transaction_id}: {old_amount} -> {new_amount} (разница: {amount_diff})"
                )
                if old_type == "income":
                    cursor.execute(
                        "SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1",
                        (transaction_id,),
                    )
                    transfer = cursor.fetchone()
                    if transfer:
                        old_transfer_amount = transfer["amount"]
                        if old_amount > 0:
                            percent = old_transfer_amount / old_amount
                            new_transfer_amount = new_amount * percent
                        else:
                            new_transfer_amount = 0
                        transfer_diff = new_transfer_amount - old_transfer_amount
                        cursor.execute(
                            'UPDATE capital_accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = ?',
                            (transfer_diff, transfer["to_account_id"]),
                        )
                        main_diff = amount_diff - transfer_diff
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                            (main_diff,),
                        )
                        cursor.execute(
                            "UPDATE transfers SET amount = ? WHERE id = ?",
                            (new_transfer_amount, transfer["id"]),
                        )
                        app_logger.info(
                            f"Пересчитан баланс капитала: {transfer_diff}, основной счёт: {main_diff}"
                        )
                    else:
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                            (amount_diff,),
                        )
                        app_logger.info(
                            f"Обновлён баланс основного счёта: {amount_diff}"
                        )
                elif old_type == "expense":
                    cursor.execute(
                        'UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1',
                        (amount_diff,),
                    )
                    app_logger.info(
                        f"Обновлён баланс основного счёта (расход): {-amount_diff}"
                    )
            elif field == "type":
                new_type = value
                app_logger.info(
                    f"Изменение типа транзакции {transaction_id}: {old_type} -> {new_type}"
                )
                if old_type == "income" and new_type == "expense":
                    cursor.execute(
                        "SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1",
                        (transaction_id,),
                    )
                    transfer = cursor.fetchone()
                    if transfer:
                        cursor.execute(
                            'UPDATE capital_accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = ?',
                            (transfer["amount"], transfer["to_account_id"]),
                        )
                        main_amount = old_amount - transfer["amount"]
                    else:
                        main_amount = old_amount
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (main_amount,),
                    )
                    cursor.execute(
                        'UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,),
                    )
                    if transfer:
                        cursor.execute(
                            "UPDATE transfers SET is_active = 0 WHERE id = ?",
                            (transfer["id"],),
                        )
                elif old_type == "expense" and new_type == "expense":
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,),
                    )
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,),
                    )

            cursor.execute(
                f"""
                UPDATE transactions
                SET {field} = ?
                WHERE id = ?
                """,
                (value, transaction_id),
            )
            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} обновлена: {field}={value}")
            return True
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка обновления транзакции {transaction_id}: {e}", exc_info=True)
            return False
