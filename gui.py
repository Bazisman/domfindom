"""
Главный модуль графического интерфейса
"""
import asyncio
import threading
from utils.logger import app_logger
from utils.backup import DatabaseBackup
from views.main_view import MainView
import core


class AsyncApp:
    """Асинхронное приложение с правильным event loop"""
    
    def __init__(self):
        app_logger.debug("Инициализация AsyncApp")
        self.root = MainView()
        self.loop = None
        self.thread = None
        self.backup_manager = DatabaseBackup()
        
        # Запускаем event loop в отдельном потоке
        self.start_loop()
        
        # Привязываем обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def start_loop(self):
        """Запускает asyncio event loop в отдельном потоке"""
        app_logger.debug("Запуск event loop в отдельном потоке")
        self.loop = asyncio.new_event_loop()
        
        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()
    
    def process_tasks(self):
        """Совместимость со старой схемой запуска asyncio"""
        # Event loop работает в отдельном потоке и не должен
        # останавливаться по таймеру из Tkinter.
        return
    
    def run_async(self, coro):
        """Запускает корутину в event loop"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
            app_logger.debug(f"Корутина запущена: {coro}")
    
    def on_closing(self):
        """При закрытии окна"""
        app_logger.info("Закрытие приложения")
        
        # Создаём бэкап перед выходом
        try:
            self.backup_manager.create_backup(reason="shutdown")
            app_logger.info("Бэкап при закрытии создан")
        except Exception as e:
            app_logger.error(f"Ошибка создания бэкапа при закрытии: {e}")
        
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.root.destroy()
        app_logger.info("Приложение завершено")
    
    def run(self):
        """Запуск приложения"""
        app_logger.info("Запуск GUI приложения")
        self.root.mainloop()


def main():
    """Точка входа"""
    app_logger.info("=" * 60)
    app_logger.info("ЗАПУСК ДОМАШНЕЙ БУХГАЛТЕРИИ")
    app_logger.info("=" * 60)
    
    # Создаём бэкап при запуске
    try:
        backup_manager = DatabaseBackup()
        backup_manager.create_backup(reason="startup")
        app_logger.info("Бэкап при запуске создан")
    except Exception as e:
        app_logger.warning(f"Не удалось создать бэкап при запуске: {e}")
    
    app_logger.info("Инициализация базы данных...")
    core.init_db()
    
    app_logger.info("Запуск приложения...")
    app = AsyncApp()
    app.run()


if __name__ == "__main__":
    main()
