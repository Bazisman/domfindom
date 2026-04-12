def get_main_account(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, balance FROM accounts WHERE id = 1")
        return cursor.fetchone()


def get_reconciliation_sources(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, balance, is_active
            FROM reconciliation_sources
            WHERE is_active = 1
            ORDER BY name
            """
        )
        return cursor.fetchall()


def add_reconciliation_source(get_connection, app_logger, name, balance=0):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reconciliation_sources (name, balance, created_at, updated_at)
            VALUES (?, ?, datetime('now'), datetime('now'))
            """,
            (name, balance),
        )
        conn.commit()
        source_id = cursor.lastrowid
        app_logger.info(f"Добавлен источник сверки: {name}, ID={source_id}")
        return source_id


def update_reconciliation_source(get_connection, source_id, **kwargs):
    allowed_fields = ["name", "balance", "is_active"]
    with get_connection() as conn:
        cursor = conn.cursor()
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(
                    f"""
                    UPDATE reconciliation_sources
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (value, source_id),
                )
        conn.commit()
        return cursor.rowcount > 0


def delete_reconciliation_source(get_connection, source_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reconciliation_sources SET is_active = 0 WHERE id = ?",
            (source_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_total_real_balance(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(balance), 0) FROM reconciliation_sources WHERE is_active = 1"
        )
        return cursor.fetchone()[0] or 0


def get_last_reconciliation(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, real_balance, program_balance, difference, adjustment_transaction_id, created_at
            FROM reconciliations
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        return cursor.fetchone()


def save_reconciliation(
    get_connection,
    app_logger,
    get_last_reconciliation_fn,
    real_balance,
    program_balance,
    difference,
    adjustment_transaction_id=None,
):
    app_logger.info(
        f"Сохранение сверки: real={real_balance}, program={program_balance}, diff={difference}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        last = get_last_reconciliation_fn()
        if last:
            cursor.execute(
                """
                UPDATE reconciliations
                SET real_balance = ?, program_balance = ?, difference = ?,
                    adjustment_transaction_id = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (real_balance, program_balance, difference, adjustment_transaction_id, last["id"]),
            )
            recon_id = last["id"]
            app_logger.info(f"Сверка обновлена: ID={recon_id}")
        else:
            cursor.execute(
                """
                INSERT INTO reconciliations (real_balance, program_balance, difference, adjustment_transaction_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (real_balance, program_balance, difference, adjustment_transaction_id),
            )
            recon_id = cursor.lastrowid
            app_logger.info(f"Сверка создана: ID={recon_id}")
        conn.commit()
        return recon_id


def get_reconciliations_history(get_connection, limit=50):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, real_balance, program_balance, difference,
                   adjustment_transaction_id, created_at, updated_at
            FROM reconciliations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()


def delete_reconciliation(get_connection, app_logger, invalidate_cache_fn, recon_id):
    app_logger.info(f"Удаление сверки ID={recon_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT adjustment_transaction_id FROM reconciliations WHERE id = ?",
            (recon_id,),
        )
        recon = cursor.fetchone()

        if recon and recon["adjustment_transaction_id"]:
            cursor.execute(
                "DELETE FROM transactions WHERE id = ?",
                (recon["adjustment_transaction_id"],),
            )
            cursor.execute(
                "SELECT amount, type FROM transactions WHERE id = ?",
                (recon["adjustment_transaction_id"],),
            )
            trans = cursor.fetchone()
            if trans:
                if trans["type"] == "income":
                    cursor.execute(
                        "UPDATE accounts SET balance = balance - ? WHERE id = 1",
                        (trans["amount"],),
                    )
                else:
                    cursor.execute(
                        "UPDATE accounts SET balance = balance + ? WHERE id = 1",
                        (trans["amount"],),
                    )

        cursor.execute("DELETE FROM reconciliations WHERE id = ?", (recon_id,))
        conn.commit()
        invalidate_cache_fn()
        return cursor.rowcount > 0


def update_reconciliation(
    get_connection,
    app_logger,
    recon_id,
    real_balance,
    program_balance,
    difference,
    adjustment_transaction_id=None,
):
    app_logger.info(f"Обновление сверки ID={recon_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reconciliations
            SET real_balance = ?, program_balance = ?, difference = ?,
                adjustment_transaction_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (real_balance, program_balance, difference, adjustment_transaction_id, recon_id),
        )
        conn.commit()
        return cursor.rowcount > 0
