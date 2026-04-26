# Локальный запуск и окружение

> Обновлено: 2026-04-26

## Основной контур разработки

Главный контур разработки сейчас — web:
- backend: FastAPI;
- frontend: React + TypeScript + Vite.

Desktop-часть считается legacy-слоем и не используется как главный путь запуска продукта.

## Требования

- Python 3.10+ локально;
- Node.js и npm для frontend;
- Windows PowerShell допустим, но для записи текстовых файлов нужно помнить про UTF-8 без BOM.

## Установка зависимостей backend

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-web.txt
```

## Установка зависимостей frontend

```bash
cd frontend
npm install
```

## Локальный запуск backend

По умолчанию локальный backend может работать в legacy SQLite-режиме:

```bash
python run_web_backend.py
```

или

```bash
python -m uvicorn backend.main:app --reload
```

Для проверки MySQL runtime локально нужны переменные:

```env
FINANCE_APP_STORAGE_BACKEND=mysql
FINANCE_APP_MYSQL_DATABASE_URL=mysql+pymysql://...
FINANCE_APP_MYSQL_READ_SHADOW=true
FINANCE_APP_MYSQL_SHADOW_WRITE=true
FINANCE_APP_MYSQL_PRIMARY_READ_PILOT=true
FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING=true
FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS=true
FINANCE_APP_MYSQL_STRICT_WRITE_ACCOUNTS_CAPITAL=true
FINANCE_APP_MYSQL_STRICT_WRITE_RECONCILIATION=true
FINANCE_APP_MYSQL_STRICT_WRITE_AUTH=true
```

Production работает именно в MySQL runtime. SQLite в локальном запуске остается удобным fallback для старых тестов и legacy desktop-слоя.

## Локальный запуск frontend

```bash
cd frontend
npm run dev
```

## Полезные проверки

Проверка кодировки:

```bash
python tools/check_encoding.py --root .
```

Сборка frontend:

```bash
cd frontend
npm run build
```

Тесты:

```bash
python -m unittest tests.test_web_api tests.test_financial_logic -v
```

## Важные замечания

- Основной production сейчас на `domfindom.ru`.
- Для production используется `Passenger`, а не локальный `uvicorn`.
- Если правятся русские строки, письма или markdown-файлы, контроль кодировки обязателен.
