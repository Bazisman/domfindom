def get_capital_accounts(
    get_connection,
    cache,
    get_cached_fn,
    cache_ttl_long,
    include_inactive=False,
):
    def fetch_capital_accounts():
        with get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, name, balance, currency, icon, color, purpose, counts_as_cushion, is_active, is_default
                FROM capital_accounts
            """
            if not include_inactive:
                query += " WHERE is_active = 1"
            query += " ORDER BY is_default DESC, name"
            cursor.execute(query)
            return cursor.fetchall()

    cache_key = f"capital_accounts_{include_inactive}"
    return get_cached_fn(cache_key, fetch_capital_accounts, ttl=cache_ttl_long)


def get_default_capital_account(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, balance, icon, color, purpose, counts_as_cushion
            FROM capital_accounts
            WHERE is_default = 1 AND is_active = 1
            LIMIT 1
            """
        )
        return cursor.fetchone()


def invalidate_capital_cache(cache):
    for key in list(cache.keys()):
        if key.split("::", 1)[-1].startswith("capital_accounts_"):
            cache[key]["timestamp"] = 0


def set_default_capital_account(
    get_connection,
    app_logger,
    invalidate_capital_cache_fn,
    account_id,
):
    app_logger.info(f"Установка основного счёта капитала: ID={account_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE capital_accounts SET is_default = 0")
        cursor.execute("UPDATE capital_accounts SET is_default = 1 WHERE id = ?", (account_id,))
        conn.commit()
        invalidate_capital_cache_fn()
        app_logger.info(f"Основной счёт капитала установлен: ID={account_id}")
        return cursor.rowcount > 0


def add_capital_account(
    get_connection,
    app_logger,
    invalidate_capital_cache_fn,
    name,
    balance=0,
    icon="💰",
    color="#ff9800",
    purpose="cushion",
    counts_as_cushion=None,
):
    purpose = "investment" if str(purpose or "").strip() == "investment" else "cushion"
    if counts_as_cushion is None:
        counts_as_cushion = purpose == "cushion"
    app_logger.info(f"Добавление счёта капитала: {name}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM capital_accounts WHERE is_active = 1")
        count = cursor.fetchone()[0]
        is_default = 1 if count == 0 else 0
        cursor.execute(
            """
            INSERT INTO capital_accounts (name, balance, icon, color, purpose, counts_as_cushion, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (name, balance, icon, color, purpose, 1 if counts_as_cushion else 0, is_default),
        )
        conn.commit()
        new_id = cursor.lastrowid
        invalidate_capital_cache_fn()
        app_logger.info(
            f"Счёт капитала добавлен: {name}, ID={new_id}, основной={is_default}"
        )
        return new_id


def update_capital_account(
    get_connection,
    app_logger,
    invalidate_capital_cache_fn,
    account_id,
    **kwargs,
):
    allowed_fields = ["name", "balance", "icon", "color", "purpose", "counts_as_cushion", "is_active"]
    with get_connection() as conn:
        cursor = conn.cursor()
        applied_updates = False
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(
                    f"""
                    UPDATE capital_accounts
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (value, account_id),
                )
                applied_updates = applied_updates or (cursor.rowcount > 0)
        conn.commit()
        if applied_updates:
            invalidate_capital_cache_fn()
        app_logger.debug(f"Обновлён счёт капитала ID={account_id}: {kwargs}")
        return applied_updates


def delete_capital_account(
    get_connection,
    app_logger,
    invalidate_capital_cache_fn,
    account_id,
):
    if account_id == 1:
        app_logger.error("Нельзя удалить основной счёт!")
        return False

    app_logger.info(f"Деактивация счёта капитала ID={account_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE transfers SET is_active = 0
            WHERE to_account_id = ? OR from_account_id = ?
            """,
            (account_id, account_id),
        )
        cursor.execute(
            "UPDATE capital_accounts SET is_active = 0 WHERE id = ?",
            (account_id,),
        )
        deactivated = cursor.rowcount > 0

        cursor.execute("SELECT is_default FROM capital_accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        if row and row["is_default"] == 1:
            cursor.execute(
                "SELECT id FROM capital_accounts WHERE is_active = 1 AND id != ? LIMIT 1",
                (account_id,),
            )
            new_default = cursor.fetchone()
            if new_default:
                cursor.execute(
                    "UPDATE capital_accounts SET is_default = 1 WHERE id = ?",
                    (new_default["id"],),
                )
                app_logger.info(
                    f"Новый основной счёт капитала: ID={new_default['id']}"
                )

        conn.commit()
        invalidate_capital_cache_fn()
        return deactivated


def get_total_capital(get_connection):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(balance) FROM capital_accounts WHERE is_active = 1")
        return cursor.fetchone()[0] or 0


def get_capital_balance_from_transfers(get_connection, account_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE to_account_id = ? AND is_active = 1",
            (account_id,),
        )
        incoming = cursor.fetchone()[0] or 0
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE from_account_id = ? AND is_active = 1",
            (account_id,),
        )
        outgoing = cursor.fetchone()[0] or 0
        return incoming - outgoing


def get_capital_balance(get_connection, account_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
        result = cursor.fetchone()
        return result["balance"] if result else 0


def get_transfers_history(get_connection, app_logger, account_id=None, limit=100, include_inactive=False):
    with get_connection() as conn:
        cursor = conn.cursor()
        active_filter = "" if include_inactive else "AND t.is_active = 1"
        if account_id:
            cursor.execute(
                f"""
                SELECT
                    t.id, t.from_account_id, t.to_account_id, t.amount, t.date, t.comment, t.is_active,
                    COALESCE(a1.name, ca1.name, 'Неизвестный') as from_name,
                    COALESCE(a2.name, ca2.name, 'Неизвестный') as to_name
                FROM transfers t
                LEFT JOIN accounts a1 ON t.from_account_id = a1.id
                LEFT JOIN capital_accounts ca1 ON t.from_account_id = ca1.id
                LEFT JOIN accounts a2 ON t.to_account_id = a2.id
                LEFT JOIN capital_accounts ca2 ON t.to_account_id = ca2.id
                WHERE (t.from_account_id = ? OR t.to_account_id = ?) {active_filter}
                ORDER BY t.date DESC, t.id DESC
                LIMIT ?
                """,
                (account_id, account_id, limit),
            )
        else:
            cursor.execute(
                f"""
                SELECT
                    t.id, t.from_account_id, t.to_account_id, t.amount, t.date, t.comment, t.is_active,
                    COALESCE(a1.name, ca1.name, 'Неизвестный') as from_name,
                    COALESCE(a2.name, ca2.name, 'Неизвестный') as to_name
                FROM transfers t
                LEFT JOIN accounts a1 ON t.from_account_id = a1.id
                LEFT JOIN capital_accounts ca1 ON t.from_account_id = ca1.id
                LEFT JOIN accounts a2 ON t.to_account_id = a2.id
                LEFT JOIN capital_accounts ca2 ON t.to_account_id = ca2.id
                WHERE 1=1 {active_filter}
                ORDER BY t.date DESC, t.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        results = cursor.fetchall()
        app_logger.debug(f"get_transfers_history: найдено {len(results)} записей")
        return results
