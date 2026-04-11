from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.auth.dependencies import require_user
from backend.auth.mailer import auth_mailer
from backend.auth.service import auth_service
from backend.config import settings
from backend.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    RegisterRequest,
)


router = APIRouter()


def _validate_email_like(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or "." not in normalized.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid email")
    return normalized


def _validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Password is too short")
    has_upper = any(char.isupper() for char in value)
    has_lower = any(char.islower() for char in value)
    has_digit = any(char.isdigit() for char in value)
    if not (has_upper and has_lower and has_digit):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Password must include upper/lowercase letters and digits",
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = auth_service.create_user(email=email, password=password)
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
    return AuthResponse(user=AuthUserResponse(**user), message="Registered")


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
            detail="Too many failed attempts. Try again later.",
        )

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
    return AuthResponse(user=AuthUserResponse(**user), message="Logged in")


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
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthUserResponse)
def me(current_user=Depends(require_user)) -> AuthUserResponse:
    return AuthUserResponse(**current_user)


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request, response: Response, current_user=Depends(require_user)):
    _validate_password_strength(payload.new_password)
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="New password must be different")

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")

    updated = auth_service.update_user_password(int(current_user["id"]), payload.new_password)
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update password")
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
    return {"message": "Password updated. Please log in again."}


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
    body: Dict[str, str] = {"message": "If account exists, reset instructions were generated."}
    if token and settings.expose_reset_token_in_response:
        body["reset_token"] = token
    return body


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmPayload, request: Request):
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    auth_service.log_auth_event(
        event_type="password_reset_confirm",
        status="success",
        user_id=int(reset_user["id"]),
        email=str(reset_user["email"]),
        ip=client_ip,
        user_agent=client_agent,
    )
    return {"message": "Password reset successful. Please log in."}
