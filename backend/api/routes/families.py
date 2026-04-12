from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.families import (
    FamilyActionResponse,
    FamilyCreatePayload,
    FamilyInviteAcceptPayload,
    FamilyInviteAcceptResponse,
    FamilyInviteCreatePayload,
    FamilyInviteCreateResponse,
    FamilyItemResponse,
    FamilyListResponse,
    FamilyMemberItemResponse,
    FamilyMemberListResponse,
    FamilyMemberRoleUpdatePayload,
    FamilyPendingInviteItemResponse,
    FamilyPendingInviteListResponse,
)


router = APIRouter()


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or "." not in normalized.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный email")
    return normalized


def _require_family_role(family_id: int, user_id: int):
    membership = auth_service.get_family_membership(family_id=family_id, user_id=user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Семья не найдена или доступ запрещен")
    return membership


def _require_family_admin_access(family_id: int, user_id: int):
    membership = _require_family_role(family_id=family_id, user_id=user_id)
    if membership["role"] not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return membership


def _validate_member_management_rules(
    actor_user_id: int,
    actor_role: str,
    target_user_id: int,
    target_role: str,
    next_role: str = "",
) -> None:
    if target_role == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя изменить владельца семьи")
    if actor_role == "admin":
        if target_role == "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Администратор не может менять другого администратора")
        if next_role == "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Администратор не может назначать других администраторов")
    if actor_user_id == target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя изменить собственную роль этим действием")


@router.post("", response_model=FamilyItemResponse, status_code=status.HTTP_201_CREATED)
def create_family(payload: FamilyCreatePayload, current_user=Depends(require_user)) -> FamilyItemResponse:
    family = auth_service.create_family(owner_user_id=int(current_user["id"]), name=payload.name.strip())
    return FamilyItemResponse(**family)


@router.get("/me", response_model=FamilyListResponse)
def list_my_families(current_user=Depends(require_user)) -> FamilyListResponse:
    items = auth_service.list_user_families(int(current_user["id"]))
    return FamilyListResponse(families=[FamilyItemResponse(**item) for item in items])


@router.get("/{family_id}/members", response_model=FamilyMemberListResponse)
def list_family_members(family_id: int, current_user=Depends(require_user)) -> FamilyMemberListResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_role(family_id=family_id, user_id=int(current_user["id"]))
    members = auth_service.list_family_members(family_id=family_id)
    return FamilyMemberListResponse(members=[FamilyMemberItemResponse(**item) for item in members])


@router.post("/{family_id}/invites", response_model=FamilyInviteCreateResponse)
def create_family_invite(
    family_id: int,
    payload: FamilyInviteCreatePayload,
    current_user=Depends(require_user),
) -> FamilyInviteCreateResponse:
    if family_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор семьи")

    _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))

    invited_email = _normalize_email(payload.email)
    try:
        invite = auth_service.create_family_invite(
            family_id=family_id,
            invited_by_user_id=int(current_user["id"]),
            email=invited_email,
            role=payload.role,
        )
    except ValueError as exc:
        if str(exc) == "user_already_member":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь уже состоит в семейном бюджете",
            ) from exc
        raise

    return FamilyInviteCreateResponse(
        message="Приглашение создано.",
        family_id=family_id,
        email=invited_email,
        role=payload.role,
        expires_at=invite["expires_at"],
        invite_token=invite["token"],
    )


@router.post("/invites/accept", response_model=FamilyInviteAcceptResponse)
def accept_family_invite(payload: FamilyInviteAcceptPayload, current_user=Depends(require_user)) -> FamilyInviteAcceptResponse:
    accepted = auth_service.accept_family_invite(token=payload.token, user_id=int(current_user["id"]))
    if not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Инвайт недействителен или истек")

    return FamilyInviteAcceptResponse(
        message="Вы подключены к семейному бюджету.",
        family_id=int(accepted["family_id"]),
        family_name=str(accepted["family_name"]),
        role=str(accepted["role"]),
    )


@router.get("/invites/pending", response_model=FamilyPendingInviteListResponse)
def list_pending_family_invites(current_user=Depends(require_user)) -> FamilyPendingInviteListResponse:
    invites = auth_service.list_pending_family_invites(int(current_user["id"]))
    return FamilyPendingInviteListResponse(invites=[FamilyPendingInviteItemResponse(**item) for item in invites])


@router.post("/invites/{invite_id}/accept", response_model=FamilyInviteAcceptResponse)
def accept_family_invite_by_id(invite_id: int, current_user=Depends(require_user)) -> FamilyInviteAcceptResponse:
    if invite_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор приглашения")
    accepted = auth_service.accept_family_invite_by_id(invite_id=invite_id, user_id=int(current_user["id"]))
    if not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение недействительно или истекло")
    return FamilyInviteAcceptResponse(
        message="Вы подключены к семейному бюджету.",
        family_id=int(accepted["family_id"]),
        family_name=str(accepted["family_name"]),
        role=str(accepted["role"]),
    )


@router.post("/invites/{invite_id}/decline", response_model=FamilyActionResponse)
def decline_family_invite_by_id(invite_id: int, current_user=Depends(require_user)) -> FamilyActionResponse:
    if invite_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректный идентификатор приглашения")
    declined = auth_service.decline_family_invite_by_id(invite_id=invite_id, user_id=int(current_user["id"]))
    if not declined:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Приглашение недействительно или уже обработано")
    return FamilyActionResponse(message="Приглашение отклонено.")


@router.patch("/{family_id}/members/{member_user_id}/role", response_model=FamilyActionResponse)
def update_family_member_role(
    family_id: int,
    member_user_id: int,
    payload: FamilyMemberRoleUpdatePayload,
    current_user=Depends(require_user),
) -> FamilyActionResponse:
    if family_id <= 0 or member_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректные параметры")

    actor = _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    target = _require_family_role(family_id=family_id, user_id=member_user_id)
    _validate_member_management_rules(
        actor_user_id=int(current_user["id"]),
        actor_role=str(actor["role"]),
        target_user_id=member_user_id,
        target_role=str(target["role"]),
        next_role=payload.role,
    )

    try:
        updated = auth_service.update_family_member_role(
            family_id=family_id,
            user_id=member_user_id,
            role=payload.role,
        )
    except ValueError as exc:
        if str(exc) == "owner_role_locked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя изменить роль владельца") from exc
        raise

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return FamilyActionResponse(message="Роль участника обновлена.")


@router.delete("/{family_id}/members/{member_user_id}", response_model=FamilyActionResponse)
def remove_family_member(
    family_id: int,
    member_user_id: int,
    current_user=Depends(require_user),
) -> FamilyActionResponse:
    if family_id <= 0 or member_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Некорректные параметры")

    actor = _require_family_admin_access(family_id=family_id, user_id=int(current_user["id"]))
    target = _require_family_role(family_id=family_id, user_id=member_user_id)
    _validate_member_management_rules(
        actor_user_id=int(current_user["id"]),
        actor_role=str(actor["role"]),
        target_user_id=member_user_id,
        target_role=str(target["role"]),
    )

    try:
        removed = auth_service.remove_family_member(family_id=family_id, user_id=member_user_id)
    except ValueError as exc:
        if str(exc) == "owner_cannot_be_removed":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя удалить владельца семьи") from exc
        raise

    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return FamilyActionResponse(message="Участник исключен из семьи.")
