# services/category_service.py
import core
from typing import List, Optional, Callable
from models import Category
from utils.logger import app_logger


class CategoryService:
    """Сервис для работы с категориями"""
    
    def __init__(self):
        self._listeners: List[Callable] = []
        app_logger.debug("CategoryService инициализирован")
    
    def add_listener(self, callback: Callable):
        """Добавляет слушателя изменений"""
        if callback not in self._listeners:
            self._listeners.append(callback)
            app_logger.debug(f"Добавлен слушатель в CategoryService: {getattr(callback, '__name__', 'lambda')}")
    
    def remove_listener(self, callback: Callable):
        """Удаляет слушателя изменений"""
        if callback in self._listeners:
            self._listeners.remove(callback)
            app_logger.debug("Слушатель удалён из CategoryService")
    
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
                    app_logger.error(f"Ошибка при уведомлении слушателя в CategoryService: {e}", exc_info=True)
    
    def get_all_categories(self, trans_type: str = None, include_inactive: bool = False) -> List[Category]:
        """Получает все активные категории"""
        try:
            rows = core.get_all_categories(trans_type, include_inactive=include_inactive)
            result = [Category(
                id=row['id'],
                name=row['name'],
                type=row['type'],
                color=row['color'],
                icon=row['icon'],
                is_active=bool(row['is_active'])
            ) for row in rows]
            app_logger.debug(f"Получено {len(result)} категорий (тип: {trans_type})")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка получения категорий: {e}", exc_info=True)
            return []
    
    def get_category_names(self, trans_type: str = None) -> List[str]:
        """Получает только названия категорий для выпадающих списков"""
        categories = self.get_all_categories(trans_type)
        return [cat.name for cat in categories]
    
    def add_category(
        self,
        name: str,
        category_type: str = 'both',
        color: str = '#808080',
        icon: str = '📁'
    ) -> Optional[int]:
        """Добавляет новую категорию"""
        try:
            app_logger.info(f"Добавление категории: {name} (тип: {category_type})")
            category_id = core.add_category(name, category_type, color=color, icon=icon)
            if category_id:
                self.notify_listeners()
                app_logger.info(f"Категория добавлена: {name}, ID={category_id}")
            return category_id
        except Exception as e:
            app_logger.error(f"Ошибка добавления категории {name}: {e}", exc_info=True)
            return None
    
    def update_category(self, category_id: int, **kwargs) -> bool:
        """Обновляет категорию"""
        try:
            app_logger.debug(f"Обновление категории ID={category_id}: {kwargs}")
            result = core.update_category(category_id, **kwargs)
            if result:
                self.notify_listeners()
                app_logger.info(f"Категория ID={category_id} обновлена")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка обновления категории ID={category_id}: {e}", exc_info=True)
            return False
    
    def delete_category(self, category_id: int) -> bool:
        """Удаляет категорию (деактивирует)"""
        try:
            app_logger.info(f"Деактивация категории ID={category_id}")
            result = core.delete_category(category_id)
            if result:
                self.notify_listeners()
                app_logger.info(f"Категория ID={category_id} деактивирована")
            return result
        except Exception as e:
            app_logger.error(f"Ошибка удаления категории ID={category_id}: {e}", exc_info=True)
            return False
    
    def get_category_by_id(self, category_id: int) -> Optional[Category]:
        """Получает категорию по ID"""
        try:
            row = core.get_category_by_id(category_id)
            if row:
                return Category(
                    id=row['id'],
                    name=row['name'],
                    type=row['type'],
                    color=row['color'],
                    icon=row['icon'],
                    is_active=bool(row['is_active'])
                )
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения категории ID={category_id}: {e}", exc_info=True)
            return None
    
    def get_category_by_name(self, name: str, include_inactive: bool = True) -> Optional[Category]:
        """Получает категорию по имени (включая неактивные)"""
        try:
            row = core.get_category_by_name(name)
            if row:
                return Category(
                    id=row['id'],
                    name=row['name'],
                    type=row['type'],
                    color=row['color'],
                    icon=row['icon'],
                    is_active=bool(row['is_active'])
                )
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения категории по имени {name}: {e}", exc_info=True)
            return None
