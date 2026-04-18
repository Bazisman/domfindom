# AUTH IMPLEMENTATION PLAN

> Обновлено: 2026-04-11
> Назначение: конкретный поэтапный план внедрения авторизации и персонализации данных пользователей в текущем web-контуре проекта.

---

## Контекст

Текущее состояние:
- backend (`FastAPI`) работает без авторизации;
- все API-эндпоинты используют общую БД без разделения по пользователям;
- в `core.py` есть жёсткие single-user допущения (например, `accounts.id = 1` для основного счёта);
- проект уже в production на `domfindom.ru` (REG.RU + Passenger, Python 3.8).

Из этого следует:
- простой и безопасный этап 1 должен минимально ломать текущую финансовую логику;
- изоляция данных должна быть жёсткой и проверяемой.

---

## Рекомендуемая стратегия

Для текущей архитектуры оптимален путь:
- `Identity DB` (отдельная БД пользователей и сессий) +
- `per-user finance DB` (отдельный файл финансовой БД на пользователя).

Почему сейчас это безопаснее, чем мгновенный `user_id` во всех таблицах:
- не требует массовой переписи всех SQL-запросов в `core.py`;
- сохраняет текущую доменную логику, где основной счёт = `id=1`, но уже в рамках каждой пользовательской БД;
- резко снижает риск утечки данных между пользователями.

---

## Целевой результат

Пользователь может:
- зарегистрироваться и войти;
- работать только со своими данными;
- хранить свои настройки автоотчислений и прочие сущности независимо от других;
- безопасно завершать сессию (logout).

---

## План По Этапам

### Этап 1. Базовая auth-инфраструктура (backend)

1. Добавить модуль `backend/auth/`:
- `models.py` (структуры пользователя/сессии);
- `storage.py` (работа с `auth.db`);
- `security.py` (хэш пароля PBKDF2, генерация токена сессии, проверка);
- `dependencies.py` (`require_user`, `optional_user`).

2. Создать `auth.db` с таблицами:
- `users` (`id`, `email`, `password_hash`, `is_active`, `created_at`, `updated_at`);
- `sessions` (`id`, `user_id`, `token_hash`, `expires_at`, `created_at`, `revoked_at`, `ip`, `user_agent`).

3. Добавить auth-эндпоинты:
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

4. Сессии:
- cookie `httpOnly`, `Secure` (в production), `SameSite=Lax`;
- TTL сессии (например, 30 дней) + ротация при логине.

Критерий готовности:
- `register/login/me/logout` работают стабильно, без изменения бизнес-логики финансов.

### Этап 2. Изоляция данных по пользователям через per-user DB

1. Добавить резолвер пути БД пользователя:
- например: `data/users/{user_id}/finance.db`.

2. Перевести `core.get_connection()` на контекстное определение БД:
- default остаётся текущая `FINANCE_APP_DB_NAME`;
- для авторизованных API-запросов выбирается БД конкретного пользователя.

3. Добавить middleware:
- извлекает сессию из cookie;
- определяет `user_id`;
- выставляет контекст БД на время запроса.

4. На регистрацию:
- создавать файл пользовательской БД;
- выполнять `core.init_db()` для нового файла.

Критерий готовности:
- два пользователя видят разные данные при одинаковых API-запросах.

### Этап 3. Защита API и корректный UX фронтенда

1. Закрыть приватные роуты зависимостью `require_user`:
- `dashboard`, `transactions`, `categories`, `budgets`, `accounts`, `transfers`, `forecast`, `settings`, `recurring`.

2. Оставить публичными:
- `health`;
- `auth/register`, `auth/login`.

3. Добавить страницу входа во frontend:
- роут `/login`;
- guard для приватных страниц;
- загрузка `me` на старте.

4. Обновить `frontend/src/lib/api.ts`:
- `credentials: "include"` для cookie-сессий;
- обработка `401` с редиректом на `/login`.

Критерий готовности:
- неавторизованный пользователь не может читать/менять финданные.

### Этап 4. Миграция текущих прод-данных

1. Миграционный скрипт:
- создать первого пользователя-владельца;
- скопировать текущую `finance.db` в его `per-user` БД;
- зафиксировать backup до/после миграции.

2. Проверка:
- после миграции все текущие данные доступны владельцу;
- новый пользователь стартует с пустой БД-шаблоном.

Критерий готовности:
- production не теряет существующую историю операций.

### Этап 5. Безопасность и эксплуатация

