from core_money import (
    MONEY_SOURCE_CASHLESS,
    account_id_for_money_source,
    normalize_money_source,
)


def _row_value(row, key, default=None):
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _transaction_money_source(row):
    return normalize_money_source(_row_value(row, "money_source", MONEY_SOURCE_CASHLESS))


def _adjust_account(cursor, account_id, amount):
    if int(account_id) < 100:
        cursor.execute(
            """
            UPDATE accounts
            SET balance = balance + ?, updated_at = datetime('now')
            WHERE id = ? AND is_active = 1
            """,
            (amount, account_id),
        )
        return cursor.rowcount > 0

    cursor.execute(
        """
        UPDATE capital_accounts
        SET balance = balance + ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (amount, account_id),
    )
    return cursor.rowcount > 0


def _active_transfer(cursor, transaction_id):
    cursor.execute(
        "SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1",
        (transaction_id,),
    )
    return cursor.fetchone()


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
    money_source=MONEY_SOURCE_CASHLESS,
):
    money_source = normalize_money_source(money_source)
    source_account_id = account_id_for_money_source(money_source)
    app_logger.info(
        f"Добавление дохода {amount} ({money_source}) с отчислением {auto_percent}% на счёт {capital_account_id}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, money_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                ("income", category, amount, comment, date, money_source),
            )
            transaction_id = cursor.lastrowid

            if auto_percent > 0 and capital_account_id:
                capital_amount = amount * (auto_percent / 100)
                main_amount = amount - capital_amount
                cursor.execute(
                    "SELECT id, name FROM capital_accounts WHERE id = ? AND is_active = 1",
                    (capital_account_id,),
                )
                capital_account = cursor.fetchone()
                if capital_account:
                    _adjust_account(cursor, source_account_id, main_amount)
                    app_logger.info(
                        f"Отчисление на счёт капитала: {capital_account['name']} (ID={capital_account['id']})"
                    )
                    cursor.execute(
                        """
                        INSERT INTO transfers (from_account_id, to_account_id, amount, transaction_id, date, comment, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            source_account_id,
                            capital_account_id,
                            capital_amount,
                            transaction_id,
                            date,
                            f"Автоотчисление {auto_percent}% от дохода: {comment}",
                        ),
                    )
                    _adjust_account(cursor, capital_account_id, capital_amount)
                else:
                    app_logger.warning(
                        f"Счёт капитала ID={capital_account_id} не найден или неактивен"
                    )
                    _adjust_account(cursor, source_account_id, amount)
            else:
                _adjust_account(cursor, source_account_id, amount)

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
    money_source=MONEY_SOURCE_CASHLESS,
):
    money_source = normalize_money_source(money_source)
    source_account_id = account_id_for_money_source(money_source)
    app_logger.info(f"Добавление расхода {amount} ({money_source})")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, money_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                ("expense", category, amount, comment, date, money_source),
            )
            transaction_id = cursor.lastrowid
            _adjust_account(cursor, source_account_id, -amount)
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

            status = _row_value(transaction, "status", "actual") or "actual"
            if status != "planned":
                source_account_id = account_id_for_money_source(_transaction_money_source(transaction))
                if transaction["type"] == "income":
                    transfer = _active_transfer(cursor, transaction_id)
                    capital_amount = 0.0
                    if transfer:
                        capital_amount = float(transfer["amount"] or 0)
                        _adjust_account(cursor, int(transfer["to_account_id"]), -capital_amount)
                        cursor.execute("UPDATE transfers SET is_active = 0 WHERE id = ?", (transfer["id"],))
                    main_amount = float(transaction["amount"] or 0) - capital_amount
                    _adjust_account(cursor, source_account_id, -main_amount)
                    app_logger.info(
                        f"Откат дохода: источник={source_account_id}, сумма={main_amount}, капитал={capital_amount}"
                    )
                else:
                    _adjust_account(cursor, source_account_id, float(transaction["amount"] or 0))
                    app_logger.info(
                        f"Откат расхода: источник={source_account_id}, сумма={transaction['amount']}"
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
    return update_transaction_fields(
        get_connection,
        app_logger,
        invalidate_cache_fn,
        transaction_id,
        **{field: value},
    )


def update_transaction_fields(
    get_connection,
    app_logger,
    invalidate_cache_fn,
    transaction_id,
    **kwargs,
):
    allowed_fields = {"category", "amount", "comment", "date", "type", "money_source"}
    update_data = {key: value for key, value in kwargs.items() if key in allowed_fields}
    if not update_data:
        app_logger.warning(f"Нет разрешённых полей для редактирования транзакции {transaction_id}")
        return False
    if "money_source" in update_data:
        update_data["money_source"] = normalize_money_source(update_data["money_source"])
    if "amount" in update_data:
        update_data["amount"] = float(update_data["amount"])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            old_transaction = cursor.fetchone()
            if not old_transaction:
                app_logger.warning(f"Транзакция {transaction_id} не найдена")
                return False

            status = _row_value(old_transaction, "status", "actual") or "actual"
            old_type = old_transaction["type"]
            old_amount = float(old_transaction["amount"] or 0)
            old_source = _transaction_money_source(old_transaction)
            new_type = update_data.get("type", old_type)
            new_amount = float(update_data.get("amount", old_amount))
            new_source = normalize_money_source(update_data.get("money_source", old_source))
            balance_changed = any(field in update_data for field in ("type", "amount", "money_source"))

            if status != "planned" and balance_changed:
                old_source_account_id = account_id_for_money_source(old_source)
                new_source_account_id = account_id_for_money_source(new_source)
                transfer = _active_transfer(cursor, transaction_id)
                transfer_target_id = int(transfer["to_account_id"]) if transfer else None
                transfer_amount = float(transfer["amount"] or 0) if transfer else 0.0
                transfer_percent = (transfer_amount / old_amount) if transfer and old_amount > 0 else 0.0

                if old_type == "income":
                    _adjust_account(cursor, old_source_account_id, -(old_amount - transfer_amount))
                    if transfer:
                        _adjust_account(cursor, transfer_target_id, -transfer_amount)
                        cursor.execute("UPDATE transfers SET is_active = 0 WHERE id = ?", (transfer["id"],))
                else:
                    _adjust_account(cursor, old_source_account_id, old_amount)

                if new_type == "income":
                    new_transfer_amount = new_amount * transfer_percent if transfer_target_id else 0.0
                    _adjust_account(cursor, new_source_account_id, new_amount - new_transfer_amount)
                    if transfer_target_id and new_transfer_amount > 0:
                        new_date = str(update_data.get("date", old_transaction["date"]))
                        new_comment = str(update_data.get("comment", old_transaction["comment"] or ""))
                        cursor.execute(
                            """
                            INSERT INTO transfers (
                                from_account_id, to_account_id, amount,
                                transaction_id, date, comment, is_active
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                            """,
                            (
                                new_source_account_id,
                                transfer_target_id,
                                new_transfer_amount,
                                transaction_id,
                                new_date,
                                f"Автоотчисление от дохода: {new_comment}",
                            ),
                        )
                        _adjust_account(cursor, transfer_target_id, new_transfer_amount)
                else:
                    _adjust_account(cursor, new_source_account_id, -new_amount)
            elif status != "planned":
                transfer = _active_transfer(cursor, transaction_id)
                if transfer:
                    if "date" in update_data:
                        cursor.execute(
                            "UPDATE transfers SET date = ? WHERE id = ?",
                            (update_data["date"], transfer["id"]),
                        )
                    if "comment" in update_data:
                        cursor.execute(
                            "UPDATE transfers SET comment = ? WHERE id = ?",
                            (f"Автоотчисление от дохода: {update_data['comment']}", transfer["id"]),
                        )

            set_clause = ", ".join(f"{field} = ?" for field in update_data)
            values = [update_data[field] for field in update_data]
            values.append(transaction_id)
            cursor.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = ?",
                values,
            )
            invalidate_cache_fn()
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} обновлена: {update_data}")
            return True
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка обновления транзакции {transaction_id}: {e}", exc_info=True)
            return False
