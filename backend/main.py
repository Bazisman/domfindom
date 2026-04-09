from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import core
from backend.api.router import api_router
from backend.config import settings


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


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "name": settings.title,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
