# API RESOURCES PLAN

> Обновлено: 2026-04-08
> Назначение: зафиксировать доменные ресурсы, основные DTO и будущие эндпоинты backend API для web-версии проекта.

---

## Зачем Нужен Этот Файл

`docs/WEB_MIGRATION_PLAN.md` уже зафиксировал целевой стек и общий путь миграции. Следующий практический шаг — разложить backend на понятные API-ресурсы, чтобы:
- не строить web-версию вслепую
- не тащить desktop-паттерны в API
- заранее договориться о названиях, полях и границах ответственности

---

## Главные Принципы API

- API должен быть `API-first`, а не “обёрткой над UI”
- финансовая логика живёт в backend, а не во frontend
- frontend получает уже подготовленные данные и не придумывает формулы сам
- `planned` и `actual` должны быть явно выражены в контрактах
- деньги в API лучше передавать как числа фиксированной точности на уровне backend-моделей и валидировать отдельно
- названия ресурсов должны отражать домен проекта, а не структуру текущих desktop-экранов

---

## Версия API

Рекомендуемый префикс:
- `/api/v1`

Примеры:
- `/api/v1/transactions`
- `/api/v1/categories`
- `/api/v1/budgets`

Это даст возможность позже менять контракты без хаотичных поломок.

---

## Базовые Доменные Ресурсы

### 1. `transactions`

Главный ресурс движения денег.

Покрывает:
- доходы
- расходы
- фактические операции
- плановые операции

Основные поля:
- `id`
- `type` = `income | expense`
- `category_id`
- `category_name`
- `amount`
- `comment`
- `date`
- `status` = `actual | planned`
- `template_id` при наличии связи с recurring-шаблоном
- `created_at`
- `updated_at`

Основные эндпоинты:
- `GET /api/v1/transactions`
- `GET /api/v1/transactions/{id}`
- `POST /api/v1/transactions`
- `PATCH /api/v1/transactions/{id}`
- `DELETE /api/v1/transactions/{id}`

Поддерживаемые фильтры:
- `type`
- `status`
- `category_id`
- `date_from`
- `date_to`
- `limit`
- `offset`

Отдельные замечания:
- `planned` не должен автоматически смешиваться с `actual`
- экспорт в будущем должен использовать отдельный поток чтения, а не UI-лимит

### 2. `categories`

Справочник категорий.

Основные поля:
- `id`
- `name`
- `type` = `income | expense | both`
- `color`
- `icon`
- `is_active`

Основные эндпоинты:
- `GET /api/v1/categories`
- `GET /api/v1/categories/{id}`
- `POST /api/v1/categories`
- `PATCH /api/v1/categories/{id}`
- `DELETE /api/v1/categories/{id}`

Поддерживаемые фильтры:
- `type`
- `include_inactive`

Отдельные замечания:
- удаление логичнее оставить мягким, через деактивацию
- frontend должен получать и `id`, и `name`, а не жить только на строковых категориях

### 3. `budgets`

Лимиты расходов по категориям.

Основные поля:
- `id`
- `category_id`
- `category_name`
- `amount`
- `period` = `monthly | yearly`

Дополнительные вычисляемые поля в расширенных ответах:
- `spent_actual`
- `remaining`
- `progress_percent`
- `is_over_limit`

Основные эндпоинты:
- `GET /api/v1/budgets`
- `GET /api/v1/budgets/{id}`
- `POST /api/v1/budgets`
- `PATCH /api/v1/budgets/{id}`
- `DELETE /api/v1/budgets/{id}`

Дополнительные endpoинты/представления:
- `GET /api/v1/budgets/report`
- `GET /api/v1/budgets/status`

Отдельные замечания:
- бюджетные отчёты и предупреждения считают только фактические расходы
- `planned` не должен влиять на факт использования бюджета
- Практически уже реализовано в web backend:
  - `GET /api/v1/budgets`
  - `GET /api/v1/budgets/{id}`
  - `POST /api/v1/budgets`
  - `PATCH /api/v1/budgets/{id}`
  - `DELETE /api/v1/budgets/{id}`
  - `GET /api/v1/budgets/report`
  - `GET /api/v1/budgets/status`

### 4. `accounts`

Счета проекта.

На первом этапе можно держать это как единый ресурс с типами, даже если внутри логика разделяет основной счёт и капитал.

Основные поля:
- `id`
- `name`
- `type` = `main | capital | savings`
- `balance`
- `currency`
- `is_active`
- `is_default` для счетов капитала, где применимо

Основные эндпоинты:
- `GET /api/v1/accounts`
- `GET /api/v1/accounts/{id}`
- `POST /api/v1/accounts`
- `PATCH /api/v1/accounts/{id}`
- `DELETE /api/v1/accounts/{id}`

Отдельные замечания:
- основной счёт сейчас системно привязан к `accounts.id = 1`
- это правило надо сохранить в backend-логике, а не навязывать frontend
- Практически уже реализовано в web backend:
  - `GET /api/v1/accounts`
  - `GET /api/v1/accounts/{id}`
  - `POST /api/v1/accounts` для счетов капитала
  - `PATCH /api/v1/accounts/{id}` для счетов капитала
  - `DELETE /api/v1/accounts/{id}` для счетов капитала

### 5. `transfers`

Переводы между счетами.

Основные поля:
- `id`
- `from_account_id`
- `to_account_id`
- `amount`
- `date`
- `comment`

Основные эндпоинты:
- `GET /api/v1/transfers`
- `GET /api/v1/transfers/{id}`
- `POST /api/v1/transfers`
- `DELETE /api/v1/transfers/{id}`

