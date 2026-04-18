# Локальный запуск и окружение

> Обновлено: 2026-04-18

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

```bash
python run_web_backend.py
```

или

```bash
python -m uvicorn backend.main:app --reload
```

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
