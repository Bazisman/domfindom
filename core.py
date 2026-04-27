"""
Ядро приложения - работа с базой данных и бизнес-логика
"""
import sqlite3
from utils.logger import app_logger
from core_runtime import (
    DB_NAME,
    _DB_NAME_CONTEXT,
    _cache,
    _CACHE_TTL,
    _CACHE_TTL_LONG,
    _get_cached,
    _invalidate_cache,
    get_connection,
    push_db_name,
    pop_db_name,
)
from core_settings import (
    get_app_setting as _settings_get_app_setting,
    set_app_setting as _settings_set_app_setting,
    get_auto_capital_settings as _settings_get_auto_capital_settings,
    set_auto_capital_settings as _settings_set_auto_capital_settings,
    get_default_money_source as _settings_get_default_money_source,
    set_default_money_source as _settings_set_default_money_source,
    get_family_visible_daily_money_sources as _settings_get_family_visible_daily_money_sources,
    set_family_visible_daily_money_source as _settings_set_family_visible_daily_money_source,
)
from core_budgets import (
    normalize_budget_period as _budgets_normalize_budget_period,
    get_budget_monthly_limit as _budgets_get_budget_monthly_limit,
    set_budget as _budgets_set_budget,
    get_budgets as _budgets_get_budgets,
    delete_budget as _budgets_delete_budget,
    get_budget_report as _budgets_get_budget_report,
    check_budget as _budgets_check_budget,
    get_budget_status as _budgets_get_budget_status,
)
from core_accounts import (
    get_all_accounts as _accounts_get_all_accounts,
    get_account_balance as _accounts_get_account_balance,
    update_daily_account as _accounts_update_daily_account,
    update_account_balance as _accounts_update_account_balance,
    sync_accounts_with_transactions as _accounts_sync_accounts_with_transactions,
)
from core_capital import (
    get_capital_accounts as _capital_get_capital_accounts,
    get_default_capital_account as _capital_get_default_capital_account,
    get_capital_balance_from_transfers as _capital_get_capital_balance_from_transfers,
    get_capital_balance as _capital_get_capital_balance,
    set_default_capital_account as _capital_set_default_capital_account,
    invalidate_capital_cache as _capital_invalidate_capital_cache,
    add_capital_account as _capital_add_capital_account,
    update_capital_account as _capital_update_capital_account,
    delete_capital_account as _capital_delete_capital_account,
    get_total_capital as _capital_get_total_capital,
    get_transfers_history as _capital_get_transfers_history,
)
from core_reports import (
    get_expenses_by_category as _reports_get_expenses_by_category,
    get_income_by_category as _reports_get_income_by_category,
    get_capital_contributions_for_period as _reports_get_capital_contributions_for_period,
    get_capital_outflow_for_period as _reports_get_capital_outflow_for_period,
    get_available_periods as _reports_get_available_periods,
)
from core_reconciliation import (
    get_main_account as _recon_get_main_account,
    get_reconciliation_sources as _recon_get_reconciliation_sources,
    add_reconciliation_source as _recon_add_reconciliation_source,
    update_reconciliation_source as _recon_update_reconciliation_source,
    delete_reconciliation_source as _recon_delete_reconciliation_source,
    get_total_real_balance as _recon_get_total_real_balance,
    get_last_reconciliation as _recon_get_last_reconciliation,
    save_reconciliation as _recon_save_reconciliation,
    get_reconciliations_history as _recon_get_reconciliations_history,
    delete_reconciliation as _recon_delete_reconciliation,
    update_reconciliation as _recon_update_reconciliation,
)
from core_recurring import (
    migrate_recurring_transactions as _recurring_migrate_recurring_transactions,
    adjust_to_workday as _recurring_adjust_to_workday,
    create_recurring_template as _recurring_create_recurring_template,
    get_recurring_templates as _recurring_get_recurring_templates,
    get_recurring_template_by_id as _recurring_get_recurring_template_by_id,
    update_recurring_template as _recurring_update_recurring_template,
    delete_recurring_template as _recurring_delete_recurring_template,
    generate_planned_transactions as _recurring_generate_planned_transactions,
    delete_planned_transactions as _recurring_delete_planned_transactions,
    delete_planned_transactions_in_period as _recurring_delete_planned_transactions_in_period,
    get_planned_transactions_due as _recurring_get_planned_transactions_due,
    get_planned_transactions_by_template as _recurring_get_planned_transactions_by_template,
)
from core_forecast import (
    get_projected_balance as _forecast_get_projected_balance,
)
from core_planned_execution import (
    execute_planned_transaction as _planned_execute_planned_transaction,
    execute_all_planned_transactions as _planned_execute_all_planned_transactions,
)
from core_categories import (
    get_all_categories as _categories_get_all_categories,
    invalidate_category_cache as _categories_invalidate_category_cache,
    add_category as _categories_add_category,
    update_category as _categories_update_category,
    delete_category as _categories_delete_category,
    get_category_by_id as _categories_get_category_by_id,
    get_category_by_name as _categories_get_category_by_name,
)
from core_admin_ops import (
    reset_to_factory as _admin_reset_to_factory,
    create_indexes_internal as _admin_create_indexes_internal,
    create_indexes as _admin_create_indexes,
    add_transfer_record as _admin_add_transfer_record,
    transfer_money as _admin_transfer_money,
)
from core_transactions_ops import (
    add_planned_transaction as _tx_add_planned_transaction,
    assign_template_to_planned_transaction as _tx_assign_template_to_planned_transaction,
    get_balance as _tx_get_balance,
    get_last_transactions as _tx_get_last_transactions,
    get_all_transactions as _tx_get_all_transactions,
    get_transactions_count as _tx_get_transactions_count,
    get_transactions_by_period as _tx_get_transactions_by_period,
    get_transaction_by_id as _tx_get_transaction_by_id,
)
from core_transactions_mutations import (
    add_income_with_capital as _txm_add_income_with_capital,
    add_expense as _txm_add_expense,
    delete_transaction as _txm_delete_transaction,
    update_transaction as _txm_update_transaction,
    update_transaction_fields as _txm_update_transaction_fields,
)
from core_bootstrap import init_db as _bootstrap_init_db


