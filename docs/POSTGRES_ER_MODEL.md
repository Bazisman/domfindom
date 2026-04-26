# PostgreSQL ER-модель

> Обновлено: 2026-04-25
> Статус: черновик целевой схемы для обсуждения перед Alembic/ETL.

## 1. Цель документа

Описать целевую PostgreSQL-схему так, чтобы:
- сохранить текущую продуктовую модель;
- перенести `auth.db` и per-user `finance.db` без потерь;
- не смешать личный и семейный контексты;
- оставить места под future privacy layer: encryption metadata, user-held keys и support grants.

Это не миграция и не SQL-скрипт. Это карта, по которой позже пишутся Alembic-миграции и ETL.

## 2. Общий принцип

В SQLite сейчас личная изоляция физическая:

```text
auth.db
data/users/12/finance.db
data/users/3/finance.db
...
```

В PostgreSQL изоляция становится логической:

```text
users.id
finance tables.user_id
family tables.family_id
access checks by current_user + family role
```

Правило:
- каждая личная финансовая запись должна иметь `user_id`;
- каждая семейная запись должна иметь `family_id`;
- локальные SQLite `id` нужно сохранить на время миграции в `legacy_*` полях или mapping-таблицах;
- семейная аналитика не должна превращаться в физическое слияние личной истории.

## 3. Схемы PostgreSQL

Рекомендуем разделить таблицы по namespace:
- `auth` — пользователи, сессии, токены, профиль;
- `finance` — личные операции, счета, категории, бюджеты;
- `family` — семьи, роли, семейный капитал, category bindings;
- `security` — ключи, encryption metadata, support grants;
- `migration` — временные mapping и audit таблицы переноса.

На первом этапе можно физически держать все в `public`, но имена таблиц и код лучше проектировать так, будто границы уже есть.

## 4. Auth / identity

### `users`

Поля:
- `id BIGSERIAL PRIMARY KEY`;
- `email TEXT NOT NULL UNIQUE`;
- `password_hash TEXT NOT NULL`;
- `email_verified BOOLEAN NOT NULL DEFAULT false`;
- `is_active BOOLEAN NOT NULL DEFAULT true`;
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`;
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`;
- `legacy_sqlite_user_id INTEGER UNIQUE NULL`.

Примечание:
- `legacy_sqlite_user_id` нужен только для ETL и сверки. После стабилизации его можно оставить как technical metadata или вынести в `migration.identity_map`.

### `sessions`

