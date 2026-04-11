from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import core
from backend.auth.service import auth_service
from backend.api.router import api_router
from backend.config import settings
from backend.services import transaction_service


@asynccontextmanager
async def lifespan(_: FastAPI):
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
            current_user
            and request.url.path.startswith("/api/v1")
            and request.url.path not in {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/register"}
        ):
            transaction_service.sync_due_planned_transactions()
        return await call_next(request)
    finally:
        if db_token is not None:
            core.pop_db_name(db_token)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "name": settings.title,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
