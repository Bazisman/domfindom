# services/sync_service.py
import core
from models import Transaction, Budget, Balance
from typing import List, Optional, Callable
from datetime import datetime, timedelta
from utils.logger import app_logger


class SyncService:
    """Сервис для синхронизации данных"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
        app_logger.debug("SyncService инициализирован")
    
    def add_listener(self, callback: Callable):
        """Добавляет слушателя изменений"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            app_logger.debug(f"Добавлен слушатель в SyncService: {getattr(callback, '__name__', 'lambda')}")
    
    def remove_listener(self, callback: Callable):
        """Удаляет слушателя изменений"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            app_logger.debug("Слушатель удалён из SyncService")
    
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
                    app_logger.error(f"Ошибка при уведомлении слушателя в SyncService: {e}", exc_info=True)
    
    def sync_transactions(self) -> bool:
        """Синхронизирует транзакции"""
        try:
            app_logger.info("Синхронизация транзакций...")
            result = core.sync_transactions()
            if result:
                self.notify_listeners()
                app_logger.info("Синхронизация транзакций завершена успешно")
            else:
                app_logger.warning("Синхронизация транзакций не дала результата")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка синхронизации транзакций: {e}", exc_info=True)
            return False
    
    def sync_budgets(self) -> bool:
        """Синхронизирует бюджеты"""
        try:
            app_logger.info("Синхронизация бюджетов...")
            result = core.sync_budgets()
            if result:
                self.notify_listeners()
                app_logger.info("Синхронизация бюджетов завершена успешно")
            else:
                app_logger.warning("Синхронизация бюджетов не дала результата")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка синхронизации бюджетов: {e}", exc_info=True)
            return False
    
    def sync_all(self) -> bool:
        """Синхронизирует все данные"""
        try:
            app_logger.info("Полная синхронизация всех данных...")
            result = core.sync_all()
            if result:
                self.notify_listeners()
                app_logger.info("Полная синхронизация завершена успешно")
            else:
                app_logger.warning("Полная синхронизация не дала результата")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка полной синхронизации: {e}", exc_info=True)
            return False