"""
Ядро приложения - работа с базой данных и бизнес-логика
"""
import os
import sqlite3
from datetime import datetime, timedelta
from contextvars import ContextVar
from utils.logger import app_logger
import time


DB_NAME = os.getenv("FINANCE_APP_DB_NAME", "finance.db")
_DB_NAME_CONTEXT: ContextVar[str] = ContextVar("finance_db_name", default=DB_NAME)

# ========== КЭШИРОВАНИЕ ==========
# Простой кэш в памяти для часто запрашиваемых данных

_cache = {
    'balance': {'data': None, 'timestamp': 0},
    'categories': {'data': None, 'timestamp': 0},
    'capital_accounts': {'data': None, 'timestamp': 0},
    'total_capital': {'data': None, 'timestamp': 0},
    'category_list': {'data': None, 'timestamp': 0},  # Список категорий для виджетов
}

_CACHE_TTL = 2  # Время жизни кэша в секундах
_CACHE_TTL_LONG = 60  # Время жизни для редко меняющихся данных (категории)


def _get_cached(key, fetch_func, force_update=False, ttl=_CACHE_TTL):
    """Получает данные из кэша или обновляет"""
    now = time.time()
    cached = _cache[key]
    
    if force_update or now - cached['timestamp'] > ttl or cached['data'] is None:
        cached['data'] = fetch_func()
        cached['timestamp'] = now
    
    return cached['data']


def _invalidate_cache(key=None):
    """Инвалидирует кэш (делает его устаревшим)"""
    if key:
        _cache[key]['timestamp'] = 0
    else:
        for k in _cache:
            _cache[k]['timestamp'] = 0


def get_connection():
    """Создает и возвращает соединение с базой данных."""
    conn = sqlite3.connect(_DB_NAME_CONTEXT.get())
    conn.row_factory = sqlite3.Row
    return conn


def push_db_name(db_name: str):
    """Временно переключает активную БД в текущем контексте выполнения."""
    return _DB_NAME_CONTEXT.set(db_name)


def pop_db_name(token):
    """Восстанавливает предыдущую активную БД после push_db_name()."""
    _DB_NAME_CONTEXT.reset(token)