Поля:
- `id BIGSERIAL PRIMARY KEY`;
- `user_id BIGINT NOT NULL REFERENCES users(id)`;
- `token_hash TEXT NOT NULL UNIQUE`;
- `expires_at TIMESTAMPTZ NOT NULL`;
- `ip TEXT`;
- `user_agent TEXT`;
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`;
- `revoked_at TIMESTAMPTZ NULL`.

Индексы:
- `(user_id)`;
- `(expires_at)`;
- `(token_hash)`.

### Auth-токены и события

Сохранить отдельные таблицы:
- `login_attempts`;
- `auth_events`;
- `password_reset_tokens`;
- `email_verification_tokens`;
- `account_deletion_tokens`.

Правило:
- token values по-прежнему хранятся только как hash;
- события не должны хранить финансовые данные.

### `user_preferences`

Поля:
- `user_id BIGINT PRIMARY KEY REFERENCES users(id)`;
- `theme_mode TEXT NOT NULL DEFAULT 'system'`;
- `workspace_mode TEXT NOT NULL DEFAULT 'personal'`;
- `display_name TEXT NOT NULL DEFAULT ''`;
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

## 5. Деньги и точность

Решение для PostgreSQL:
- внутри БД хранить деньги как integer в минимальных единицах валюты: `amount_minor`, `balance_minor`, `remaining_minor`;
- для RUB минимальная единица — копейка;
- `1000.50 ₽` хранится как `100050`;
- API на переходном этапе может продолжать отдавать `float`, но storage/repository слой должен конвертировать через точную decimal-логику, а не через бинарный float.

Почему не `NUMERIC(14,2)` как основной тип:
- `NUMERIC` тоже точный, но integer-копейки проще проверять, суммировать, сравнивать и шифровать;
- текущий код уже имеет много `float`, и PostgreSQL-слой должен стать местом, где эта неточность заканчивается;
- для будущего шифрования integer payload проще и стабильнее, чем decimal-представление.

Правила:
- входящие суммы округлять/валидировать до 2 знаков после запятой;
- отрицательные значения не принимать для `amount`, где по продукту сумма должна быть положительной;
- знак дохода/расхода остается в `type`, а не в отрицательной сумме;
- валюту пока считать `RUB`, но таблицы должны оставлять поле `currency`.

Переходный API-контракт:
- внешние Pydantic-схемы могут временно оставаться на `float`;
- новый data-access слой возвращает наружу рубли как decimal/float только на границе API;
- внутри ETL и PostgreSQL хранение идет в `*_minor`.

## 6. Finance

### Общие правила

Для всех finance-таблиц:
- `id BIGSERIAL PRIMARY KEY`;
- `user_id BIGINT NOT NULL REFERENCES users(id)`;
- `legacy_local_id INTEGER NOT NULL`;
- уникальность `(user_id, legacy_local_id)` для таблиц, где переносится старый id;
- `created_at` / `updated_at` в `TIMESTAMPTZ`, если поле есть в текущей модели.

Это позволяет:
- сохранить связи из SQLite;
- отлаживать ETL;
- строить rollback-сверку.

### `finance.accounts`

Переносит повседневные счета:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `name`;
- `type`;
- `money_source TEXT NULL`;
- `balance_minor BIGINT NOT NULL DEFAULT 0`;
- `currency TEXT NOT NULL DEFAULT 'RUB'`;
- `is_active BOOLEAN NOT NULL DEFAULT true`;
- `created_at`;
- `updated_at`.

Правила:
- счет `Безнал` сохраняет смысл `cashless`;
- счет `Наличные` сохраняет смысл `cash`;
- не полагаться в PostgreSQL только на `id=1/2`; лучше иметь `money_source`.

### `finance.categories`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `name`;
- `type`;
- `color`;
- `icon`;
- `is_active`;
- `semantic_key TEXT NULL`;
- `category_uid UUID NULL`;
- `scope TEXT NOT NULL DEFAULT 'personal'`;
- `family_category_id BIGINT NULL`;
- `sync_status TEXT NOT NULL DEFAULT 'unlinked'`;
- `original_name TEXT NULL`;
- `created_at`;
- `updated_at`.

Примечание:
- дополнительные поля совпадают с направлением `CATEGORY_SYNC_SPEC.md`;
- заполнять их можно поэтапно, не обязательно в первом ETL.

### `finance.transactions`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `type TEXT NOT NULL`;
- `category TEXT NOT NULL`;
- `category_id BIGINT NULL REFERENCES finance.categories(id)`;
- `semantic_key TEXT NULL`;
- `original_category_name TEXT NULL`;
- `amount_minor BIGINT NOT NULL`;
- `comment TEXT NULL`;
- `date DATE NOT NULL`;
- `money_source TEXT NOT NULL DEFAULT 'cashless'`;
- `status TEXT NOT NULL DEFAULT 'actual'`;
- `executed_at TIMESTAMPTZ NULL`;
- `template_id BIGINT NULL`;
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`;
- encryption metadata fields, если включается шифрование.

Индексы:
- `(user_id, date)`;
- `(user_id, status, date)`;
- `(user_id, type, date)`;
- `(user_id, category_id)`;
- `(user_id, template_id)`.

Важно:
- `amount_minor`, `comment`, `category` — кандидаты на future encryption;
- если `amount` шифруется строго, серверные отчеты потребуют отдельной стратегии.

