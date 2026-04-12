from typing import List, Literal, Optional

from pydantic import BaseModel, Field


FamilyRole = Literal["owner", "member", "viewer"]
InviteRole = Literal["member", "viewer"]


class FamilyCreatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class FamilyItemResponse(BaseModel):
    id: int
    name: str
    role: FamilyRole
    status: str
    created_at: str


class FamilyListResponse(BaseModel):
    families: List[FamilyItemResponse]


class FamilyMemberItemResponse(BaseModel):
    user_id: int
    email: str
    role: FamilyRole
    status: str
    joined_at: str


class FamilyMemberListResponse(BaseModel):
    members: List[FamilyMemberItemResponse]


class FamilyInviteCreatePayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: InviteRole = "member"


class FamilyInviteCreateResponse(BaseModel):
    message: str
    family_id: int
    email: str
    role: InviteRole
    expires_at: str
    invite_token: Optional[str] = None


class FamilyInviteAcceptPayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class FamilyInviteAcceptResponse(BaseModel):
    message: str
    family_id: int
    family_name: str
    role: FamilyRole


class FamilyMemberRoleUpdatePayload(BaseModel):
    role: InviteRole


class FamilyActionResponse(BaseModel):
    message: str


class FamilyPendingInviteItemResponse(BaseModel):
    invite_id: int
    family_id: int
    family_name: str
    role: InviteRole
    invited_by_email: str
    expires_at: str
    created_at: str


class FamilyPendingInviteListResponse(BaseModel):
    invites: List[FamilyPendingInviteItemResponse]


class FamilyDashboardBalanceResponse(BaseModel):
    main_balance: float
    income: float
    expense: float
    difference: float


class FamilyDashboardTransactionResponse(BaseModel):
    id: int
    type: Literal["income", "expense"]
    category: str
    amount: float
    comment: str
    date: str
    status: Literal["actual", "planned"]
    owner_user_id: int
    owner_email: str


class FamilyDashboardResponse(BaseModel):
    family_id: int
    family_name: str
    members_count: int
    balance: FamilyDashboardBalanceResponse
    recent_transactions: List[FamilyDashboardTransactionResponse]


class FamilyTransactionListResponse(BaseModel):
    family_id: int
    family_name: str
    owner_user_id: Optional[int] = None
    limit: int
    transactions: List[FamilyDashboardTransactionResponse]
