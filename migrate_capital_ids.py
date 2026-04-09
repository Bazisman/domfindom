# migrate_capital_ids.py
import sqlite3

print("=" * 60)
print("МИГРАЦИЯ ID СЧЕТОВ КАПИТАЛА")
print("=" * 60)

conn = sqlite3.connect('finance.db')
cursor = conn.cursor()

# Получаем существующие счета капитала
cursor.execute("SELECT id, name FROM capital_accounts ORDER BY id")
accounts = cursor.fetchall()

if not accounts:
    print("Нет счетов капитала для миграции")
    conn.close()
    exit()

print("\n📋 Текущие счета капитала:")
for acc in accounts:
    print(f"   ID={acc[0]}: {acc[1]}")

# Создаём временную таблицу для переноса
cursor.execute("""
    CREATE TABLE capital_accounts_new (
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
""")

# Сбрасываем счётчик, чтобы новые ID начинались с 100
cursor.execute("DELETE FROM sqlite_sequence")
cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('capital_accounts_new', 99)")

# Переносим данные
old_to_new = {}
for i, acc in enumerate(accounts):
    new_id = 100 + i
    old_to_new[acc[0]] = new_id
    
    cursor.execute("""
        INSERT INTO capital_accounts_new (id, name, balance, currency, icon, color, is_default, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_id, acc[1], 0, 'RUB', '💰', '#ff9800', 0, 1, None, None))
    
    print(f"   ID={acc[0]} → ID={new_id}")

# Обновляем is_default (делаем первый счёт основным)
if accounts:
    cursor.execute("UPDATE capital_accounts_new SET is_default = 1 WHERE id = 100")

# Обновляем transfers — меняем старые ID на новые
for old_id, new_id in old_to_new.items():
    cursor.execute("UPDATE transfers SET to_account_id = ? WHERE to_account_id = ?", (new_id, old_id))
    cursor.execute("UPDATE transfers SET from_account_id = ? WHERE from_account_id = ?", (new_id, old_id))
    print(f"   Обновлены переводы: {old_id} → {new_id}")

# Заменяем таблицу
cursor.execute("DROP TABLE capital_accounts")
cursor.execute("ALTER TABLE capital_accounts_new RENAME TO capital_accounts")

conn.commit()

# Проверяем результат
cursor.execute("SELECT id, name, is_default FROM capital_accounts")
print("\n📋 Новые счета капитала:")
for acc in cursor.fetchall():
    default = "⭐ ОСНОВНОЙ" if acc[2] else ""
    print(f"   ID={acc[0]}: {acc[1]} {default}")

conn.close()

print("\n" + "=" * 60)
print("✅ МИГРАЦИЯ ЗАВЕРШЕНА!")
print("=" * 60)