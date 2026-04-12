def init_db(
    get_connection,
    app_logger,
    migrate_recurring_transactions_fn,
    create_indexes_fn,
):
    app_logger.info("Инициализация базы данных")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                comment TEXT,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                balance REAL DEFAULT 0,
                currency TEXT DEFAULT 'RUB',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account_id INTEGER NOT NULL,
                to_account_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                transaction_id INTEGER,
                date TEXT NOT NULL,
                comment TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                color TEXT DEFAULT '#808080',
                icon TEXT DEFAULT '📁',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                period TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS capital_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                balance REAL DEFAULT 0,
                currency TEXT DEFAULT 'RUB',
                icon TEXT DEFAULT '💰',
                color TEXT DEFAULT '#ff9800',
                is_default INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reconciliation_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                balance REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                real_balance REAL NOT NULL,
                program_balance REAL NOT NULL,
                difference REAL NOT NULL,
                adjustment_transaction_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (adjustment_transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
            )
            """
        )

        cursor.execute("SELECT COUNT(*) FROM accounts WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """
                INSERT INTO accounts (id, name, type, balance, created_at, updated_at)
                VALUES (1, 'Основной счёт', 'main', 0, datetime('now'), datetime('now'))
                """
            )
            app_logger.info("Создан основной счёт с ID=1")

        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            default_categories = [
                ("Продукты", "expense", "#4CAF50", "🛒"),
                ("Транспорт", "expense", "#FF9800", "🚗"),
                ("Развлечения", "expense", "#9C27B0", "🎮"),
                ("Зарплата", "income", "#2196F3", "💼"),
                ("Подарки", "both", "#E91E63", "🎁"),
                ("Коммунальные", "expense", "#00BCD4", "💡"),
                ("Здоровье", "expense", "#F44336", "🏥"),
            ]
            for name, cat_type, color, icon in default_categories:
                cursor.execute(
                    """
                    INSERT INTO categories (name, type, color, icon, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (name, cat_type, color, icon),
                )
            app_logger.info(f"Создано {len(default_categories)} стандартных категорий")

        cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='capital_accounts'")
        seq = cursor.fetchone()
        if not seq or seq[0] < 99:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='capital_accounts'")
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('capital_accounts', 99)")
            app_logger.info("Счётчик ID для capital_accounts установлен на 100")

        default_settings = {
            "auto_capital_enabled": "1",
            "auto_capital_percent": "10",
        }
        for key, value in default_settings.items():
            cursor.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value),
            )

        conn.commit()

    migrate_recurring_transactions_fn()
    create_indexes_fn()
    app_logger.info("Database initialization completed")

