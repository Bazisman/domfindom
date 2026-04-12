# Протокол: Core Refactor Phase 1
Дата: 2026-04-12

## Что сделано
- Добавлен новый модуль: `core_runtime.py`.
- В `core_runtime.py` вынесены инфраструктурные примитивы:
  - `DB_NAME`
  - `_DB_NAME_CONTEXT`
  - `_cache`
  - `_CACHE_TTL`, `_CACHE_TTL_LONG`
  - `_get_cached`, `_invalidate_cache`
  - `get_connection`, `push_db_name`, `pop_db_name`
- В `core.py` удалены дубли этих определений и подключен импорт из `core_runtime.py`.
- Совместимость сохранена: публичные имена остаются доступны через `core`.
- Дополнительно выделен модуль `core_settings.py`:
  - `get_app_setting`
  - `set_app_setting`
  - `get_auto_capital_settings`
  - `set_auto_capital_settings`
- В `core.py` эти методы теперь тонкие обертки над `core_settings.py` (поведение не изменено).
- Добавлен модуль `core_budgets.py` с бюджетной логикой:
  - `normalize_budget_period`
  - `get_budget_monthly_limit`
  - `set_budget`
  - `get_budgets`
  - `delete_budget`
  - `get_budget_report`
  - `check_budget`
  - `get_budget_status`
- В `core.py` бюджетные функции переведены на обертки над `core_budgets.py`.
- Добавлен модуль `core_accounts.py`:
  - `get_all_accounts`
  - `get_account_balance`
  - `update_account_balance`
  - `sync_accounts_with_transactions`
- В `core.py` эти функции переключены на обертки над `core_accounts.py`.
- Добавлен модуль `core_capital.py`:
  - `get_capital_accounts`
  - `get_default_capital_account`
  - `set_default_capital_account`
  - `invalidate_capital_cache`
  - `add_capital_account`
  - `update_capital_account`
  - `delete_capital_account`
  - `get_total_capital`
  - `get_transfers_history`
- В `core.py` блок капитала и история переводов переведены на обертки над `core_capital.py`.
- Добавлен модуль `core_reports.py`:
  - `get_expenses_by_category`
  - `get_income_by_category`
  - `get_capital_contributions_for_period`
  - `get_available_periods`
- В `core.py` аналитический блок переведен на обертки над `core_reports.py`.
- Добавлен модуль `core_reconciliation.py`:
  - `get_main_account`
  - `get_reconciliation_sources`
  - `add_reconciliation_source`
  - `update_reconciliation_source`
  - `delete_reconciliation_source`
  - `get_total_real_balance`
  - `get_last_reconciliation`
  - `save_reconciliation`
  - `get_reconciliations_history`
  - `delete_reconciliation`
  - `update_reconciliation`
- В `core.py` блок сверки переведен на обертки над `core_reconciliation.py`.
- Добавлен модуль `core_recurring.py`:
  - `_migrate_recurring_transactions`
  - `_adjust_to_workday`
  - `create_recurring_template`
  - `get_recurring_templates`
  - `get_recurring_template_by_id`
  - `update_recurring_template`
  - `delete_recurring_template`
  - `generate_planned_transactions`
  - `delete_planned_transactions`
  - `delete_planned_transactions_in_period`
  - `get_planned_transactions_due`
  - `get_planned_transactions_by_template`
- В `core.py` блок шаблонов/плановых транзакций переведен на обертки над `core_recurring.py`.
- Добавлен модуль `core_forecast.py`:
  - `get_projected_balance`
- В `core.py` прогнозный расчёт переведен на обертку над `core_forecast.py`.

## Проверки
- `python tools/check_encoding.py --root .` — OK.
- `npm run build` (frontend) — OK.
- `python -c "import core; ..."` — OK (экспорт и вызовы доступны).
- Дополнительно проверены бюджетные вызовы:
  - `core.get_budget_report('2026-04')`
  - `core.check_budget(...)`
  - `core.get_budget_status()`
- Проверка структуры accounts-блока:
  - импорты и сборка проходят;
  - при тестовом mutating-вызове в текущей среде пойман `sqlite3.OperationalError: disk I/O error` (ограничение окружения на запись в конкретную БД), не связано с изменением архитектуры модуля.
- Проверка структуры capital-блока:
  - `import core` и целевые функции доступны;
  - `python tools/check_encoding.py --root .` — OK;
  - `npm run build` — OK.
- Проверка структуры reports-блока:
  - `import core` и целевые функции доступны;
  - `python tools/check_encoding.py --root .` — OK;
  - `npm run build` — OK.
- Проверка структуры reconciliation/recurring-блоков:
  - `import core` и целевые функции доступны;
  - `python tools/check_encoding.py --root .` — OK;
  - `npm run build` — OK.
- Проверка структуры forecast-блока:
  - `import core` проходит;
  - `python tools/check_encoding.py --root .` — OK;
  - `npm run build` — OK;
  - при локальном прямом вызове `get_projected_balance()` в текущей среде снова наблюдается `sqlite3.OperationalError: disk I/O error` (ограничение окружения на запись/доступ к файлу БД).

## Важно
- Поведение бизнес-логики не менялось.
- Это инфраструктурный шаг для дальнейшего безопасного дробления `core.py` на доменные модули.
- Зафиксирован риск: `Set-Content -Encoding UTF8` в Windows PowerShell 5.1 записывает UTF-8 с BOM.
  Для безопасной записи без BOM используем `System.IO.File.WriteAllText(..., new UTF8Encoding($false))`.

## Update: Phase 1 Continued
- Added `core_categories.py` and moved category logic behind `core.py` wrappers.
- Added `core_admin_ops.py` and moved maintenance/index/transfer logic behind `core.py` wrappers.
- Validation repeated:
  - `python tools/check_encoding.py --root .` passed
  - `npm run build` passed
- Current `core.py` line count: 1117.
- Continued extraction: added `core_transactions_ops.py`.
- Moved to wrappers in `core.py`:
  - `add_planned_transaction`
  - `assign_template_to_planned_transaction`
  - `get_balance`
  - `get_last_transactions`
  - `get_all_transactions`
  - `get_transactions_count`
  - `get_transactions_by_period`
  - `get_transaction_by_id`
- Validation:
  - encoding check passed
  - frontend build passed
- Current `core.py` line count: 1057.


## Update: Phase 1 Continued (Facade Cleanup)
- Added `core_bootstrap.py` and moved DB bootstrap/seed logic from `core.py::init_db`.
- Added `get_capital_balance_from_transfers` and `get_capital_balance` to `core_capital.py`.
- `core.py` now uses wrappers for:
  - `init_db`
  - `_get_capital_balance_from_transfers`
  - `get_capital_balance`
- Fixed bootstrap flow to call `create_indexes()` after migration using a valid fresh DB connection path.
- Current `core.py` line count: 548.

### Validation
- `python tools/check_encoding.py --root .` passed.
- `npm run build` passed.
- `python -B -c "import core; ..."` import check passed.
- `pytest` is not available in the current environment (`No module named pytest`).
