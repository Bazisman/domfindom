# 📝 Code Style — Правила стиля кода

> **Версия:** 1.0  
> **Дата:** 30 марта 2026

---

## 1. Именование

### Функции и методы
```python
# ✓ Правильно
def get_balance():
def add_transaction():
def calculate_total():

# ✗ Неправильно
def GetBalance():
def addTransaction():
def calculate_total_amounts():
```

### Классы
```python
# ✓ Правильно
class TransactionView:
class CapitalAccount:
class ReconcileWindow:

# ✗ Неправильно
class transaction_view:
class capital_account:
class ReconcileWindowClass:
```

### Константы
```python
# ✓ Правильно
MAX_ITEMS = 500
CACHE_TTL = 60
DEFAULT_COLOR = "gray90"

# ✗ Неправильно
maxItems = 500
cache_ttl = 60
default_color = "gray90"
```

### Приватные методы
```python
# ✓ Правильно
def _internal_method():
def _validate_input():

# ✗ Неправильно
def __private_method():
def internalMethod():
```

---

## 2. Импорты

```python
# ✓ Правильно — группировка: stdlib → third-party → local
import os
import sys
from datetime import datetime

import customtkinter as ctk

from core import get_connection, get_balance
from models import Transaction, Category

# ✗ Неправильно — вперемешку
import os
from core import get_balance
import customtkinter as ctk
from datetime import datetime
```

---

## 3. Docstrings

### Для функций
```python
def get_balance():
    """Возвращает текущий баланс основного счёта.
    
    Returns:
        tuple: (main_balance, income, expense)
    """
    pass
```

### Для классов
```python
class TransactionView(ctk.CTkFrame):
    """Вкладка операций.
    
    Отображает список транзакций и позволяет
    добавлять/редактировать/удалять записи.
    """
    pass
```

---

## 4. Type Hints

```python
# ✓ Правильно
def get_balance() -> tuple[float, float, float]:
def add_transaction(transaction: Transaction) -> int:
def update_item(item_id: int, name: str = None) -> bool:

# ✗ Неправильно
def get_balance():
def add_transaction(transaction):
```

---

## 5. Паттерны GUI

### Создание вкладки
```python
class MyView(ctk.CTkFrame):
    def __init__(self, parent, transaction_service, category_service):
        super().__init__(parent)
        self.transaction_service = transaction_service
        self.category_service = category_service
        
        # Подписка на изменения
        self.transaction_service.add_listener(self.on_data_changed)
        
        # Создание UI
        self.setup_ui()
        
        # Загрузка данных
        self.load_data()
    
    def on_data_changed(self):
        """Обновление при изменении данных."""
        self.load_data()
    
    def setup_ui(self):
        """Создание элементов интерфейса."""
        pass
    
    def load_data(self):
        """Загрузка данных из БД."""
        pass
```

### Inline-форма добавления
```python
def setup_add_form(self):
    form = ctk.CTkFrame(self)
    form.pack(fill="x", padx=20, pady=10)
    
    self.name_entry = ctk.CTkEntry(form, width=150)
    self.name_entry.pack(side="left", padx=5)
    
    self.amount_entry = ctk.CTkEntry(form, width=100)
    self.amount_entry.pack(side="left", padx=5)
    
    ctk.CTkButton(
        form, text="+", 
        command=self.add_item
    ).pack(side="left", padx=5)

def add_item(self):
    name = self.name_entry.get().strip()
    amount = self.amount_entry.get().strip()
    # ... валидация и сохранение
```

### Сохранение при потере фокуса
```python
entry.bind("<FocusOut>", lambda e, id=item_id: self.save_item(id, entry.get()))
entry.bind("<Return>", lambda e, id=item_id: self.save_item(id, entry.get()))
```

---

## 6. Работа с БД

### Чтение данных
```python
def get_items() -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, balance FROM table WHERE is_active = 1")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

### Запись данных (безопасная)
```python
def update_item(item_id: int, **kwargs) -> bool:
    """Обновляет элемент.
    
    Args:
        item_id: ID элемента
        **kwargs: Поля для обновления (только name, balance)
    """
    allowed_fields = {'name', 'balance'}  # БЕЗОПАСНЫЕ ПОЛЯ
    
    with get_connection() as conn:
        cursor = conn.cursor()
        for field, value in kwargs.items():
            if field in allowed_fields:
                cursor.execute(
                    f"UPDATE table SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
                    (value, item_id)
                )
        conn.commit()
    return True
```

---

## 7. Логирование

```python
from utils.logger import app_logger

# Использование
app_logger.info("Операция выполнена")
app_logger.warning("Что-то пошло не так")
app_logger.error("Ошибка", exc_info=True)  # с трейсбеком
app_logger.debug("Отладочная информация")
```

---

## 8. Цвета CustomTkinter

```python
# ✓ Правильно — имена цветов
fg_color=("gray10", "gray90")
hover_color=("#3B8ED0", "#36719F")

# ✗ Неправильно — hex-цвета с #
fg_color=("#gray10", "#gray90")
hover_color=("#3B8ED0")
```

---

## 9. Коммиты и сообщения

Если бы использовали git:

```
feat: добавить сверку баланса
fix: исправить сохранение суммы в источниках
refactor: объединить документацию
docs: обновить CHANGELOG
```

---

## 10. Чеклист перед PR

- [ ] Проверить синтаксис: `python -c "from X import Y"`
- [ ] Запустить приложение
- [ ] Проверить что всё работает
- [ ] Проверить логи на ошибки
- [ ] Обновить документацию если нужно

---

*Обновлено: 2026-03-30*
