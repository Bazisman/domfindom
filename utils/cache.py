# utils/cache.py
from functools import wraps
import time
from typing import Dict, Any, Callable

class Cache:
    """Простой кэш с временем жизни"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
    
    def get(self, key: str):
        if key in self._cache and self.is_valid(key):
            return self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 60):
        self._cache[key] = value
        self._timestamps[key] = time.time() + ttl
    
    def clear(self):
        self._cache.clear()
        self._timestamps.clear()
    
    def is_valid(self, key: str) -> bool:
        if key not in self._timestamps:
            return False
        return time.time() < self._timestamps[key]
    
    def invalidate(self, key: str):
        """Удаляет конкретный ключ из кэша"""
        if key in self._cache:
            del self._cache[key]
        if key in self._timestamps:
            del self._timestamps[key]

# Глобальный экземпляр кэша
_cache = Cache()

def cached(ttl: int = 60):
    """Декоратор для кэширования результатов функций"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Создаём ключ из имени функции и аргументов
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}:{v}" for k, v in kwargs.items())
            key = ":".join(key_parts)
            
            # Проверяем кэш
            cached_result = _cache.get(key)
            if cached_result is not None:
                return cached_result
            
            # Выполняем функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем в кэш
            _cache.set(key, result, ttl)
            return result
        return wrapper
    return decorator

def invalidate_cache(pattern: str = None):
    """Сбрасывает кэш (частично или полностью)"""
    if pattern is None:
        _cache.clear()
    # Здесь можно добавить частичную инвалидацию по паттерну