# PostgreSQL Stage Runbook

> Обновлено: 2026-04-26
> Статус: рабочий протокол stage-проверки перед любым cutover.

## Цель

Проверить миграцию SQLite -> PostgreSQL на копии данных, не записывая ничего в production SQLite-БД.

## Границы безопасности

- Production `auth.db` содержит приватные auth/user/family данные.
- Production `data/users/*/finance.db` содержит финансовые данные пользователей.
- Эти файлы нельзя скачивать в обычную рабочую директорию без отдельного явного разрешения.
- Snapshot-root должен быть в ignored-директории, например `backups/postgres_stage_snapshot_YYYYMMDD`.
- Snapshot нельзя коммитить.
- Stage PostgreSQL target должен быть отдельной БД, не production.

## Read-only preflight на production

Допустимо запускать read-only preflight на production-хосте, если он возвращает только counts/warnings/issues без email, имен, комментариев и сумм:

```bash
.venv/bin/python .tmp/postgres_preflight/sqlite_family_preflight.py --source-root . --format json
```

Текущий production preflight:
- `issues=0`;
- `warnings=8`;
- warning type: `orphan_contribution_source_transaction`;
- причина: часть исторических семейных отчислений ссылается на исходные транзакции, которые уже удалены из пользовательских SQLite-БД.

## Snapshot copy

Для локального или stage source-root:

```powershell
python -B tools\sqlite_snapshot_copy.py `
  --source-root <source-root> `
  --target-root backups\postgres_stage_snapshot_YYYYMMDD `
  --overwrite
```

Скрипт копирует:
- `auth.db`;
- legacy/root `finance.db`, если он есть;
- `data/users/*/finance.db`.

Скрипт сохраняет manifest с target path, size и SHA256 в stdout.

## Stage check

После подготовки snapshot:

```powershell
python -B tools\postgres_stage_check.py `
  --source-root backups\postgres_stage_snapshot_YYYYMMDD `
  --database-url postgresql+psycopg://<user>:<password>@localhost:5432/<stage-db> `
  --reset-target
```

Что делает stage-check:
1. Family preflight.
2. Alembic `downgrade base`.
3. Alembic `upgrade head`.
4. ETL write-target.
5. Reconciliation.

Успешный результат:
- `preflight issues=0`;
- допустимые warnings явно разобраны и отражены в модели;
- `reconciliation failed=0`.

## Shadow read

После успешного stage-check можно проверить готовность cutover/shadow-read:

```powershell
python -B tools\postgres_cutover_check.py `
  --source-root <snapshot-or-production-root> `
  --database-url postgresql+psycopg://<user>:<password>@<host>:5432/<db> `
  --year 2026 `
  --month 4
```

Готовность к `shadow-read` означает:
- Python PostgreSQL-зависимости установлены;
- `FINANCE_APP_DATABASE_URL` подключается;
- Alembic revision совпадает с ожидаемой;
- family preflight, reconciliation и read-compare проходят без failed checks.

После этого можно включить теневое чтение для `/dashboard` на stage или production:

```text
FINANCE_APP_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<stage-db>
FINANCE_APP_POSTGRES_READ_SHADOW=true
FINANCE_APP_POSTGRES_SHADOW_WRITE=false
FINANCE_APP_STORAGE_BACKEND=sqlite
```

Правило:
- ответ API по-прежнему строится из SQLite;
- PostgreSQL читается только для сравнения;
- при расхождении в лог пишется user id и количество issues, без вывода финансовых значений;
- production cutover не считается разрешенным только по факту включения shadow-read.
- `FINANCE_APP_STORAGE_BACKEND=postgres` сейчас намеренно заблокирован startup guard до готовности write-path адаптера.

После отдельной проверки write target можно включать shadow-write:

```text
FINANCE_APP_POSTGRES_SHADOW_WRITE=true
```

Правило:
- SQLite остается primary write;
- PostgreSQL получает зеркальную запись только после успешного SQLite-коммита;
- ошибки PostgreSQL пишутся в лог и не ломают пользовательский запрос;
- удаление личной actual transaction зеркалируется в PostgreSQL с откатом balance effects;
- редактирование личной actual transaction зеркалируется в PostgreSQL как delete+insert текущего SQLite-состояния;
- личные planned transactions зеркалируются без изменения balances, включая связь с recurring template;
- create/update/delete recurring templates зеркалируются вместе с актуальным набором связанных planned transactions;
- create/update/delete личных категорий, бюджетов и счетов капитала зеркалируются в PostgreSQL после SQLite-коммита;
- ручные личные transfers зеркалируются в PostgreSQL с тем же изменением балансов счетов;
- семейные автоотчисления пока пропускаются до отдельного family write-path.

## Что нельзя делать

- Нельзя запускать stage-check на production PostgreSQL target.
- Нельзя использовать production SQLite source-root как target для записи.
- Нельзя менять production env на PostgreSQL до stage-check, ручной проверки и rollback-плана.
- Нельзя считать warnings безопасными молча: каждый warning должен быть либо исправлен, либо отражен в migration model.
