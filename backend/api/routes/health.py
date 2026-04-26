from typing import Dict

from fastapi import APIRouter

from backend.config import settings
from backend.storage.mysql_runtime import mysql_runtime_mode


router = APIRouter()


@router.get("/health")
def healthcheck() -> Dict[str, str]:
    return {
        "status": "ok",
        "storage_backend": settings.storage_backend,
        "runtime_mode": mysql_runtime_mode(),
    }
