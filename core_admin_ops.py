from datetime import datetime


def reset_to_factory(get_connection, app_logger, db_name, init_db_fn):
    import os
    import gc
    import time

    app_logger.warning("=" * 60)
    app_logger.warning("ВЫПОЛНЯЕТСЯ СБРОС ДО ЗАВОДСКИХ НАСТРОЕК")
    app_logger.warning("=" * 60)
    gc.collect()
    time.sleep(0.5)
    if os.path.exists(db_name):
        try:
            os.remove(db_name)
            app_logger.info(f"Файл {db_name} удалён")
        except PermissionError:
            app_logger.warning("Файл занят, пробуем ещё раз...")
            time.sleep(1)
            os.remove(db_name)
            app_logger.info(f"Файл {db_name} удалён")
        except Exception as e:
            app_logger.error(f"Не удалось удалить {db_name}: {e}")
            raise
    init_db_fn()
    app_logger.info("База данных сброшена до заводских настроек")
    app_logger.warning("=" * 60)
    return True


def create_indexes_internal(cursor, app_logger):
    indexes = [
        ("idx_transactions_date", "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)"),
        ("idx_transactions_type", "CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)"),
        ("idx_transactions_category", "CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)"),
        ("idx_transfers_from", "CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers(from_account_id)"),
        ("idx_transfers_to", "CREATE INDEX IF NOT EXISTS idx_transfers_to ON transfers(to_account_id)"),
        ("idx_transfers_active", "CREATE INDEX IF NOT EXISTS idx_transfers_active ON transfers(is_active)"),
        ("idx_transfers_transaction", "CREATE INDEX IF NOT EXISTS idx_transfers_transaction ON transfers(transaction_id)"),
        ("idx_capital_accounts_active", "CREATE INDEX IF NOT EXISTS idx_capital_accounts_active ON capital_accounts(is_active)"),
        ("idx_categories_type", "CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type)"),
    ]
    for name, sql in indexes:
        try:
            cursor.execute(sql)
            app_logger.debug(f"Индекс {name} создан/проверен")
        except Exception as e:
            app_logger.warning(f"Не удалось создать индекс {name}: {e}")


def create_indexes(get_connection, app_logger, create_indexes_internal_fn):
    app_logger.info("Создание индексов для оптимизации...")
    with get_connection() as conn:
        cursor = conn.cursor()
        create_indexes_internal_fn(cursor)
        conn.commit()
    app_logger.info("Индексы созданы/проверены")


def add_transfer_record(get_connection, app_logger, from_account_id, to_account_id, amount, date=None, comment=""):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    app_logger.debug(f"Добавление записи о переводе: {amount} с {from_account_id} на {to_account_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transfers (from_account_id, to_account_id, amount, date, comment, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (from_account_id, to_account_id, amount, date, comment),
        )
        conn.commit()
        app_logger.info(f"Запись о переводе добавлена, ID: {cursor.lastrowid}")


def transfer_money(get_connection, app_logger, from_account_id, to_account_id, amount, date=None, comment=""):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    app_logger.info(f"Выполняется перевод: {amount} со счёта {from_account_id} на {to_account_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("SELECT balance FROM accounts WHERE id = ?", (from_account_id,))
            from_balance = cursor.fetchone()
            if from_balance and from_balance["balance"] < amount:
                app_logger.warning(f"Недостаточно средств: {from_balance['balance']} < {amount}")
                raise ValueError("Недостаточно средств")
            cursor.execute(
                """
                UPDATE accounts SET balance = balance - ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (amount, from_account_id),
            )
            cursor.execute(
                """
                UPDATE accounts SET balance = balance + ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (amount, to_account_id),
            )
            cursor.execute(
                """
                INSERT INTO transfers (from_account_id, to_account_id, amount, date, comment, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (from_account_id, to_account_id, amount, date, comment),
            )
            conn.commit()
            app_logger.info(f"Перевод выполнен успешно: {amount}")
            return True
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка перевода: {e}", exc_info=True)
            return False
