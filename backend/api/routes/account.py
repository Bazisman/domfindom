from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_user
from backend.auth.service import auth_service
from backend.schemas.account import (
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


@router.post("/backup/save", response_model=BackupSaveResponse)
def save_backup(current_user=Depends(require_user)) -> BackupSaveResponse:
    result = auth_service.save_user_backup_slot(int(current_user["id"]))
    return BackupSaveResponse(message="Резервная копия сохранена.", **result)


@router.post("/backup/restore", response_model=BackupRestoreResponse)
def restore_backup(current_user=Depends(require_user)) -> BackupRestoreResponse:
    restored = auth_service.restore_user_backup_slot(int(current_user["id"]))
    if not restored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось восстановить данные. Проверьте наличие резервной копии.",
        )
    return BackupRestoreResponse(message="Данные восстановлены из резервной копии.")


@router.post("/reset-all", response_model=ResetAllResponse)
def reset_all(payload: ResetAllPayload, current_user=Depends(require_user)) -> ResetAllResponse:
    if payload.confirm_text.strip().upper() != "СБРОС":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Введите слово СБРОС для подтверждения.",
        )
    auth_service.reset_user_finance_data(int(current_user["id"]))
    return ResetAllResponse(message="Данные очищены. Можно начать заново.")
