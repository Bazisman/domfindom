# utils/async_helper.py
import asyncio
import threading
from typing import Coroutine, Any, Optional
from utils.logger import app_logger

class AsyncHelper:
    """Помощник для работы с asyncio в tkinter"""
    
    _instance = None
    _loop = None
    _thread = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._start_loop()
        return cls._instance
    
    def _start_loop(self):
        """Запускает event loop в отдельном потоке"""
        self._loop = asyncio.new_event_loop()
        
        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
    
    def run_coroutine(self, coro: Coroutine) -> Optional[Any]:
        """Безопасно запускает корутину"""
        if not self._loop or not self._loop.is_running():
            app_logger.error("Ошибка: event loop не запущен")
            return None
        
        # Создаём future
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        
        # Пытаемся получить результат (не блокируя)
        try:
            return future.result(timeout=0.1)
        except asyncio.TimeoutError:
            # Корутина ещё выполняется - это нормально
            pass
        except Exception as e:
            app_logger.error(f"Ошибка при выполнении корутины: {e}", exc_info=True)
        
        return None

# Глобальный экземпляр
async_helper = AsyncHelper()
