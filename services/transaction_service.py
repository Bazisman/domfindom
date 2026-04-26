# services/transaction_service.py
import core
import core_runtime
from models import Transaction, Balance, Transfer
from typing import List, Optional, Callable, Any
from datetime import datetime, timedelta
import calendar
from pathlib import Path
from utils.logger import app_logger


def _legacy_user_id_from_current_db() -> Optional[int]:
    parts = Path(core_runtime._current_db_name()).parts
    for index, part in enumerate(parts):
        if part == "users" and index + 1 < len(parts):
            try:
                return int(parts[index + 1])
            except (TypeError, ValueError):
                return None
    return None


def _mysql_primary_reads_enabled() -> bool:
    try:
        from backend.config import settings

        return bool(
            settings.mysql_database_url
            and (
                settings.storage_backend == "mysql"
                or getattr(settings, "mysql_primary_read_pilot_enabled", False)
            )
        )
    except Exception:
        return False


def _mysql_read_repo_for_current_user():
    if not _mysql_primary_reads_enabled():
        return None, None
    legacy_user_id = _legacy_user_id_from_current_db()
    if legacy_user_id is None:
        return None, None
    from backend.config import settings
    from backend.storage.mysql_read import MySqlReadRepository

    return MySqlReadRepository(settings.mysql_database_url), legacy_user_id


