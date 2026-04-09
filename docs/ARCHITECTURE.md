# 🏗️ Архитектура

## Слои приложения

```
┌─────────────────────────────────────────────────────────┐
│ GUI (views/)                                            │
│ Пользовательский интерфейс, вкладки                     │
├─────────────────────────────────────────────────────────┤
│ Services (services/)                                    │
│ Бизнес-логика, подписки                                 │
├─────────────────────────────────────────────────────────┤
│ Core (core.py)                                          │
│ Работа с БД, SQL-запросы                                │
├─────────────────────────────────────────────────────────┤
│ Database (SQLite)                                       │
│ finance.db                                              │
└─────────────────────────────────────────────────────────┘
```

## Паттерны проектирования

### 1. Слушатель (Observer)

Обновление интерфейса при изменении данных:

```python
# Вкладка подписывается
self.transaction_service.add_listener(self.on_data_changed)

# Метод обновления
def on_data_changed(self):
    self.load_data()  # Перезагружаем данные
```

### 2. Сервисный слой

Отделение бизнес-логики от GUI:

- `TransactionService` — работа с транзакциями
- `CategoryService` — работа с категориями
- бюджеты в актуальной архитектуре обслуживаются через `TransactionService` и `core.py`

### 3. Data Access Object

`core.py` содержит все SQL-запросы.

#### Основные методы core.py

```python
# Транзакции
get_transactions_by_period(start_date, end_date)
get_income_by_category(start_date, end_date)
get_expenses_by_category(start_date, end_date)
delete_transaction(transaction_id)

# Капитал
get_capital_contributions_for_period(start_date, end_date)
get_total_capital()

# Баланс
get_balance()  # Возвращает (main_balance, income, expense)
```

**Важно:** При удалении транзакции с автоотчислением средства возвращаются на тот счёт капитала, куда был сделан перевод (`transfer['to_account_id']`), а не на текущий основной счёт.

---

## Структура базы данных

### Особенности ID счетов

| Тип счёта | Таблица | ID | Примечание |
|-----------|---------|-----|------------|
| **Основной счёт (бюджет)** | `accounts` | **1** | Создаётся один раз |
| **Счета капитала** | `capital_accounts` | 100, 101, 102... | Пользователь добавляет сам |
| **Шаблоны регулярных платежей** | `recurring_templates` | 1, 2, 3... | ID генерируются автоматически |

**Преимущества системы ID:**
- ID никогда не пересекаются
- Не нужны дополнительные поля для определения типа счёта
- Легко отлаживать

---

### Таблицы базы данных

#### `transactions` — транзакции

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | ID транзакции |
| type | TEXT | 'income' или 'expense' |
| category | TEXT | Название категории |
| amount | REAL | Сумма |
| comment | TEXT | Комментарий |
| date | TEXT | Дата (YYYY-MM-DD) |
| created_at | TEXT | Дата создания |
| status | TEXT | 'actual' (фактическая) или 'planned' (плановая) |
| executed_at | TEXT | дата исполнения (NULL для planned) |
| template_id | INTEGER | ссылка на шаблон (NULL для обычных транзакций) |

#### `categories` — категории

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | ID категории |
| name | TEXT | Название |
| type | TEXT | 'income', 'expense', 'both' |
| color | TEXT | Цвет (#RRGGBB) |
| icon | TEXT | Эмодзи иконка |
| is_active | INTEGER | 1 - активна, 0 - удалена |

#### `budgets` — бюджеты

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | ID бюджета |
| category_id | INTEGER | Ссылка на categories.id |
| amount | REAL | Сумма бюджета |
| period | TEXT | 'monthly' или 'yearly' |

#### `accounts` — основной счёт

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | **Всегда 1** |
| name | TEXT | Название ('Основной счёт') |
| type | TEXT | **Всегда 'main'** |
| balance | REAL | Текущий баланс |
| currency | TEXT | Валюта (RUB) |
| is_active | INTEGER | 1 - активен |
| created_at | TEXT | Дата создания |
| updated_at | TEXT | Дата обновления |

#### `capital_accounts` — счета капитала

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | ID счёта (100, 101, 102...) |
| name | TEXT | Название |
| balance | REAL | Текущий баланс |
| currency | TEXT | Валюта (RUB) |
| icon | TEXT | Эмодзи иконка |
| color | TEXT | Цвет (#RRGGBB) |
| is_default | INTEGER | 1 - основной счёт для отчислений |
| is_active | INTEGER | 1 - активен |
| created_at | TEXT | Дата создания |
| updated_at | TEXT | Дата обновления |

#### `transfers` — переводы

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | ID перевода |
| from_account_id | INTEGER | ID счёта отправителя |
| to_account_id | INTEGER | ID счёта получателя |
| amount | REAL | Сумма |
| transaction_id | INTEGER | Ссылка на транзакцию |
| date | TEXT | Дата |
| comment | TEXT | Комментарий |
| is_active | INTEGER | 1 - активен, 0 - отменён |
| created_at | TEXT | Дата создания |