def init_db():
    """Создает таблицы, если их еще нет."""
    app_logger.info("Инициализация базы данных")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Таблица транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                comment TEXT,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        
        # Таблица счетов
        cursor.execute('''
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
        ''')
        
        # Таблица переводов
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
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
            )
        ''')
        
        # Таблица категорий
        cursor.execute('''
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
        ''')
        
        # Таблица бюджетов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                period TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
            )
        ''')
        
        # Таблица для хранения капитала
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
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Таблица простых ключ-значение настроек приложения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        
        # Таблица источников для сверки баланса
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reconciliation_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                balance REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        
        # Таблица сверок баланса
        cursor.execute('''
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
        ''')
        
        conn.commit()
        
        # 🔥 ПРОВЕРЯЕМ, ЕСТЬ ЛИ ОСНОВНОЙ СЧЁТ
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO accounts (id, name, type, balance, created_at, updated_at)
                VALUES (1, 'Основной счёт', 'main', 0, datetime('now'), datetime('now'))
            ''')
            app_logger.info("Создан основной счёт с ID=1")
        else:
            app_logger.debug("Основной счёт уже существует")
        
        # 🔥 ПРОВЕРЯЕМ, ЕСТЬ ЛИ СТАНДАРТНЫЕ КАТЕГОРИИ
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
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
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (name, cat_type, color, icon))
            app_logger.info(f"Создано {len(default_categories)} стандартных категорий")
        
        # 🔥 УСТАНАВЛИВАЕМ СЧЁТЧИК ДЛЯ capital_accounts НА 100
        cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='capital_accounts'")
        seq = cursor.fetchone()
        if not seq or seq[0] < 99:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='capital_accounts'")
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('capital_accounts', 99)")
            app_logger.info("Счётчик ID для capital_accounts установлен на 100")

        default_settings = {
            'auto_capital_enabled': '1',
            'auto_capital_percent': '10',
        }
        for key, value in default_settings.items():
            cursor.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value),
            )
        
        conn.commit()
    
    # Миграция для регулярных платежей (создание таблицы recurring_templates и полей)
    _migrate_recurring_transactions()
    
    # Создаём индексы для оптимизации
    _create_indexes_internal(cursor)

    # Убран пересчёт балансов при запуске
    # Балансы теперь обновляются только при операциях
    # recalc_all_balances() больше не вызывается
    app_logger.info("Database initialization completed")


#


def get_app_setting(key, default=None):
    """Возвращает строковое значение настройки приложения."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ? LIMIT 1", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default


def set_app_setting(key, value):
    """Сохраняет настройку приложения."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, str(value)),
        )
        conn.commit()
        return True


def get_auto_capital_settings():
    """Возвращает настройки автоотчислений из постоянного хранилища."""
    enabled_raw = get_app_setting('auto_capital_enabled', '1')
    percent_raw = get_app_setting('auto_capital_percent', '10')
    try:
        percent = int(percent_raw)
    except (TypeError, ValueError):
        percent = 10
    return {
        'enabled': str(enabled_raw) == '1',
        'percent': max(0, min(percent, 100)),
    }


def set_auto_capital_settings(enabled: bool, percent: int):
    """Сохраняет настройки автоотчислений."""
    normalized_percent = max(0, min(int(percent), 100))
    set_app_setting('auto_capital_enabled', '1' if enabled else '0')
    set_app_setting('auto_capital_percent', str(normalized_percent))
    return {
        'enabled': bool(enabled),
        'percent': normalized_percent,
    }





# ========== РАБОТА С БАЛАНСАМИ ==========




def _get_capital_balance_from_transfers(account_id):
    """Вычисляет баланс счёта капитала из активных переводов"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE to_account_id = ? AND is_active = 1", 
                      (account_id,))
        incoming = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE from_account_id = ? AND is_active = 1", 
                      (account_id,))
        outgoing = cursor.fetchone()[0] or 0
        
        return incoming - outgoing


def get_capital_balance(account_id):
    """Получает баланс счёта капитала"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
        result = cursor.fetchone()
        return result['balance'] if result else 0


# ========== РАБОТА С ТРАНЗАКЦИЯМИ И ОТЧИСЛЕНИЯМИ ==========

def add_income_with_capital(amount, category, comment, date, auto_percent, capital_account_id):
    """
    Добавляет доход и автоматическое отчисление в капитал.
    """
    app_logger.info(f"Добавление дохода {amount} с отчислением {auto_percent}% на счёт {capital_account_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # 1. Добавляем транзакцию
            cursor.execute('''
                INSERT INTO transactions (type, category, amount, comment, date, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', ('income', category, amount, comment, date))
            transaction_id = cursor.lastrowid
            
            # 2. Если есть отчисление
            if auto_percent > 0 and capital_account_id:
                capital_amount = amount * (auto_percent / 100)
                main_amount = amount - capital_amount
                
                # Обновляем баланс основного счёта
                cursor.execute('UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1', 
                              (main_amount,))
                
                # Проверяем, существует ли счёт капитала
                cursor.execute('SELECT id, name FROM capital_accounts WHERE id = ? AND is_active = 1', (capital_account_id,))
                capital_account = cursor.fetchone()
                
                if capital_account:
                    app_logger.info(f"Отчисление на счёт капитала: {capital_account['name']} (ID={capital_account['id']})")
                    
                    # 🔥 Записываем перевод (без from_table/to_table)
                    cursor.execute('''
                        INSERT INTO transfers (from_account_id, to_account_id, amount, transaction_id, date, comment, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    ''', (1, capital_account_id, capital_amount, transaction_id, date,
                          f"Автоотчисление {auto_percent}% от дохода: {comment}"))
                    
                    # Обновляем баланс счёта капитала
                    cursor.execute('''
                        UPDATE capital_accounts SET balance = balance + ?, updated_at = datetime("now") 
                        WHERE id = ? AND is_active = 1
                    ''', (capital_amount, capital_account_id))
                else:
                    app_logger.warning(f"Счёт капитала ID={capital_account_id} не найден или неактивен")
                    cursor.execute('UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1', 
                                  (capital_amount,))
            else:
                # Нет отчисления — вся сумма идёт на основной счёт
                cursor.execute('UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1', 
                              (amount,))
            
            # Инвалидируем кэш после изменения данных
            _invalidate_cache()
            
            conn.commit()
            app_logger.info(f"Доход добавлен: транзакция={transaction_id}")
            return transaction_id
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка добавления дохода: {e}", exc_info=True)
            raise


def add_expense(amount, category, comment, date):
    """Добавляет расход"""
    app_logger.info(f"Добавление расхода {amount}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Добавляем транзакцию
            cursor.execute('''
                INSERT INTO transactions (type, category, amount, comment, date, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', ('expense', category, amount, comment, date))
            transaction_id = cursor.lastrowid
            
            # Уменьшаем баланс основного счёта
            cursor.execute('UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1', 
                          (amount,))
            
            # Инвалидируем кэш после изменения данных
            _invalidate_cache()
            
            conn.commit()
            app_logger.info(f"Расход добавлен: транзакция={transaction_id}")
            return transaction_id
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка добавления расхода: {e}", exc_info=True)
            raise


def add_planned_transaction(transaction_type, category, amount, comment, date, template_id=None):
    """Добавляет неисполненную (planned) транзакцию без изменения баланса."""
    app_logger.info(
        f"Добавление planned-транзакции: type={transaction_type}, amount={amount}, date={date}, template_id={template_id}"
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id, created_at)
                VALUES (?, ?, ?, ?, ?, 'planned', ?, datetime('now'))
            ''',
            (transaction_type, category, amount, comment, date, template_id),
        )
        conn.commit()
        transaction_id = cursor.lastrowid
        _invalidate_cache()
        return transaction_id


def assign_template_to_planned_transaction(transaction_id, template_id):
    """Привязывает planned-транзакцию к шаблону регулярной операции."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
                UPDATE transactions
                SET template_id = ?
                WHERE id = ? AND status = 'planned'
            ''',
            (template_id, transaction_id),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            _invalidate_cache()
        return updated


def delete_transaction(transaction_id):
    """
    Удаляет транзакцию и все связанные с ней операции.
    Возвращает True если успешно.
    """
    app_logger.info(f"Удаление транзакции {transaction_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # 1. Получаем информацию о транзакции
            cursor.execute('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
            transaction = cursor.fetchone()
            
            if not transaction:
                app_logger.warning(f"Транзакция {transaction_id} не найдена")
                return False
            
            # 2. Если это доход — находим связанный перевод
            if transaction['type'] == 'income':
                app_logger.info(f"Это доход, ищем связанный перевод...")
                
                # Ищем по transaction_id
                cursor.execute('SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1', (transaction_id,))
                transfer = cursor.fetchone()
                
                if transfer:
                    app_logger.info(f"Найден перевод ID={transfer['id']}, amount={transfer['amount']}, from={transfer['from_account_id']}, to={transfer['to_account_id']}")
                    
                    # Используем тот счёт, куда реально ушёл перевод (transfer['to_account_id'])
                    target_account_id = transfer['to_account_id']
                    
                    # Проверяем, существует ли этот счёт и активен ли он
                    cursor.execute('SELECT id, is_active FROM capital_accounts WHERE id = ?', (target_account_id,))
                    target_account = cursor.fetchone()
                    
                    if target_account and target_account['is_active'] == 1:
                        # Счёт капитала существует и активен — возвращаем средства на него
                        cursor.execute('''
                            UPDATE capital_accounts 
                            SET balance = balance - ?, updated_at = datetime("now")
                            WHERE id = ?
                        ''', (transfer['amount'], target_account_id))
                        app_logger.info(f"Возврат {transfer['amount']} на счёт капитала {target_account_id}")
                    else:
                        # Если счёт капитала удалён/неактивен — возвращаем на основной счёт
                        cursor.execute('''
                            UPDATE accounts 
                            SET balance = balance + ?, updated_at = datetime("now")
                            WHERE id = 1
                        ''', (transfer['amount'],))
                        app_logger.info(f"Счёт капитала {target_account_id} неактивен, возврат {transfer['amount']} на основной счёт")
                    
                    # Помечаем перевод как неактивный
                    cursor.execute('UPDATE transfers SET is_active = 0 WHERE id = ?', (transfer['id'],))
                else:
                    app_logger.warning(f"Перевод для транзакции {transaction_id} НЕ НАЙДЕН! (transaction_id может быть null или перевод уже неактивен)")
                    # Проверим все переводы
                    cursor.execute('SELECT id, transaction_id, amount, date, is_active FROM transfers ORDER BY id DESC LIMIT 10')
                    all_transfers = cursor.fetchall()
                    app_logger.warning(f"Последние переводы: {all_transfers}")
            
            # 3. Откатываем баланс основного счёта
            if transaction['type'] == 'income':
                # При доходе с автоотчислением на основной счёт зачислялась сумма за вычетом отчисления
                # Нужно вычесть именно ту сумму, которая была зачислена, а не полную сумму транзакции
                # Используем данные transfer из п.2 (уже получен и сохранён в переменной transfer)
                capital_amount = transfer['amount'] if transfer else 0
                
                # Сумма которая была зачислена на основной счёт = полная сумма - отчисление
                main_amount = transaction['amount'] - capital_amount
                
                app_logger.info(f"Откат баланса: вычитаем {main_amount} (было зачислено) из основного счёта, отчисление было {capital_amount}")
                cursor.execute('UPDATE accounts SET balance = balance - ? WHERE id = 1', (main_amount,))
            else:
                app_logger.info(f"Откат баланса: прибавляем {transaction['amount']} к основному счёту")
                cursor.execute('UPDATE accounts SET balance = balance + ? WHERE id = 1', (transaction['amount'],))
            
            # 4. Удаляем транзакцию
            app_logger.info(f"Удаление транзакции {transaction_id} из БД...")
            cursor.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
            deleted_rows = cursor.rowcount
            app_logger.info(f"Удалено строк: {deleted_rows}")
            
            # Инвалидируем кэш после изменения данных
            _invalidate_cache()
            
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} удалена")
            return True
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка удаления транзакции {transaction_id}: {e}", exc_info=True)
            return False


def get_balance(force_update=False):
    """Возвращает баланс основного счёта, доходы и расходы (с кэшированием)"""
    
    def fetch_balance():
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT balance FROM accounts WHERE id = 1")
            main_balance = cursor.fetchone()[0] or 0
            
            # Учитываем только фактические транзакции (status='actual' или NULL)
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income' AND (status = 'actual' OR status IS NULL)")
            income = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND (status = 'actual' OR status IS NULL)")
            expense = cursor.fetchone()[0] or 0
            
            # Округляем до 2 знаков
            return round(main_balance, 2), round(income, 2), round(expense, 2)
    
    return _get_cached('balance', fetch_balance, force_update)


def get_last_transactions(limit=10, offset=0):
    """Возвращает последние N транзакций с поддержкой пагинации"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, date, type, category, amount, comment, status, template_id
            FROM transactions
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return cursor.fetchall()


def get_all_transactions():
    """Возвращает все транзакции без лимита для экспорта и служебных операций"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, date, type, category, amount, comment, status, template_id
            FROM transactions
            ORDER BY date DESC, id DESC
        ''')
        return cursor.fetchall()


def get_transactions_count():
    """Возвращает общее количество транзакций"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM transactions')
        return cursor.fetchone()[0]


def get_transactions_by_period(start_date, end_date, limit=500):
    """Возвращает транзакции за период с ограничением"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, date, type, category, amount, comment, status, template_id
            FROM transactions
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, id DESC
            LIMIT ?
        ''', (start_date, end_date, limit))
        return cursor.fetchall()


def get_transaction_by_id(transaction_id):
    """Получает транзакцию по ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, date, type, category, amount, comment, status, template_id
            FROM transactions
            WHERE id = ?
        ''', (transaction_id,))
        return cursor.fetchone()
         

def update_transaction(transaction_id, field, value):
    """
    Обновляет поле в транзакции.
    При изменении суммы или типа транзакции пересчитывает балансы.
    """
    allowed_fields = ['category', 'amount', 'comment', 'date', 'type']
    if field not in allowed_fields:
        app_logger.warning(f"Поле {field} нельзя редактировать")
        return False
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Получаем старую транзакцию для пересчёта балансов
            cursor.execute('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
            old_transaction = cursor.fetchone()
            
            if not old_transaction:
                app_logger.warning(f"Транзакция {transaction_id} не найдена")
                return False
            
            old_type = old_transaction['type']
            old_amount = old_transaction['amount']
            old_category = old_transaction['category']
            
            # Если меняется amount - пересчитываем балансы
            if field == 'amount':
                new_amount = float(value)
                amount_diff = new_amount - old_amount
                
                app_logger.info(f"Изменение суммы транзакции {transaction_id}: {old_amount} -> {new_amount} (разница: {amount_diff})")
                
                if old_type == 'income':
                    # Для дохода: ищем связанный перевод в капитал
                    cursor.execute(
                        'SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1',
                        (transaction_id,)
                    )
                    transfer = cursor.fetchone()
                    
                    if transfer:
                        # Было автоотчисление - нужно пересчитать и основной счёт, и капитал
                        old_transfer_amount = transfer['amount']
                        # Новое отчисление = новый доход * (старое отчисление / старый доход)
                        if old_amount > 0:
                            percent = old_transfer_amount / old_amount
                            new_transfer_amount = new_amount * percent
                        else:
                            new_transfer_amount = 0
                        
                        transfer_diff = new_transfer_amount - old_transfer_amount
                        
                        # Обновляем баланс капитала
                        cursor.execute(
                            'UPDATE capital_accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = ?',
                            (transfer_diff, transfer['to_account_id'])
                        )
                        
                        # Обновляем баланс основного счёта (разница между суммами дохода минус разница отчислений)
                        main_diff = amount_diff - transfer_diff
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                            (main_diff,)
                        )
                        
                        # Обновляем сумму перевода
                        cursor.execute(
                            'UPDATE transfers SET amount = ? WHERE id = ?',
                            (new_transfer_amount, transfer['id'])
                        )
                        
                        app_logger.info(f"Пересчитан баланс капитала: {transfer_diff}, основной счёт: {main_diff}")
                    else:
                        # Не было автоотчисления - просто меняем баланс основного счёта
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                            (amount_diff,)
                        )
                        app_logger.info(f"Обновлён баланс основного счёта: {amount_diff}")
                
                elif old_type == 'expense':
                    # Для расхода: увеличиваем баланс на разницу
                    cursor.execute(
                        'UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1',
                        (amount_diff,)
                    )
                    app_logger.info(f"Обновлён баланс основного счёта (расход): {-amount_diff}")
            
            # Если меняется type (income <-> expense)
            elif field == 'type':
                new_type = value
                
                app_logger.info(f"Изменение типа транзакции {transaction_id}: {old_type} -> {new_type}")
                
                if old_type == 'income' and new_type == 'expense':
                    # Был доход - возвращаем на основной счёт, списываем как расход
                    # Возвращаем сумму дохода (всю или за вычетом отчисления)
                    cursor.execute(
                        'SELECT * FROM transfers WHERE transaction_id = ? AND is_active = 1',
                        (transaction_id,)
                    )
                    transfer = cursor.fetchone()
                    
                    if transfer:
                        # Возвращаем отчисление в капитал обратно на основной счёт
                        cursor.execute(
                            'UPDATE capital_accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = ?',
                            (transfer['amount'], transfer['to_account_id'])
                        )
                        # Основной счёт: возвращаем сумму дохода минус отчисление
                        main_amount = old_amount - transfer['amount']
                    else:
                        main_amount = old_amount
                    
                    # Возвращаем на основной счёт
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (main_amount,)
                    )
                    # Списываем как расход
                    cursor.execute(
                        'UPDATE accounts SET balance = balance - ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,)
                    )
                    
                    # Деактивируем перевод если был
                    if transfer:
                        cursor.execute(
                            'UPDATE transfers SET is_active = 0 WHERE id = ?',
                            (transfer['id'],)
                        )
                
                elif old_type == 'expense' and new_type == 'expense':
                    # Расход -> доход: возвращаем сумму и зачисляем как доход
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,)
                    )
                    # Зачисляем как доход
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ?, updated_at = datetime("now") WHERE id = 1',
                        (old_amount,)
                    )
            
            # Обновляем поле транзакции
            cursor.execute(f'''
                UPDATE transactions 
                SET {field} = ? 
                WHERE id = ?
            ''', (value, transaction_id))
            
            # Инвалидируем кэш после изменения данных
            _invalidate_cache()
            
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} обновлена: {field}={value}")
            return True
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка обновления транзакции {transaction_id}: {e}", exc_info=True)
            return False


# ========== РАБОТА С КАТЕГОРИЯМИ ==========

def get_all_categories(trans_type=None, include_inactive=False):
    """Возвращает список категорий (с кэшированием)"""
    
    def fetch_categories():
        with get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, name, type, color, icon, is_active FROM categories"
            params = []
            
            where_clauses = []
            if not include_inactive:
                where_clauses.append("is_active = 1")
            
            if trans_type and trans_type != 'both':
                where_clauses.append(f"type IN ('{trans_type}', 'both')")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            query += " ORDER BY name"
            cursor.execute(query, params)
            return cursor.fetchall()
    
    # Используем длинный TTL для категорий (они меняются редко)
    cache_key = f'categories_{trans_type}_{include_inactive}'
    if cache_key not in _cache:
        _cache[cache_key] = {'data': None, 'timestamp': 0}
    
    return _get_cached(cache_key, fetch_categories, ttl=_CACHE_TTL_LONG)


def add_category(name, category_type='both', color='#808080', icon='📁'):
    """Добавляет новую категорию"""
    app_logger.info(f"Добавление категории: {name} ({category_type})")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO categories (name, type, color, icon)
                VALUES (?, ?, ?, ?)
            ''', (name, category_type, color, icon))
            conn.commit()
            
            # Инвалидируем кэш категорий
            _invalidate_category_cache()
            
            app_logger.info(f"Категория добавлена: {name}")
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            app_logger.warning(f"Категория '{name}' уже существует")
            return None


def update_category(category_id, **kwargs):
    """Обновляет категорию"""
    allowed_fields = ['name', 'type', 'color', 'icon', 'is_active']
    
    with get_connection() as conn:
        cursor = conn.cursor()
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(f'''
                    UPDATE categories 
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (value, category_id))
        conn.commit()
        
        # Инвалидируем кэш категорий
        _invalidate_category_cache()
        
        app_logger.debug(f"Категория ID={category_id} обновлена: {kwargs}")
        return cursor.rowcount > 0


def delete_category(category_id):
    """Мягкое удаление категории"""
    app_logger.info(f"Деактивация категории ID={category_id}")
    result = update_category(category_id, is_active=0)
    _invalidate_category_cache()
    return result


def _invalidate_category_cache():
    """Инвалидирует кэш категорий"""
    for key in list(_cache.keys()):
        if key.startswith('categories_'):
            _cache[key]['timestamp'] = 0


def get_category_by_id(category_id):
    """Получает категорию по ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, type, color, icon, is_active 
            FROM categories 
            WHERE id = ?
        ''', (category_id,))
        return cursor.fetchone()   
         

def get_category_by_name(name):
    """Получает категорию по имени"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, type, color, icon, is_active 
            FROM categories 
            WHERE name = ?
        ''', (name,))
        return cursor.fetchone()


# ========== РАБОТА С КАПИТАЛОМ ==========

def get_capital_accounts(include_inactive=False):
    """Получает все счета капитала (с кэшированием)"""
    
    def fetch_capital_accounts():
        with get_connection() as conn:
            cursor = conn.cursor()
            query = '''
                SELECT id, name, balance, currency, icon, color, is_active, is_default
                FROM capital_accounts
            '''
            if not include_inactive:
                query += " WHERE is_active = 1"
            query += " ORDER BY is_default DESC, name"
            cursor.execute(query)
            return cursor.fetchall()
    
    cache_key = f'capital_accounts_{include_inactive}'
    if cache_key not in _cache:
        _cache[cache_key] = {'data': None, 'timestamp': 0}
    
    return _get_cached(cache_key, fetch_capital_accounts, ttl=_CACHE_TTL_LONG)


def get_default_capital_account():
    """Получает основной счёт капитала (is_default = 1)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, balance, icon, color 
            FROM capital_accounts 
            WHERE is_default = 1 AND is_active = 1
            LIMIT 1
        ''')
        return cursor.fetchone()


def set_default_capital_account(account_id):
    """Устанавливает основной счёт капитала"""
    app_logger.info(f"Установка основного счёта капитала: ID={account_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE capital_accounts SET is_default = 0")
        cursor.execute("UPDATE capital_accounts SET is_default = 1 WHERE id = ?", (account_id,))
        conn.commit()
        
        # Инвалидируем кэш капитала
        _invalidate_capital_cache()
        
        app_logger.info(f"Основной счёт капитала установлен: ID={account_id}")
        return cursor.rowcount > 0


def _invalidate_capital_cache():
    """Инвалидирует кэш капитала"""
    for key in list(_cache.keys()):
        if key.startswith('capital_accounts_'):
            _cache[key]['timestamp'] = 0


def add_capital_account(name, balance=0, icon='💰', color='#ff9800'):
    """Добавляет новый счёт капитала (ID начиная с 100)"""
    app_logger.info(f"Добавление счёта капитала: {name}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже активные счета
        cursor.execute("SELECT COUNT(*) FROM capital_accounts WHERE is_active = 1")
        count = cursor.fetchone()[0]
        is_default = 1 if count == 0 else 0
        
        cursor.execute('''
            INSERT INTO capital_accounts (name, balance, icon, color, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', (name, balance, icon, color, is_default))
        conn.commit()
        
        new_id = cursor.lastrowid
        
        # Инвалидируем кэш капитала
        _invalidate_capital_cache()
        
        app_logger.info(f"Счёт капитала добавлен: {name}, ID={new_id}, основной={is_default}")
        return new_id


def update_capital_account(account_id, **kwargs):
    """Обновляет счёт капитала"""
    allowed_fields = ['name', 'balance', 'icon', 'color', 'is_active']
    
    with get_connection() as conn:
        cursor = conn.cursor()
        applied_updates = False
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(f'''
                    UPDATE capital_accounts 
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (value, account_id))
                applied_updates = applied_updates or (cursor.rowcount > 0)
        conn.commit()
        if applied_updates:
            _invalidate_capital_cache()
        app_logger.debug(f"Обновлён счёт капитала ID={account_id}: {kwargs}")
        return applied_updates


def delete_capital_account(account_id):
    """Мягкое удаление счёта капитала (деактивация)"""
    if account_id == 1:
        app_logger.error("Нельзя удалить основной счёт!")
        return False
    
    app_logger.info(f"Деактивация счёта капитала ID={account_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Помечаем все переводы с этим счётом как неактивные
        cursor.execute('''
            UPDATE transfers SET is_active = 0 
            WHERE to_account_id = ? OR from_account_id = ?
        ''', (account_id, account_id))
        
        # Деактивируем счёт
        cursor.execute('UPDATE capital_accounts SET is_active = 0 WHERE id = ?', (account_id,))
        deactivated = cursor.rowcount > 0
        
        # Если это был основной счёт, назначаем новый основной
        cursor.execute("SELECT is_default FROM capital_accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        if row and row['is_default'] == 1:
            # Находим любой другой активный счёт
            cursor.execute("SELECT id FROM capital_accounts WHERE is_active = 1 AND id != ? LIMIT 1", (account_id,))
            new_default = cursor.fetchone()
            if new_default:
                cursor.execute("UPDATE capital_accounts SET is_default = 1 WHERE id = ?", (new_default['id'],))
                app_logger.info(f"Новый основной счёт капитала: ID={new_default['id']}")
        
        conn.commit()
        _invalidate_capital_cache()
        return deactivated


def get_total_capital():
    """Получает общую сумму всех активных счетов капитала"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(balance) FROM capital_accounts WHERE is_active = 1")
        return cursor.fetchone()[0] or 0


# ========== РАБОТА С ПЕРЕВОДАМИ ==========

def get_transfers_history(account_id=None, limit=100, include_inactive=False):
    """Получает историю переводов"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        active_filter = "" if include_inactive else "AND t.is_active = 1"
        
        if account_id:
            cursor.execute(f'''
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
            ''', (account_id, account_id, limit))
        else:
            cursor.execute(f'''
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
            ''', (limit,))
        
        results = cursor.fetchall()
        app_logger.debug(f"get_transfers_history: найдено {len(results)} записей")
        return results


# ========== РАБОТА С БЮДЖЕТАМИ ==========

def set_budget(category_id, amount, period='monthly'):
    """Устанавливает бюджет для категории (создаёт или обновляет)"""
    app_logger.info(f"Установка бюджета: category_id={category_id}, amount={amount}, period={period}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Пробуем обновить существующую запись
        cursor.execute('''
            UPDATE budgets SET amount = ?, period = ?
            WHERE category_id = ?
        ''', (amount, period, category_id))
        
        # Если запись не существовала, создаём новую
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO budgets (category_id, amount, period)
                VALUES (?, ?, ?)
            ''', (category_id, amount, period))
        
        conn.commit()
        return True


def get_budgets():
    """Возвращает все бюджеты с названиями категорий"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.id, b.category_id, c.name as category, b.amount, b.period
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            ORDER BY c.name
        ''')
        return cursor.fetchall()


def _normalize_budget_period(period):
    """Приводит период бюджета к поддерживаемому значению."""
    normalized = (period or 'monthly').lower()
    if normalized in {'daily', 'weekly', 'monthly', 'yearly'}:
        return normalized
    return 'monthly'


def _get_budget_monthly_limit(amount, period):
    """Возвращает месячный эквивалент бюджета для прогнозов и экранов месяца."""
    normalized_period = _normalize_budget_period(period)

    if normalized_period == 'daily':
        return amount * 30
    if normalized_period == 'weekly':
        return amount * 4
    if normalized_period == 'yearly':
        return amount / 12
    return amount


def delete_budget(budget_id):
    """Удаляет бюджет"""
    app_logger.info(f"Удаление бюджета ID={budget_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM budgets WHERE id = ?', (budget_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_budget_report(month=None):
    """Возвращает отчёт по бюджетам за месяц"""
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    
    start_date = month + '-01'
    year, month_num = map(int, month.split('-'))
    
    if month_num == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month_num+1:02d}-01"
    
    with get_connection() as conn:
        cursor = conn.cursor()
        budgets = get_budgets()
        report = []
        
        for budget in budgets:
            category_id = budget['category_id']
            category_name = budget['category']
            budget_amount = _get_budget_monthly_limit(
                budget['amount'] or 0,
                budget['period'] if 'period' in budget.keys() else 'monthly',
            )
            
            cursor.execute('''
                SELECT SUM(amount) as total 
                FROM transactions 
                WHERE type = 'expense' 
                AND category = ? 
                AND (status = 'actual' OR status IS NULL)
                AND date >= ? AND date < ?
            ''', (category_name, start_date, end_date))
            
            spent = cursor.fetchone()['total'] or 0
            percent = (spent / budget_amount * 100) if budget_amount > 0 else 0
            
            report.append({
                'category_id': category_id,
                'category': category_name,
                'budget': budget_amount,
                'spent': spent,
                'remaining': budget_amount - spent,
                'percent': percent,
                'status': 'OK' if spent <= budget_amount else 'ПРЕВЫШЕНИЕ'
            })
        
        return report

# ========== РАБОТА СО СЧЕТАМИ ==========

def get_all_accounts(include_inactive=False):
    """Получает все счета (только accounts, не capital_accounts)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, name, type, balance, currency, is_active FROM accounts"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY type, name"
        cursor.execute(query)
        return cursor.fetchall()


def get_account_balance(account_id):
    """Получает баланс счёта"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if account_id == 1:
            cursor.execute("SELECT balance FROM accounts WHERE id = 1")
            result = cursor.fetchone()
            return result['balance'] if result else 0
        
        if account_id >= 100:
            cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
            result = cursor.fetchone()
            return result['balance'] if result else 0
        
        return 0


def update_account_balance(account_id, amount):
    """Обновляет баланс счёта"""
    app_logger.debug(f"update_account_balance: account_id={account_id}, amount={amount}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # ID=1 всегда основной счёт (accounts)
        if account_id == 1:
            cursor.execute('''
                UPDATE accounts 
                SET balance = balance + ?, updated_at = datetime('now')
                WHERE id = 1
            ''', (amount,))
            conn.commit()
            app_logger.info(f"Баланс основного счёта обновлён: изменение={amount}")
            return True
        
        # ID >= 100 — счета капитала
        if account_id >= 100:
            cursor.execute("SELECT balance FROM capital_accounts WHERE id = ?", (account_id,))
            result = cursor.fetchone()
            if result:
                cursor.execute('''
                    UPDATE capital_accounts 
                    SET balance = balance + ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (amount, account_id))
                conn.commit()
                _invalidate_capital_cache()
                app_logger.info(f"Баланс счёта капитала {account_id} обновлён: изменение={amount}")
                return True
        
        app_logger.error(f"Счёт {account_id} не найден")
        return False


def sync_accounts_with_transactions():
    """Синхронизирует балансы счетов с транзакциями"""
    app_logger.info("Синхронизация счетов с транзакциями")

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Учитываем только фактические транзакции (status='actual' или NULL)
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='income' AND (status = 'actual' OR status IS NULL)")
        total_income = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE type='expense' AND (status = 'actual' OR status IS NULL)")
        total_expense = cursor.fetchone()[0] or 0
        total_balance = total_income - total_expense
        
        cursor.execute("SELECT SUM(amount) FROM transfers WHERE to_account_id IN (SELECT id FROM capital_accounts) AND is_active = 1")
        total_to_capital = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(amount) FROM transfers WHERE from_account_id IN (SELECT id FROM capital_accounts) AND is_active = 1")
        total_from_capital = cursor.fetchone()[0] or 0
        
        main_balance = total_balance - total_to_capital + total_from_capital
        
        cursor.execute("UPDATE accounts SET balance = ? WHERE type = 'main'", (main_balance,))
        
        # Обновляем балансы счетов капитала
        cursor.execute("SELECT id FROM capital_accounts WHERE is_active = 1")
        for row in cursor.fetchall():
            balance = _get_capital_balance_from_transfers(row['id'])
            cursor.execute("UPDATE capital_accounts SET balance = ? WHERE id = ?", (balance, row['id']))
        
        conn.commit()
        app_logger.info(f"Синхронизация завершена: основной счёт={main_balance:.2f}")
        return main_balance


def get_expenses_by_category(start_date=None, end_date=None):
    """Возвращает расходы по категориям за период (только фактические)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'expense' AND (status = 'actual' OR status IS NULL)
        '''
        params = []
        
        if start_date and end_date:
            query += ' AND date BETWEEN ? AND ?'
            params = [start_date, end_date]
        elif start_date:
            query += ' AND date >= ?'
            params = [start_date]
        elif end_date:
            query += ' AND date <= ?'
            params = [end_date]
        
        query += ' GROUP BY category ORDER BY total DESC'
        cursor.execute(query, params)
        return cursor.fetchall()


def get_income_by_category(start_date=None, end_date=None):
    """Возвращает доходы по категориям за период (только фактические)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'income' AND (status = 'actual' OR status IS NULL)
        '''
        params = []
        
        if start_date and end_date:
            query += ' AND date BETWEEN ? AND ?'
            params = [start_date, end_date]
        elif start_date:
            query += ' AND date >= ?'
            params = [start_date]
        elif end_date:
            query += ' AND date <= ?'
            params = [end_date]
        
        query += ' GROUP BY category ORDER BY total DESC'
        cursor.execute(query, params)
        return cursor.fetchall()


def get_capital_contributions_for_period(start_date=None, end_date=None):
    """Возвращает сумму отчислений в капитал за период"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        query = 'SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE is_active = 1'
        params = []
        
        if start_date and end_date:
            query += ' AND date BETWEEN ? AND ?'
            params = [start_date, end_date]
        elif start_date:
            query += ' AND date >= ?'
            params = [start_date]
        elif end_date:
            query += ' AND date <= ?'
            params = [end_date]
        
        cursor.execute(query, params)
        return cursor.fetchone()[0] or 0


def get_available_periods():
    """Возвращает список доступных месяцев с данными"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT strftime('%Y-%m', date) as month
            FROM transactions 
            ORDER BY month DESC
        ''')
        return [row['month'] for row in cursor.fetchall()]


def check_budget(category_id, amount, date=None):
    """Проверяет, не превысит ли новая трата бюджет"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, period FROM budgets 
            WHERE category_id = ?
        ''', (category_id,))
        budget = cursor.fetchone()
        
        if not budget:
            return None
        
        budget_amount = _get_budget_monthly_limit(
            budget['amount'] or 0,
            budget['period'] if 'period' in budget.keys() else 'monthly',
        )
        start_date = date[:8] + '01'
        
        cursor.execute('''
            SELECT SUM(amount) as total 
            FROM transactions 
            WHERE type = 'expense' 
            AND category = (SELECT name FROM categories WHERE id = ?)
            AND (status = 'actual' OR status IS NULL)
            AND date >= ?
        ''', (category_id, start_date))
        
        spent = cursor.fetchone()['total'] or 0
        total_with_new = spent + amount
        
        return (total_with_new > budget_amount, spent, budget_amount)

def reset_to_factory():
    """
    Полный сброс базы данных до заводских настроек.
    Удаляет все данные и создаёт чистую БД.
    """
    import os
    import gc
    import time
    
    app_logger.warning("=" * 60)
    app_logger.warning("ВЫПОЛНЯЕТСЯ СБРОС ДО ЗАВОДСКИХ НАСТРОЕК")
    app_logger.warning("=" * 60)
    
    # Принудительно закрываем все соединения
    gc.collect()
    time.sleep(0.5)
    
    # Удаляем существующую базу данных
    if os.path.exists(DB_NAME):
        try:
            os.remove(DB_NAME)
            app_logger.info(f"Файл {DB_NAME} удалён")
        except PermissionError:
            app_logger.warning("Файл занят, пробуем ещё раз...")
            time.sleep(1)
            os.remove(DB_NAME)
            app_logger.info(f"Файл {DB_NAME} удалён")
        except Exception as e:
            app_logger.error(f"Не удалось удалить {DB_NAME}: {e}")
            raise
    
    # Создаём новую базу данных
    init_db()
    
    
    
    app_logger.info("База данных сброшена до заводских настроек")
    app_logger.warning("=" * 60)
    return True


def _create_indexes_internal(cursor):
    """Внутренняя функция для создания индексов (используется в init_db)"""
    indexes = [
        # transactions
        ('idx_transactions_date', 'CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)'),
        ('idx_transactions_type', 'CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)'),
        ('idx_transactions_category', 'CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)'),
        
        # transfers
        ('idx_transfers_from', 'CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers(from_account_id)'),
        ('idx_transfers_to', 'CREATE INDEX IF NOT EXISTS idx_transfers_to ON transfers(to_account_id)'),
        ('idx_transfers_active', 'CREATE INDEX IF NOT EXISTS idx_transfers_active ON transfers(is_active)'),
        ('idx_transfers_transaction', 'CREATE INDEX IF NOT EXISTS idx_transfers_transaction ON transfers(transaction_id)'),
        
        # capital_accounts
        ('idx_capital_accounts_active', 'CREATE INDEX IF NOT EXISTS idx_capital_accounts_active ON capital_accounts(is_active)'),
        
        # categories
        ('idx_categories_type', 'CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type)'),
    ]
    
    for name, sql in indexes:
        try:
            cursor.execute(sql)
            app_logger.debug(f"Индекс {name} создан/проверен")
        except Exception as e:
            app_logger.warning(f"Не удалось создать индекс {name}: {e}")


def create_indexes():
    """
    Создаёт индексы для оптимизации производительности.
    Вызывать после init_db() или при необходимости оптимизации.
    """
    app_logger.info("Создание индексов для оптимизации...")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        _create_indexes_internal(cursor)
        conn.commit()
    
    app_logger.info("Индексы созданы/проверены")


def add_transfer_record(from_account_id, to_account_id, amount, date=None, comment=""):
    """Добавляет запись о переводе в историю"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    app_logger.debug(f"Добавление записи о переводе: {amount} с {from_account_id} на {to_account_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transfers (from_account_id, to_account_id, amount, date, comment, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (from_account_id, to_account_id, amount, date, comment))
        conn.commit()
        app_logger.info(f"Запись о переводе добавлена, ID: {cursor.lastrowid}")

def transfer_money(from_account_id, to_account_id, amount, date=None, comment=""):
    """Переводит деньги между счетами"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    app_logger.info(f"Выполняется перевод: {amount} со счёта {from_account_id} на {to_account_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Проверяем достаточно ли средств
            cursor.execute("SELECT balance FROM accounts WHERE id = ?", (from_account_id,))
            from_balance = cursor.fetchone()
            
            if from_balance and from_balance['balance'] < amount:
                app_logger.warning(f"Недостаточно средств: {from_balance['balance']} < {amount}")
                raise ValueError("Недостаточно средств")
            
            # Списание
            cursor.execute('''
                UPDATE accounts SET balance = balance - ?, updated_at = datetime('now')
                WHERE id = ?
            ''', (amount, from_account_id))
            
            # Зачисление
            cursor.execute('''
                UPDATE accounts SET balance = balance + ?, updated_at = datetime('now')
                WHERE id = ?
            ''', (amount, to_account_id))
            
            # Запись о переводе
            cursor.execute('''
                INSERT INTO transfers (from_account_id, to_account_id, amount, date, comment, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (from_account_id, to_account_id, amount, date, comment))
            
            conn.commit()
            app_logger.info(f"Перевод выполнен успешно: {amount}")
            return True
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка перевода: {e}", exc_info=True)
            return False

def get_main_account():
    """Получает основной счёт (всегда ID=1)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, type, balance FROM accounts WHERE id = 1")
        return cursor.fetchone()   
         

# ========== РАБОТА СО СВЕРКОЙ БАЛАНСА ==========

def get_reconciliation_sources():
    """Получает все источники для сверки баланса"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, balance, is_active, created_at, updated_at
            FROM reconciliation_sources
            ORDER BY is_active DESC, name
        ''')
        return cursor.fetchall()


def add_reconciliation_source(name, balance=0):
    """Добавляет новый источник для сверки баланса"""
    app_logger.info(f"Добавление источника сверки: {name}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reconciliation_sources (name, balance, is_active, created_at, updated_at)
            VALUES (?, ?, 1, datetime('now'), datetime('now'))
        ''', (name, balance))
        conn.commit()
        app_logger.info(f"Источник сверки добавлен: {name}, ID={cursor.lastrowid}")
        return cursor.lastrowid


def update_reconciliation_source(source_id, **kwargs):
    """Обновляет источник сверки"""
    allowed_fields = ['name', 'balance', 'is_active']
    
    with get_connection() as conn:
        cursor = conn.cursor()
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(f'''
                    UPDATE reconciliation_sources 
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (value, source_id))
        conn.commit()
        app_logger.debug(f"Источник сверки ID={source_id} обновлён: {kwargs}")
        return cursor.rowcount > 0


def delete_reconciliation_source(source_id):
    """Удаляет источник сверки (мягкое удаление)"""
    app_logger.info(f"Удаление источника сверки ID={source_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE reconciliation_sources 
            SET is_active = 0, updated_at = datetime('now')
            WHERE id = ?
        ''', (source_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_total_real_balance():
    """Получает суммарный реальный баланс всех активных источников"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM reconciliation_sources WHERE is_active = 1")
        return cursor.fetchone()[0] or 0


def get_last_reconciliation():
    """Получает последнюю сверку баланса"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, real_balance, program_balance, difference, 
                   adjustment_transaction_id, created_at, updated_at
            FROM reconciliations
            ORDER BY created_at DESC
            LIMIT 1
        ''')
        return cursor.fetchone()


def save_reconciliation(real_balance, program_balance, difference, adjustment_transaction_id=None):
    """Сохраняет сверку баланса"""
    app_logger.info(f"Сохранение сверки: real={real_balance}, program={program_balance}, diff={difference}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем, есть ли последняя сверка
        last = get_last_reconciliation()
        
        if last:
            # Обновляем существующую сверку
            cursor.execute('''
                UPDATE reconciliations 
                SET real_balance = ?, program_balance = ?, difference = ?,
                    adjustment_transaction_id = ?, updated_at = datetime('now')
                WHERE id = ?
            ''', (real_balance, program_balance, difference, adjustment_transaction_id, last['id']))
            recon_id = last['id']
            app_logger.info(f"Сверка обновлена: ID={recon_id}")
        else:
            # Создаём новую сверку
            cursor.execute('''
                INSERT INTO reconciliations (real_balance, program_balance, difference, adjustment_transaction_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            ''', (real_balance, program_balance, difference, adjustment_transaction_id))
            recon_id = cursor.lastrowid
            app_logger.info(f"Сверка создана: ID={recon_id}")
        
        conn.commit()
        return recon_id


def get_reconciliations_history(limit=50):
    """Получает историю сверок баланса"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, real_balance, program_balance, difference, 
                   adjustment_transaction_id, created_at, updated_at
            FROM reconciliations
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()


def delete_reconciliation(recon_id):
    """Удаляет сверку баланса"""
    app_logger.info(f"Удаление сверки ID={recon_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем сверку
        cursor.execute('SELECT adjustment_transaction_id FROM reconciliations WHERE id = ?', (recon_id,))
        recon = cursor.fetchone()
        
        if recon and recon['adjustment_transaction_id']:
            # Удаляем связанную транзакцию
            cursor.execute('DELETE FROM transactions WHERE id = ?', (recon['adjustment_transaction_id'],))
            # Обновляем баланс основного счёта
            cursor.execute('SELECT amount, type FROM transactions WHERE id = ?', (recon['adjustment_transaction_id'],))
            trans = cursor.fetchone()
            if trans:
                if trans['type'] == 'income':
                    cursor.execute('UPDATE accounts SET balance = balance - ? WHERE id = 1', (trans['amount'],))
                else:
                    cursor.execute('UPDATE accounts SET balance = balance + ? WHERE id = 1', (trans['amount'],))
        
        cursor.execute('DELETE FROM reconciliations WHERE id = ?', (recon_id,))
        conn.commit()
        
        # Инвалидируем кэш
        _invalidate_cache()
        
        return cursor.rowcount > 0


def update_reconciliation(recon_id, real_balance, program_balance, difference, adjustment_transaction_id=None):
    """Обновляет сверку баланса"""
    app_logger.info(f"Обновление сверки ID={recon_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE reconciliations 
            SET real_balance = ?, program_balance = ?, difference = ?,
                adjustment_transaction_id = ?, updated_at = datetime('now')
            WHERE id = ?
        ''', (real_balance, program_balance, difference, adjustment_transaction_id, recon_id))
        conn.commit()
        return cursor.rowcount > 0


# ========== РЕГУЛЯРНЫЕ ПЛАТЕЖИ (ПЛАНОВЫЕ ТРАНЗАКЦИИ) ==========

def _migrate_recurring_transactions():
    """Миграция: добавление полей и таблицы для регулярных платежей"""
    app_logger.info("Миграция: добавление полей для регулярных платежей...")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем и добавляем поле status
        try:
            cursor.execute("SELECT status FROM transactions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'actual'")
            app_logger.info("Добавлено поле 'status' в таблицу transactions")
        
        # Проверяем и добавляем поле executed_at
        try:
            cursor.execute("SELECT executed_at FROM transactions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN executed_at TEXT")
            app_logger.info("Добавлено поле 'executed_at' в таблицу transactions")
        
        # Проверяем и добавляем поле template_id
        try:
            cursor.execute("SELECT template_id FROM transactions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE transactions ADD COLUMN template_id INTEGER")
            app_logger.info("Добавлено поле 'template_id' в таблицу transactions")
        
        # Создаём таблицу recurring_templates если её нет
        cursor.execute('''
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
        ''')
        app_logger.info("Создана таблица recurring_templates")
        
        # Создаём индексы для оптимизации
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_template ON transactions(template_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_executed ON transactions(executed_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_templates_active ON recurring_templates(is_active)')
        app_logger.info("Созданы индексы для регулярных платежей")
        
        conn.commit()
        app_logger.info("Миграция завершена")


def _adjust_to_workday(date_str):
    """Переносит дату на ближайший следующий рабочий день (пн-пт)."""
    from datetime import datetime, timedelta

    date_value = datetime.strptime(date_str, '%Y-%m-%d')

    # 5 = суббота, 6 = воскресенье -> переносим на следующий рабочий день
    while date_value.weekday() >= 5:
        date_value += timedelta(days=1)

    return date_value.strftime('%Y-%m-%d')


def create_recurring_template(template_type, name, amount, day_of_month, category_id=None, 
                              comment_template="", months_ahead=12, working_days_only=0):
    """Создаёт шаблон регулярного платежа"""
    app_logger.info(f"Создание шаблона: {name}, тип={template_type}, сумма={amount}, день={day_of_month}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO recurring_templates 
            (type, name, amount, day_of_month, category_id, comment_template, months_ahead, working_days_only)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (template_type, name, amount, day_of_month, category_id, comment_template, months_ahead, working_days_only))
        conn.commit()
        
        template_id = cursor.lastrowid
        app_logger.info(f"Шаблон создан: ID={template_id}")
        
        # Генерируем плановые транзакции
        generate_planned_transactions(template_id)
        
        return template_id


def get_recurring_templates(template_type=None):
    """Получает список шаблонов регулярных платежей"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if template_type:
            cursor.execute('''
                SELECT rt.id, rt.type, rt.name, rt.amount, rt.day_of_month, rt.category_id,
                       c.name as category_name, rt.comment_template, rt.months_ahead,
                       rt.working_days_only, rt.is_active, rt.created_at
                FROM recurring_templates rt
                LEFT JOIN categories c ON c.id = rt.category_id
                WHERE rt.type = ? AND rt.is_active = 1
                ORDER BY rt.day_of_month
            ''', (template_type,))
        else:
            cursor.execute('''
                SELECT rt.id, rt.type, rt.name, rt.amount, rt.day_of_month, rt.category_id,
                       c.name as category_name, rt.comment_template, rt.months_ahead,
                       rt.working_days_only, rt.is_active, rt.created_at
                FROM recurring_templates rt
                LEFT JOIN categories c ON c.id = rt.category_id
                WHERE rt.is_active = 1
                ORDER BY rt.day_of_month
            ''')
        
        return cursor.fetchall()


def get_recurring_template_by_id(template_id):
    """Получает шаблон по ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, type, name, amount, day_of_month, category_id, 
                   comment_template, months_ahead, working_days_only, is_active, created_at
            FROM recurring_templates
            WHERE id = ?
        ''', (template_id,))
        return cursor.fetchone()


def update_recurring_template(template_id, **kwargs):
    """Обновляет шаблон регулярного платежа"""
    allowed_fields = ['type', 'name', 'amount', 'day_of_month', 'category_id', 
                     'comment_template', 'months_ahead', 'working_days_only', 'is_active']
    
    with get_connection() as conn:
        cursor = conn.cursor()

        normalized_kwargs = dict(kwargs)
        if 'template_type' in normalized_kwargs and 'type' not in normalized_kwargs:
            normalized_kwargs['type'] = normalized_kwargs.pop('template_type')

        for field, value in normalized_kwargs.items():
            if field in allowed_fields:
                cursor.execute(f'''
                    UPDATE recurring_templates 
                    SET {field} = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (value, template_id))
        
        conn.commit()
        
        # Если изменились параметры - перегенерируем плановые транзакции
        if any(f in normalized_kwargs for f in ['type', 'amount', 'day_of_month', 'category_id', 'comment_template', 'months_ahead', 'working_days_only']):
            # Удаляем старые плановые транзакции
            delete_planned_transactions(template_id)
            # Создаём новые
            generate_planned_transactions(template_id)
        
        app_logger.info(f"Шаблон ID={template_id} обновлён: {normalized_kwargs}")
        return cursor.rowcount > 0


def delete_recurring_template(template_id):
    """Удаляет шаблон и связанные плановые транзакции"""
    app_logger.info(f"Удаление шаблона ID={template_id}")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Удаляем плановые транзакции шаблона
        cursor.execute('DELETE FROM transactions WHERE template_id = ? AND status = "planned"', (template_id,))
        
        # Удаляем сам шаблон
        cursor.execute('DELETE FROM recurring_templates WHERE id = ?', (template_id,))
        
        conn.commit()
        app_logger.info(f"Шаблон ID={template_id} удалён")
        return True


def generate_planned_transactions(template_id, months=None):
    """Генерирует плановые транзакции для шаблона"""
    from datetime import datetime, timedelta
    import calendar
    
    template = get_recurring_template_by_id(template_id)
    if not template:
        app_logger.warning(f"Шаблон {template_id} не найден")
        return 0
    
    # Определяем период генерации (используем переданный months или значение из шаблона)
    months_value = months if months else template['months_ahead']
    start_date = datetime.now()
    end_date = start_date + timedelta(days=months_value * 30)
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Удаляем существующие плановые транзакции для этого шаблона
        cursor.execute('DELETE FROM transactions WHERE template_id = ? AND status = "planned"', (template_id,))
        
        # Генерируем транзакции на каждый месяц
        current_date = start_date
        count = 0
        
        while current_date <= end_date:
            # Вычисляем день месяца
            day = min(template['day_of_month'], calendar.monthrange(current_date.year, current_date.month)[1])
            trans_date = datetime(current_date.year, current_date.month, day)
            
            # Если день уже прошёл в текущем месяце - пропускаем
            if trans_date <= start_date:
                current_date = (current_date + timedelta(days=32)).replace(day=1)
                continue
            
            # Корректировка на рабочий день если нужно
            date_str = trans_date.strftime('%Y-%m-%d')
            if template['working_days_only']:
                date_str = _adjust_to_workday(date_str)
            
            # Создаём плановую транзакцию
            comment = template['comment_template'] or f"{template['name']} (запланировано)"
            
            # Получаем название категории по ID
            cursor.execute('SELECT name FROM categories WHERE id = ?', (template['category_id'],))
            cat_row = cursor.fetchone()
            if cat_row:
                category_name = cat_row['name']
            else:
                category_name = template['name'] or 'Без категории'
                app_logger.warning(
                    f"Для шаблона {template_id} не найдена категория по ID={template['category_id']}, "
                    f"используем fallback '{category_name}'"
                )
            
            cursor.execute('''
                INSERT INTO transactions (type, category, amount, comment, date, status, template_id)
                VALUES (?, ?, ?, ?, ?, 'planned', ?)
            ''', (template['type'], category_name, template['amount'], comment, date_str, template_id))
            
            count += 1
            current_date = (current_date + timedelta(days=32)).replace(day=1)
        
        conn.commit()
        app_logger.info(f"Сгенерировано {count} плановых транзакций для шаблона {template_id}")
        return count


def delete_planned_transactions(template_id, from_date=None):
    """Удаляет плановые транзакции шаблона"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if from_date:
            cursor.execute('''
                DELETE FROM transactions 
                WHERE template_id = ? AND status = 'planned' AND date >= ?
            ''', (template_id, from_date))
        else:
            cursor.execute('''
                DELETE FROM transactions 
                WHERE template_id = ? AND status = 'planned'
            ''', (template_id,))
        
        conn.commit()
        deleted = cursor.rowcount
        app_logger.info(f"Удалено {deleted} плановых транзакций шаблона {template_id}")
        return deleted


def delete_planned_transactions_in_period(template_id, start_date, end_date):
    """Удаляет плановые транзакции шаблона в указанном диапазоне дат включительно."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
                DELETE FROM transactions
                WHERE template_id = ? AND status = 'planned' AND date BETWEEN ? AND ?
            ''',
            (template_id, start_date, end_date),
        )
        conn.commit()
        deleted = cursor.rowcount
        app_logger.info(
            f"Удалено {deleted} плановых транзакций шаблона {template_id} в период {start_date}..{end_date}"
        )
        return deleted


def get_planned_transactions_due():
    """Получает просроченные плановые транзакции"""
    from datetime import datetime
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.type, t.category, t.amount, t.comment, t.date, t.template_id,
                   rt.name as template_name
            FROM transactions t
            LEFT JOIN recurring_templates rt ON t.template_id = rt.id
            WHERE t.status = 'planned' AND t.date < ?
            ORDER BY t.date
        ''', (today,))
        return cursor.fetchall()


def get_planned_transactions_by_template(template_id):
    """Получает плановые транзакции шаблона"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, type, category, amount, comment, date, status, template_id, executed_at
            FROM transactions
            WHERE template_id = ? AND status = 'planned'
            ORDER BY date
        ''', (template_id,))
        return cursor.fetchall()


def execute_planned_transaction(transaction_id, auto_percent=0, capital_account_id=None):
    """Исполняет плановую транзакцию (превращает в фактическую)"""
    app_logger.info(
        f"Исполнение плановой транзакции ID={transaction_id}, "
        f"auto_percent={auto_percent}, capital_account_id={capital_account_id}"
    )
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Получаем плановую транзакцию
            cursor.execute('''
                SELECT id, type, category, amount, comment, date, template_id
                FROM transactions
                WHERE id = ? AND status = 'planned'
            ''', (transaction_id,))
            planned = cursor.fetchone()
            
            if not planned:
                app_logger.warning(f"Плановая транзакция {transaction_id} не найдена")
                return False
            
            # Обновляем транзакцию: меняем статус на actual
            cursor.execute('''
                UPDATE transactions 
                SET status = 'actual', executed_at = datetime('now')
                WHERE id = ?
            ''', (transaction_id,))
            
            # Обновляем баланс основного счёта
            if planned['type'] == 'income':
                apply_auto_capital = (
                    auto_percent > 0
                    and capital_account_id
                    and planned['category'] != 'Остаток'
                )
                
                if apply_auto_capital:
                    capital_amount = planned['amount'] * (auto_percent / 100)
                    main_amount = planned['amount'] - capital_amount
                    
                    # Проверяем, существует ли счёт капитала
                    cursor.execute(
                        'SELECT id, name FROM capital_accounts WHERE id = ? AND is_active = 1',
                        (capital_account_id,)
                    )
                    capital_account = cursor.fetchone()
                    
                    if capital_account:
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ? WHERE id = 1',
                            (main_amount,)
                        )
                        cursor.execute('''
                            INSERT INTO transfers (
                                from_account_id, to_account_id, amount,
                                transaction_id, date, comment, is_active
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                        ''', (
                            1,
                            capital_account_id,
                            capital_amount,
                            transaction_id,
                            planned['date'],
                            f"Автоотчисление {auto_percent}% от планового дохода: {planned['comment']}"
                        ))
                        cursor.execute('''
                            UPDATE capital_accounts
                            SET balance = balance + ?, updated_at = datetime("now")
                            WHERE id = ? AND is_active = 1
                        ''', (capital_amount, capital_account_id))
                    else:
                        app_logger.warning(
                            f"Счёт капитала ID={capital_account_id} не найден или неактивен, "
                            "плановый доход будет зачислен полностью на основной счёт"
                        )
                        cursor.execute(
                            'UPDATE accounts SET balance = balance + ? WHERE id = 1',
                            (planned['amount'],)
                        )
                else:
                    cursor.execute(
                        'UPDATE accounts SET balance = balance + ? WHERE id = 1',
                        (planned['amount'],)
                    )
            else:  # expense
                cursor.execute('UPDATE accounts SET balance = balance - ? WHERE id = 1', (planned['amount'],))
            
            # Инвалидируем кэш
            _invalidate_cache()
            
            conn.commit()
            app_logger.info(f"Транзакция {transaction_id} исполнена")
            return True
            
        except Exception as e:
            conn.rollback()
            app_logger.error(f"Ошибка исполнения транзакции {transaction_id}: {e}", exc_info=True)
            return False


def execute_all_planned_transactions(auto_percent=0, capital_account_id=None):
    """Исполняет все просроченные плановые транзакции"""
    app_logger.info(
        "Исполнение просроченных плановых транзакций "
        f"(auto_percent={auto_percent}, capital_account_id={capital_account_id})"
    )
    
    due_transactions = get_planned_transactions_due()
    count = 0
    
    for trans in due_transactions:
        if execute_planned_transaction(trans['id'], auto_percent, capital_account_id):
            count += 1
    
    app_logger.info(f"Исполнено {count} плановых транзакций")
    return count


def get_projected_balance(end_date=None):
    """Рассчитывает прогнозируемый баланс с учётом плана и остатка бюджетов"""
    from datetime import datetime
    
    if not end_date:
        # По умолчанию - конец текущего месяца
        today = datetime.now()
        last_day = datetime(today.year, today.month, 28)  # 28-го числа точно есть
        # Добавляем дни до конца месяца
        import calendar
        last_day = datetime(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        end_date = last_day.strftime('%Y-%m-%d')
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Текущий баланс
        cursor.execute("SELECT balance FROM accounts WHERE id = 1")
        current_balance = cursor.fetchone()[0] or 0
        
        # Запланированные доходы до end_date
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE status = 'planned' AND type = 'income' AND date <= ?
        ''', (end_date,))
        planned_income = cursor.fetchone()[0] or 0
        
        # Запланированные расходы до end_date
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE status = 'planned' AND type = 'expense' AND date <= ?
        ''', (end_date,))
        planned_expense = cursor.fetchone()[0] or 0

        start_of_month = today[:8] + '01'

        # Уже исполненные регулярные доходы текущего месяца.
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE template_id IS NOT NULL
              AND type = 'income'
              AND date >= ?
              AND date <= ?
              AND (status = 'actual' OR status IS NULL)
        ''', (start_of_month, today))
        executed_planned_income = cursor.fetchone()[0] or 0

        # Уже исполненные регулярные расходы текущего месяца.
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE template_id IS NOT NULL
              AND type = 'expense'
              AND date >= ?
              AND date <= ?
              AND (status = 'actual' OR status IS NULL)
        ''', (start_of_month, today))
        executed_planned_expense = cursor.fetchone()[0] or 0
        
        # === Учёт бюджетов: в прогноз попадает только оставшаяся часть бюджета ===
        cursor.execute('''
            SELECT b.amount, b.period, c.name as category_name
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
        ''')
        budgets = cursor.fetchall()
        
        total_budgets = 0
        current_expenses = 0
        for budget in budgets:
            monthly_amount = _get_budget_monthly_limit(
                budget['amount'] or 0,
                budget['period'] if 'period' in budget.keys() else 'monthly',
            )
            
            total_budgets += monthly_amount
            
            # Фактические расходы уже уменьшили current_balance, поэтому из бюджета
            # учитываем только то, что ещё осталось потратить в этом месяце.
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as spent
                FROM transactions
                WHERE type = 'expense'
                  AND category = ?
                  AND date >= ?
                  AND date <= ?
                  AND (status = 'actual' OR status IS NULL)
            ''', (budget['category_name'], start_of_month, today))
            spent = cursor.fetchone()[0] or 0
            current_expenses += min(spent, monthly_amount)

        budget_remaining = max(total_budgets - current_expenses, 0)
        combined_pending_expense = planned_expense + budget_remaining
        combined_executed_expense = executed_planned_expense + current_expenses

        projected_balance = current_balance + planned_income - planned_expense - budget_remaining

        app_logger.debug(
            "Forecast calc: current=%s planned_income=%s planned_expense=%s "
            "executed_planned_income=%s executed_planned_expense=%s total_budgets=%s "
            "current_expenses=%s budget_remaining=%s combined_pending_expense=%s "
            "combined_executed_expense=%s projected=%s end_date=%s",
            round(current_balance, 2),
            round(planned_income, 2),
            round(planned_expense, 2),
            round(executed_planned_income, 2),
            round(executed_planned_expense, 2),
            round(total_budgets, 2),
            round(current_expenses, 2),
            round(budget_remaining, 2),
            round(combined_pending_expense, 2),
            round(combined_executed_expense, 2),
            round(projected_balance, 2),
            end_date,
        )
        
        return {
            'current_balance': round(current_balance, 2),
            'planned_income': round(planned_income, 2),
            'planned_expense': round(planned_expense, 2),
            'executed_planned_income': round(executed_planned_income, 2),
            'executed_planned_expense': round(executed_planned_expense, 2),
            'monthly_budget': round(total_budgets, 2),
            'total_budgets': round(total_budgets, 2),
            'current_expenses': round(current_expenses, 2),
            'budget_remaining': round(budget_remaining, 2),
            'combined_pending_expense': round(combined_pending_expense, 2),
            'combined_executed_expense': round(combined_executed_expense, 2),
            'projected': round(projected_balance, 2),
            'projected_balance': round(projected_balance, 2),
            'end_date': end_date
        }


def get_budget_status(category_id: int = None):
    """Получает статус бюджетов по категориям"""
    from datetime import datetime
    
    # Текущий месяц
    today = datetime.now()
    start_of_month = today.replace(day=1).strftime('%Y-%m-%d')
    end_of_month = today.strftime('%Y-%m-%d')
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем все бюджеты с категориями
        cursor.execute('''
            SELECT b.id, b.category_id, c.name as category_name, c.icon, c.color, b.amount as budget_amount, b.period
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
        ''')
        budgets = cursor.fetchall()
        
        result = []
        for budget in budgets:
            budget_amount = _get_budget_monthly_limit(
                budget['budget_amount'] or 0,
                budget['period'] if 'period' in budget.keys() else 'monthly',
            )
            # Получаем фактические расходы за месяц
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as spent
                FROM transactions
                WHERE type = 'expense'
                  AND category = ?
                  AND date >= ?
                  AND date <= ?
                  AND (status = 'actual' OR status IS NULL)
            ''', (budget['category_name'], start_of_month, end_of_month))
            spent = cursor.fetchone()[0] or 0
            
            remaining = budget_amount - spent
            percent = (spent / budget_amount * 100) if budget_amount > 0 else 0
            
            result.append({
                'category_id': budget['category_id'],
                'category_name': budget['category_name'],
                'icon': budget['icon'],
                'color': budget['color'],
                'budget_amount': round(budget_amount, 2),
                'spent': round(spent, 2),
                'remaining': round(remaining, 2),
                'percent': round(percent, 1),
                'over_budget': remaining < 0
            })
        
        return result


if __name__ == "__main__":
    init_db()
    app_logger.info("База данных инициализирована")



