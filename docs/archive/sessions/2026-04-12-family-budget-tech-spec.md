# Техспека 2026-04-12 (Family Budget, Flexible v1)

## 1. Цель

Сделать семейный режим, который подходит разным типам семей:

- полностью прозрачный бюджет;
- частично приватный режим;
- строгий режим с ограничением доступа.

Ключевой принцип неизменен:

- личные данные и счета пользователей не сливаются физически;
- семейный слой строится как аналитика поверх данных участников.

## 2. Базовые сущности

- User: личный аккаунт.
- Family: семейное пространство.
- Membership: участие пользователя в семье (роль + статус).
- FamilyPolicy: гибкие правила видимости и прав в семье.
- PermissionOverride: точечные разрешения сверх роли (опционально).

## 3. Модель данных

### 3.1 families

- id INTEGER PRIMARY KEY AUTOINCREMENT
- name TEXT NOT NULL
- owner_user_id INTEGER NOT NULL
- created_at TEXT DEFAULT (datetime('now'))
- updated_at TEXT DEFAULT (datetime('now'))
- archived_at TEXT NULL

### 3.2 family_memberships

- id INTEGER PRIMARY KEY AUTOINCREMENT
- family_id INTEGER NOT NULL
- user_id INTEGER NOT NULL
- role TEXT NOT NULL CHECK(role IN ('owner','admin','accountant','member','viewer'))
- status TEXT NOT NULL CHECK(status IN ('active','invited','revoked'))
- invited_by_user_id INTEGER NULL
- created_at TEXT DEFAULT (datetime('now'))
- updated_at TEXT DEFAULT (datetime('now'))

Индексы:

- UNIQUE(family_id, user_id)
- idx_family_memberships_family (family_id, status)
- idx_family_memberships_user (user_id, status)

### 3.3 family_invites

- id INTEGER PRIMARY KEY AUTOINCREMENT
- family_id INTEGER NOT NULL
- email TEXT NOT NULL
- role TEXT NOT NULL CHECK(role IN ('admin','accountant','member','viewer'))
- token_hash TEXT NOT NULL UNIQUE
- invited_by_user_id INTEGER NOT NULL
- expires_at TEXT NOT NULL
- accepted_at TEXT NULL
- revoked_at TEXT NULL
- created_at TEXT DEFAULT (datetime('now'))

### 3.4 family_settings

- family_id INTEGER PRIMARY KEY
- auto_capital_enabled INTEGER NOT NULL DEFAULT 0
- auto_capital_percent INTEGER NOT NULL DEFAULT 0
- default_capital_owner_user_id INTEGER NULL
- default_capital_account_id INTEGER NULL
- updated_by_user_id INTEGER NULL
- updated_at TEXT DEFAULT (datetime('now'))

### 3.5 family_policies (новое для гибкости)

- family_id INTEGER PRIMARY KEY
- visibility_mode TEXT NOT NULL CHECK(visibility_mode IN ('transparent','private_balances','strict_private'))
- allow_members_create_categories INTEGER NOT NULL DEFAULT 0
- allow_members_edit_own_transactions INTEGER NOT NULL DEFAULT 1
- allow_members_edit_others_transactions INTEGER NOT NULL DEFAULT 0
- allow_members_delete_own_transactions INTEGER NOT NULL DEFAULT 0
- allow_members_delete_others_transactions INTEGER NOT NULL DEFAULT 0
- allow_members_view_member_balances INTEGER NOT NULL DEFAULT 1
- allow_members_view_member_transactions INTEGER NOT NULL DEFAULT 1
- allow_members_manage_recurring INTEGER NOT NULL DEFAULT 0
- updated_by_user_id INTEGER NULL
- updated_at TEXT DEFAULT (datetime('now'))

Назначение:

- role задает базовый уровень;
- family_policies тонко настраивает правила под конкретную семью.

### 3.6 family_permission_overrides (опционально, v1.1)

- id INTEGER PRIMARY KEY AUTOINCREMENT
- family_id INTEGER NOT NULL
- user_id INTEGER NOT NULL
- permission_key TEXT NOT NULL
- effect TEXT NOT NULL CHECK(effect IN ('allow','deny'))
- created_by_user_id INTEGER NOT NULL
- created_at TEXT DEFAULT (datetime('now'))

Пример permission_key:

- transactions.edit_others
- categories.manage
- settings.auto_capital.manage

## 4. Метаданные операций

В таблицу transactions (в личной БД пользователя):

- owner_user_id INTEGER NOT NULL
- created_by_user_id INTEGER NOT NULL
- family_id INTEGER NULL

Смысл:

