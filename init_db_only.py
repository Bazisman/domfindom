# init_db_only.py
import sqlite3
from datetime import datetime

print("=" * 60)
print("СОЗДАНИЕ БАЗЫ ДАННЫХ")
print("=" * 60)

# Удаляем старую БД
import os
if os.path.exists('finance.db'):
    os.remove('finance.db')
    print("✅ Старая БД удалена")

# Создаём новое соединение
conn = sqlite3.connect('finance.db')
cursor = conn.cursor()

print("\n📁 Создание таблиц...")

# Таблица accounts (основной счёт)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        balance REAL DEFAULT 0,
        currency TEXT DEFAULT 'RUB',
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
''')
print("  ✅ accounts")

# Вставляем основной счёт ID=1
cursor.execute('''
    INSERT INTO accounts (id, name, type, balance, created_at, updated_at)
    VALUES (1, 'Основной счёт', 'main', 0, datetime("now"), datetime("now"))
''')
print("  ✅ основной счёт (ID=1)")

# Таблица capital_accounts (счета капитала)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS capital_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        balance REAL DEFAULT 0,
        currency TEXT DEFAULT 'RUB',
        icon TEXT DEFAULT '💰',
        color TEXT DEFAULT '#ff9800',
        is_default INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
''')
print("  ✅ capital_accounts")

# Устанавливаем начальный ID = 100
cursor.execute("DELETE FROM sqlite_sequence WHERE name='capital_accounts'")
cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('capital_accounts', 99)")
print("  ✅ счётчик ID для capital_accounts установлен на 100")

# Таблица transactions
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        comment TEXT,
        date TEXT NOT NULL,
        created_at TEXT
    )
''')
print("  ✅ transactions")

# Таблица categories
cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL,
        color TEXT DEFAULT '#808080',
        icon TEXT DEFAULT '📁',
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
''')
print("  ✅ categories")

# Добавляем стандартные категории
default_categories = [
    ('Продукты', 'expense', '#4CAF50', '🛒'),
    ('Транспорт', 'expense', '#FF9800', '🚗'),
    ('Развлечения', 'expense', '#9C27B0', '🎮'),
    ('Зарплата', 'income', '#2196F3', '💼'),
    ('Подарки', 'both', '#E91E63', '🎁'),
    ('Коммунальные', 'expense', '#00BCD4', '💡'),
    ('Здоровье', 'expense', '#F44336', '🏥'),
]
for name, cat_type, color, icon in default_categories:
    cursor.execute('''
        INSERT INTO categories (name, type, color, icon, created_at)
        VALUES (?, ?, ?, ?, datetime("now"))
    ''', (name, cat_type, color, icon))
print("  ✅ стандартные категории")

# Таблица budgets
cursor.execute('''
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        period TEXT NOT NULL,
        FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
    )
''')
print("  ✅ budgets")

# Таблица transfers
cursor.execute('''
    CREATE TABLE IF NOT EXISTS transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_account_id INTEGER NOT NULL,
        to_account_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        transaction_id INTEGER,
        date TEXT NOT NULL,
        comment TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
    )
''')
print("  ✅ transfers")

# Создаём индексы для оптимизации производительности
print("\n📊 Создание индексов...")

# Индексы для transactions
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)')
print("  ✅ idx_transactions_date")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)')
print("  ✅ idx_transactions_type")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)')
print("  ✅ idx_transactions_category")

# Индексы для transfers
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers(from_account_id)')
print("  ✅ idx_transfers_from")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transfers_to ON transfers(to_account_id)')
print("  ✅ idx_transfers_to")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transfers_active ON transfers(is_active)')
print("  ✅ idx_transfers_active")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_transfers_transaction ON transfers(transaction_id)')
print("  ✅ idx_transfers_transaction")

# Индексы для capital_accounts
cursor.execute('CREATE INDEX IF NOT EXISTS idx_capital_accounts_active ON capital_accounts(is_active)')
print("  ✅ idx_capital_accounts_active")

# Индексы для categories
cursor.execute('CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type)')
print("  ✅ idx_categories_type")

conn.commit()
conn.close()

print("\n" + "=" * 60)
print("✅ БАЗА ДАННЫХ СОЗДАНА УСПЕШНО!")
print("   Основной счёт ID=1")
print("   Счета капитала начинаются с ID=100")
print("=" * 60)