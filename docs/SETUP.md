# ⚙️ Установка и настройка

## Требования

- Python 3.10 или выше
- Windows 7 и выше

## Установка

### 1. Клонировать репозиторий

```bash
git clone <repo_url>
cd finance_app
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

Основные зависимости:
- `customtkinter` — GUI фреймворк
- `tkinter` — встроен в Python
- `ttk` — встроен в Python

### 3. Запустить приложение

```bash
cd src
python run.py
```

---

## Структура файлов

```
finance_app/
├── src/                         # Исходный код приложения
│   ├── run.py                   # Точка входа
│   ├── gui.py                   # Главное окно
│   ├── core.py                  # Работа с БД
│   ├── models.py                # Модели данных
│   │
│   ├── views/                   # Вкладки интерфейса
│   │   ├── transactions_view.py # Операции (доходы/расходы)
│   │   ├── categories_view.py   # Категории
│   │   ├── budgets_view.py      # Бюджеты
│   │   ├── capital_view.py      # Капитал (счета накоплений)
│   │   ├── settings_view.py     # Настройки
│   │   └── main_view.py         # Главная вкладка
│   │
│   ├── services/                # Бизнес-логика
│   │   ├── transaction_service.py
│   │   ├── category_service.py
│   │   └── budget_service.py
│   │
│   ├── widgets/                 # Переиспользуемые виджеты
│   │   ├── amount_entry.py      # Поле ввода суммы
│   │   ├── date_picker.py       # Выбор даты
│   │   ├── category_selector.py # Выбор категории
│   │   └── calendar.py          # Календарь
│   │
│   ├── utils/                   # Утилиты
│   │   ├── logger.py            # Логирование
│   │   └── backup.py            # Бэкапы
│   │
│   ├── backups/                 # Бэкапы БД
│   └── logs/                    # Логи приложения
│
├── docs/                        # Документация
│   ├── README.md                # Главная страница
│   ├── ARCHITECTURE.md          # Архитектура и БД
│   ├── FEATURES.md              # Ключевые функции
│   ├── API.md                   # API сервисов
│   ├── SETUP.md                 # Установка и настройка
│   └── CHANGELOG.md             # История изменений
│
├── finance.db                   # База данных SQLite
├── CHANGELOG.md                 # История изменений (ссылка на docs/)
└── PROJECT_DOCS.md              # Основная документация (устарел)
```

---

## Настройка

### База данных

При первом запуске создаётся `finance.db` со структурой:
- Таблицы транзакций, категорий, бюджетов
- Основной счёт (id=1)
- Начальные категории

### Логирование

Логи сохраняются в папку `logs/`:
- `finance_app.log` — основной лог
- `finance_error.log` — ошибки

Настройки в `utils/logger.py`:
- Максимальный размер файла: 10 MB
- Количество бэкапов: 5

### Бэкапы

Бэкапы создаются автоматически:
- При запуске (`startup`)
- При закрытии (`shutdown`)

Хранятся в папке `backups/`:
- Последних 10 штук
- Формат: `finance_YYYYMMDD_HHMMSS_reason.db`

---

## Сброс до заводских настроек

### Через интерфейс

Настройки → Сбросить до заводских настроек

### Вручную

```bash
cd src
python -c "
import os
os.remove('finance.db')
print('База данных удалена')
"
python run.py  # Создаст новую БД
```

---

## Устранение проблем

### Ошибка: No module named 'customtkinter'

```bash
pip install customtkinter
```

### Ошибка: Database is locked

Закрыты все другие экземпляры приложения.

### Логи не записываются

Проверьте права на папку `logs/`.

---

## Разработка

### Запуск тестов

```bash
cd src
python -m pytest
```

### Структура проекта

```bash
cd src
python tree.py
```

Результат сохраняется в `PROJECT_STRUCTURE.md`.

---

## Контакты

Для вопросов и предложений: создайте issue в репозитории.

---

## Web Запуск

### Backend

```bash
cd src
pip install -r requirements-web.txt
python -m uvicorn backend.main:app --reload
```

или

```bash
cd src
python run_web_backend.py
```

### Frontend

```bash
cd src/frontend
npm install
npm run dev
```
