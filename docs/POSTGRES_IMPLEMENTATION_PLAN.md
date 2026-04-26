# PostgreSQL Implementation Plan

> Обновлено: 2026-04-26
> Статус: Alembic scaffold, initial migration и первый локальный ETL write-target подготовлены; production остается на SQLite.

## 1. Цель

Перевести проект с текущей схемы:

```text
auth.db + data/users/*/finance.db
```

на PostgreSQL без потери данных, без смешивания пользователей и без одновременного внедрения сложной криптографии.

Этот план начинается после:
- read-only инвентаризации SQLite;
- черновой ER-модели;
- решения хранить деньги как `*_minor` integer-копейки.

## 2. Что не делаем в первом PostgreSQL-релизе

Не делаем:
- user-held key;
- support grant;
- шифрование всех финансовых полей;
- переписывание forecast/business-логики;
- изменение продуктовой модели семьи;
- big bang rewrite всего `core.py`.

Разрешено подготовить таблицы/metadata под future security layer, но не включать криптографическое поведение до отдельной задачи.

## 3. Зависимости

Будущие зависимости:
- `SQLAlchemy>=2`;
- `Alembic`;
- PostgreSQL driver:
  - `psycopg` для sync-подхода;
  - или `asyncpg`, если будет принято решение переводить backend data-access в async.

Предварительная рекомендация:
- начать с sync SQLAlchemy/psycopg, потому что текущий `core.py` и сервисный слой синхронные;
- async можно рассмотреть позже, когда storage слой уже отделен.

Статус на 2026-04-25:
- добавлен отдельный `requirements-postgres.txt`;
- runtime `requirements-web.txt` пока не изменяется, чтобы production не получил новые зависимости до готовности storage-слоя.
- для локального Python 3.14 диапазон `psycopg[binary]` поднят до `>=3.2,<3.3`, потому что `3.1.x` не имеет подходящего binary wheel в текущей среде.
- локально установлены `SQLAlchemy`, `Alembic` и `psycopg`; запускать Alembic в этой среде нужно через `python -m alembic`, потому что scripts directory не находится в `PATH`.
- локально установлен PostgreSQL 17 server для dev-проверок.

## 4. Конфигурация

Добавить переменные:

```text
FINANCE_APP_STORAGE_BACKEND=sqlite|postgres
FINANCE_APP_DATABASE_URL=postgresql+psycopg://...
FINANCE_APP_RUN_DB_MIGRATIONS=false
```

Правило:
- production остается на SQLite, пока PostgreSQL не пройдет dry-run, stage и cutover;
- backend не должен случайно переключиться на PostgreSQL без явного env.

## 5. Alembic

Порядок:
1. Добавить Alembic scaffolding.
2. Создать initial migration по `docs/POSTGRES_ER_MODEL.md`.
3. Добавить индексы сразу в initial migration.
4. Не подключать Alembic auto-run к production startup.

Почему не auto-run:
- текущий проект уже пережил schema-инцидент;
- production-миграции должны быть явным шагом релиза, а не побочным эффектом старта Passenger.

Статус на 2026-04-25:
- добавлен Alembic scaffold (`alembic.ini`, `migrations/`);
- `migrations/env.py` требует явный `FINANCE_APP_DATABASE_URL`;
- initial migration `20260425_0001_initial_postgres_schema.py` создана по черновой ER-модели;
- startup backend/Passenger не подключен к Alembic.
- добавлены статические тесты `tests/test_postgres_migration_scaffold.py`, которые проверяют ключевые инварианты migration-файла без локального PostgreSQL.
- Alembic offline SQL generation проходит успешно с dummy `FINANCE_APP_DATABASE_URL`, то есть migration-файл загружается и генерирует PostgreSQL DDL без подключения к серверу.
- initial migration успешно применена на локальную пустую PostgreSQL-БД `finance_app_dev`.

Проверка локальной БД после миграции:
- `alembic_version = 20260425_0001`;
- создано 9 таблиц в `auth`, 10 в `finance`, 9 в `family`, 3 в `security`, 2 в `migration`.

## 6. ETL dry-run

Скрипт:

```text
tools/sqlite_to_postgres_etl.py
```

Режимы:
- `--source-root`;
- `--database-url`;
- `--write-target`;
- `--wipe-target` только для локального/stage окружения;
- `--format markdown|json`.

Правила:
- исходные SQLite-файлы открывать read-only;
- ETL должен быть повторяемым;
- все mapping сохранять в `migration.*`;
- суммы конвертировать `REAL -> Decimal -> minor integer`, а не через прямое умножение бинарного float без округления.

