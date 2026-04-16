import sqlite3
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.auth.dependencies import require_user
from backend.auth.mailer import auth_mailer
from backend.auth.service import auth_service
from backend.config import settings
from backend.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    EmailVerificationConfirmPayload,
    LoginRequest,
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    RevokeSessionsResponse,
    RegisterRequest,
    SessionItemResponse,
    SessionListResponse,
)


router = APIRouter()


def _validate_email_like(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or "." not in normalized.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный email")
    return normalized


def _validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пароль слишком короткий")
    has_upper = any(char.isupper() for char in value)
    has_lower = any(char.islower() for char in value)
    has_digit = any(char.isdigit() for char in value)
    if not (has_upper and has_lower and has_digit):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Пароль должен содержать заглавные и строчные буквы, а также цифры",
        )
    return value


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=auth_service.create_csrf_token(token),
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response) -> AuthResponse:
    email = _validate_email_like(payload.email)
    password = _validate_password_strength(payload.password)
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    if auth_service.get_user_by_email(email):
        auth_service.log_auth_event(
            event_type="register",
            status="fail",
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="user_exists",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже существует")

    require_email_verification = settings.require_email_verification

    try:
        user = auth_service.create_user(
            email=email,
            password=password,
            email_verified=not require_email_verification,
        )
    except sqlite3.IntegrityError:
        auth_service.log_auth_event(
            event_type="register",
            status="fail",
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="user_exists_race",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже существует")

    if require_email_verification:
        verify_token = auth_service.create_email_verification_token(int(user["id"]))
        sent_email = False
        if verify_token and auth_mailer.is_configured():
            try:
                auth_mailer.send_email_verification_email(email, verify_token)
                sent_email = True
            except Exception:
                sent_email = False
        message = (
            "Подтвердите email по ссылке из письма, чтобы завершить регистрацию."
            if sent_email
            else "Аккаунт создан. Подтверждение email временно недоступно, обратитесь в поддержку."
        )
        auth_service.log_auth_event(
            event_type="register",
            status="success" if sent_email else "fail",
            user_id=int(user["id"]),
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="verification_email_sent" if sent_email else "verification_email_not_sent",
        )
        return AuthResponse(
            user=AuthUserResponse(**user),
            message=message,
            requires_email_verification=True,
        )

    token = auth_service.create_session(
        user_id=int(user["id"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    auth_service.log_auth_event(
        event_type="register",
        status="success",
        user_id=int(user["id"]),
        email=email,
        ip=client_ip,
        user_agent=client_agent,
    )
    _set_session_cookie(response, token)
    return AuthResponse(user=AuthUserResponse(**user), message="Регистрация выполнена")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    email = _validate_email_like(payload.email)
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    if auth_service.is_login_rate_limited(email, client_ip):
        auth_service.log_auth_event(
            event_type="login",
            status="blocked",
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="rate_limited",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много неудачных попыток входа. Попробуйте позже.",
        )

    user_row = auth_service.get_user_by_email(email)
    if (
        settings.require_email_verification
        and user_row
        and bool(user_row["is_active"])
        and auth_service.verify_password(payload.password, str(user_row["password_hash"]))
        and not auth_service.is_email_verified(user_row)
    ):
        auth_service.record_login_attempt(email=email, ip=client_ip, success=False)
        auth_service.log_auth_event(
            event_type="login",
            status="fail",
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="email_not_verified",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Подтвердите email по ссылке из письма.")

    user = auth_service.authenticate(email=email, password=payload.password)
    if not user:
        auth_service.record_login_attempt(email=email, ip=client_ip, success=False)
        auth_service.log_auth_event(
            event_type="login",
            status="fail",
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="invalid_credentials",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    auth_service.record_login_attempt(email=email, ip=client_ip, success=True)
    token = auth_service.create_session(
        user_id=int(user["id"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    auth_service.log_auth_event(
        event_type="login",
        status="success",
        user_id=int(user["id"]),
        email=email,
        ip=client_ip,
        user_agent=client_agent,
    )
    _set_session_cookie(response, token)
    return AuthResponse(user=AuthUserResponse(**user), message="Вход выполнен")


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(payload: EmailVerificationConfirmPayload, request: Request, response: Response) -> AuthResponse:
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    verified_user = auth_service.verify_email_by_token(payload.token)
    if not verified_user:
        auth_service.log_auth_event(
            event_type="verify_email",
            status="fail",
            ip=client_ip,
            user_agent=client_agent,
            detail="invalid_or_expired_token",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен подтверждения недействителен или истёк")

    auth_service.log_auth_event(
        event_type="verify_email",
        status="success",
        user_id=int(verified_user["id"]),
        email=str(verified_user["email"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    token = auth_service.create_session(
        user_id=int(verified_user["id"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    _set_session_cookie(response, token)
    return AuthResponse(
        user=AuthUserResponse(**verified_user),
        message="Email успешно подтверждён.",
        requires_email_verification=False,
    )


@router.post("/logout")
def logout(request: Request, response: Response) -> Dict[str, str]:
    raw_token = request.cookies.get(settings.session_cookie_name)
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    if raw_token:
        user = auth_service.resolve_session(raw_token)
        auth_service.revoke_session(raw_token)
        auth_service.log_auth_event(
            event_type="logout",
            status="success",
            user_id=int(user["id"]) if user else None,
            email=str(user["email"]) if user else "",
            ip=client_ip,
            user_agent=client_agent,
        )
    _clear_session_cookie(response)
    return {"message": "Вы вышли из аккаунта"}


@router.get("/me", response_model=AuthUserResponse)
def me(current_user=Depends(require_user)) -> AuthUserResponse:
    return AuthUserResponse(**current_user)


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    limit: int = Query(default=8, ge=1, le=50),
    current_user=Depends(require_user),
) -> SessionListResponse:
    raw_token = request.cookies.get(settings.session_cookie_name, "")
    sessions = auth_service.list_active_user_sessions(int(current_user["id"]), raw_token, limit=limit)
    return SessionListResponse(sessions=[SessionItemResponse(**item) for item in sessions])


@router.post("/sessions/revoke-others", response_model=RevokeSessionsResponse)
def revoke_other_sessions(request: Request, current_user=Depends(require_user)) -> RevokeSessionsResponse:
    raw_token = request.cookies.get(settings.session_cookie_name, "")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    revoked_count = auth_service.revoke_other_user_sessions(int(current_user["id"]), raw_token)
    return RevokeSessionsResponse(revoked_count=revoked_count, message="Остальные сессии завершены")


@router.delete("/sessions/{session_id}", response_model=RevokeSessionsResponse)
def revoke_session_by_id(session_id: int, request: Request, response: Response, current_user=Depends(require_user)) -> RevokeSessionsResponse:
    if session_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор сессии")
    raw_token = request.cookies.get(settings.session_cookie_name, "")
    active_sessions = auth_service.list_active_user_sessions(int(current_user["id"]), raw_token, limit=50)
    target = next((item for item in active_sessions if int(item["id"]) == session_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    revoked = auth_service.revoke_user_session_by_id(int(current_user["id"]), session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    if bool(target.get("is_current")):
        _clear_session_cookie(response)
        return RevokeSessionsResponse(revoked_count=1, message="Текущая сессия завершена. Войдите снова.")

    return RevokeSessionsResponse(revoked_count=1, message="Сессия завершена")


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request, response: Response, current_user=Depends(require_user)):
    _validate_password_strength(payload.new_password)
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Новый пароль должен отличаться от текущего")

    email = str(current_user["email"])
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    verified = auth_service.authenticate(email=email, password=payload.current_password)
    if not verified:
        auth_service.log_auth_event(
            event_type="change_password",
            status="fail",
            user_id=int(current_user["id"]),
            email=email,
            ip=client_ip,
            user_agent=client_agent,
            detail="invalid_current_password",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Текущий пароль указан неверно")

    updated = auth_service.update_user_password(int(current_user["id"]), payload.new_password)
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось обновить пароль")
    auth_service.revoke_all_user_sessions(int(current_user["id"]))
    auth_service.log_auth_event(
        event_type="change_password",
        status="success",
        user_id=int(current_user["id"]),
        email=email,
        ip=client_ip,
        user_agent=client_agent,
    )
    _clear_session_cookie(response)
    return {"message": "Пароль обновлён. Войдите снова."}


@router.post("/password-reset/request")
def request_password_reset(payload: PasswordResetRequestPayload, request: Request):
    email = _validate_email_like(payload.email)
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    token = auth_service.create_password_reset_token(email)
    sent_email = False
    mail_error = ""
    if token and auth_mailer.is_configured():
        try:
            auth_mailer.send_password_reset_email(email, token)
            sent_email = True
        except Exception:
            mail_error = "mail_delivery_failed"
    auth_service.log_auth_event(
        event_type="password_reset_request",
        status="success" if token and (sent_email or not auth_mailer.is_configured()) else "fail",
        email=email,
        ip=client_ip,
        user_agent=client_agent,
        detail=(
            "issued_via_email"
            if token and sent_email
            else "issued_without_email"
            if token and not auth_mailer.is_configured()
            else mail_error
            if token
            else "user_not_found_or_inactive"
        ),
    )
    if not auth_mailer.is_configured() and not settings.expose_reset_token_in_response:
        return {"message": "Восстановление через email временно недоступно. Обратитесь в поддержку."}

    body: Dict[str, str] = {"message": "Ссылка на сброс пароля отправлена на почту."}
    if token and settings.expose_reset_token_in_response:
        body["reset_token"] = token
    return body


@router.post("/password-reset/confirm", response_model=AuthResponse)
def confirm_password_reset(payload: PasswordResetConfirmPayload, request: Request, response: Response):
    _validate_password_strength(payload.new_password)
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")
    reset_user = auth_service.reset_password_by_token(payload.token, payload.new_password)
    if not reset_user:
        auth_service.log_auth_event(
            event_type="password_reset_confirm",
            status="fail",
            ip=client_ip,
            user_agent=client_agent,
            detail="invalid_or_expired_token",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен недействителен или истёк")
    auth_service.log_auth_event(
        event_type="password_reset_confirm",
        status="success",
        user_id=int(reset_user["id"]),
        email=str(reset_user["email"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    token = auth_service.create_session(
        user_id=int(reset_user["id"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    _set_session_cookie(response, token)
    return AuthResponse(
        user=AuthUserResponse(**reset_user),
        message="Пароль успешно сброшен.",
    )
