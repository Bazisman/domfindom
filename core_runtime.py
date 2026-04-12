import os
import sqlite3
import time
from contextvars import ContextVar


DB_NAME = os.getenv("FINANCE_APP_DB_NAME", "finance.db")
_DB_NAME_CONTEXT: ContextVar[str] = ContextVar("finance_db_name", default=DB_NAME)

_cache = {
    "balance": {"data": None, "timestamp": 0},
    "categories": {"data": None, "timestamp": 0},
    "capital_accounts": {"data": None, "timestamp": 0},
    "total_capital": {"data": None, "timestamp": 0},
    "category_list": {"data": None, "timestamp": 0},
}

_CACHE_TTL = 2
_CACHE_TTL_LONG = 60


def _get_cached(key, fetch_func, force_update=False, ttl=_CACHE_TTL):
    now = time.time()
    cached = _cache[key]
    if force_update or now - cached["timestamp"] > ttl or cached["data"] is None:
        cached["data"] = fetch_func()
        cached["timestamp"] = now
    return cached["data"]


def _invalidate_cache(key=None):
    if key:
        _cache[key]["timestamp"] = 0
        return
    for cache_key in _cache:
        _cache[cache_key]["timestamp"] = 0


def get_connection():
    conn = sqlite3.connect(_DB_NAME_CONTEXT.get())
    conn.row_factory = sqlite3.Row
    return conn


def push_db_name(db_name: str):
    return _DB_NAME_CONTEXT.set(db_name)


def pop_db_name(token):
    _DB_NAME_CONTEXT.reset(token)