# DB context and cache primitives are centralized in core_runtime.py.


def init_db():
    return _bootstrap_init_db(
        get_connection,
        app_logger,
        _migrate_recurring_transactions,
        create_indexes,
    )


#


def get_app_setting(key, default=None):
    return _settings_get_app_setting(get_connection, key, default)


def set_app_setting(key, value):
    return _settings_set_app_setting(get_connection, key, value)


def get_auto_capital_settings():
    return _settings_get_auto_capital_settings(get_connection)


def set_auto_capital_settings(enabled: bool, percent: int):
    return _settings_set_auto_capital_settings(get_connection, enabled, percent)


def get_default_money_source():
    return _settings_get_default_money_source(get_connection)


def set_default_money_source(money_source: str):
    return _settings_set_default_money_source(get_connection, money_source)


def get_family_visible_daily_money_sources():
    return _settings_get_family_visible_daily_money_sources(get_connection)


def set_family_visible_daily_money_source(money_source: str, visible: bool):
    return _settings_set_family_visible_daily_money_source(get_connection, money_source, visible)



def _get_capital_balance_from_transfers(account_id):
    return _capital_get_capital_balance_from_transfers(get_connection, account_id)


def get_capital_balance(account_id):
    return _capital_get_capital_balance(get_connection, account_id)

# ========== РАБОТА С ТРАНЗАКЦИЯМИ И ОТЧИСЛЕНИЯМИ ==========

def add_income_with_capital(amount, category, comment, date, auto_percent, capital_account_id, money_source="cashless"):
    return _txm_add_income_with_capital(
        get_connection,
        app_logger,
        _invalidate_cache,
        amount,
        category,
        comment,
        date,
        auto_percent,
        capital_account_id,
        money_source=money_source,
    )


def add_expense(amount, category, comment, date, money_source="cashless"):
    return _txm_add_expense(
        get_connection,
        app_logger,
        _invalidate_cache,
        amount,
        category,
        comment,
        date,
        money_source=money_source,
    )


def add_planned_transaction(transaction_type, category, amount, comment, date, template_id=None, money_source="cashless"):
    return _tx_add_planned_transaction(
        get_connection,
        _invalidate_cache,
        app_logger,
        transaction_type,
        category,
        amount,
        comment,
        date,
        template_id=template_id,
        money_source=money_source,
    )


