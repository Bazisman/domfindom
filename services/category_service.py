# services/category_service.py
import core
from typing import List, Optional, Callable
from models import Category
from services.transaction_service import _mysql_read_repo_for_current_user, _mysql_write_repo_for_current_user
from utils.logger import app_logger


def _category_from_row(row) -> Category:
    return Category(
        id=row['id'],
        name=row['name'],
        type=row['type'],
        color=row['color'],
        icon=row['icon'],
        is_active=bool(row['is_active'])
    )


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
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_categories(
                        conn,
                        legacy_user_id,
                        trans_type=trans_type,
                        include_inactive=include_inactive,
                    )
            else:
                rows = core.get_all_categories(trans_type, include_inactive=include_inactive)
            result = [_category_from_row(row) for row in rows]
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
            repo, legacy_user_id, source_db_path = _mysql_write_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    result = repo.create_category(
                        conn,
                        legacy_user_id=legacy_user_id,
                        source_db_path=source_db_path,
                        name=name,
                        category_type=category_type,
                        color=color,
                        icon=icon,
                    )
                    conn.commit()
                category_id = int(result["legacy_category_id"])
            else:
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
            repo, legacy_user_id, _source_db_path = _mysql_write_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    write_result = repo.update_category(
                        conn,
                        legacy_user_id=legacy_user_id,
                        legacy_category_id=category_id,
                        **kwargs,
                    )
                    conn.commit()
                result = write_result.get("status") in {"updated", "noop"}
            else:
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
            repo, legacy_user_id, _source_db_path = _mysql_write_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    write_result = repo.delete_category(
                        conn,
                        legacy_user_id=legacy_user_id,
                        legacy_category_id=category_id,
                    )
                    conn.commit()
                result = write_result.get("status") == "updated"
            else:
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
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_categories(conn, legacy_user_id, include_inactive=True)
                row = next((item for item in rows if int(item["id"]) == int(category_id)), None)
            else:
                row = core.get_category_by_id(category_id)
            if row:
                return _category_from_row(row)
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения категории ID={category_id}: {e}", exc_info=True)
            return None
    
    def get_category_by_name(self, name: str, include_inactive: bool = True) -> Optional[Category]:
        """Получает категорию по имени (включая неактивные)"""
        try:
            repo, legacy_user_id = _mysql_read_repo_for_current_user()
            if repo is not None and legacy_user_id is not None:
                with repo.connect() as conn:
                    rows = repo.get_categories(conn, legacy_user_id, include_inactive=include_inactive)
                row = next((item for item in rows if item["name"] == name), None)
            else:
                row = core.get_category_by_name(name)
            if row:
                return _category_from_row(row)
            return None
        except Exception as e:
            app_logger.error(f"Ошибка получения категории по имени {name}: {e}", exc_info=True)
            return None