Статус на 2026-04-25:
- добавлен первый read-only scaffold `tools/sqlite_to_postgres_etl.py`;
- добавлен guarded write-target режим: запись в PostgreSQL требует явные `--database-url`, `--write-target` и `--wipe-target`;
- текущий write-target покрывает `auth.users`, `auth.user_preferences` и личные finance-таблицы (`accounts`, `categories`, `transactions`, `budgets`, `capital_accounts`, `recurring_templates`, `reconciliation_sources`, `reconciliations`, `app_settings`, `transfers`);
- write-target расширен на семейные auth-таблицы: `families`, `family_memberships`, `family_invites`, `family_capital_accounts`, `family_capital_member_settings`, `family_capital_contributions`, `family_categories`, `family_category_bindings`, `family_category_audit_resolutions`;
- support/security поведение и production/stage cutover пока не включены.
- production dry-run выполнен временным запуском tool-файлов на хосте; все найденные денежные колонки в `auth.db`, legacy `finance.db` и `data/users/*/finance.db` прошли конвертацию без invalid values;
- временные tool-файлы на production удалены после проверки.
- dry-run дополнен проверкой transfer refs: каждая сторона перевода должна однозначно указывать либо на daily account, либо на capital account.
- повторный production summary после проверки transfer refs: `databases=13`, `invalid_money=0`, `transfer_issues=0`; временные tool-файлы на production удалены.
- локальная ETL-загрузка в `finance_app_dev` прошла успешно на текущем legacy `finance.db`: перенесены 1 account, 22 categories, 184 transactions, 1 budget, 3 capital accounts, 4 recurring templates, 13 reconciliation sources, 1 reconciliation, 2 app settings и 35 transfers;
- после локальной загрузки `finance.transactions.category_id` заполнен у всех 184 транзакций, `migration.id_map` содержит 264 строки.
- локальная проверка семейного ETL прошла только на пустой `auth.db`;
- добавлен read-only production preflight для семейных SQLite-связей без записи в production;
- production preflight показал реальные семейные данные и `issues=0`, но нашел 8 предупреждений `orphan_contribution_source_transaction`: у части исторических семейных отчислений исходная транзакция уже отсутствует в пользовательской SQLite-БД;
- initial PostgreSQL schema и ETL адаптированы под это: `family.capital_contributions.source_transaction_id` nullable, а старый id сохраняется в `legacy_source_transaction_id`.

## 7. Mapping

Обязательные mapping:
- `users`: `legacy_sqlite_user_id -> users.id`;
- `categories`: `(user_id, local_category_id) -> finance.categories.id`;
- `accounts`: `(user_id, local_account_id) -> finance.accounts.id`;
- `capital_accounts`: `(user_id, local_capital_account_id) -> finance.capital_accounts.id`;
- `transactions`: `(user_id, local_transaction_id) -> finance.transactions.id`;
- `recurring_templates`: `(user_id, local_template_id) -> finance.recurring_templates.id`.

Особо важно:
- `family_category_bindings.local_category_id` в `auth.db` сейчас указывает на локальный SQLite id категории пользователя;
- `family_capital_contributions.source_transaction_id` нужно переводить через transaction mapping;
- `family_capital_accounts.capital_account_id` нужно переводить через capital account mapping.

## 8. Сверка

Скрипт:

```text
tools/postgres_reconciliation.py
```

Минимальные проверки:
- количество строк по таблицам;
- сумма `amount_minor` по пользователю, типу и месяцу;
- `cashless` / `cash` balances;
- capital balances;
- transfers totals;
- recurring templates count;
- planned/actual transactions count;
- family memberships and roles;
- family category bindings count;
- family dashboard/forecast для production-семьи.

Результат:
- markdown-отчет;
- json-отчет для автоматической проверки.

Статус на 2026-04-26:
- добавлен `tools/postgres_reconciliation.py`;
- сверка сравнивает counts, money sums, monthly transaction sums, transaction type/status/money_source sums и transfer active sums;
- старые SQLite-БД без `money_source` сравниваются с PostgreSQL как `cashless`, то есть по тому же правилу, которое использует ETL;
- локальная сверка `finance.db` -> `finance_app_dev` прошла без расхождений (`failed=0`).
- reconciliation расширен на counts семейных auth-таблиц; локально `auth.db` и `finance.db` сверяются с PostgreSQL без расхождений (`failed=0`).

## 9. Переходный storage слой

Цель:
- не ломать текущий API.

Подход:
- добавить интерфейс storage/repository для одной области, например `transactions`;
- реализовать SQLite-backed адаптер поверх текущего `core`;
- реализовать PostgreSQL-backed адаптер;
- сравнить ответы на одном наборе данных;
- постепенно расширять области.

Кандидаты по порядку:
1. Read-only reports/summary.
2. Categories.
3. Transactions read.
4. Transactions write.
5. Accounts/transfers.
6. Budgets/forecast.
7. Family aggregates.