def assign_template_to_planned_transaction(transaction_id, template_id):
    return _tx_assign_template_to_planned_transaction(
        get_connection,
        _invalidate_cache,
        transaction_id,
        template_id,
    )


def delete_transaction(transaction_id):
    return _txm_delete_transaction(
        get_connection,
        app_logger,
        _invalidate_cache,
        transaction_id,
    )


def get_balance(force_update=False):
    return _tx_get_balance(get_connection, _get_cached, force_update=force_update)


def get_last_transactions(limit=10, offset=0):
    return _tx_get_last_transactions(get_connection, limit=limit, offset=offset)


def get_all_transactions():
    return _tx_get_all_transactions(get_connection)


def get_transactions_count():
    return _tx_get_transactions_count(get_connection)


def get_transactions_by_period(start_date, end_date, limit=500, offset=0):
    return _tx_get_transactions_by_period(
        get_connection,
        start_date,
        end_date,
        limit=limit,
        offset=offset,
    )


def get_transaction_by_id(transaction_id):
    return _tx_get_transaction_by_id(get_connection, transaction_id)


def update_transaction(transaction_id, field, value):
    return _txm_update_transaction(
        get_connection,
        app_logger,
        _invalidate_cache,
        transaction_id,
        field,
        value,
    )


def update_transaction_fields(transaction_id, **kwargs):
    return _txm_update_transaction_fields(
        get_connection,
        app_logger,
        _invalidate_cache,
        transaction_id,
        **kwargs,
    )


# ========== РАБОТА С КАТЕГОРИЯМИ ==========

def get_all_categories(trans_type=None, include_inactive=False):
    return _categories_get_all_categories(
        get_connection,
        _cache,
        _get_cached,
        _CACHE_TTL_LONG,
        trans_type=trans_type,
        include_inactive=include_inactive,
    )


def add_category(name, category_type='both', color='#808080', icon='📁'):
    return _categories_add_category(
        get_connection,
        app_logger,
        _invalidate_category_cache,
        sqlite3,
        name,
        category_type=category_type,
        color=color,
        icon=icon,
    )


def update_category(category_id, **kwargs):
    return _categories_update_category(
        get_connection,
        app_logger,
        _invalidate_category_cache,
        category_id,
        **kwargs,
    )


def delete_category(category_id):
    return _categories_delete_category(
        app_logger,
        update_category,
        _invalidate_category_cache,
        category_id,
    )


def _invalidate_category_cache():
    _categories_invalidate_category_cache(_cache)


def get_category_by_id(category_id):
    return _categories_get_category_by_id(get_connection, category_id)


def get_category_by_name(name):
    return _categories_get_category_by_name(get_connection, name)


# ========== РАБОТА С КАПИТАЛОМ ==========

def get_capital_accounts(include_inactive=False):
    return _capital_get_capital_accounts(
        get_connection,
        _cache,
        _get_cached,
        _CACHE_TTL_LONG,
        include_inactive=include_inactive,
    )


def get_default_capital_account():
    return _capital_get_default_capital_account(get_connection)


def set_default_capital_account(account_id):
    return _capital_set_default_capital_account(
        get_connection,
        app_logger,
        _invalidate_capital_cache,
        account_id,
    )


def _invalidate_capital_cache():
    _capital_invalidate_capital_cache(_cache)


def add_capital_account(name, balance=0, icon='💰', color='#ff9800', purpose='cushion', counts_as_cushion=None):
    return _capital_add_capital_account(
        get_connection,
        app_logger,
        _invalidate_capital_cache,
        name,
        balance=balance,
        icon=icon,
        color=color,
        purpose=purpose,
        counts_as_cushion=counts_as_cushion,
    )


def update_capital_account(account_id, **kwargs):
    return _capital_update_capital_account(
        get_connection,
        app_logger,
        _invalidate_capital_cache,
        account_id,
        **kwargs,
    )


def delete_capital_account(account_id):
    return _capital_delete_capital_account(
        get_connection,
        app_logger,
        _invalidate_capital_cache,
        account_id,
    )


def get_total_capital():
    return _capital_get_total_capital(get_connection)


# ========== РАБОТА С ПЕРЕВОДАМИ ==========

def get_transfers_history(account_id=None, limit=100, include_inactive=False):
    return _capital_get_transfers_history(
        get_connection,
        app_logger,
        account_id=account_id,
        limit=limit,
        include_inactive=include_inactive,
    )


