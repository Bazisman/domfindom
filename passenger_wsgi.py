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

DEFAULT_FRONTEND_DIST = "/var/www/u3480024/data/www/domfindom.ru"
os.environ.setdefault("FINANCE_APP_DB_NAME", os.path.join(PROJECT_ROOT, "finance.db"))
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

import core
from a2wsgi import ASGIMiddleware
from backend.site_app import app


core.init_db()
application = ASGIMiddleware(app)
