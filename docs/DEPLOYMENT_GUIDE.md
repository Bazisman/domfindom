# Руководство по выкладке

> Обновлено: 2026-04-25
> Production: `domfindom.ru`

## Текущая схема production

Проект работает на REG.RU shared hosting.

Схема:
- backend-репозиторий расположен в `~/finance-app`;
- backend запускается через `Passenger` и `passenger_wsgi.py`;
- frontend собирается локально;
- содержимое `frontend/dist` выкладывается в `/var/www/u3480024/data/www/domfindom.ru`.

## Что делать перед выкладкой

1. Проверить кодировку:

```bash
python tools/check_encoding.py --root .
```

2. Собрать frontend:

```bash
cd frontend
npm run build
```

3. Если изменения затрагивали backend-логику, прогнать релевантные тесты:

```bash
python -m unittest tests.test_web_api tests.test_financial_logic -v
```

## Выкладка backend

На сервере:

```bash
cd /var/www/u3480024/data/finance-app
git pull --ff-only
```

Если менялись Python-зависимости:

```bash
source .venv/bin/activate
python -m pip install -r requirements-web.txt
```

Если релиз меняет схему пользовательских SQLite-БД:
- миграция должна быть идемпотентной и выполняться для уже существующих `data/users/*/finance.db`, а не только для новых баз;
- `auth_service.ensure_user_finance_db()` обязан прогонять `core.init_db()` при первом доступе к базе в процессе;
- перед завершением выкладки нужно проверить хотя бы наличие новых колонок/таблиц во всех production `finance.db`;
- после schema-релиза вручную проверить живой сценарий, который пишет в измененную таблицу, а не ограничиваться только `health`.

Production-инцидент 2026-04-25 показал риск: `health` оставался зеленым, но создание транзакций падало, потому что старые пользовательские БД не имели новой колонки `transactions.money_source`.

## Выкладка frontend

Стандартный рабочий путь:
- локально собрать `frontend/dist`;
- упаковать `frontend/dist` в архив;
- загрузить архив на хост;
- распаковать поверх текущей статики в `/var/www/u3480024/data/www/domfindom.ru`.

## Перезапуск приложения

После обновления backend или frontend:

```bash
touch /var/www/u3480024/data/www/domfindom.ru/tmp/restart.txt
```

Это текущая основная проверенная точка перезапуска.

## Проверка после выкладки

```bash
curl -L https://domfindom.ru/api/v1/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

После этого вручную проверить минимум:
- вход в аккаунт;
- экран, который менялся;
- если менялась схема БД — создание/редактирование записи на измененном экране;
- если менялись письма — соответствующий email-flow.

## Правило протокола

После заметной выкладки:
- обновить `docs/WORK_LOG.md`;
- если был крупный инцидент, можно отдельно зафиксировать его в архиве.
