import os
import sys


DEFAULT_PROJECT_ROOT = "/var/www/u3480024/data/finance-app"
CURRENT_ROOT = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = os.environ.get(
    "FINANCE_APP_PROJECT_ROOT",
    DEFAULT_PROJECT_ROOT if os.path.exists(DEFAULT_PROJECT_ROOT) else CURRENT_ROOT,
)
VENV_PYTHON = os.environ.get(
    "FINANCE_APP_VENV_PYTHON",
    os.path.join(PROJECT_ROOT, ".venv", "bin", "python"),
)

if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.execl(VENV_PYTHON, VENV_PYTHON, *sys.argv)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _load_env_file(env_file_path: str) -> None:
    if not os.path.exists(env_file_path):
        return
    try:
        with open(env_file_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except Exception:
        # Keep startup resilient if .env contains malformed lines.
        pass


_load_env_file(os.path.join(PROJECT_ROOT, ".env"))

DEFAULT_FRONTEND_DIST = "/var/www/u3480024/data/www/domfindom.ru"
os.environ.setdefault("FINANCE_APP_DB_NAME", os.path.join(PROJECT_ROOT, "finance.db"))
os.environ.setdefault("FINANCE_APP_AUTH_DB_NAME", os.path.join(PROJECT_ROOT, "auth.db"))
os.environ.setdefault("FINANCE_APP_USERS_DATA_DIR", os.path.join(PROJECT_ROOT, "data", "users"))
os.environ.setdefault(
    "FINANCE_APP_FRONTEND_DIST",
    DEFAULT_FRONTEND_DIST
    if os.path.exists(DEFAULT_FRONTEND_DIST)
    else os.path.join(PROJECT_ROOT, "frontend", "dist"),
)
os.environ.setdefault(
    "FINANCE_APP_CORS_ORIGINS",
    "http://domfindom.ru,https://domfindom.ru,http://www.domfindom.ru,https://www.domfindom.ru",
)
os.environ.setdefault("FINANCE_APP_SESSION_COOKIE_SECURE", "true")
os.environ.setdefault("FINANCE_APP_ENV", "production")
os.environ.setdefault("FINANCE_APP_EXPOSE_RESET_TOKEN_IN_RESPONSE", "false")

import core
from backend.auth.service import auth_service
from a2wsgi import ASGIMiddleware
from backend.site_app import app


core.init_db()
auth_service.init_auth_db()
application = ASGIMiddleware(app)
