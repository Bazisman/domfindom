# Инцидент 2026-04-25: money_source и старые пользовательские БД

## Контекст

В релизе повседневных денег добавлены источники `cashless` и `cash`, а таблица `transactions` получила поле `money_source`.

## Симптом

На production экран `Транзакции` показывал сообщение `Сервис временно недоступен` при добавлении расхода.

`GET /api/v1/health` при этом возвращал `{"status":"ok"}`, поэтому приложение не было полностью недоступно.

## Причина

Существующие пользовательские SQLite-БД в `data/users/*/finance.db` не прошли миграцию и не имели колонки `transactions.money_source`.

Новый backend уже выполнял `INSERT INTO transactions (..., money_source, ...)`, из-за чего SQLite возвращал:

```text
table transactions has no column named money_source
```

Дополнительно чтение planned/recurring-операций падало на запросах к `t.money_source`.

## Восстановление

- Все production `finance.db` были промигрированы: добавлены `transactions.money_source`, `recurring_templates.money_source`, счет `Наличные` (`id=2`) и настройка `default_money_source`.
- Backend получил hotfix `9d3c966`: `auth_service.ensure_user_finance_db()` теперь запускает `core.init_db()` для существующей пользовательской базы при первом доступе в процессе.
- Добавлен регрессионный тест, который имитирует старую пользовательскую БД без `money_source`.
- Production перезапущен через Passenger.

## Проверки

- `python -m unittest discover -s tests` — 84 теста OK.
- `python tools/check_encoding.py --root .` — OK.
- Production schema-check всех `finance.db` — OK.
- `https://domfindom.ru/api/v1/health` — `{"status":"ok"}`.

## Урок

Для schema-релизов per-user SQLite-БД `health` недостаточен. Нужно проверять миграцию старых пользовательских БД и живой write-сценарий измененного экрана.
