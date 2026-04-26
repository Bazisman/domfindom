# MySQL Runtime Runbook

> Обновлено: 2026-04-26
> Production backend: MySQL primary runtime.

## Текущий статус

Production `domfindom.ru` работает с `FINANCE_APP_STORAGE_BACKEND=mysql`.

Ожидаемый health:

```json
{"status":"ok","storage_backend":"mysql","runtime_mode":"mysql-primary-read-strict-dual-write"}
```

`tools/mysql_cutover_check.py` должен показывать:

- `Ready for runtime mysql: True`
- `Blockers: 0`
- `runtime_adapter: mysql-primary-read-strict-dual-write`

## Production-переменные

Обязательные переменные для MySQL runtime:

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

Startup guard в `backend/config.py` разрешает `storage_backend=mysql` только при полной strict-конфигурации. Если один из strict-флагов или MySQL URL отсутствует, приложение не должно стартовать как MySQL primary.

## Что уже пишет в MySQL

Runtime write-path переведен на MySQL для:

- auth/users/sessions/tokens/preferences strict path;
- categories;
- budgets;
- app settings;
- reconciliation sources;
- reconciliations shadow/write adapter;
- daily accounts и capital accounts;
- standalone transfers;
- actual transaction create/update/delete;
- planned transaction create/assign/generate/execute;
- recurring template create/update/delete.

## Что читает из MySQL

Primary read-path переведен на MySQL для:

- dashboard balance/month stats/projected balance;
- transaction list, single transaction, export and date-range reads;
- accounts/capital/transfers;
- categories/budgets/budget status/report;
- recurring templates and due planned transactions;
- reconciliation sources, totals and history;
- category audit snapshots.

## SQLite после cutover

SQLite-код и `core.py` остаются в репозитории как legacy/fallback layer:

- для локального режима `FINANCE_APP_STORAGE_BACKEND=sqlite`;
- для desktop/старых view-модулей;
- для rollback-разбора и исторических migration tools.

Новый web-runtime код не должен добавлять прямые `core.*` вызовы в routes. Web routes должны идти через service layer, где уже есть MySQL-aware read/write path.

## Проверка после backend deploy

На сервере:

```bash
cd /var/www/u3480024/data/finance-app
git pull --ff-only
touch /var/www/u3480024/data/www/domfindom.ru/tmp/restart.txt
sleep 3
curl -sS -L https://domfindom.ru/api/v1/health
set -a && . ./.env && set +a
.venv/bin/python tools/mysql_cutover_check.py \
  --database-url "$FINANCE_APP_MYSQL_DATABASE_URL" \
  --year 2026 \
  --month 4 \
  --skip-data-checks \
  --format markdown
```

Минимальный ручной smoke-test:

- войти в аккаунт;
- создать доход;
- создать расход;
- создать перевод между счетами;
- создать будущую recurring operation;
- открыть dashboard;
- открыть budgets/reconciliation screens.

## Rollback

Перед cutover был сохранен production `.env` snapshot:

```text
.env.before_storage_backend_mysql_20260426
```

Rollback должен быть отдельным осознанным действием:

1. остановить новые пользовательские записи или включить maintenance window;
2. вернуть `.env` на SQLite config;
3. перезапустить Passenger;
4. проверить health;
5. отдельно решить, что делать с MySQL-only записями, появившимися после cutover.

Нельзя молча переключать production обратно на SQLite после того, как пользователи уже писали новые данные в MySQL.
