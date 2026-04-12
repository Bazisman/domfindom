from datetime import datetime, timedelta
import calendar


def migrate_recurring_transactions(get_connection, app_logger, sqlite3_module):
    app_logger.info("Миграция: добавление полей для регулярных платежей...")
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT status FROM transactions LIMIT 1")
        except sqlite3_module.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'actual'")
            app_logger.info("Добавлено поле 'status' в таблицу transactions")

        try:
            cursor.execute("SELECT executed_at FROM transactions LIMIT 1")
        except sqlite3_module.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN executed_at TEXT")
            app_logger.info("Добавлено поле 'executed_at' в таблицу transactions")

        try:
            cursor.execute("SELECT template_id FROM transactions LIMIT 1")
        except sqlite3_module.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN template_id INTEGER")
            app_logger.info("Добавлено поле 'template_id' в таблицу transactions")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                day_of_month INTEGER NOT NULL,
                category_id INTEGER,
                comment_template TEXT,
                months_ahead INTEGER DEFAULT 12,
                working_days_only INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_template ON transactions(template_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_executed ON transactions(executed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_active ON recurring_templates(is_active)")
        conn.commit()
        app_logger.info("Миграция завершена")


def adjust_to_workday(date_str):
    date_value = datetime.strptime(date_str, "%Y-%m-%d")
    while date_value.weekday() >= 5:
        date_value += timedelta(days=1)
    return date_value.strftime("%Y-%m-%d")


def create_recurring_template(
    get_connection,
    app_logger,
    generate_planned_transactions_fn,
    template_type,
    name,
    amount,
    day_of_month,
    category_id=None,
    comment_template="",
    months_ahead=12,
    working_days_only=0,
):
    app_logger.info(
        f"Создание шаблона: {name}, тип={template_type}, сумма={amount}, день={day_of_month}"
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO recurring_templates
            (type, name, amount, day_of_month, category_id, comment_template, months_ahead, working_days_only)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (template_type, name, amount, day_of_month, category_id, comment_template, months_ahead, working_days_only),
        )
        conn.commit()
        template_id = cursor.lastrowid
        generate_planned_transactions_fn(template_id)
        return template_id


def get_recurring_templates(get_connection, template_type=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if template_type:
            cursor.execute(
                """
                SELECT rt.id, rt.type, rt.name, rt.amount, rt.day_of_month, rt.category_id,
                       c.name as category_name, rt.comment_template, rt.months_ahead,
                       rt.working_days_only, rt.is_active, rt.created_at
                FROM recurring_templates rt
                LEFT JOIN categories c ON c.id = rt.category_id
                WHERE rt.type = ? AND rt.is_active = 1
                ORDER BY rt.day_of_month
                """,
                (template_type,),
            )
        else:
            cursor.execute(
                """
                SELECT rt.id, rt.type, rt.name, rt.amount, rt.day_of_month, rt.category_id,
                       c.name as category_name, rt.comment_template, rt.months_ahead,
                       rt.working_days_only, rt.is_active, rt.created_at
                FROM recurring_templates rt
                LEFT JOIN categories c ON c.id = rt.category_id
                WHERE rt.is_active = 1
                ORDER BY rt.day_of_month
                """
            )
        return cursor.fetchall()


def get_recurring_template_by_id(get_connection, template_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, type, name, amount, day_of_month, category_id,
                   comment_template, months_ahead, working_days_only, is_active, created_at
            FROM recurring_templates
            WHERE id = ?
            """,
            (template_id,),
        )
        return cursor.fetchone()


def update_recurring_template(
    get_connection,
    app_logger,
    delete_planned_transactions_fn,
    generate_planned_transactions_fn,
    template_id,
    **kwargs,
):
    allowed_fields = [
        "type",
        "name",
        "amount",
        "day_of_month",
        "category_id",
        "comment_template",
        "months_ahead",
        "working_days_only",
        "is_active",
    ]
    with get_connection() as conn:
        cursor = conn.cursor()
        normalized_kwargs = dict(kwargs)
        if "template_type" in normalized_kwargs and "type" not in normalized_kwargs:
            normalized_kwargs["type"] = normalized_kwargs.pop("template_type")

        for field, value in normalized_kwargs.items():
            if field in allowed_fields:
                cursor.execute(
                    f"""
                    UPDATE recurring_templates
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (value, template_id),
                )
        conn.commit()
        if any(
            f in normalized_kwargs
            for f in ["type", "amount", "day_of_month", "category_id", "comment_template", "months_ahead", "working_days_only"]
        ):
            delete_planned_transactions_fn(template_id)
            generate_planned_transactions_fn(template_id)
        app_logger.info(f"Шаблон ID={template_id} обновлён: {normalized_kwargs}")
        return cursor.rowcount > 0


def delete_recurring_template(get_connection, app_logger, template_id):
    app_logger.info(f"Удаление шаблона ID={template_id}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM transactions WHERE template_id = ? AND status = "planned"', (template_id,))
        cursor.execute("DELETE FROM recurring_templates WHERE id = ?", (template_id,))
        conn.commit()
        return True


def generate_planned_transactions(
    get_connection,
    app_logger,
    get_recurring_template_by_id_fn,
    adjust_to_workday_fn,
    template_id,
    months=None,
):
    template = get_recurring_template_by_id_fn(template_id)
    if not template:
        app_logger.warning(f"Шаблон {template_id} не найден")
        return 0

    months_value = months if months else template["months_ahead"]
    start_date = datetime.now()
    end_date = start_date + timedelta(days=months_value * 30)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM transactions WHERE template_id = ? AND status = "planned"', (template_id,))
        current_date = start_date
        count = 0
        while current_date <= end_date:
            day = min(template["day_of_month"], calendar.monthrange(current_date.year, current_date.month)[1])
            trans_date = datetime(current_date.year, current_date.month, day)
            if trans_date <= start_date:
                current_date = (current_date + timedelta(days=32)).replace(day=1)
                continue

            date_str = trans_date.strftime("%Y-%m-%d")
            if template["working_days_only"]:
                date_str = adjust_to_workday_fn(date_str)

            comment = template["comment_template"] or f"{template['name']} (запланировано)"
            cursor.execute("SELECT name FROM categories WHERE id = ?", (template["category_id"],))
            cat_row = cursor.fetchone()
            if cat_row:
                category_name = cat_row["name"]
            else:
                category_name = template["name"] or "Без категории"
                app_logger.warning(
                    f"Для шаблона {template_id} не найдена категория по ID={template['category_id']}, используем fallback '{category_name}'"
                )
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, 'planned', ?)
                """,
                (template["type"], category_name, template["amount"], comment, date_str, template_id),
            )
            count += 1
            current_date = (current_date + timedelta(days=32)).replace(day=1)
        conn.commit()
        app_logger.info(f"Сгенерировано {count} плановых транзакций для шаблона {template_id}")
        return count


def delete_planned_transactions(get_connection, app_logger, template_id, from_date=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if from_date:
            cursor.execute(
                """
                DELETE FROM transactions
                WHERE template_id = ? AND status = 'planned' AND date >= ?
                """,
                (template_id, from_date),
            )
        else:
            cursor.execute(
                """
                DELETE FROM transactions
                WHERE template_id = ? AND status = 'planned'
                """,
                (template_id,),
            )
        conn.commit()
        deleted = cursor.rowcount
        app_logger.info(f"Удалено {deleted} плановых транзакций шаблона {template_id}")
        return deleted


def delete_planned_transactions_in_period(get_connection, app_logger, template_id, start_date, end_date):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
                DELETE FROM transactions
                WHERE template_id = ? AND status = 'planned' AND date BETWEEN ? AND ?
            """,
            (template_id, start_date, end_date),
        )
        conn.commit()
        deleted = cursor.rowcount
        app_logger.info(f"Удалено {deleted} плановых транзакций шаблона {template_id} в период {start_date}..{end_date}")
        return deleted


def get_planned_transactions_due(get_connection):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.id, t.type, t.category, t.amount, t.comment, t.date, t.template_id,
                   rt.name as template_name
            FROM transactions t
            LEFT JOIN recurring_templates rt ON t.template_id = rt.id
            WHERE t.status = 'planned' AND t.date < ?
            ORDER BY t.date
            """,
            (today,),
        )
        return cursor.fetchall()


def get_planned_transactions_by_template(get_connection, template_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, type, category, amount, comment, date, status, template_id, executed_at
            FROM transactions
            WHERE template_id = ? AND status = 'planned'
            ORDER BY date
            """,
            (template_id,),
        )
        return cursor.fetchall()
