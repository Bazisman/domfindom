# 🔌 API Сервисов

## TransactionService

Главный сервис для работы с транзакциями.

### Методы

#### Транзакции

```python
# Получить все транзакции
transactions = service.get_transactions(limit=1000, period="month")

# Получить транзакции за период
transactions = service.get_transactions_by_date_range(start_date, end_date)

# Добавить транзакцию
success = service.add_transaction(transaction)

# Обновить транзакцию
service.update_transaction(tid, field, value)

# Удалить транзакцию
success = service.delete_transaction(tid)
```

#### Счета

```python
# Получить основной счёт
account = service.get_main_account()

# Получить баланс счёта
balance = service.get_account_balance(account_id)

# Получить все счета капитала
capital_accounts = service.get_capital_accounts()

# Добавить счёт капитала
account_id = service.add_capital_account(name, balance, icon, color)

# Обновить счёт капитала
service.update_capital_account(account_id, name=name, icon=icon, color=color)

# Удалить счёт капитала
service.delete_capital_account(account_id)

# Установить основной счёт капитала
service.set_default_capital_account(account_id)
```

#### Переводы

```python
# Перевод между счетами
success = service.transfer_money(from_id, to_id, amount, date, comment)

# История переводов
transfers = service.get_transfers_history(limit=100)
```

#### Статистика

```python
# Получить статистику за месяц
stats = service.get_monthly_stats(year, month)
# Возвращает: {'income': float, 'expense': float, 'capital': float, 'year': int, 'month': int}
```

#### Автоотчисления

```python
# Настройки автоотчислений
service.set_auto_capital_settings(enabled, percent)

# Проверить бюджет
result = service.check_budget(category, amount)
# Возвращает: (over, spent, budget) или None
```

#### Подписки

```python
# Подписаться на изменения
service.add_listener(callback)

# Отписаться
service.remove_listener(callback)

# Уведомить всех
service.notify_listeners()
```

---

## CategoryService

Сервис для работы с категориями.

### Методы

```python
# Получить все категории
categories = service.get_all_categories()

# Получить названия категорий
names = service.get_category_names(type=None)
# type: "income", "expense", "both" или None (все)

# Получить категорию по имени
category = service.get_category_by_name(name)

# Добавить категорию
category_id = service.add_category(name, type, color, icon)

# Обновить категорию
service.update_category(category_id, name, type, color, icon)

# Удалить категорию
service.delete_category(category_id)
```

---

## Бюджеты

Работа с бюджетами в актуальной архитектуре проходит через `TransactionService`.

### Методы

```python
# Получить все бюджеты
budgets = transaction_service.get_budgets()

# Установить бюджет
transaction_service.set_budget(category_id, amount, period)

# Удалить бюджет
transaction_service.delete_budget(budget_id)

# Получить статус бюджета
status = transaction_service.get_budget_status(category_id)
```

### Семантика статуса бюджета

- `monthly` и `yearly` бюджеты в `status` показывают обычный лимит периода и остаток до него.
- `daily` бюджет в `status` показывает ожидаемый итог категории к концу текущего месяца:
  - `spent` — уже потрачено по категории на текущую дату;
  - `budget_amount = spent + daily_amount * remaining_days_including_today`;
  - `remaining = daily_amount * remaining_days_including_today`.
- В семейном режиме та же логика применяется к общему факту семьи по категории, а не к личным тратам текущего пользователя.

---

## Модели данных

### Transaction

```python
@dataclass
class Transaction:
    type: str        # "income" или "expense"
    category: str    # Название категории
    amount: float    # Сумма
    comment: str     # Комментарий
    date: str        # Дата (YYYY-MM-DD)
```

### Category

```python
@dataclass
class Category:
    id: int
    name: str
    type: str        # "income", "expense" или "both"
    color: str       # #RRGGBB
    icon: str        # Эмодзи
    is_active: int   # 1 или 0
```

### Budget

```python
@dataclass
class Budget:
    id: int
    category_id: int
    amount: float
    period: str      # "monthly" или "yearly"
```

---

## Пример использования

```python
from services.transaction_service import TransactionService
from services.category_service import CategoryService
from models import Transaction

# Создание сервисов
transaction_service = TransactionService()
category_service = CategoryService()

# Добавление транзакции
transaction = Transaction(
    type="expense",
    category="Еда",
    amount=1500.00,
    comment="Продукты",
    date="2026-03-28"
)
transaction_service.add_transaction(transaction)

# Подписка на изменения
def on_data_changed():
    print("Данные изменились!")

transaction_service.add_listener(on_data_changed)
```
