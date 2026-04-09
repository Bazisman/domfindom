import os
from dataclasses import dataclass
from typing import List


def _parse_cors_origins() -> List[str]:
    raw_value = os.getenv("FINANCE_APP_CORS_ORIGINS", "").strip()
    if raw_value:
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]


@dataclass
class AppConfig:
    title: str
    version: str
    cors_origins: List[str]
    backend_host: str
    backend_port: int
    backend_reload: bool


settings = AppConfig(
    title=os.getenv("FINANCE_APP_TITLE", "Finance App API"),
    version=os.getenv("FINANCE_APP_VERSION", "0.1.0"),
    cors_origins=_parse_cors_origins(),
    backend_host=os.getenv("FINANCE_APP_BACKEND_HOST", "127.0.0.1"),
    backend_port=int(os.getenv("FINANCE_APP_BACKEND_PORT", "8000")),
    backend_reload=os.getenv("FINANCE_APP_BACKEND_RELOAD", "true").lower() in {"1", "true", "yes"},
)
