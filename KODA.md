# KODA.md — Краткая справка для ИИ-ассистента

> **Версия:** 2.0  
> **Дата:** 30 марта 2026  
> **Проект:** Домашняя бухгалтерия

> ⚠️ **Полная документация:** см. папку `docs/`

---

## Быстрый старт

```bash
# Запуск
python run.py

# Проверка синтаксиса
python -c "from views.transactions_view import TransactionsView; print('OK')"
```

---

## Обзор проекта

**Домашняя бухгалтерия** — десктопное приложение для учёта личных финансов, разработанное на Python. Поддерживается совместно человеком и ИИ.

### Основные возможности

- Учёт доходов и расходов
- Категории транзакций с иконками и цветами
- Бюджетирование (месячное/годовое)
- Управление капиталом (несколько счетов)
- Автоматические отчисления в капитал с каждого дохода
- Переводы между счетами
- История операций
- Экспорт данных в CSV
- Автоматические бэкапы
- Логирование

### Технологический стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.10+ |
| GUI | CustomTkinter |
| База данных | SQLite |
| Асинхронность | Asyncio |

---

## Структура проекта

```
finance_app/
├── run.py                 # Точка входа в приложение
├── core.py                # Ядро: работа с БД, SQL-запросы, бизнес-логика
├── gui.py                 # Главное окно приложения (AsyncApp)
├── models.py              # Модели данных (dataclasses)
├── init_db_only.py        # Скрипт инициализации БД
├── migrate_capital_ids.py # Миграция ID счетов капитала
├── tree.py                # Древовидные структуры
│
├── views/                 # Вкладки интерфейса
│   ├── main_view.py       # Главное представление
│   ├── transactions_view.py
│   ├── categories_view.py
│   ├── budgets_view.py
│   ├── capital_view.py
│   ├── reports_view.py
│   └── settings_view.py
│
├── services/              # Бизнес-логика
│   ├── transaction_service.py
│   ├── category_service.py
│   ├── budget_service.py
│   └── sync_service.py
│
├── widgets/               # Переиспользуемые виджеты
│   ├── amount_entry.py
│   ├── category_selector.py
│   ├── date_picker.py
│   └── modern_table.py
│
├── utils/                 # Утилиты
│   ├── logger.py          # Логирование
│   ├── backup.py          # Резервное копирование
│   ├── cache.py           # Кэширование
│   ├── formatters.py      # Форматирование данных
│   └── async_helper.py    # Помощник для async операций
│
├── backups/               # Автоматические бэкапы БД
├── logs/                  # Логи приложения
└── docs/                  # Документация
```

---

## Запуск приложения

### Команда запуска

```bash
python run.py
```

Приложение запускается из корневой директории проекта. Автоматически:
1. Инициализирует базу данных (создаёт таблицы, если их нет)
2. Создаёт бэкап при запуске
3. Запускает GUI-приложение

### Запуск в режиме разработки

```bash
# Активировать виртуальное окружение (если используется)
# Windows:
myenv\Scripts\activate

# Запуск
python run.py
```

---

## Архитектура приложения

### Слои приложения

```
┌─────────────────────────────────────────────────────────┐
│ GUI (views/)                                            │
│ Пользовательский интерфейс, вкладки                     │
├─────────────────────────────────────────────────────────┤
│ Services (services/)                                    │
│ Бизнес-логика, подписки на изменения                    │
├─────────────────────────────────────────────────────────┤
│ Core (core.py)                                          │
│ Работа с БД, SQL-запросы                                │
├─────────────────────────────────────────────────────────┤
│ Database (SQLite)                                       │
│ finance.db                                              │
└─────────────────────────────────────────────────────────┘
```

### Паттерны проектирования

#### 1. Наблюдатель (Observer)

Обновление интерфейса при изменении данных:

```python
# Вкладка подписывается на изменения
self.transaction_service.add_listener(self.on_data_changed)

# Метод обновления
def on_data_changed(self):
    self.load_data()  # Перезагружаем данные
```

#### 2. Сервисный слой

Отделение бизнес-логики от GUI:
- `TransactionService` — работа с транзакциями
- `CategoryService` — работа с категориями
- бюджеты в актуальной архитектуре обслуживаются через `TransactionService` и `core.py`

#### 3. Data Access Object

`core.py` содержит все SQL-запросы и методы работы с БД.

---

## Структура базы данных

### Таблицы

| Таблица | Назначение |
|---------|------------|
| `transactions` | Транзакции (доходы/расходы) |
| `categories` | Категории транзакций |
| `accounts` | Основной счёт (всегда ID=1) |
| `capital_accounts` | Счета капитала (ID ≥ 100) |
| `transfers` | Переводы между счетами |
| `budgets` | Бюджеты категорий |

### Особенности ID счетов

| Тип счёта | Таблица | ID | Примечание |
|-----------|---------|-----|------------|
| **Основной счёт** | `accounts` | **1** | Создаётся один раз при инициализации |
| **Счета капитала** | `capital_accounts` | 100, 101, 102... | Пользователь добавляет сам |

**Важно:** При удалении транзакции с автоотчислением средства возвращаются на тот счёт капитала, куда был сделан перевод (`transfer['to_account_id']`), а не на основной счёт.

---

## Основные методы core.py

### Транзакции