# ========== РАБОТА С БЮДЖЕТАМИ ==========

def set_budget(category_id, amount, period='monthly'):
    return _budgets_set_budget(get_connection, app_logger, category_id, amount, period)


def get_budgets():
    return _budgets_get_budgets(get_connection)


def _normalize_budget_period(period):
    return _budgets_normalize_budget_period(period)


def _get_budget_monthly_limit(amount, period, reference_date=None):
    return _budgets_get_budget_monthly_limit(amount, period, reference_date)


def delete_budget(budget_id):
    return _budgets_delete_budget(get_connection, app_logger, budget_id)


def get_budget_report(month=None):
    return _budgets_get_budget_report(
        get_connection,
        get_budgets,
        _get_budget_monthly_limit,
        month=month,
    )

# ========== РАБОТА СО СЧЕТАМИ ==========

def get_all_accounts(include_inactive=False):
    return _accounts_get_all_accounts(get_connection, include_inactive=include_inactive)


def get_account_balance(account_id):
    return _accounts_get_account_balance(get_connection, account_id)


def update_account_balance(account_id, amount):
    result = _accounts_update_account_balance(
        get_connection,
        app_logger,
        _invalidate_capital_cache,
        account_id,
        amount,
    )
    if result:
        _invalidate_cache()
    return result


def update_daily_account(account_id, **kwargs):
    result = _accounts_update_daily_account(
        get_connection,
        app_logger,
        account_id,
        name=kwargs.get("name"),
        balance=kwargs.get("balance"),
    )
    if result:
        _invalidate_cache()
    return result


def sync_accounts_with_transactions():
    return _accounts_sync_accounts_with_transactions(
        get_connection,
        app_logger,
        _get_capital_balance_from_transfers,
    )


def get_expenses_by_category(start_date=None, end_date=None):
    return _reports_get_expenses_by_category(
        get_connection,
        start_date=start_date,
        end_date=end_date,
    )


def get_income_by_category(start_date=None, end_date=None):
    return _reports_get_income_by_category(
        get_connection,
        start_date=start_date,
        end_date=end_date,
    )


def get_capital_contributions_for_period(start_date=None, end_date=None):
    return _reports_get_capital_contributions_for_period(
        get_connection,
        start_date=start_date,
        end_date=end_date,
    )


def get_capital_outflow_for_period(start_date=None, end_date=None):
    return _reports_get_capital_outflow_for_period(
        get_connection,
        start_date=start_date,
        end_date=end_date,
    )


def get_available_periods():
    return _reports_get_available_periods(get_connection)


def check_budget(category_id, amount, date=None):
    return _budgets_check_budget(
        get_connection,
        _get_budget_monthly_limit,
        category_id,
        amount,
        date=date,
    )


def reset_to_factory():
    return _admin_reset_to_factory(get_connection, app_logger, DB_NAME, init_db)


def _create_indexes_internal(cursor):
    return _admin_create_indexes_internal(cursor, app_logger)


def create_indexes():
    return _admin_create_indexes(get_connection, app_logger, _create_indexes_internal)


def add_transfer_record(from_account_id, to_account_id, amount, date=None, comment=""):
    return _admin_add_transfer_record(
        get_connection,
        app_logger,
        from_account_id,
        to_account_id,
        amount,
        date=date,
        comment=comment,
    )


def transfer_money(from_account_id, to_account_id, amount, date=None, comment=""):
    return _admin_transfer_money(
        get_connection,
        app_logger,
        from_account_id,
        to_account_id,
        amount,
        date=date,
        comment=comment,
    )


def get_main_account():
    return _recon_get_main_account(get_connection)


def get_reconciliation_sources():
    return _recon_get_reconciliation_sources(get_connection)


def add_reconciliation_source(name, balance=0):
    return _recon_add_reconciliation_source(get_connection, app_logger, name, balance=balance)


def update_reconciliation_source(source_id, **kwargs):
    return _recon_update_reconciliation_source(get_connection, source_id, **kwargs)


def delete_reconciliation_source(source_id):
    return _recon_delete_reconciliation_source(get_connection, source_id)


def get_total_real_balance():
    return _recon_get_total_real_balance(get_connection)


def get_last_reconciliation():
    return _recon_get_last_reconciliation(get_connection)


