def get_all_categories(
    get_connection,
    cache,
    get_cached_fn,
    cache_ttl_long,
    trans_type=None,
    include_inactive=False,
):
    def fetch_categories():
        with get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, name, type, color, icon, is_active FROM categories"
            where_clauses = []
            if not include_inactive:
                where_clauses.append("is_active = 1")
            if trans_type and trans_type != "both":
                where_clauses.append(f"type IN ('{trans_type}', 'both')")
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            query += " ORDER BY name"
            cursor.execute(query)
            return cursor.fetchall()

    cache_key = f"categories_{trans_type}_{include_inactive}"
    return get_cached_fn(cache_key, fetch_categories, ttl=cache_ttl_long)


def invalidate_category_cache(cache):
    for key in list(cache.keys()):
        if key.split("::", 1)[-1].startswith("categories_"):
            cache[key]["timestamp"] = 0


def add_category(
    get_connection,
    app_logger,
    invalidate_category_cache_fn,
    sqlite3_module,
    name,
    category_type="both",
    color="#808080",
    icon="📁",
):
    app_logger.info(f"Добавление категории: {name} ({category_type})")
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO categories (name, type, color, icon)
                VALUES (?, ?, ?, ?)
                """,
                (name, category_type, color, icon),
            )
            conn.commit()
            invalidate_category_cache_fn()
            app_logger.info(f"Категория добавлена: {name}")
            return cursor.lastrowid
        except sqlite3_module.IntegrityError:
            app_logger.warning(f"Категория '{name}' уже существует")
            return None


def update_category(
    get_connection,
    app_logger,
    invalidate_category_cache_fn,
    category_id,
    **kwargs,
):
    allowed_fields = ["name", "type", "color", "icon", "is_active"]
    with get_connection() as conn:
        cursor = conn.cursor()
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(
                    f"""
                    UPDATE categories
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (value, category_id),
                )
        conn.commit()
        invalidate_category_cache_fn()
        app_logger.debug(f"Категория ID={category_id} обновлена: {kwargs}")
        return cursor.rowcount > 0


def delete_category(app_logger, update_category_fn, invalidate_category_cache_fn, category_id):
    app_logger.info(f"Деактивация категории ID={category_id}")
    result = update_category_fn(category_id, is_active=0)
    invalidate_category_cache_fn()
    return result


def get_category_by_id(get_connection, category_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, type, color, icon, is_active
            FROM categories
            WHERE id = ?
            """,
            (category_id,),
        )
        return cursor.fetchone()


def get_category_by_name(get_connection, name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, type, color, icon, is_active
            FROM categories
            WHERE name = ?
            """,
            (name,),
        )
        return cursor.fetchone()
