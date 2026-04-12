from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.account import (
    AccountActivityItemResponse,
    AccountActivityResponse,
    AccountPreferencesResponse,
    AccountPreferencesUpdatePayload,
    BackupRestoreResponse,
    BackupSaveResponse,
    BackupSlotInfoResponse,
    ResetAllPayload,
    ResetAllResponse,
)


router = APIRouter()


@router.get("/preferences", response_model=AccountPreferencesResponse)
def get_preferences(current_user=Depends(require_user)) -> AccountPreferencesResponse:
    result = auth_service.get_user_preferences(int(current_user["id"]))
    return AccountPreferencesResponse(**result)


@router.put("/preferences", response_model=AccountPreferencesResponse)
def update_preferences(
    payload: AccountPreferencesUpdatePayload,
    current_user=Depends(require_user),
) -> AccountPreferencesResponse:
    result = auth_service.update_user_preferences(int(current_user["id"]), payload.theme_mode)
    return AccountPreferencesResponse(**result)


@router.get("/backup", response_model=BackupSlotInfoResponse)
def get_backup_info(current_user=Depends(require_user)) -> BackupSlotInfoResponse:
    result = auth_service.get_user_backup_slot_info(int(current_user["id"]))
    return BackupSlotInfoResponse(**result)


@router.get("/activity", response_model=AccountActivityResponse)
def get_account_activity(limit: int = 20, current_user=Depends(require_user)) -> AccountActivityResponse:
    events = auth_service.list_user_auth_events(int(current_user["id"]), limit=limit)
    return AccountActivityResponse(events=[AccountActivityItemResponse(**item) for item in events])


@router.post("/backup/save", response_model=BackupSaveResponse)
def save_backup(request: Request, current_user=Depends(require_user)) -> BackupSaveResponse:
    user_id = int(current_user["id"])
    user_email = str(current_user["email"])
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")

    result = auth_service.save_user_backup_slot(user_id)
    auth_service.log_auth_event(
        event_type="backup_save",
        status="success",
        user_id=user_id,
        email=user_email,
        ip=client_ip,
        user_agent=client_agent,
    )
    return BackupSaveResponse(message="Р В Р ВµР В·Р ВµРЎР‚Р Р†Р Р…Р В°РЎРЏ Р С”Р С•Р С—Р С‘РЎРЏ РЎРѓР С•РЎвЂ¦РЎР‚Р В°Р Р…Р ВµР Р…Р В°.", **result)


@router.post("/backup/restore", response_model=BackupRestoreResponse)
def restore_backup(request: Request, current_user=Depends(require_user)) -> BackupRestoreResponse:
    user_id = int(current_user["id"])
    user_email = str(current_user["email"])
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")

    restored = auth_service.restore_user_backup_slot(user_id)
    if not restored:
        auth_service.log_auth_event(
            event_type="backup_restore",
            status="fail",
            user_id=user_id,
            email=user_email,
            ip=client_ip,
            user_agent=client_agent,
            detail="missing_or_invalid_backup",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р Р†Р С•РЎРѓРЎРѓРЎвЂљР В°Р Р…Р С•Р Р†Р С‘РЎвЂљРЎРЉ Р Т‘Р В°Р Р…Р Р…РЎвЂ№Р Вµ. Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЉРЎвЂљР Вµ Р Р…Р В°Р В»Р С‘РЎвЂЎР С‘Р Вµ РЎР‚Р ВµР В·Р ВµРЎР‚Р Р†Р Р…Р С•Р в„– Р С”Р С•Р С—Р С‘Р С‘.",
        )

    auth_service.log_auth_event(
        event_type="backup_restore",
        status="success",
        user_id=user_id,
        email=user_email,
        ip=client_ip,
        user_agent=client_agent,
    )
    return BackupRestoreResponse(message="Р вЂќР В°Р Р…Р Р…РЎвЂ№Р Вµ Р Р†Р С•РЎРѓРЎРѓРЎвЂљР В°Р Р…Р С•Р Р†Р В»Р ВµР Р…РЎвЂ№ Р С‘Р В· РЎР‚Р ВµР В·Р ВµРЎР‚Р Р†Р Р…Р С•Р в„– Р С”Р С•Р С—Р С‘Р С‘.")


@router.post("/reset-all", response_model=ResetAllResponse)
def reset_all(payload: ResetAllPayload, request: Request, current_user=Depends(require_user)) -> ResetAllResponse:
    confirm_token = payload.confirm_text.strip().upper()
    if confirm_token not in {"СБРОС", "РЎР‘Р РћРЎ"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Р вЂ™Р Р†Р ВµР Т‘Р С‘РЎвЂљР Вµ РЎРѓР В»Р С•Р Р†Р С• Р РЋР вЂР В Р С›Р РЋ Р Т‘Р В»РЎРЏ Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р…Р С‘РЎРЏ.",
        )

    user_id = int(current_user["id"])
    user_email = str(current_user["email"])
    client_ip = request.client.host if request.client else ""
    client_agent = request.headers.get("user-agent", "")

    auth_service.reset_user_finance_data(user_id)
    auth_service.log_auth_event(
        event_type="reset_all_data",
        status="success",
        user_id=user_id,
        email=user_email,
        ip=client_ip,
        user_agent=client_agent,
    )
    return ResetAllResponse(message="Р вЂќР В°Р Р…Р Р…РЎвЂ№Р Вµ Р С•РЎвЂЎР С‘РЎвЂ°Р ВµР Р…РЎвЂ№. Р СљР С•Р В¶Р Р…Р С• Р Р…Р В°РЎвЂЎР В°РЎвЂљРЎРЉ Р В·Р В°Р Р…Р С•Р Р†Р С•.")