### `finance.budgets`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `category_id BIGINT NOT NULL REFERENCES finance.categories(id)`;
- `amount_minor BIGINT NOT NULL`;
- `period TEXT NOT NULL`.

Индексы:
- `(user_id, category_id)`.

### `finance.recurring_templates`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `type`;
- `name`;
- `amount_minor`;
- `day_of_month`;
- `category_id BIGINT NULL`;
- `comment_template TEXT`;
- `money_source TEXT NOT NULL DEFAULT 'cashless'`;
- `months_ahead INTEGER DEFAULT 12`;
- `working_days_only BOOLEAN DEFAULT false`;
- `is_active BOOLEAN DEFAULT true`;
- `created_at`;
- `updated_at`.

### `finance.transfers`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `legacy_from_account_id INTEGER NOT NULL`;
- `legacy_to_account_id INTEGER NOT NULL`;
- `from_account_kind TEXT NOT NULL`;
- `to_account_kind TEXT NOT NULL`;
- `from_daily_account_id BIGINT NULL`;
- `to_daily_account_id BIGINT NULL`;
- `from_capital_account_id BIGINT NULL`;
- `to_capital_account_id BIGINT NULL`;
- `amount_minor BIGINT NOT NULL`;
- `transaction_id BIGINT NULL`;
- `date DATE NOT NULL`;
- `comment TEXT NULL`;
- `is_active BOOLEAN DEFAULT true`;
- `created_at`.

Правило:
- текущий SQLite хранит стороны перевода как общий числовой id, где `1/2` — повседневные счета, а капитал живет в отдельной таблице и диапазоне id;
- PostgreSQL должен явно хранить kind стороны перевода (`daily` или `capital`) и ссылку на правильную таблицу;
- legacy ids сохраняются для ETL-сверки и rollback.

### `finance.capital_accounts`

Поля:
- `id`;
- `user_id`;
- `legacy_local_id`;
- `name`;
- `balance_minor BIGINT DEFAULT 0`;
- `currency TEXT DEFAULT 'RUB'`;
- `icon`;
- `color`;
- `is_default BOOLEAN DEFAULT false`;
- `is_active BOOLEAN DEFAULT true`;
- `created_at`;
- `updated_at`.

### Reconciliation

Сохранить:
- `finance.reconciliation_sources`;
- `finance.reconciliations`.

Обе таблицы получают `user_id` и `legacy_local_id`.

## 7. Family

### `family.families`

Поля:
- `id BIGSERIAL PRIMARY KEY`;
- `name TEXT NOT NULL`;
- `owner_user_id BIGINT NOT NULL REFERENCES users(id)`;
- `created_at`;
- `updated_at`;
- `archived_at`.

### `family.memberships`

Поля:
- `id`;
- `family_id`;
- `user_id`;
- `role TEXT NOT NULL`;
- `status TEXT NOT NULL DEFAULT 'active'`;
- `invited_by_user_id`;
- `created_at`;
- `updated_at`.

Ограничения:
- `UNIQUE(family_id, user_id)`;
- role in `owner`, `member`, `viewer`.

### Family invites/capital

Сохранить семантику текущих таблиц:
- `family_invites`;
- `family_capital_accounts`;
- `family_capital_member_settings`;
- `family_capital_contributions`.

Важное правило переноса:
- `owner_user_id + capital_account_id` из SQLite нужно маппить на PostgreSQL `finance.capital_accounts.id`;
- `source_transaction_id` нужно маппить на PostgreSQL `finance.transactions.id`.

### `family.categories`

Поля:
- `id`;
- `family_id`;
- `semantic_key`;
- `display_name`;
- `type`;
- `is_active`;
- `created_by_user_id`;
- `created_at`;
- `updated_at`.

Ограничение:
- `UNIQUE(family_id, semantic_key)`.

### `family.category_bindings`

Поля:
- `id`;
- `family_id`;
- `family_category_id`;
- `user_id`;
- `local_category_id BIGINT NOT NULL REFERENCES finance.categories(id)`;
- `local_category_name`;
- `local_category_type`;
- `status`;
- `confirmed_by_user_id`;
- `created_at`;
- `updated_at`.

