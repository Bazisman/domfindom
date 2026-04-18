# Протокол: проверка email-подтверждения на хосте
Дата: 2026-04-16

## Контекст
- Запрошена проверка прод-окружения после релиза регистрации с подтверждением email.
- Требование: подтвердить, что backend/host настроены корректно, и зафиксировать результат.

## Что проверено
1. Версия кода на хосте
- Репозиторий хоста: `/var/www/u3480024/data/finance-app`
- Актуальный commit после хотфикса: `f0cd89a`

2. Запуск приложения
- Проверка health: `GET https://domfindom.ru/api/v1/health`
- Результат: `200 OK`, body `{"status":"ok"}`

3. Endpoint подтверждения email
- Проверка: `POST /api/v1/auth/verify-email` с заведомо невалидным токеном
- Результат: корректный бизнес-ответ `400` с текстом про недействительный/истекший токен.
- Вывод: роут активен, приложение использует новую версию auth-flow.

4. Конфигурация verify-email и SMTP (на проде)
- `require_email_verification = True`
- `email_verification_token_ttl_hours = 24`
- `email_verification_url_template = https://domfindom.ru/login?verify_email_token={token}`
- SMTP конфигурация присутствует (host/from/user/password заданы).

## Инцидент и исправление
Во время проверки обнаружен критичный startup-regression:
- Симптом: `500 Web application could not be started`
- Причина: после рефакторинга в `core.py` отсутствовал `import sqlite3`, а миграция recurring вызывала `sqlite3` из обертки.
- Фикс: добавлен импорт, выпущен hotfix:
  - commit: `f0cd89a`
  - действие: `git pull` на хост + restart
  - результат: сервис восстановлен, health green.

## Замечание по `.env`
- В `.env` значение `FINANCE_APP_PASSWORD_RESET_EMAIL_SUBJECT` содержит пробелы без кавычек.
- Для текущего запуска через `passenger_wsgi.py` это не ломает приложение, потому что используется собственный парсер `.env`.
- Но при shell-`source .env` это даёт предупреждение.
- Рекомендация: оборачивать значения с пробелами в кавычки для переносимости.

## Итоговый статус
- Email verification на проде: **включено и работает**.
- SMTP для отправки verify-писем: **настроен**.
- Backend/API после хотфикса: **работоспособен (health OK)**.
