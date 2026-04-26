import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import core
from backend.auth.service import auth_service
from backend.api.router import api_router
from backend.config import settings
from backend.services import transaction_service
from utils.logger import app_logger


def _guard_unwired_postgres_backend() -> None:
    if settings.storage_backend in {"postgres", "mysql"}:
        raise RuntimeError(
            f"FINANCE_APP_STORAGE_BACKEND={settings.storage_backend} is not enabled yet: "
            "SQL migration currently supports ETL, reconciliation and shadow-read only."
        )
    if settings.postgres_read_shadow_enabled:
        app_logger.info("PostgreSQL shadow-read is enabled; primary runtime storage remains SQLite")
    if settings.postgres_shadow_write_enabled:
        app_logger.info("PostgreSQL shadow-write is enabled; primary runtime storage remains SQLite")
    if settings.mysql_read_shadow_enabled:
        app_logger.info("MySQL shadow-read is enabled; primary runtime storage remains SQLite")


def _frontend_dist_path() -> Path:
    configured_path = os.getenv("FINANCE_APP_FRONTEND_DIST")
    if configured_path:
        return Path(configured_path)

    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    _guard_unwired_postgres_backend()
    auth_service.init_auth_db()
    core.init_db()
    transaction_service.sync_due_planned_transactions()
    try:
        yield
    finally:
        auth_service.close()


app = FastAPI(
    title=settings.title,
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

_CSRF_EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/account-delete/confirm",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
}


def _append_security_headers(request: Request, response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.env in {"prod", "production"} and request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def attach_user_context_and_sync(request: Request, call_next):
    db_token = None
    current_user = None
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        current_user = auth_service.resolve_session(raw_token)
        if current_user:
            user_db_path = auth_service.ensure_user_finance_db(int(current_user["id"]))
            db_token = core.push_db_name(user_db_path)

    request.state.current_user = current_user

    try:
        if (
            settings.csrf_protection_enabled
            and current_user
            and request.url.path.startswith("/api/v1")
            and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path not in _CSRF_EXEMPT_PATHS
        ):
            csrf_header = request.headers.get("x-csrf-token", "")
            if not auth_service.verify_csrf_token(raw_token or "", csrf_header):
                return JSONResponse({"detail": "Ошибка проверки защитного токена. Обновите страницу и попробуйте снова."}, status_code=403)

        if (
            current_user
            and request.url.path.startswith("/api/v1")
            and request.url.path not in {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/register"}
        ):
            transaction_service.sync_due_planned_transactions()
        response = await call_next(request)
        if current_user and raw_token:
            response.set_cookie(
                key=settings.csrf_cookie_name,
                value=auth_service.create_csrf_token(raw_token),
                httponly=False,
                secure=settings.session_cookie_secure,
                samesite=settings.session_cookie_samesite,
                max_age=settings.session_ttl_hours * 3600,
                path="/",
            )
        _append_security_headers(request, response)
        return response
    finally:
        if db_token is not None:
            core.pop_db_name(db_token)

frontend_dist = _frontend_dist_path()
assets_path = frontend_dist / "assets"

if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")


@app.get("/", include_in_schema=False)
def serve_index():
    index_path = frontend_dist / "index.html"
    if not index_path.exists():
        return JSONResponse(
            {
                "name": settings.title,
                "version": settings.version,
                "docs": "/docs",
                "health": "/api/v1/health",
                "frontend": "не найден",
            },
            status_code=503,
        )

    return FileResponse(index_path)


@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    requested_path = frontend_dist / path
    if requested_path.is_file():
        return FileResponse(requested_path)

    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return JSONResponse({"detail": "Фронтенд-сборка не найдена"}, status_code=404)
