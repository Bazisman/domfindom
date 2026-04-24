from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from backend.schemas.forecast import ForecastResponse


FamilyRole = Literal["owner", "member", "viewer"]
InviteRole = Literal["member", "viewer"]
CategoryAuditSeverity = Literal["critical", "warning", "info"]
CategoryAuditGroupStatus = Literal["confirmed", "suggested", "unlinked", "conflict"]


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
    display_name: str
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
    capital_balance: float = 0
    income: float
    expense: float
    difference: float


class FamilyCapitalAccountItemResponse(BaseModel):
    owner_user_id: int
    owner_email: str
    owner_display_name: str
    capital_account_id: int
    name: str
    balance: float
    color: Optional[str] = None
    icon: Optional[str] = None
    is_visible: bool
    is_default_target: bool


class FamilyCapitalSelectionResponse(BaseModel):
    target_owner_user_id: Optional[int] = None
    target_capital_account_id: Optional[int] = None


class FamilyCapitalContributionItemResponse(BaseModel):
    id: int
    family_id: int
    source_user_id: int
    source_transaction_id: int
    target_owner_user_id: int
    target_capital_account_id: int
    amount: float
    date: str
    comment: str
    source_email: str
    source_display_name: str
    target_owner_email: str
    target_owner_display_name: str
    target_account_name: str = ""


class FamilyCapitalContributionListResponse(BaseModel):
    family_id: int
    items: List[FamilyCapitalContributionItemResponse]


class FamilyCapitalTargetUpdatePayload(BaseModel):
    target_owner_user_id: Optional[int] = None
    target_capital_account_id: Optional[int] = None


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
    owner_display_name: str


class FamilyDashboardResponse(BaseModel):
    family_id: int
    family_name: str
    members_count: int
    balance: FamilyDashboardBalanceResponse
    forecast: ForecastResponse
    capital_accounts: List[FamilyCapitalAccountItemResponse] = []
    current_member_capital_target: FamilyCapitalSelectionResponse = FamilyCapitalSelectionResponse()
    recent_transactions: List[FamilyDashboardTransactionResponse]


class FamilyTransactionListResponse(BaseModel):
    family_id: int
    family_name: str
    owner_user_id: Optional[int] = None
    limit: int
    offset: int = 0
    total: int = 0
    transactions: List[FamilyDashboardTransactionResponse]


class FamilyCategoryAuditSummaryResponse(BaseModel):
    members_count: int
    active_categories_count: int
    transaction_categories_count: int
    findings_count: int
    critical_count: int
    warning_count: int
    info_count: int
    duplicate_candidates_count: int
    orphan_transaction_categories_count: int
    missing_member_categories_count: int


class FamilyCategoryAuditMemberResponse(BaseModel):
    user_id: int
    email: str
    display_name: str
    active_categories_count: int
    inactive_categories_count: int
    transaction_categories_count: int
    budget_count: int
    recurring_template_count: int


class FamilyCategoryAuditGroupResponse(BaseModel):
    group_key: str
    semantic_key: Optional[str] = None
    display_name: str
    category_names: List[str]
    owner_names: List[str]
    types: List[str]
    confirmed_bindings_count: int = 0
    transaction_count: int = 0
    planned_transaction_count: int = 0
    transaction_total: float = 0
    budget_count: int = 0
    budget_total: float = 0
    recurring_count: int = 0
    status: CategoryAuditGroupStatus


class FamilyCategoryAuditFindingResponse(BaseModel):
    severity: CategoryAuditSeverity
    code: str
    title: str
    description: str
    category_names: List[str] = Field(default_factory=list)
    owner_names: List[str] = Field(default_factory=list)
    affected_transaction_count: int = 0
    affected_budget_count: int = 0
    affected_recurring_count: int = 0
    recommended_action: str
    can_apply_automatically: bool = False


class FamilyCategoryAuditResponse(BaseModel):
    family_id: int
    family_name: str
    generated_at: str
    summary: FamilyCategoryAuditSummaryResponse
    members: List[FamilyCategoryAuditMemberResponse]
    category_groups: List[FamilyCategoryAuditGroupResponse]
    findings: List[FamilyCategoryAuditFindingResponse]


class FamilyCategoryBindingPreviewPayload(BaseModel):
    semantic_key: str = Field(min_length=2, max_length=120)
    display_name: Optional[str] = Field(default=None, max_length=120)
    category_names: List[str] = Field(min_length=1)


class FamilyCategoryBindingCandidateResponse(BaseModel):
    user_id: int
    owner_name: str
    local_category_id: int
    local_category_name: str
    local_category_type: str
    transaction_count: int = 0
    planned_transaction_count: int = 0
    transaction_total: float = 0
    budget_count: int = 0
    recurring_count: int = 0
    already_bound: bool = False


class FamilyCategoryBindingPreviewResponse(BaseModel):
    family_id: int
    semantic_key: str
    display_name: str
    type: str
    candidates: List[FamilyCategoryBindingCandidateResponse]
    candidate_count: int
    already_bound_count: int
    new_binding_count: int
    affected_transaction_count: int
    affected_budget_count: int
    affected_recurring_count: int
    can_apply: bool
    message: str


class FamilyCategoryBindingApplyResponse(BaseModel):
    message: str
    preview: FamilyCategoryBindingPreviewResponse
    applied_bindings_count: int