Ограничение:
- `UNIQUE(family_id, user_id, local_category_id)`.

Важно:
- при ETL старый `local_category_id` из `auth.db` указывает на локальный SQLite id категории пользователя;
- его нужно заменить на новый PostgreSQL id через mapping.

### `family.category_audit_resolutions`

Сохранить текущую семантику:
- решение скрывает разобранное предупреждение;
- не переписывает категории, бюджеты, шаблоны или историю.

## 8. Security / privacy

Эти таблицы можно создать не в первом релизе PostgreSQL, но ER-модель должна их учитывать.

### `security.user_data_keys`

Поля:
- `id`;
- `user_id`;
- `key_version INTEGER NOT NULL`;
- `wrapped_key BYTEA NOT NULL`;
- `wrap_method TEXT NOT NULL`;
- `salt BYTEA NULL`;
- `kdf_params JSONB NOT NULL DEFAULT '{}'`;
- `created_at`;
- `rotated_at`;
- `revoked_at`.

Назначение:
- хранить не сам открытый data key, а защищенную форму ключа.

### `security.encryption_metadata`

Вариант 1:
- хранить metadata рядом с каждой encrypted-колонкой.

Вариант 2:
- отдельная таблица:
  - `entity_type`;
  - `entity_id`;
  - `field_name`;
  - `key_version`;
  - `nonce`;
  - `algorithm`;
  - `created_at`.

Для первого этапа проще metadata рядом с полем, но это нужно решить отдельно.

### `security.support_access_grants`

Поля:
- `id`;
- `user_id`;
- `granted_by_user_id`;
- `support_public_key_id`;
- `encrypted_grant BYTEA NOT NULL`;
- `reason TEXT`;
- `expires_at`;
- `created_at`;
- `revoked_at`;
- `used_at`.

Правило:
- grant создается только после действия пользователя;
- email подтверждает действие, но не переносит главный ключ.

### `security.support_access_audit`

Поля:
- `id`;
- `grant_id`;
- `actor`;
- `action`;
- `ip`;
- `user_agent`;
- `created_at`;
- `detail`.

## 9. Migration mapping

Для ETL нужны временные таблицы:
- `migration.user_map`;
- `migration.category_map`;
- `migration.account_map`;
- `migration.capital_account_map`;
- `migration.transaction_map`;
- `migration.recurring_template_map`;
- `migration.transfer_map`.

Минимальные поля:
- `source_db_path`;
- `source_user_id`;
- `source_table`;
- `source_local_id`;
- `target_table`;
- `target_id`;
- `created_at`.

Эти таблицы критичны для:
- family category bindings;
- family capital contributions;
- rollback-сверки;
- повторяемого dry-run.

## 10. ETL порядок

1. `users` и auth-таблицы.
2. `user_preferences`.
3. `families`, memberships, invites.
4. Per-user finance справочники:
   - accounts;
   - categories;
   - capital_accounts.
5. Finance факты:
   - transactions;
   - transfers;
   - budgets;
   - recurring_templates;
   - reconciliation.
6. Family capital links/contributions через mapping.
7. Family categories и category bindings через mapping.
8. Audit resolutions.
9. Сверка агрегатов.

## 11. Открытые решения

- Использовать SQLAlchemy ORM полностью или SQLAlchemy Core для миграционного слоя.
- Когда добавлять `category_id` в новые транзакции: в первый PostgreSQL-релиз или следующим этапом.
- Какие поля шифровать на первом privacy-этапе.
- Как считать семейные forecast/status при строгом user-held key.
- Нужен ли PostgreSQL Row Level Security в первом релизе или достаточно application-level проверок + тестов.

## 12. Следующий шаг

До кода:
- согласовать эту ER-модель;
- решить, включать ли security schema сразу пустыми таблицами;
- затем писать Alembic initial migration и ETL dry-run.
