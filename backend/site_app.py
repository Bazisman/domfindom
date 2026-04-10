import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import core
from backend.api.router import api_router
from backend.config import settings


def _frontend_dist_path() -> Path:
    configured_path = os.getenv("FINANCE_APP_FRONTEND_DIST")
    if configured_path:
        return Path(configured_path)

    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    core.init_db()
    yield


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
                "frontend": "not found",
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

    return JSONResponse({"detail": "Frontend build not found"}, status_code=404)
