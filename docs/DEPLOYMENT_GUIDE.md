# Руководство по выкладке

> Обновлено: 2026-04-18
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
- если менялись письма — соответствующий email-flow.

## Правило протокола

После заметной выкладки:
- обновить `docs/WORK_LOG.md`;
- если был крупный инцидент, можно отдельно зафиксировать его в архиве.
