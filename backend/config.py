import os
import warnings
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


def _repair_mojibake_utf8_from_cp1251(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw
    if "Р" not in raw and "С" not in raw:
        return raw
    try:
        repaired = raw.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw
    before_markers = raw.count("Р") + raw.count("С")
    after_markers = repaired.count("Р") + repaired.count("С")
    return repaired if after_markers < before_markers else raw


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
    storage_backend: str
    database_url: str
    run_db_migrations: bool
    postgres_read_shadow_enabled: bool
    postgres_shadow_write_enabled: bool
    mysql_database_url: str
    mysql_read_shadow_enabled: bool
    mysql_shadow_write_enabled: bool
    mysql_primary_read_pilot_enabled: bool
    mysql_strict_write_transactions_enabled: bool
    mysql_strict_write_accounts_capital_enabled: bool
    mysql_strict_write_reconciliation_enabled: bool
    mysql_strict_write_categories_budgets_recurring_enabled: bool
    auth_db_name: str
    users_data_dir: str
    session_cookie_name: str
    csrf_cookie_name: str
    session_ttl_hours: int
    session_secret: str
    session_cookie_secure: bool
    session_cookie_samesite: str
    csrf_protection_enabled: bool
    enforce_strict_session_secret: bool
    allow_insecure_session_secret: bool
    login_rate_limit_attempts: int
    login_rate_limit_window_minutes: int
    expose_reset_token_in_response: bool
    require_email_verification: bool
    email_verification_token_ttl_hours: int
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    password_reset_url_template: str
    password_reset_email_subject: str
    family_invite_url_template: str
    family_invite_email_subject: str
    email_verification_url_template: str
    email_verification_email_subject: str
    account_delete_url_template: str
    account_delete_email_subject: str
    account_delete_token_ttl_minutes: int


settings = AppConfig(
    env=os.getenv("FINANCE_APP_ENV", "").strip().lower() or "development",
    title=os.getenv("FINANCE_APP_TITLE", "Finance App API"),
    version=os.getenv("FINANCE_APP_VERSION", "0.1.0"),
    cors_origins=_parse_cors_origins(),
    backend_host=os.getenv("FINANCE_APP_BACKEND_HOST", "127.0.0.1"),
    backend_port=_parse_int(os.getenv("FINANCE_APP_BACKEND_PORT", "8000"), 8000),
    backend_reload=_parse_bool(os.getenv("FINANCE_APP_BACKEND_RELOAD", "true"), default=True),
    storage_backend=os.getenv("FINANCE_APP_STORAGE_BACKEND", "sqlite").strip().lower() or "sqlite",
    database_url=os.getenv("FINANCE_APP_DATABASE_URL", "").strip(),
    run_db_migrations=_parse_bool(os.getenv("FINANCE_APP_RUN_DB_MIGRATIONS", "false")),
    postgres_read_shadow_enabled=_parse_bool(os.getenv("FINANCE_APP_POSTGRES_READ_SHADOW", "false")),
    postgres_shadow_write_enabled=_parse_bool(os.getenv("FINANCE_APP_POSTGRES_SHADOW_WRITE", "false")),
    mysql_database_url=os.getenv("FINANCE_APP_MYSQL_DATABASE_URL", "").strip(),
    mysql_read_shadow_enabled=_parse_bool(os.getenv("FINANCE_APP_MYSQL_READ_SHADOW", "false")),
    mysql_shadow_write_enabled=_parse_bool(os.getenv("FINANCE_APP_MYSQL_SHADOW_WRITE", "false")),
    mysql_primary_read_pilot_enabled=_parse_bool(os.getenv("FINANCE_APP_MYSQL_PRIMARY_READ_PILOT", "false")),
    mysql_strict_write_transactions_enabled=_parse_bool(
        os.getenv("FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS", "false")
    ),
    mysql_strict_write_accounts_capital_enabled=_parse_bool(
        os.getenv("FINANCE_APP_MYSQL_STRICT_WRITE_ACCOUNTS_CAPITAL", "false")
    ),
    mysql_strict_write_reconciliation_enabled=_parse_bool(
        os.getenv("FINANCE_APP_MYSQL_STRICT_WRITE_RECONCILIATION", "false")
    ),
    mysql_strict_write_categories_budgets_recurring_enabled=_parse_bool(
        os.getenv("FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING", "false")
    ),
    auth_db_name=os.getenv("FINANCE_APP_AUTH_DB_NAME", "auth.db"),
    users_data_dir=os.getenv("FINANCE_APP_USERS_DATA_DIR", "data/users"),
    session_cookie_name=os.getenv("FINANCE_APP_SESSION_COOKIE_NAME", "finance_session"),
    csrf_cookie_name=os.getenv("FINANCE_APP_CSRF_COOKIE_NAME", "finance_csrf"),
    session_ttl_hours=max(1, _parse_int(os.getenv("FINANCE_APP_SESSION_TTL_HOURS", "720"), 720)),
    session_secret=os.getenv("FINANCE_APP_SESSION_SECRET", "dev-insecure-change-me"),
    session_cookie_secure=_parse_bool(os.getenv("FINANCE_APP_SESSION_COOKIE_SECURE", "false")),
    session_cookie_samesite=os.getenv("FINANCE_APP_SESSION_COOKIE_SAMESITE", "lax").strip().lower() or "lax",
    csrf_protection_enabled=_parse_bool(
        os.getenv("FINANCE_APP_CSRF_PROTECTION_ENABLED", "true" if _is_production() else "false")
    ),
    enforce_strict_session_secret=_parse_bool(
        os.getenv("FINANCE_APP_ENFORCE_STRICT_SESSION_SECRET", "true" if _is_production() else "false")
    ),
    allow_insecure_session_secret=_parse_bool(
        os.getenv("FINANCE_APP_ALLOW_INSECURE_SESSION_SECRET", "false")
    ),
    login_rate_limit_attempts=max(1, _parse_int(os.getenv("FINANCE_APP_LOGIN_RATE_LIMIT_ATTEMPTS", "5"), 5)),
    login_rate_limit_window_minutes=max(
        1, _parse_int(os.getenv("FINANCE_APP_LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"), 15)
    ),
    expose_reset_token_in_response=_parse_bool(
        os.getenv("FINANCE_APP_EXPOSE_RESET_TOKEN_IN_RESPONSE", "true" if not _is_production() else "false")
    ),
    require_email_verification=_parse_bool(
        os.getenv("FINANCE_APP_REQUIRE_EMAIL_VERIFICATION", "true" if _is_production() else "false")
    ),
    email_verification_token_ttl_hours=max(
        1, _parse_int(os.getenv("FINANCE_APP_EMAIL_VERIFICATION_TOKEN_TTL_HOURS", "24"), 24)
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
    password_reset_email_subject=_repair_mojibake_utf8_from_cp1251(os.getenv(
        "FINANCE_APP_PASSWORD_RESET_EMAIL_SUBJECT",
        "Восстановление пароля",
    )).strip(),
    family_invite_url_template=os.getenv(
        "FINANCE_APP_FAMILY_INVITE_URL_TEMPLATE",
        "https://domfindom.ru/login?family_invite_token={token}",
    ).strip(),
    family_invite_email_subject=_repair_mojibake_utf8_from_cp1251(os.getenv(
        "FINANCE_APP_FAMILY_INVITE_EMAIL_SUBJECT",
        "Приглашение в семейный бюджет",
    )).strip(),
    email_verification_url_template=os.getenv(
        "FINANCE_APP_EMAIL_VERIFICATION_URL_TEMPLATE",
        "https://domfindom.ru/login?verify_email_token={token}",
    ).strip(),
    email_verification_email_subject=_repair_mojibake_utf8_from_cp1251(os.getenv(
        "FINANCE_APP_EMAIL_VERIFICATION_EMAIL_SUBJECT",
        "Подтверждение email в домашней бухгалтерии",
    )).strip(),
    account_delete_url_template=os.getenv(
        "FINANCE_APP_ACCOUNT_DELETE_URL_TEMPLATE",
        "https://domfindom.ru/login?account_delete_token={token}",
    ).strip(),
    account_delete_email_subject=_repair_mojibake_utf8_from_cp1251(os.getenv(
        "FINANCE_APP_ACCOUNT_DELETE_EMAIL_SUBJECT",
        "Удаление аккаунта",
    )).strip(),
    account_delete_token_ttl_minutes=max(
        5, _parse_int(os.getenv("FINANCE_APP_ACCOUNT_DELETE_TOKEN_TTL_MINUTES", "30"), 30)
    ),
)


if settings.session_cookie_samesite not in {"lax", "strict", "none"}:
    settings.session_cookie_samesite = "lax"

if settings.storage_backend not in {"sqlite", "postgres", "mysql"}:
    settings.storage_backend = "sqlite"

if _is_production() and settings.session_secret == "dev-insecure-change-me":
    if settings.enforce_strict_session_secret and not settings.allow_insecure_session_secret:
        raise RuntimeError(
            "FINANCE_APP_SESSION_SECRET must be configured in production. "
            "Set a strong secret or temporarily set FINANCE_APP_ALLOW_INSECURE_SESSION_SECRET=true."
        )
    warnings.warn(
        "FINANCE_APP_SESSION_SECRET is not set in production; configure a strong secret.",
        RuntimeWarning,
        stacklevel=1,
    )
