# Security Hardening Phase 2: Production Hotfix (2026-04-11)

## Incident
- После выката фазы управления активными сессиями production начал отдавать `500` с Passenger error page (`Web application could not be started`).

## Root cause
- На сервере используется `Python 3.8.6`.
- В новых аннотациях были использованы `list[...]` в backend-коде:
  - `backend/schemas/auth.py`
  - `backend/auth/service.py`
- Для данного окружения это вызвало проблему при старте приложения.

## Fix
- Перевели аннотации на совместимый стиль:
  - `List[...]` вместо `list[...]`
  - добавлен импорт `from typing import List`
- Commit: `436f302` (`Fix Python 3.8 typing compatibility for session DTOs`)

## Deployment
- Обновлен backend-репозиторий на сервере:
  - `/var/www/u3480024/data/finance-app` -> `git pull --ff-only` до `436f302`
- Перезапуск Passenger:
  - `touch /var/www/u3480024/data/www/domfindom.ru/.restart-app`
- Фронтенд уже загружен с актуальным бандлом:
  - `/assets/index-z0Izk_js.js`

## Verification
- `GET /api/v1/health` -> `200 {"status":"ok"}`
- `POST /api/v1/auth/login` -> `200`, выставляются cookies `finance_session` и `finance_csrf`
- `GET /api/v1/auth/sessions`:
  - без авторизации -> `401 Unauthorized`
  - с валидной сессией и CSRF -> `200` и JSON со списком сессий
- Главная страница отдает корректный HTML c `<meta charset="UTF-8">`.

## Notes
- Обновление backend нужно выполнять в рабочем каталоге git-репозитория:
  - `/var/www/u3480024/data/finance-app`
- Каталог `/var/www/u3480024/data/www/domfindom.ru` используется как web root для статики/Passenger entrypoint, но не как основной git checkout приложения.
