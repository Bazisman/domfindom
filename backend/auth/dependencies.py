from typing import Dict

from fastapi import HTTPException, Request, status


def optional_user(request: Request):
    return getattr(request.state, "current_user", None)


def require_user(request: Request) -> Dict[str, object]:
    user = optional_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    return user
