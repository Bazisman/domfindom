# KODA.md — быстрый вход в проект

> Версия: 4.0
> Обновлено: 2026-04-18

## Что это за проект

`Домфиндом` — web-приложение для личной и семейной домашней бухгалтерии.

Главный активный продукт сейчас:
- `backend/` — FastAPI API;
- `frontend/` — React + TypeScript + Vite;
- `backend/auth/` — авторизация, семьи, сессии, письма и настройки пользователя.

Desktop-часть осталась в репозитории как исторический слой, но не определяет новые продуктовые решения.

## Что читать в новой сессии

1. `TASKS.md`
2. `docs/PROJECT_STATE.md`
3. `docs/DECISIONS.md`
4. `docs/WORKING_MEMORY.md`
5. `docs/WORK_LOG.md`
6. `docs/PROJECT_HISTORY.md`

Если нужен очень старый контекст:
- смотреть `docs/archive/`

## Основные директории

```text
backend/        FastAPI API, авторизация, семьи, account API
frontend/       React + TypeScript + Vite интерфейс
backend/auth/   auth.db, email-flow, семьи, сессии, preferences
core*.py        историческое финансовое ядро и инфраструктурная логика
tests/          backend и финансовые автотесты
docs/           актуальная документация
docs/archive/   архив старых планов, session-файлов и legacy-документов
```

## Правила, которые нельзя забывать

- Основной интерфейс проекта — web.
- `display_name` имеет приоритет над email в UI.
- Личный и семейный режим — разные контексты.
- Семейные данные не сливаются физически в один личный журнал; семейный обзор строится поверх данных участников.
- Если пользователь пишет `запротоколируй`, нужно обновить документацию и обязательно дополнить `docs/WORK_LOG.md`.
- `docs/archive/` — архив, а не основной ежедневный журнал.

## Кодировка

- Все текстовые файлы проекта должны быть в `UTF-8` без BOM.
- Перед сборкой и деплоем обязательно:

```bash
python tools/check_encoding.py --root .
```

- Нельзя лечить битую кириллицу угадыванием перекодировки.

## Базовые команды

```bash
python tools/check_encoding.py --root .
cd frontend
npm run build
```

```bash
python -m unittest tests.test_web_api tests.test_financial_logic -v
```

## Production

Текущий production находится на `domfindom.ru`.

Схема:
- backend живет в `~/finance-app`;
- frontend собирается локально;
- `frontend/dist` загружается как статика;
- backend запускается через `Passenger`.