Отдельные замечания:
- перевод — самостоятельная финансовая сущность
- он не должен теряться в истории только потому, что связан с автоотчислением
- Практически уже реализовано в web backend:
  - `GET /api/v1/transfers`
  - `POST /api/v1/transfers`

### 6. `recurring-templates`

Шаблоны регулярных операций.

Основные поля:
- `id`
- `name`
- `type`
- `category_id`
- `category_name`
- `amount`
- `comment`
- `day_of_month`
- `is_active`
- `start_date`
- `end_date`

Основные эндпоинты:
- `GET /api/v1/recurring-templates`
- `GET /api/v1/recurring-templates/{id}`
- `POST /api/v1/recurring-templates`
- `PATCH /api/v1/recurring-templates/{id}`
- `DELETE /api/v1/recurring-templates/{id}`

Служебные действия:
- `POST /api/v1/recurring-templates/{id}/regenerate`
- `POST /api/v1/recurring-templates/execute-overdue`

Отдельные замечания:
- редактирование шаблона не должно терять категорию
- регенерация planned должна происходить в одном центре логики

### 7. `forecast`

Прогноз и агрегаты для планирования.

Это не “справочник”, а вычисляемый ресурс.

Основные поля ответа:
- `current_balance`
- `planned_income`
- `planned_expense`
- `budget_reserved`
- `projected_balance`
- `period`

Основные эндпоинты:
- `GET /api/v1/forecast`
- `GET /api/v1/forecast/month-end`

Отдельные замечания:
- этот ресурс должен возвращать уже согласованную формулу прогноза
- frontend не должен самостоятельно вычитать бюджеты и плановые расходы

### 8. `dashboard`

Агрегированный ресурс для главного экрана web-версии.

Возможные части ответа:
- `balance`
- `month_summary`
- `forecast`
- `recent_transactions`
- `budget_highlights`

Основной эндпоинт:
- `GET /api/v1/dashboard`

Отдельные замечания:
- удобно для первого web MVP
- может быть собран как композиция из других ресурсов, но для frontend полезен как единая точка входа

### 9. `settings`

Проектные и пользовательские настройки.

На первом этапе сюда можно вынести:
- настройки автоотчислений
- UI-предпочтения
- системные флаги поведения

Основные поля:
- `auto_capital_enabled`
- `auto_capital_percent`
- `default_capital_account_id`

Основные эндпоинты:
- `GET /api/v1/settings`
- `PATCH /api/v1/settings`

---

## Рекомендуемые Форматы DTO

### Transaction DTO

```json
{
  "id": 123,
  "type": "expense",
  "category_id": 5,
  "category_name": "Продукты",
  "amount": 3000.0,
  "comment": "Пятерочка",
  "date": "2026-04-08",
  "status": "actual",
  "template_id": null
}
```

### Category DTO

```json
{
  "id": 5,
  "name": "Продукты",
  "type": "expense",
  "color": "#4caf50",
  "icon": "cart",
  "is_active": true
}
```

### Budget Report DTO

```json
{
  "id": 7,
  "category_id": 5,
  "category_name": "Продукты",
  "amount": 30000.0,
  "period": "monthly",
  "spent_actual": 12450.0,
  "remaining": 17550.0,
  "progress_percent": 41.5,
  "is_over_limit": false
}
```

### Forecast DTO

```json
{
  "period": "2026-04",
  "current_balance": 105500.0,
  "planned_income": 120000.0,
  "planned_expense": 15000.0,
  "budget_reserved": 20000.0,
  "projected_balance": 210500.0
}
```

---

## Что Лучше Уточнить До Реализации

### 1. Деньги

Нужно решить:
- оставаться ли на `float` внутри старого слоя как переходном варианте
- или сразу готовить отдельный подход для точных денежных значений

Практичный путь:
- на первом этапе оставить текущую модель
- в API-валидации и новых схемах зафиксировать правила округления

### 2. Даты

Нужно унифицировать:
- `YYYY-MM-DD` для дат операций
- `YYYY-MM` для месячных отчётов и бюджетных периодов

### 3. Ошибки API

Нужно заранее договориться о типовых ошибках:
- `validation_error`
- `not_found`
- `business_rule_error`
- `conflict`

### 4. Идентификаторы

Frontend должен работать по `id`, а не по отображаемым именам, особенно для:
- категорий
- счетов
- recurring-шаблонов

---

## Минимальный Набор Для Первого Web MVP

Если выбирать только самое нужное для старта:

- `GET /api/v1/dashboard`
- `GET /api/v1/transactions`
- `POST /api/v1/transactions`
- `PATCH /api/v1/transactions/{id}`
- `DELETE /api/v1/transactions/{id}`
- `GET /api/v1/categories`
- `GET /api/v1/budgets/report`
- `GET /api/v1/forecast/month-end`

Этого уже достаточно, чтобы сделать первый полезный web-клиент с:
- балансом
- списком транзакций
- добавлением операций
- отображением категорий
- бюджетами
- прогнозом конца месяца

Дополнительно уже доступны backend-ресурсы, которые хорошо готовят следующий экран после dashboard:
- `GET /api/v1/accounts`
- `GET /api/v1/transfers`

---

## Что Улучшить В Проекте Перед Реализацией API

- разделить доменную логику и UI-слушатели в `services/`
- уменьшить зависимость от строковых `category_name` там, где уже пора перейти на `category_id`
- постепенно отделить агрегаты для dashboard и forecast от desktop view-формата
- начать формализовать response-схемы до создания FastAPI-роутов

---

## Следующий Логичный Документ

После этого файла полезнее всего создать:
- `docs/WEB_MVP_SCOPE.md`

Там нужно зафиксировать:
- какие именно web-экраны войдут в первую версию
- что будет обязательно
- что сознательно откладывается