1. Добавить rate limit на `/auth/login`.
2. Добавить аудит auth-событий (login success/fail, logout).
3. Добавить endpoint смены пароля.
4. Добавить reset password через одноразовый токен (следующим шагом).
5. Настроить backup не только `finance.db`, но и `auth.db` + директории пользовательских БД.

Критерий готовности:
- auth-контур пригоден для публичного использования несколькими людьми.

---

## Изменения По Файлам (первый проход)

Backend:
- `backend/api/router.py` (подключение `auth` роутов)
- `backend/api/routes/auth.py` (новый)
- `backend/main.py` и `backend/site_app.py` (middleware auth + DB context)
- `backend/config.py` (настройки cookie/session/auth-db)
- `core.py` (контекстный выбор БД в `get_connection`)

Frontend:
- `frontend/src/lib/api.ts` (`credentials: include`, auth API)
- `frontend/src/main.tsx` / `frontend/src/AppShellNext.tsx` (роуты и guard)
- новая страница `frontend/src/pages/LoginPage.tsx`

Docs:
- `docs/API_RESOURCES_PLAN.md` (добавить ресурс `auth`)
- `docs/DEPLOYMENT_GUIDE.md` (переменные окружения и backup для auth/per-user DB)
- `docs/DECISIONS.md` (после финального подтверждения выбранной стратегии)

---

## Тест-план (обязательный минимум)

Backend (`tests/test_web_api.py` + новый `tests/test_auth_api.py`):
- регистрация нового пользователя;
- login/logout;
- `401` без сессии;
- data isolation между двумя пользователями;
- доступность текущих данных после миграции владельца.

Frontend:
- guard приватных страниц;
- редирект на `/login` при `401`;
- устойчивость после перезагрузки страницы (cookie-сессия сохраняется).

---

## Риски и Контроль

Риски:
- случайное смешение данных при неверной настройке DB context;
- поломка production из-за миграции без backup;
- несовместимость зависимостей с Python 3.8 на REG.RU.

Контроль:
- делать auth на встроенных возможностях Python (без тяжёлых/нестабильных новых зависимостей);
- внедрять по этапам с автотестами после каждого шага;
- перед миграцией production обязательно делать backup и dry-run локально.

---

## Предлагаемый Порядок Реализации

1. Этап 1 (auth endpoints + sessions) на локальной среде.
2. Этап 2 (per-user DB routing) + тесты изоляции.
3. Этап 3 (frontend login + route guard).
4. Этап 4 (production migration + backup plan).
5. Этап 5 (hardening и эксплуатационные улучшения).

---

## Implementation Protocol (2026-04-11)

Status:
- Stage 1 (`register/login/logout/me`) implemented.
- Stage 2 (per-user finance DB routing) implemented.
- Stage 3 (frontend login + protected routes) implemented.
- Baseline hardening started.

Security/performance protocol:
1. Keep identity/session data in `auth.db` and business data in per-user DB files.
2. Enforce `HttpOnly` session cookies, `SameSite=Lax`, and `Secure=true` in production.
3. Require a non-default `FINANCE_APP_SESSION_SECRET` when `FINANCE_APP_ENV=production`.
4. Use strong password hashing (`scrypt`) and reject weak passwords at registration.
5. Run session cleanup for revoked/expired records to keep auth lookup fast.
6. Initialize each user finance DB once (on first use), never on every request.
7. Keep private API routers behind `require_user`; leave only `health` and `auth` public.
8. Validate by automated suite (`python -m unittest tests.test_financial_logic tests.test_web_api -v`) and frontend build (`npm run build`).

Next hardening backlog:
1. Add login rate limiting on `/api/v1/auth/login`.
2. Add password change and reset flow.
3. Add auth audit trail (success/fail login, logout, session revoke).
4. Add production backup policy for both `auth.db` and `data/users/**/finance.db`.

### Update 2026-04-11 (implemented)
- Login rate limiting is now implemented in backend auth flow.
- Auth audit events are now persisted (`register/login/logout`, success/fail/blocked).

### Update 2026-04-11 (implemented)
- Added `POST /api/v1/auth/change-password` (requires auth, validates current password, revokes sessions).
- Added password reset flow:
  - `POST /api/v1/auth/password-reset/request`
  - `POST /api/v1/auth/password-reset/confirm`
- Added `password_reset_tokens` storage with expiry and one-time token usage.
- Added auth event logging for password change and reset flows.

### Update 2026-04-11 (email reset delivery)
- Added SMTP-based password reset email delivery (configurable via env).
- Password reset request now sends mail when SMTP is configured; otherwise it keeps fallback flow.
- Added environment settings for SMTP host/port/user/password/from and reset link template.
