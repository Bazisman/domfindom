import os
from dataclasses import dataclass
from typing import List


def _parse_bool(value: str, default: bool = False) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_production() -> bool:
    return os.getenv("FINANCE_APP_ENV", "").strip().lower() in {"prod", "production"}


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
    env: str
    title: str
    version: str
    cors_origins: List[str]
    backend_host: str
    backend_port: int
    backend_reload: bool
    auth_db_name: str
    users_data_dir: str
    session_cookie_name: str
    session_ttl_hours: int
    session_secret: str
    session_cookie_secure: bool
    login_rate_limit_attempts: int
    login_rate_limit_window_minutes: int
    expose_reset_token_in_response: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    password_reset_url_template: str
    password_reset_email_subject: str


settings = AppConfig(
    env=os.getenv("FINANCE_APP_ENV", "").strip().lower() or "development",
    title=os.getenv("FINANCE_APP_TITLE", "Finance App API"),
    version=os.getenv("FINANCE_APP_VERSION", "0.1.0"),
    cors_origins=_parse_cors_origins(),
    backend_host=os.getenv("FINANCE_APP_BACKEND_HOST", "127.0.0.1"),
    backend_port=_parse_int(os.getenv("FINANCE_APP_BACKEND_PORT", "8000"), 8000),
    backend_reload=_parse_bool(os.getenv("FINANCE_APP_BACKEND_RELOAD", "true"), default=True),
    auth_db_name=os.getenv("FINANCE_APP_AUTH_DB_NAME", "auth.db"),
    users_data_dir=os.getenv("FINANCE_APP_USERS_DATA_DIR", "data/users"),
    session_cookie_name=os.getenv("FINANCE_APP_SESSION_COOKIE_NAME", "finance_session"),
    session_ttl_hours=max(1, _parse_int(os.getenv("FINANCE_APP_SESSION_TTL_HOURS", "720"), 720)),
    session_secret=os.getenv("FINANCE_APP_SESSION_SECRET", "dev-insecure-change-me"),
    session_cookie_secure=_parse_bool(os.getenv("FINANCE_APP_SESSION_COOKIE_SECURE", "false")),
    login_rate_limit_attempts=max(1, _parse_int(os.getenv("FINANCE_APP_LOGIN_RATE_LIMIT_ATTEMPTS", "10"), 10)),
    login_rate_limit_window_minutes=max(
        1, _parse_int(os.getenv("FINANCE_APP_LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"), 15)
    ),
    expose_reset_token_in_response=_parse_bool(
        os.getenv("FINANCE_APP_EXPOSE_RESET_TOKEN_IN_RESPONSE", "true" if not _is_production() else "false")
    ),
    smtp_host=os.getenv("FINANCE_APP_SMTP_HOST", "").strip(),
    smtp_port=_parse_int(os.getenv("FINANCE_APP_SMTP_PORT", "587"), 587),
    smtp_user=os.getenv("FINANCE_APP_SMTP_USER", "").strip(),
    smtp_password=os.getenv("FINANCE_APP_SMTP_PASSWORD", ""),
    smtp_from=os.getenv("FINANCE_APP_SMTP_FROM", "").strip(),
    smtp_use_tls=_parse_bool(os.getenv("FINANCE_APP_SMTP_USE_TLS", "true")),
    smtp_use_ssl=_parse_bool(os.getenv("FINANCE_APP_SMTP_USE_SSL", "false")),
    password_reset_url_template=os.getenv(
        "FINANCE_APP_PASSWORD_RESET_URL_TEMPLATE",
        "https://domfindom.ru/login?reset_token={token}",
    ).strip(),
    password_reset_email_subject=os.getenv(
        "FINANCE_APP_PASSWORD_RESET_EMAIL_SUBJECT",
        "Password reset request",
    ).strip(),
)


if _is_production() and settings.session_secret == "dev-insecure-change-me":
    raise RuntimeError("FINANCE_APP_SESSION_SECRET must be set in production")