class TransactionService:
    """Сервис для работы с транзакциями"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
        self._auto_percent = 10
        self._auto_enabled = True
        app_logger.debug("TransactionService инициализирован")

    def sync_due_planned_transactions(self) -> int:
        """Автоматически исполняет просроченные плановые транзакции для web/API."""
        count = self.execute_planned_transactions()
        if count > 0:
            app_logger.info(f"Автосинхронизация исполнила {count} просроченных плановых транзакций")
        return count
    
    def set_auto_capital_settings(self, enabled: bool, percent: int):
        """Устанавливает настройки автоотчислений."""
        settings = core.set_auto_capital_settings(enabled, percent)
        self._auto_enabled = settings['enabled']
        self._auto_percent = settings['percent']
        app_logger.info(f"Настройки автоотчислений: enabled={enabled}, percent={percent}%")
    
    def add_listener(self, callback: Callable):
        """Подписка на изменения данных"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            app_logger.debug(f"Добавлен слушатель: {getattr(callback, '__name__', 'lambda')}")
    
    def remove_listener(self, callback: Callable):
        """Отписка от изменений"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            app_logger.debug("Слушатель удалён")
    
    def notify_listeners(self, update_all=False):
        """
        Уведомляет всех подписчиков об изменениях
        
        Args:
            update_all: если True - обновляются все вкладки, если False - только активная
        """
        listeners = self._listeners.copy()
        
        # Получаем активную вкладку один раз
        active_view = None
        root_ref = None
        
        for callback in listeners:
            try:
                if hasattr(callback, '__self__') and hasattr(callback.__self__, 'winfo_exists'):
                    if not callback.__self__.winfo_exists():
                        self.remove_listener(callback)
                        continue
                
                callback()
                
                # Сохраняем root для дальнейшего использования
                if hasattr(callback, '__self__') and hasattr(callback.__self__, 'winfo_toplevel'):
                    if root_ref is None:
                        root_ref = callback.__self__.winfo_toplevel()
                        
                        # Обновляем баланс
                        if hasattr(root_ref, 'update_balance'):
                            root_ref.update_balance()
                        
                        # Получаем активную вкладку
                        if hasattr(root_ref, 'current_view'):
                            active_view = root_ref.current_view
                
            except Exception as e:
                if "invalid command name" not in str(e) and "bad window path" not in str(e):
                    app_logger.error(f"Ошибка при уведомлении слушателя: {e}", exc_info=True)
    
        # Обновляем только активную вкладку (для оптимизации)
        if root_ref and hasattr(root_ref, 'content_frame'):
            for child in root_ref.content_frame.winfo_children():
                if hasattr(child, 'refresh'):
                    # Обновляем только если:
                    # 1. update_all=True (явный запрос на обновление всех)
                    # 2. РР»Рё СЌС‚Рѕ Р°РєС‚РёРІРЅР°СЏ РІРєР»Р°РґРєР°
                    # 3. РР»Рё СЌС‚Рѕ РіР»Р°РІРЅРѕРµ РїСЂРµРґСЃС‚Р°РІР»РµРЅРёРµ (main_view)
                    should_refresh = update_all or (active_view is child) or (hasattr(child, '__class__') and 'MainView' in str(child.__class__))
                    
                    if should_refresh:
                        try:
                            child.refresh()
                        except Exception as ex:
                            app_logger.debug(f"Ошибка обновления вкладки: {ex}")
    
    def get_balance(self, force_update: bool = False) -> Balance:
        """Получает баланс основного счёта"""
        try:
            if _mysql_primary_reads_enabled():
                repo, legacy_user_id = _mysql_read_repo_for_current_user()
                if repo is not None and legacy_user_id is not None:
                    with repo.connect() as conn:
                        data = repo.get_balance(conn, legacy_user_id)
                    return Balance(
                        main_balance=data.get("main_balance") or 0.0,
                        income=data.get("income") or 0.0,
                        expense=data.get("expense") or 0.0,
                    )
            main_balance, income, expense = core.get_balance(force_update=force_update)
            return Balance(main_balance=main_balance or 0.0, income=income or 0.0, expense=expense or 0.0)
        except Exception as e:
            app_logger.error(f"Ошибка получения баланса: {e}", exc_info=True)
            return Balance()

    def get_transactions(self, limit: int = 100, period: str = "all", offset: int = 0) -> List[Transaction]:
        """Получает список транзакций с поддержкой пагинации"""
        try:
            # Ограничиваем максимальное количество для производительности
            limit = min(limit, 500)
            
            today = datetime.now()
            start = None
            end = None
            
            if period == "month":
                start = today.replace(day=1).strftime("%Y-%m-%d")
                end = today.replace(day=calendar.monthrange(today.year, today.month)[1]).strftime("%Y-%m-%d")
            elif period == "last_month":
                if today.month == 1:
                    start = today.replace(year=today.year-1, month=12, day=1)
                    end = today.replace(year=today.year-1, month=12, day=31)
                else:
                    start = today.replace(month=today.month-1, day=1)
                    end = today.replace(day=1) - timedelta(days=1)
                start = start.strftime("%Y-%m-%d")
                end = end.strftime("%Y-%m-%d")
            elif period == "year":
                start = today.replace(month=1, day=1).strftime("%Y-%m-%d")
                end = today.replace(month=12, day=31).strftime("%Y-%m-%d")

            if _mysql_primary_reads_enabled():
                repo, legacy_user_id = _mysql_read_repo_for_current_user()
                if repo is not None and legacy_user_id is not None:
                    with repo.connect() as conn:
                        raw = repo.get_transactions(conn, legacy_user_id, limit=limit, offset=offset, start_date=start, end_date=end)
                else:
                    raw = []
            elif start and end:
                raw = core.get_transactions_by_period(start, end, limit, offset)
            else:
                raw = core.get_last_transactions(limit, offset)
            
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual',
                    money_source=row['money_source'] if 'money_source' in row.keys() else 'cashless',
                ))
            
            app_logger.debug(f"Получено {len(result)} транзакций")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка получения транзакций: {e}", exc_info=True)
            return []

    def get_transactions_for_export(self) -> List[Transaction]:
        """Получает все транзакции без UI-лимита для экспорта"""
        try:
            raw = core.get_all_transactions()
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual',
                    money_source=row['money_source'] if 'money_source' in row.keys() else 'cashless',
                ))
            app_logger.debug(f"Получено {len(result)} транзакций для экспорта")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка получения транзакций для экспорта: {e}", exc_info=True)
            return []
    
    def get_transaction_by_id(self, tid: int) -> Optional[Transaction]:
        """Получает транзакцию по ID"""
        try:
            row = core.get_transaction_by_id(tid)
            if row:
                return Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual',
                    money_source=row['money_source'] if 'money_source' in row.keys() else 'cashless',
                )
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения транзакции {tid}: {e}", exc_info=True)
            return None

    def get_transaction_row_by_id(self, tid: int):
        """Получает сырую строку транзакции по ID для совместимости с mirror/write слоями."""
        try:
            return core.get_transaction_by_id(tid)
        except Exception as e:
            app_logger.error(f"Ошибка получения строки транзакции {tid}: {e}", exc_info=True)
            return None
    
    def add_transaction(self, transaction: Transaction) -> bool:
        """Добавляет новую транзакцию"""
        try:
            app_logger.info(f"Добавление транзакции: {transaction.type} - {transaction.amount}")
            
            if transaction.type == "income":
                # Проверяем категорию - для "Остаток" отчисление не делается
                if "Остаток" in transaction.category:
                    app_logger.info(f"Категория '{transaction.category}' - отчисление не делается")
                    core.add_income_with_capital(
                        transaction.amount, transaction.category, transaction.comment,
                        transaction.date, 0, None, money_source=transaction.money_source
                    )
                else:
                    # Получаем основной счёт капитала
                    capital_account = core.get_default_capital_account()
                    
                    if not capital_account:
                        app_logger.warning("Нет основного счёта капитала! Отчисление не будет выполнено.")
                        # Добавляем доход без отчисления
                        core.add_income_with_capital(
                            transaction.amount, transaction.category, transaction.comment,
                            transaction.date, 0, None, money_source=transaction.money_source
                        )
                    else:
                        # Добавляем доход с отчислением
                        core.add_income_with_capital(
                            transaction.amount, transaction.category, transaction.comment,
                            transaction.date, self._auto_percent if self._auto_enabled else 0,
                            capital_account['id'], money_source=transaction.money_source
                        )
            else:
                # Расход
                core.add_expense(
                    transaction.amount,
                    transaction.category,
                    transaction.comment,
                    transaction.date,
                    money_source=transaction.money_source,
                )
            
            self.notify_listeners()
            app_logger.info(f"Транзакция добавлена успешно")
            return True
            
        except Exception as e:
            app_logger.error(f"Ошибка добавления транзакции: {e}", exc_info=True)
            return False

    def add_income_with_capital(
        self,
        amount: float,
        category: str,
        comment: str,
        date: str,
        capital_percent: int = 0,
        capital_account_id: int = None,
        money_source: str = "cashless",
    ):
        """Создаёт доход с возможным отчислением в капитал и возвращает ID."""
        try:
            result = core.add_income_with_capital(
                amount,
                category,
                comment,
                date,
                capital_percent,
                capital_account_id,
                money_source=money_source,
            )
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка создания дохода: {e}", exc_info=True)
            return None

    def add_expense(
        self,
        amount: float,
        category: str,
        comment: str,
        date: str,
        money_source: str = "cashless",
    ):
        """Создаёт расход и возвращает ID."""
        try:
            result = core.add_expense(amount, category, comment, date, money_source=money_source)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка создания расхода: {e}", exc_info=True)
            return None

    def add_planned_transaction(
        self,
        transaction_type: str,
        category: str,
        amount: float,
        comment: str,
        planned_date: str,
        template_id: int = None,
        money_source: str = "cashless",
    ):
        """Создаёт плановую транзакцию и возвращает ID."""
        try:
            result = core.add_planned_transaction(
                transaction_type,
                category,
                amount,
                comment,
                planned_date,
                template_id=template_id,
                money_source=money_source,
            )
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка создания плановой транзакции: {e}", exc_info=True)
            return None
    
    def get_main_account(self):
        """Получает основной счёт"""
        try:
            accounts = core.get_all_accounts()
            for acc in accounts:
                if acc['id'] == 1:
                    return acc
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения основного счёта: {e}", exc_info=True)
            return None

    def update_transaction(self, tid: int, field: str, value) -> bool:
        """Обновляет поле транзакции"""
        try:
            result = core.update_transaction(tid, field, value)
            if result:
                self.notify_listeners()
                app_logger.debug(f"Транзакция {tid} обновлена: {field}={value}")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления транзакции {tid}: {e}", exc_info=True)
            return False

    def update_transaction_fields(self, tid: int, **kwargs) -> bool:
        """Обновляет несколько полей транзакции."""
        try:
            result = core.update_transaction_fields(tid, **kwargs)
            if result:
                self.notify_listeners()
                app_logger.debug(f"Транзакция {tid} обновлена: {kwargs}")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления транзакции {tid}: {e}", exc_info=True)
            return False
    
    def delete_transaction(self, tid: int) -> bool:
        """Удаляет транзакцию."""
        try:
            result = core.delete_transaction(tid)
            if result:
                self.notify_listeners()
                app_logger.info(f"Транзакция {tid} удалена")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления транзакции {tid}: {e}", exc_info=True)
            return False

    def rollback_created_transaction(self, tid: int) -> bool:
        """Удаляет только что созданную транзакцию при откате составной операции."""
        try:
            result = core.delete_transaction(tid)
            if result:
                self.notify_listeners()
                app_logger.info(f"Созданная транзакция {tid} удалена при откате")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка rollback удаления транзакции {tid}: {e}", exc_info=True)
            return False
    
    def get_categories(self, trans_type: str = None) -> List[str]:
        """Получает список всех категорий"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    categories = repo.get_categories(conn, legacy_user_id, trans_type=trans_type)
            else:
                categories = core.get_all_categories(trans_type)
            return [cat['name'] for cat in categories]
        except Exception as e:
            app_logger.error(f"Ошибка получения категорий: {e}", exc_info=True)
            return []
    
    def get_expenses_by_category(self, start_date=None, end_date=None):
        """Получает расходы по категориям"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_category_totals(conn, legacy_user_id, "expense", start_date, end_date)
            return core.get_expenses_by_category(start_date, end_date)
        except Exception as e:
            app_logger.error(f"Ошибка получения расходов: {e}", exc_info=True)
            return []
    
    def get_income_by_category(self, start_date=None, end_date=None):
        """Получает доходы по категориям"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_category_totals(conn, legacy_user_id, "income", start_date, end_date)
            return core.get_income_by_category(start_date, end_date)
        except Exception as e:
            app_logger.error(f"Ошибка получения доходов: {e}", exc_info=True)
            return []

    def get_planned_expenses_by_category(self, end_date: str):
        """Получает плановые расходы по категориям до указанной даты включительно."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_planned_expenses_by_category(conn, legacy_user_id, end_date)
            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT category, COALESCE(SUM(amount), 0) as total
                    FROM transactions
                    WHERE type = 'expense'
                      AND status = 'planned'
                      AND date <= ?
                    GROUP BY category
                    """,
                    (end_date,),
                )
                return cursor.fetchall()
        except Exception as e:
            app_logger.error(f"Ошибка получения плановых расходов по категориям: {e}", exc_info=True)
            return []

    def get_category_audit_snapshot(self) -> dict:
        """Собирает диагностический снимок категорий и связанных объектов."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_category_audit_snapshot(conn, legacy_user_id)

            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, name, type, color, icon, is_active
                    FROM categories
                    ORDER BY name
                    """
                )
                categories = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT type, category, COALESCE(status, 'actual') AS status,
                           COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
                    FROM transactions
                    GROUP BY type, category, COALESCE(status, 'actual')
                    ORDER BY type, category
                    """
                )
                transactions = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT b.id, b.category_id, b.amount, b.period,
                           c.name AS category, c.type AS category_type, c.is_active AS category_is_active
                    FROM budgets b
                    LEFT JOIN categories c ON c.id = b.category_id
                    ORDER BY c.name
                    """
                )
                budgets = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'recurring_templates'
                    LIMIT 1
                    """
                )
                recurring_templates = []
                if cursor.fetchone() is not None:
                    cursor.execute(
                        """
                        SELECT rt.id, rt.type, rt.name, rt.amount, rt.day_of_month,
                               rt.category_id, rt.is_active,
                               c.name AS category, c.type AS category_type, c.is_active AS category_is_active
                        FROM recurring_templates rt
                        LEFT JOIN categories c ON c.id = rt.category_id
                        ORDER BY rt.type, rt.name
                        """
                    )
                    recurring_templates = [dict(row) for row in cursor.fetchall()]
            return {
                "categories": categories,
                "transactions": transactions,
                "budgets": budgets,
                "recurring_templates": recurring_templates,
            }
        except Exception as e:
            app_logger.error(f"Ошибка получения category audit snapshot: {e}", exc_info=True)
            return {"categories": [], "transactions": [], "budgets": [], "recurring_templates": []}

    def get_capital_outflow_for_period(self, start_date=None, end_date=None):
        """Получает сумму переводов в капитал за период."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_capital_contributions_total(conn, legacy_user_id, start_date, end_date)
            return core.get_capital_outflow_for_period(start_date, end_date)
        except Exception as e:
            app_logger.error(f"Ошибка получения отчислений в капитал: {e}", exc_info=True)
            return 0

    def get_capital_contributions_for_period(self, start_date=None, end_date=None):
        """Получает сумму переводов за период для месячной статистики."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_capital_contributions_total(conn, legacy_user_id, start_date, end_date)
            return core.get_capital_contributions_for_period(start_date, end_date)
        except Exception as e:
            app_logger.error(f"Ошибка получения переводов за период: {e}", exc_info=True)
            return 0
        
    def get_monthly_stats(self, year: int, month: int) -> dict:
        """Возвращает статистику за месяц: доходы, расходы, отчисления в капитал"""
        try:
            if _mysql_primary_reads_enabled():
                repo, legacy_user_id = _mysql_read_repo_for_current_user()
                if repo is not None and legacy_user_id is not None:
                    with repo.connect() as conn:
                        return repo.get_monthly_stats(conn, legacy_user_id, year, month)
            # Формируем даты
            start_date = f"{year}-{month:02d}-01"
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
            
            # Получаем данные за период
            income = core.get_income_by_category(start_date, end_date)
            expenses = core.get_expenses_by_category(start_date, end_date)
            capital = self.get_capital_contributions_for_period(start_date, end_date)
            
            # Суммируем
            total_income = sum(item['total'] for item in income) if income else 0
            total_expense = sum(item['total'] for item in expenses) if expenses else 0
            
            return {
                'income': round(total_income, 2),
                'expense': round(total_expense, 2),
                'capital': round(capital, 2),
                'year': year,
                'month': month
            }
        except Exception as e:
            app_logger.error(f"Ошибка получения месячной статистики: {e}", exc_info=True)
            return {'income': 0, 'expense': 0, 'capital': 0, 'year': year, 'month': month}
        
    def get_transactions_by_date_range(self, start_date, end_date):
        """Получает транзакции за произвольный диапазон дат"""
        try:
            raw = core.get_transactions_by_period(start_date, end_date)
            result = []
            for row in raw:
                result.append(Transaction(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    amount=row['amount'],
                    comment=row['comment'],
                    date=row['date'],
                    status=row['status'] if 'status' in row.keys() else 'actual',
                    money_source=row['money_source'] if 'money_source' in row.keys() else 'cashless',
                ))
            return result
        except Exception as e:
            app_logger.error(f"Ошибка получения транзакций за период: {e}", exc_info=True)
            return []
    
    # ========== РњР•РўРћР”Р« Р”Р›РЇ Р РђР‘РћРўР« РЎРћ РЎР§Р•РўРђРњР ==========

    def get_all_accounts(self, include_inactive=False):
        """Получает все счета"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_accounts(conn, legacy_user_id, include_inactive=include_inactive)
            return core.get_all_accounts(include_inactive)
        except Exception as e:
            app_logger.error(f"Ошибка получения счетов: {e}", exc_info=True)
            return []

    def get_account_balance(self, account_id):
        """Получает баланс счёта по ID"""
        try:
            # Сначала проверяем в accounts
            accounts = self.get_all_accounts()
            for acc in accounts:
                if acc['id'] == account_id:
                    return acc['balance']
            
            # Затем проверяем в capital_accounts
            capital = self.get_capital_accounts()
            for acc in capital:
                if acc['id'] == account_id:
                    return acc['balance']
            
            app_logger.warning(f"Счёт {account_id} не найден")
            return 0
        except Exception as e:
            app_logger.error(f"Ошибка получения баланса: {e}", exc_info=True)
            return 0
    
    # ========== РњР•РўРћР”Р« Р”Р›РЇ Р РђР‘РћРўР« РЎ РљРђРџРРўРђР›РћРњ ==========

    def get_capital_accounts(self, include_inactive=False):
        """Получает все счета капитала"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_capital_accounts(conn, legacy_user_id, include_inactive=include_inactive)
            return core.get_capital_accounts(include_inactive=include_inactive)
        except Exception as e:
            app_logger.error(f"Ошибка получения счетов капитала: {e}", exc_info=True)
            return []

    def adjust_daily_account_balance(self, money_source: str, amount_delta: float) -> None:
        """Корректирует дневной счёт наличных или безнала."""
        try:
            account_id = 2 if money_source == "cash" else 1
            core.update_account_balance(account_id, amount_delta)
            self.notify_listeners()
        except Exception as e:
            app_logger.error(f"Ошибка корректировки дневного счёта {money_source}: {e}", exc_info=True)
            raise

    def adjust_capital_account_balance(self, capital_account_id: int, amount_delta: float) -> bool:
        """Корректирует баланс активного счёта капитала."""
        try:
            with core.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE capital_accounts
                    SET balance = balance + ?, updated_at = datetime("now")
                    WHERE id = ? AND is_active = 1
                    """,
                    (amount_delta, capital_account_id),
                )
                conn.commit()
                core._invalidate_cache()
                updated = cursor.rowcount > 0
            if updated:
                self.notify_listeners()
            return updated
        except Exception as e:
            app_logger.error(f"Ошибка корректировки счёта капитала {capital_account_id}: {e}", exc_info=True)
            raise

    def get_default_capital_account(self):
        """Возвращает основной счёт капитала для автоотчислений."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_default_capital_account(conn, legacy_user_id)
            return core.get_default_capital_account()
        except Exception as e:
            app_logger.error(f"Ошибка получения основного счёта капитала: {e}", exc_info=True)
            return None

    def set_default_capital_account(self, account_id):
        """Устанавливает основной счёт капитала."""
        try:
            result = core.set_default_capital_account(account_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Основной счёт капитала изменён на ID={account_id}")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка установки основного счёта капитала: {e}", exc_info=True)
            return False

    def add_capital_account(self, name, balance=0, icon='💰', color='#ff9800'):
        """Добавляет новый счёт капитала."""
        try:
            result = core.add_capital_account(name, balance, icon, color)
            if result:
                app_logger.info(f"Добавлен счёт капитала: {name}")
                self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка добавления счёта капитала: {e}", exc_info=True)
            return None

    def update_capital_account(self, account_id, **kwargs):
        """Обновляет счёт капитала"""
        try:
            result = core.update_capital_account(account_id, **kwargs)
            if result:
                self.notify_listeners()
                app_logger.debug(f"Обновлён счёт капитала {account_id}: {kwargs}")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления счёта капитала: {e}", exc_info=True)
            return False

    def delete_capital_account(self, account_id):
        """Удаляет счёт капитала (деактивирует)."""
        try:
            result = core.delete_capital_account(account_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Счёт капитала {account_id} деактивирован")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления счёта капитала: {e}", exc_info=True)
            return False

    def get_total_capital(self):
        """Получает общую сумму всех счетов капитала"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_total_capital(conn, legacy_user_id)
            return core.get_total_capital()
        except Exception as e:
            app_logger.error(f"Ошибка получения общего капитала: {e}", exc_info=True)
            return 0
    
    def get_transfers_history(self, account_id=None, limit=100, include_inactive=False):
        """Получает историю переводов"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_transfers_history(
                        conn,
                        legacy_user_id,
                        account_id=account_id,
                        limit=limit,
                        include_inactive=include_inactive,
                    )
            return core.get_transfers_history(account_id, limit, include_inactive=include_inactive)
        except Exception as e:
            app_logger.error(f"Ошибка получения истории переводов: {e}", exc_info=True)
            return []
    
    def check_budget(self, category: str, amount: float):
        """Проверяет бюджет для категории"""
        try:
            # Находим категорию по имени
            cat = core.get_category_by_name(category)
            if cat:
                return core.check_budget(cat['id'], amount)
            return None
        except Exception as e:
            app_logger.error(f"Ошибка проверки бюджета: {e}", exc_info=True)
            return None
        
    def transfer_money(self, from_account_id, to_account_id, amount, date=None, comment=""):
        """Переводит деньги между счетами."""
        import core
        from utils.logger import app_logger
        
        app_logger.info(f"Перевод: {amount} со счёта {from_account_id} на {to_account_id}")
        
        try:
            if amount <= 0:
                app_logger.warning(f"Попытка перевода с суммой <= 0: {amount}")
                return False
            
            # Проверяем, достаточно ли средств
            from_balance = self.get_account_balance(from_account_id)
            if from_balance < amount:
                app_logger.warning(f"Недостаточно средств: {from_balance} < {amount}")
                return False
            
            # Обновляем балансы
            core.update_account_balance(from_account_id, -amount)
            core.update_account_balance(to_account_id, amount)
            
            # Добавляем запись о переводе
            core.add_transfer_record(from_account_id, to_account_id, amount, date, comment)
            
            self.notify_listeners()
            app_logger.info(f"Перевод {amount} выполнен успешно")
            return True
            
        except Exception as e:
            app_logger.error(f"Ошибка перевода: {e}", exc_info=True)
            return False
    
    # ========== Р Р•Р“РЈР›РЇР РќР«Р• РџР›РђРўР•Р–Р ==========
    
    def add_transaction_with_recurring(self, transaction: Transaction, months_ahead: int = 12) -> bool:
        """Добавляет транзакцию с созданием шаблона регулярного платежа"""
        try:
            app_logger.info(f"Добавление транзакции с повторением: {transaction.type} - {transaction.amount} на {months_ahead} месяцев")
            
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            is_future = transaction.date > today
            
            # 1. Если дата в прошлом или сегодня - добавляем фактическую транзакцию
            # Если дата в будущем - НЕ добавляем транзакцию, только создаём шаблон
            if not is_future:
                self.add_transaction(transaction)
                app_logger.info(f"Фактическая транзакция добавлена (дата: {transaction.date})")
            else:
                app_logger.info(f"Дата в будущем ({transaction.date}) - транзакция не добавляется, только планирование")
            
            # 2. Получаем ID категории
            category = core.get_category_by_name(transaction.category)
            category_id = category['id'] if category else None
            
            # 3. Определяем название шаблона (из комментария или категории)
            template_name = transaction.comment.strip() if transaction.comment else transaction.category
            
            # 4. Создаём шаблон
            template_id = core.create_recurring_template(
                template_type=transaction.type,
                name=template_name,
                amount=transaction.amount,
                day_of_month=int(transaction.date.split('-')[2]),
                category_id=category_id,
                comment_template=transaction.comment,
                months_ahead=months_ahead,
                working_days_only=True,
                money_source=transaction.money_source,
            )

            # 5. Уведомляем всех слушателей (включая планирование)
            self.notify_listeners()
            
            app_logger.info(f"Создан шаблон ID={template_id} с {months_ahead} плановыми транзакциями")
            return True
            
        except Exception as e:
            app_logger.error(f"Ошибка добавления транзакции с повторением: {e}", exc_info=True)
            return False
    
    def get_recurring_templates(self, template_type: str = None) -> list:
        """Получает список шаблонов регулярных платежей"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_recurring_templates(conn, legacy_user_id, template_type=template_type)
            return core.get_recurring_templates(template_type)
        except Exception as e:
            app_logger.error(f"Ошибка получения шаблонов: {e}", exc_info=True)
            return []

    def get_recurring_template_by_id(self, template_id: int):
        """Получает шаблон регулярного платежа по ID."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_recurring_templates(conn, legacy_user_id)
                return next((row for row in rows if int(row["id"]) == int(template_id)), None)
            return core.get_recurring_template_by_id(template_id)
        except Exception as e:
            app_logger.error(f"Ошибка получения шаблона ID={template_id}: {e}", exc_info=True)
            return None
    
    def create_recurring_template(self, template_type: str, name: str, amount: float, 
                                   day_of_month: int, category_id: int = None,
                                   comment_template: str = None, months_ahead: int = 12,
                                   working_days_only: bool = True,
                                   money_source: str = "cashless") -> int:
        """Создаёт шаблон регулярного платежа"""
        try:
            template_id = core.create_recurring_template(
                template_type, name, amount, day_of_month, category_id,
                comment_template, months_ahead, working_days_only, money_source
            )
            self.notify_listeners()
            return template_id
        except Exception as e:
            app_logger.error(f"Ошибка создания шаблона: {e}", exc_info=True)
            return None

    def adjust_to_workday(self, date: str) -> str:
        """Сдвигает дату на рабочий день по правилам legacy ядра."""
        try:
            return core._adjust_to_workday(date)
        except Exception as e:
            app_logger.error(f"Ошибка корректировки даты {date}: {e}", exc_info=True)
            return date

    def delete_planned_transactions_in_period(self, template_id: int, start_date: str, end_date: str) -> None:
        """Удаляет плановые транзакции шаблона в указанном периоде."""
        try:
            core.delete_planned_transactions_in_period(template_id, start_date, end_date)
            self.notify_listeners()
        except Exception as e:
            app_logger.error(f"Ошибка удаления плановых транзакций шаблона {template_id}: {e}", exc_info=True)

    def assign_template_to_planned_transaction(self, transaction_id: int, template_id: int) -> None:
        """Привязывает плановую транзакцию к регулярному шаблону."""
        try:
            core.assign_template_to_planned_transaction(transaction_id, template_id)
            self.notify_listeners()
        except Exception as e:
            app_logger.error(
                f"Ошибка привязки плановой транзакции {transaction_id} к шаблону {template_id}: {e}",
                exc_info=True,
            )
    
    def update_recurring_template(self, template_id: int, **kwargs) -> bool:
        """Обновляет шаблон и перегенерирует плановые транзакции"""
        try:
            schedule_changed = any(field in kwargs for field in ("day_of_month", "working_days_only"))
            result = core.update_recurring_template(template_id, **kwargs)
            if result and schedule_changed:
                executed_count = self.execute_planned_transactions()
                if executed_count == 0:
                    self.notify_listeners()
            else:
                self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления шаблона: {e}", exc_info=True)
            return False
    
    def delete_recurring_template(self, template_id: int) -> bool:
        """Удаляет шаблон и связанные транзакции"""
        try:
            result = core.delete_recurring_template(template_id)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления шаблона: {e}", exc_info=True)
            return False

    def get_planned_transactions_due(self) -> list:
        """Получает просроченные плановые транзакции."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_planned_transactions_due(conn, legacy_user_id)
            return core.get_planned_transactions_due()
        except Exception as e:
            app_logger.error(f"Ошибка получения просроченных плановых транзакций: {e}", exc_info=True)
            return []
    
    def regenerate_template_transactions(self, template_id: int) -> int:
        """Принудительно перегенерирует плановые транзакции для шаблона"""
        try:
            # Удаляем старые плановые транзакции
            core.delete_planned_transactions(template_id)
            
            # Получаем шаблон
            template = core.get_recurring_template_by_id(template_id)
            if not template:
                return 0
            
            # Генерируем новые
            count = core.generate_planned_transactions(template_id, months=template['months_ahead'])
            self.notify_listeners()
            return count
        except Exception as e:
            app_logger.error(f"Ошибка перегенерации транзакций: {e}", exc_info=True)
            return 0
    
    def execute_planned_transactions(self) -> int:
        """Исполняет все просроченные плановые транзакции."""
        try:
            # Получаем настройки автоотчислений
            auto_percent = self._auto_percent if self._auto_enabled else 0
            capital_account = self.get_default_capital_account()
            capital_account_id = capital_account['id'] if capital_account else None
            
            # Исполняем
            count = core.execute_all_planned_transactions(auto_percent, capital_account_id)
            
            if count > 0:
                self.notify_listeners(update_all=True)
                app_logger.info(f"Исполнено {count} плановых транзакций")
            
            return count
        except Exception as e:
            app_logger.error(f"Ошибка исполнения плановых транзакций: {e}", exc_info=True)
            return 0
    
    def get_projected_balance(self, end_date: str = None) -> dict:
        """Получает прогнозируемый баланс"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_projected_balance(conn, legacy_user_id, end_date=end_date)
            return core.get_projected_balance(end_date)
        except Exception as e:
            app_logger.error(f"Ошибка получения прогноза: {e}", exc_info=True)
            return {
                'current_balance': 0,
                'planned_income': 0,
                'planned_expense': 0,
                'budget_remaining': 0,
                'projected': 0,
                'end_date': end_date or ''
            }
    
    def get_auto_capital_settings(self) -> tuple:
        """Возвращает настройки автоотчислений (enabled, percent)"""
        settings = core.get_auto_capital_settings()
        self._auto_enabled = settings['enabled']
        self._auto_percent = settings['percent']
        return (self._auto_enabled, self._auto_percent)

    def get_default_money_source(self) -> str:
        """Получает источник денег по умолчанию."""
        try:
            return core.get_default_money_source()
        except Exception as e:
            app_logger.error(f"Ошибка получения источника денег по умолчанию: {e}", exc_info=True)
            return "cashless"

    def set_default_money_source(self, money_source: str) -> str:
        """Устанавливает источник денег по умолчанию."""
        try:
            result = core.set_default_money_source(money_source)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка установки источника денег по умолчанию: {e}", exc_info=True)
            return self.get_default_money_source()
    
    # ========== БЮДЖЕТЫ ==========
    
    def get_budgets(self) -> list:
        """Получает все бюджеты"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_budgets(conn, legacy_user_id)
            return core.get_budgets()
        except Exception as e:
            app_logger.error(f"Ошибка получения бюджетов: {e}", exc_info=True)
            return []
    
    def set_budget(self, category_id: int, amount: float, period: str = 'monthly') -> bool:
        """Устанавливает бюджет для категории"""
        try:
            result = core.set_budget(category_id, amount, period)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка установки бюджета: {e}", exc_info=True)
            return False
    
    def delete_budget(self, category_id: int) -> bool:
        """Удаляет бюджет для категории"""
        try:
            result = core.delete_budget(category_id)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления бюджета: {e}", exc_info=True)
            return False
    
    def get_budget_status(self, category_id: int = None):
        """Получает статус бюджета для категории"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_budget_status(conn, legacy_user_id, category_id=category_id)
            return core.get_budget_status(category_id)
        except Exception as e:
            app_logger.error(f"Ошибка получения статуса бюджета: {e}", exc_info=True)
            if category_id is None:
                return []
            return {'spent': 0, 'budget': 0, 'remaining': 0, 'percent': 0}

    def get_budget_report(self, month: str = None):
        """Получает отчет по бюджетам."""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    return repo.get_budget_report(conn, legacy_user_id, month=month)
            return core.get_budget_report(month)
        except Exception as e:
            app_logger.error(f"Ошибка получения отчета по бюджетам: {e}", exc_info=True)
            return []

    def get_budget_monthly_limit(self, amount: float, period: str, reference_date=None) -> float:
        """Возвращает месячный эквивалент бюджета."""
        try:
            return core._get_budget_monthly_limit(amount, period, reference_date)
        except Exception as e:
            app_logger.error(f"Ошибка пересчета бюджета в месяц: {e}", exc_info=True)
            return float(amount or 0)

    # ========== СВЕРКА БАЛАНСА ==========

    def get_program_balance(self) -> float:
        """Получает программный баланс для сверки."""
        try:
            main_balance, _, _ = core.get_balance(force_update=True)
            return float(main_balance or 0)
        except Exception as e:
            app_logger.error(f"Ошибка получения программного баланса: {e}", exc_info=True)
            return 0.0

    def get_reconciliation_sources(self) -> list:
        """Получает источники реального баланса."""
        try:
            return core.get_reconciliation_sources()
        except Exception as e:
            app_logger.error(f"Ошибка получения источников сверки: {e}", exc_info=True)
            return []

    def add_reconciliation_source(self, name: str, balance: float = 0):
        """Добавляет источник реального баланса."""
        try:
            result = core.add_reconciliation_source(name, balance)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка добавления источника сверки: {e}", exc_info=True)
            return None

    def update_reconciliation_source(self, source_id: int, **kwargs) -> bool:
        """Обновляет источник реального баланса."""
        try:
            result = core.update_reconciliation_source(source_id, **kwargs)
            if result:
                self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления источника сверки {source_id}: {e}", exc_info=True)
            return False

    def delete_reconciliation_source(self, source_id: int) -> bool:
        """Удаляет источник реального баланса."""
        try:
            result = core.delete_reconciliation_source(source_id)
            if result:
                self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления источника сверки {source_id}: {e}", exc_info=True)
            return False

    def get_total_real_balance(self) -> float:
        """Получает общий реальный баланс."""
        try:
            return float(core.get_total_real_balance() or 0)
        except Exception as e:
            app_logger.error(f"Ошибка получения реального баланса: {e}", exc_info=True)
            return 0.0

    def get_last_reconciliation(self):
        """Получает последнюю сверку."""
        try:
            return core.get_last_reconciliation()
        except Exception as e:
            app_logger.error(f"Ошибка получения последней сверки: {e}", exc_info=True)
            return None

    def get_reconciliations_history(self, limit: int = 50) -> list:
        """Получает историю сверок."""
        try:
            return core.get_reconciliations_history(limit=limit)
        except Exception as e:
            app_logger.error(f"Ошибка получения истории сверок: {e}", exc_info=True)
            return []

    def save_reconciliation(
        self,
        real_balance: float,
        program_balance: float,
        difference: float,
        adjustment_transaction_id: int = None,
    ):
        """Сохраняет результат сверки."""
        try:
            result = core.save_reconciliation(real_balance, program_balance, difference, adjustment_transaction_id)
            self.notify_listeners()
            return result
        except Exception as e:
            app_logger.error(f"Ошибка сохранения сверки: {e}", exc_info=True)
            return None

    def ensure_category_exists(self, name: str, category_type: str, color: str, icon: str) -> None:
        """Создает категорию, если она отсутствует."""
        try:
            if core.get_category_by_name(name):
                return
            core.add_category(name, category_type, color, icon)
            self.notify_listeners()
        except Exception as e:
            app_logger.error(f"Ошибка проверки/создания категории {name}: {e}", exc_info=True)
