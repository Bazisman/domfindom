import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(name: str = "finance_app", log_level: str = "INFO"):
    """Настройка централизованного логирования с ротацией"""
    
    # Создаем папку logs если нет
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Настройка форматирования
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Получаем логгер
    logger = logging.getLogger(name)
    
    # Очищаем существующие обработчики, чтобы не дублировать
    if logger.handlers:
        logger.handlers.clear()
    
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Обработчик для файла с ротацией (все уровни)
    # 🔥 Используем utf-8-sig для корректного отображения в Windows
    file_handler = RotatingFileHandler(
        log_dir / "finance.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8-sig"  # utf-8-sig добавляет BOM для корректного отображения в Windows
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Обработчик для ошибок с ротацией (отдельный файл)
    error_handler = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8-sig"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # Обработчик для консоли (только INFO и выше)
    # 🔥 Принудительно устанавливаем UTF-8 для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# Глобальный логгер для всего приложения
app_logger = setup_logger()