def save_reconciliation(real_balance, program_balance, difference, adjustment_transaction_id=None):
    return _recon_save_reconciliation(
        get_connection,
        app_logger,
        get_last_reconciliation,
        real_balance,
        program_balance,
        difference,
        adjustment_transaction_id=adjustment_transaction_id,
    )


def get_reconciliations_history(limit=50):
    return _recon_get_reconciliations_history(get_connection, limit=limit)


def delete_reconciliation(recon_id):
    return _recon_delete_reconciliation(
        get_connection,
        app_logger,
        _invalidate_cache,
        recon_id,
    )


def update_reconciliation(recon_id, real_balance, program_balance, difference, adjustment_transaction_id=None):
    return _recon_update_reconciliation(
        get_connection,
        app_logger,
        recon_id,
        real_balance,
        program_balance,
        difference,
        adjustment_transaction_id=adjustment_transaction_id,
    )


# ========== РЕГУЛЯРНЫЕ ПЛАТЕЖИ (ПЛАНОВЫЕ ТРАНЗАКЦИИ) ==========

def _migrate_recurring_transactions():
    return _recurring_migrate_recurring_transactions(get_connection, app_logger, sqlite3)


def _adjust_to_workday(date_str):
    return _recurring_adjust_to_workday(date_str)


def create_recurring_template(template_type, name, amount, day_of_month, category_id=None,
                              comment_template="", months_ahead=12, working_days_only=0,
                              money_source="cashless"):
    return _recurring_create_recurring_template(
        get_connection,
        app_logger,
        generate_planned_transactions,
        template_type,
        name,
        amount,
        day_of_month,
        category_id=category_id,
        comment_template=comment_template,
        months_ahead=months_ahead,
        working_days_only=working_days_only,
        money_source=money_source,
    )


def get_recurring_templates(template_type=None):
    return _recurring_get_recurring_templates(get_connection, template_type=template_type)


def get_recurring_template_by_id(template_id):
    return _recurring_get_recurring_template_by_id(get_connection, template_id)


def update_recurring_template(template_id, **kwargs):
    return _recurring_update_recurring_template(
        get_connection,
        app_logger,
        delete_planned_transactions,
        generate_planned_transactions,
        template_id,
        **kwargs,
    )


def delete_recurring_template(template_id):
    return _recurring_delete_recurring_template(get_connection, app_logger, template_id)


def generate_planned_transactions(template_id, months=None, include_current_due=False):
    return _recurring_generate_planned_transactions(
        get_connection,
        app_logger,
        get_recurring_template_by_id,
        _adjust_to_workday,
        template_id,
        months=months,
        include_current_due=include_current_due,
    )


def delete_planned_transactions(template_id, from_date=None):
    return _recurring_delete_planned_transactions(
        get_connection,
        app_logger,
        template_id,
        from_date=from_date,
    )


def delete_planned_transactions_in_period(template_id, start_date, end_date):
    return _recurring_delete_planned_transactions_in_period(
        get_connection,
        app_logger,
        template_id,
        start_date,
        end_date,
    )


def get_planned_transactions_due():
    return _recurring_get_planned_transactions_due(get_connection)


def get_planned_transactions_by_template(template_id):
    return _recurring_get_planned_transactions_by_template(get_connection, template_id)


def execute_planned_transaction(transaction_id, auto_percent=0, capital_account_id=None):
    return _planned_execute_planned_transaction(
        get_connection,
        app_logger,
        _invalidate_cache,
        transaction_id,
        auto_percent=auto_percent,
        capital_account_id=capital_account_id,
    )


def execute_all_planned_transactions(auto_percent=0, capital_account_id=None):
    return _planned_execute_all_planned_transactions(
        app_logger,
        get_planned_transactions_due,
        execute_planned_transaction,
        auto_percent=auto_percent,
        capital_account_id=capital_account_id,
    )


def get_projected_balance(end_date=None):
    return _forecast_get_projected_balance(
        get_connection,
        _get_budget_monthly_limit,
        app_logger,
        end_date=end_date,
    )


def get_budget_status(category_id: int = None):
    return _budgets_get_budget_status(
        get_connection,
        _get_budget_monthly_limit,
        category_id=category_id,
    )


if __name__ == "__main__":
    init_db()
    app_logger.info("База данных инициализирована")