- owner_user_id: чьи это деньги;
- created_by_user_id: кто внес запись;
- family_id: операция участвует в семейной аналитике.

## 5. Профили приватности семьи

### 5.1 transparent (по умолчанию)

- Все участники видят транзакции и балансы всех участников.
- В ленте всегда видно владельца операции.

### 5.2 private_balances

- Участники видят общие семейные агрегаты.
- Транзакции других участников видны, но личные балансы по участникам скрыты.
- Детализация по владельцам ограничена (например, только имя без суммы счета).

### 5.3 strict_private

- Участники (role member/viewer) видят:
- свои операции;
- агрегаты семьи без детальной чужой транзакционной истории.
- Owner/Admin/Accountant могут иметь расширенный просмотр по роли.

## 6. Гибкая матрица прав

Роль дает базу, политика семьи может ужесточать или расширять в допустимых границах.

### owner

- полный доступ;
- роли/участники/инвайты;
- семейные политики и настройки;
- передача ownership.

### admin

- управление участниками (кроме передачи owner);
- управление семейными настройками;
- может менять policies в рамках owner-ограничений.

### accountant

- операции, категории, бюджеты, отчеты;
- без управления участниками и ownership.

### member

- добавление операций;
- редактирование/удаление — по family_policies;
- просмотр чужих данных — по visibility_mode/policies.

### viewer

- только чтение, объем чтения зависит от visibility_mode.

## 7. API-контур (расширенный)

Префикс: /api/v1/families

### Семья

- POST /families
- GET /families/me
- GET /families/{family_id}

### Участники и роли

- GET /families/{family_id}/members
- PATCH /families/{family_id}/members/{user_id}/role
- DELETE /families/{family_id}/members/{user_id}

### Приглашения

- POST /families/{family_id}/invites
- GET /families/{family_id}/invites
- POST /families/invites/accept
- POST /families/invites/revoke

### Настройки и политики

- GET /families/{family_id}/settings
- PATCH /families/{family_id}/settings
- GET /families/{family_id}/policies
- PATCH /families/{family_id}/policies

### Семейная аналитика

- GET /families/{family_id}/dashboard
- GET /families/{family_id}/transactions

Параметры:

- view=all|mine|member:{user_id}
- period=month|year|custom
- limit/offset

Сервер обязан отфильтровать результат согласно role + policies.

## 8. UX

- Переключатель контекста: "Личный" / "Семья".
- В семейном контексте:
- блок "Деньги семьи" (агрегаты);
- фильтр видимости транзакций (Все/Мои/Участник) в рамках прав;
- бейдж владельца у каждой операции.
- Раздел "Приватность и правила семьи":
- выбор visibility_mode;
- тумблеры granular-политик;
- предпросмотр "кто что увидит".

## 9. Правила разрешений (алгоритм)

При каждом запросе:

1. Проверить membership и статус active.
2. Взять базовые permissions из role.
3. Применить family_policies.
4. Применить personal override (если включено v1.1).
5. Выполнить финальную фильтрацию данных.

Важно: все проверки только на backend.

## 10. Производительность

- Агрегаты семьи кэшировать 10-30 сек.
- Инвалидировать кэш при изменении транзакций участников семьи.
- Для family transactions — строгая пагинация.
- Для больших семей подготовить materialized snapshot (v2).

## 11. Безопасность и аудит

- family_events:
- invite_create/accept/revoke
- role_change
- policy_change
- settings_change
- member_remove
- sensitive_action_confirm

- Критичные операции через подтверждение (доп. шаг).
- Нельзя удалить последнего owner.
- Owner не может покинуть семью без передачи ownership.

## 12. Поэтапный план

### Этап A (MVP core)

- families + memberships + invites + settings
- создание семьи, приглашение, роли
- семейный dashboard без приватных профилей (только transparent)

### Этап B (flex policies)

- family_policies
- режимы visibility_mode
- серверная фильтрация по policy

### Этап C (fine-grained)

- permission_overrides
- расширенная модель прав на уровне конкретного участника

## 13. Решения по умолчанию (рекомендация)

- visibility_mode = transparent
- member:
- может создавать операции
- может редактировать только свои
- не может удалять чужие
- категории управляют owner/admin/accountant

Это дает понятный старт и легкую настройку под менее прозрачные семьи.

## 14. Definition of Done для гибкой v1

- Семья создается и работает без слияния личных данных.
- Есть роли и применяются ограничения.
- Есть минимум 2 профиля видимости (transparent + strict_private).
- В семейной ленте корректно фильтруются данные по правам.
- Участник видит семейные агрегаты и свои личные данные одновременно.