from typing import Literal

from pydantic import BaseModel


ThemeMode = Literal["light", "dark", "system"]


class AccountPreferencesResponse(BaseModel):
    theme_mode: ThemeMode


class AccountPreferencesUpdatePayload(BaseModel):
    theme_mode: ThemeMode


class BackupSlotInfoResponse(BaseModel):
    has_backup: bool
    created_at: str
    updated_at: str
    checksum: str


class BackupSaveResponse(BaseModel):
    message: str
    created_at: str
    updated_at: str
    checksum: str


class BackupRestoreResponse(BaseModel):
    message: str


class ResetAllPayload(BaseModel):
    confirm_text: str


class ResetAllResponse(BaseModel):
    message: str
