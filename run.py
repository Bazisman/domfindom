# run.py
import sys
import io
from utils.logger import app_logger
from utils.backup import DatabaseBackup
import core
import gui

# Устанавливаем UTF-8 для консоли Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def main():
    """Точка входа"""
    app_logger.info("=" * 50)
    app_logger.info("Запуск приложения Домашняя бухгалтерия")
    app_logger.info("=" * 50)
    
    # 🔥 СНАЧАЛА ИНИЦИАЛИЗИРУЕМ БД
    app_logger.info("Инициализация базы данных...")
    core.init_db()
    
    # 🔥 Проверяем/создаём индексы для оптимизации
    app_logger.info("Проверка индексов...")
    core.create_indexes()
    
    # 🔥 ИСПОЛНЯЕМ ПРОСРОЧЕННЫЕ ПЛАНОВЫЕ ТРАНЗАКЦИИ
    try:
        app_logger.info("Проверка плановых транзакций...")
        count = core.execute_all_planned_transactions(0, None)
        if count > 0:
            app_logger.info(f"Исполнено {count} плановых транзакций при запуске")
    except Exception as e:
        app_logger.warning(f"Не удалось исполнить плановые транзакции: {e}")
    
    # 🔥 ПОТОМ СОЗДАЁМ БЭКАП (после того как БД создана и соединения закрыты)
    try:
        backup_manager = DatabaseBackup()
        backup_manager.create_backup(reason="startup")
        app_logger.info("Бэкап при запуске создан")
    except Exception as e:
        app_logger.warning(f"Не удалось создать бэкап при запуске: {e}")
    
    app_logger.info("Запуск GUI...")
    app = gui.AsyncApp()
    app.run()
    
    app_logger.info("Приложение завершено")


if __name__ == "__main__":
    main()