```python
get_transactions_by_period(start_date, end_date)
get_income_by_category(start_date, end_date)
get_expenses_by_category(start_date, end_date)
delete_transaction(transaction_id)
add_income_with_capital(amount, category, comment, date, auto_percent, capital_account_id)
add_expense(amount, category, comment, date)
update_transaction(transaction_id, field, value)  # Пересчитывает балансы!
```

### Капитал

```python
get_capital_contributions_for_period(start_date, end_date)
get_total_capital()
get_capital_accounts(include_inactive=False)
get_default_capital_account()
sync_accounts_with_transactions()  # Синхронизация балансов после импорта
```

### Баланс

```python
get_balance()  # Возвращает (main_balance, income, expense)
```

### Сверка баланса (Ревизия)

```python
# Источники для сверки
get_reconciliation_sources()  # Все источники (включая is_active=0)
add_reconciliation_source(name, balance)  # Добавить источник
update_reconciliation_source(source_id, name=..., balance=...)  # Обновить
delete_reconciliation_source(source_id)  # Мягкое удаление (is_active=0)
get_total_real_balance()  # Сумма активных источников

# Сверки
get_last_reconciliation()  # Последняя сверка
save_reconciliation(real_balance, program_balance, difference, transaction_id)  # Сохранить
get_reconciliations_history(limit=50)  # История сверок
delete_reconciliation(recon_id)  # Удалить сверку
```

**Таблицы БД:**
- `reconciliation_sources` — источники (id, name, balance, is_active)
- `reconciliations` — история сверок (id, real_balance, program_balance, difference, adjustment_transaction_id)

---

## Правила разработки

### Принципы работы с БД

1. **Бэкап перед изменениями БД** — обязательно создавать бэкап перед любой операцией, изменяющей данные:
   ```python
   from utils.backup import DatabaseBackup
   DatabaseBackup().create_backup(reason='ai_change')
   ```

2. **Транзакции** — все операции с БД должны быть обёрнуты в транзакции:
   ```python
   cursor.execute("BEGIN TRANSACTION")
   try:
       # операции
       conn.commit()
   except Exception as e:
       conn.rollback()
   ```

### Важные константы

- **Основной счёт:** `accounts.id = 1` (всегда)
- **Счета капитала:** `capital_accounts.id = 100, 101, 102...`
- **Автоотчисления:** работают через `core.py` → `add_income_with_capital()`
- **Обновление UI:** через `notify_listeners()` в сервисах

### Стиль кода

- Использование dataclasses для моделей (`models.py`)
- Логирование через `utils.logger.app_logger`
- Асинхронные операции через asyncio
- Типизация с использованием `typing.Optional`

---

## Утилиты

### Резервное копирование

```python
from utils.backup import DatabaseBackup
backup = DatabaseBackup()
backup.create_backup(reason="startup")  # при запуске
backup.create_backup(reason="shutdown") # при закрытии
backup.create_backup(reason="ai_change") # перед изменениями
```

Бэкапы сохраняются в директорию `backups/` с timestamp в имени файла.

### Логирование

```python
from utils.logger import app_logger

app_logger.info("Сообщение")
app_logger.debug("Отладочное сообщение")
app_logger.warning("Предупреждение")
app_logger.error("Ошибка")
```

Логи сохраняются в директорию `logs/`.

---

## Документация

Полная документация в директории `docs/`:

| Файл | Содержание |
|------|------------|
| `README.md` | Главная страница |
| `PROJECT_STATE.md` | Текущее состояние проекта |
| `DECISIONS.md` | Зафиксированные решения по логике |
| `ARCHITECTURE.md` | Архитектура и БД |
| `API.md` | Основные методы |
| `CODE_STYLE.md` | Правила стиля кода |
| `AI_GUIDE.md` | Инструкция для ИИ |
| `ERROR_LEARNING.md` | Грабли и уроки |
| `CHANGELOG.md` | История версий |
| `sessions/*.md` | Журнал рабочих сессий |

---

## Быстрый Вход Для Новой Модели

Если чат новый или модель не знает контекст, читать в таком порядке:

1. `KODA.md`
2. `docs/PROJECT_STATE.md`
3. `docs/DECISIONS.md`
4. последнюю запись в `docs/sessions/`
5. `docs/ERROR_LEARNING.md`

## Команды для разработки

```bash
# Запуск приложения
python run.py

# Создание бэкапа
python -c "from utils.backup import DatabaseBackup; DatabaseBackup().create_backup(reason='manual')"

# Инициализация БД (только)
python init_db_only.py

# Миграция ID капитала
python migrate_capital_ids.py
```

---

## Часто задаваемые вопросы

### Как добавить новую категорию?

```python
from models import Category
# Используйте CategoryService или напрямую core.add_category()
```

### Как работают автоотчисления?

При добавлении дохода можно указать процент отчисления в капитал и ID целевого счёта капитала. Функция `add_income_with_capital()` автоматически:
1. Создаёт транзакцию дохода
2. Зачисляет основную сумму на основной счёт
3. Создаёт перевод на счёт капитала
4. Обновляет балансы обоих счетов

### Как удалить транзакцию?

```python
core.delete_transaction(transaction_id)
```

При удалении会自动:
- Возвращаются средства на исходный счёт капитала
- Перевод помечается как неактивный
- Баланс основного счёта корректируется
