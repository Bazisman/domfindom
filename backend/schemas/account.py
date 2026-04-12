from typing import List, Literal, Optional

from pydantic import BaseModel


ThemeMode = Literal["light", "dark", "system"]
WorkspaceMode = Literal["personal", "family"]


class AccountPreferencesResponse(BaseModel):
    theme_mode: ThemeMode
    workspace_mode: WorkspaceMode


class AccountPreferencesUpdatePayload(BaseModel):
    theme_mode: Optional[ThemeMode] = None
    workspace_mode: Optional[WorkspaceMode] = None


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


class AccountActivityItemResponse(BaseModel):
    event_type: str
    status: str
    detail: str
    ip: str
    user_agent: str
    created_at: str


class AccountActivityResponse(BaseModel):
    events: List[AccountActivityItemResponse]