Статус на 2026-04-26:
- добавлен первый read-only PostgreSQL adapter `backend/storage/postgres_read.py`;
- adapter подключен к runtime API только как выключенный по умолчанию shadow-read для `/dashboard`;
- покрытые чтения: balance, transactions list, category totals, monthly stats, capital contribution totals;
- добавлен `tools/postgres_read_compare.py`, который сравнивает ответы PostgreSQL read-model с SQLite snapshot по каждому пользователю;
- сравнение на production snapshot прошло по 11 пользователям без расхождений (`failed=0`);
- для категорий с одинаковой суммой принят детерминированный порядок `total DESC, category ASC`.
- добавлены runtime-флаги `FINANCE_APP_STORAGE_BACKEND`, `FINANCE_APP_DATABASE_URL`, `FINANCE_APP_RUN_DB_MIGRATIONS`, `FINANCE_APP_POSTGRES_READ_SHADOW`;
- `FINANCE_APP_POSTGRES_READ_SHADOW=false` по умолчанию, поэтому production продолжает отвечать из SQLite;
- при явном включении shadow-read `/dashboard` сравнивает SQLite-ответ с PostgreSQL read-model и пишет только количество расхождений в лог, не меняя ответ пользователю.
- добавлен первый PostgreSQL write adapter `backend/storage/postgres_write.py` для будущего dual-write личных actual transactions;
- adapter умеет зеркалировать уже созданную SQLite-транзакцию в PostgreSQL один раз, обновляя daily/capital balances и связанные transfers;
- добавлен rollback-probe `tools/postgres_shadow_write_probe.py`, который проверяет write adapter на stage PostgreSQL без сохранения тестовой записи.
- добавлен выключенный по умолчанию runtime `FINANCE_APP_POSTGRES_SHADOW_WRITE`; при включении новые личные actual transactions после SQLite-коммита зеркалируются в PostgreSQL, а ошибки пишутся в лог и не ломают основной SQLite-ответ;
- shadow-write расширен на удаление личных actual transactions: PostgreSQL-зеркало откатывает balance effects, деактивирует связанные transfers и удаляет transaction row;
- shadow-write расширен на редактирование личных actual transactions через безопасную модель delete+insert внутри PostgreSQL transaction, чтобы пересчитать balances/transfers по текущему SQLite-состоянию;
- planned transactions и семейные автоотчисления пока явно пропускаются shadow-write слоем до отдельной поддержки семейного write-path.

## 10. Stage и cutover

Stage:
- поднять PostgreSQL;
- залить копию production через ETL;
- переключить backend env на PostgreSQL;
- прогнать тесты и ручные сценарии.

Stage check command:

```powershell
python -B tools\postgres_stage_check.py `
  --source-root <snapshot-root> `
  --database-url postgresql+psycopg://<user>:<password>@localhost:5432/<stage-db> `
  --reset-target
```

Правила:
- `--reset-target` обязателен, потому что stage target должен быть явно пересоздан;
- без `--allow-nonlocal-target` скрипт разрешает только localhost/127.0.0.1/::1;
- production SQLite-файлы не должны скачиваться в рабочую директорию без отдельного явного разрешения;
- production preflight можно запускать read-only на сервере, возвращая только counts/warnings/issues.
- подробный протокол snapshot/stage проверки вынесен в `docs/POSTGRES_STAGE_RUNBOOK.md`.

Статус на 2026-04-26:
- добавлен `tools/postgres_stage_check.py`;
- добавлен `tools/sqlite_snapshot_copy.py` для явной подготовки ignored snapshot-root;
- локальный stage-check на `finance_app_dev` прошел полный цикл: preflight, Alembic downgrade/upgrade, ETL write-target, reconciliation;
- результат локального stage-check: `preflight issues=0`, `preflight warnings=0`, `reconciliation failed=0`.
- после отдельного явного разрешения подготовлен ignored production snapshot `backups/postgres_stage_snapshot_20260426`;
- stage-check на копии production-данных прошел без записи в production: `preflight issues=0`, `preflight warnings=8`, `reconciliation failed=0`;
- итоговая локальная PostgreSQL stage-БД содержит 11 users, 417 finance transactions, 107 finance categories, 14 family capital contributions, 15 family category bindings и 676 id-map строк;
- 8 family capital contributions сохранены как исторические orphan-ссылки: `legacy_source_transaction_id` заполнен, `source_transaction_id IS NULL`.

Production cutover:
- только после stage;
- только с backup;
- только в maintenance window;
- только с rollback на SQLite snapshot.

## 11. Первый кодовый шаг

До установки зависимостей:
- подготовить `tools/sqlite_inventory.py` уже сделано;
- добавить `tools/money_minor.py` с чистыми функциями:
  - `to_minor(value, currency='RUB')`;
  - `from_minor(value, currency='RUB')`;
- покрыть эти функции тестами;
- затем использовать их в будущем ETL.

Этот шаг малый, не трогает production runtime и снижает риск денежных расхождений.

Статус на 2026-04-25:
- `tools/money_minor.py` добавлен;
- базовые тесты конвертации и округления добавлены в `tests/test_money_minor.py`.
