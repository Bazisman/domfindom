"""Совместимый сервис бюджетов.

Файл сохранён для обратной совместимости, но основная рабочая
логика бюджетов в проекте проходит через TransactionService и core.py.
"""

import core
from models import Budget
from services.transaction_service import _mysql_read_repo_for_current_user
from typing import List, Optional, Callable
from utils.logger import app_logger


class BudgetService:
    """Сервис для работы с бюджетом"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
        app_logger.debug("BudgetService инициализирован")
    
    def add_listener(self, callback: Callable):
        """Добавляет слушателя изменений"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            app_logger.debug(f"Добавлен слушатель в BudgetService: {getattr(callback, '__name__', 'lambda')}")
    
    def remove_listener(self, callback: Callable):
        """Удаляет слушателя изменений"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            app_logger.debug("Слушатель удалён из BudgetService")
    
    def notify_listeners(self):
        """Уведомляет всех слушателей об изменениях"""
        listeners = self._listeners.copy()
        for callback in listeners:
            try:
                if hasattr(callback, '__self__') and hasattr(callback.__self__, 'winfo_exists'):
                    if not callback.__self__.winfo_exists():
                        self.remove_listener(callback)
                        continue
                callback()
            except Exception as e:
                if "invalid command name" not in str(e) and "bad window path" not in str(e):
                    app_logger.error(f"Ошибка при уведомлении слушателя в BudgetService: {e}", exc_info=True)
    
    def get_all_budgets(self) -> List[Budget]:
        """Получает все бюджеты"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_budgets(conn, legacy_user_id)
            else:
                rows = core.get_budgets()
            result = [Budget.from_row(row) for row in rows]
            app_logger.debug(f"Получено {len(result)} бюджетов")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка получения бюджетов: {e}", exc_info=True)
            return []
    
    def get_budget_by_category(self, category: str) -> Optional[Budget]:
        """Получает бюджет по категории"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_budgets(conn, legacy_user_id)
            else:
                rows = core.get_budgets()
            row = next((item for item in rows if item['category'] == category), None)
            if row:
                app_logger.debug(f"Получен бюджет для категории {category}: {row['amount']}")
                return Budget.from_row(row)
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения бюджета для категории {category}: {e}", exc_info=True)
            return None
    
    def add_budget(self, category_id: int, amount: float, period: str = 'monthly') -> Optional[int]:
        """Добавляет новый бюджет"""
        try:
            app_logger.info(f"Добавление бюджета: category_id={category_id} - {amount} ({period})")
            result = core.set_budget(category_id, amount, period)
            if result:
                self.notify_listeners()
                return category_id
            return None
        except Exception as e:
            app_logger.error(f"Ошибка добавления бюджета для category_id={category_id}: {e}", exc_info=True)
            return None
    
    def update_budget(self, category_id: int, **kwargs) -> bool:
        """Обновляет бюджет"""
        try:
            app_logger.debug(f"Обновление бюджета для category_id={category_id}: {kwargs}")
            amount = kwargs.get('amount')
            period = kwargs.get('period', 'monthly')
            result = core.set_budget(category_id, amount, period) if amount is not None else False
            if result:
                self.notify_listeners()
                app_logger.info(f"Бюджет для category_id={category_id} обновлён")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления бюджета для category_id={category_id}: {e}", exc_info=True)
            return False
    
    def delete_budget(self, budget_id: int) -> bool:
        """Удаляет бюджет"""
        try:
            app_logger.info(f"Удаление бюджета ID={budget_id}")
            result = core.delete_budget(budget_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Бюджет ID={budget_id} удалён")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления бюджета ID={budget_id}: {e}", exc_info=True)
            return False
