export type DashboardResponse = {
  balance: {
    main_balance: number;
    income: number;
    expense: number;
    difference: number;
  };
  forecast: {
    current_balance: number;
    planned_income: number;
    planned_expense: number;
    executed_planned_income: number;
    executed_planned_expense: number;
    monthly_budget: number;
    total_budgets: number;
    current_expenses: number;
    budget_remaining: number;
    combined_pending_expense: number;
    combined_executed_expense: number;
    projected_balance: number;
    end_date: string;
  };
  recent_transactions: Array<{
    id: number;
    type: "income" | "expense";
    category: string;
    amount: number;
    comment: string;
    date: string;
    status: "actual" | "planned";
    money_source: MoneySource;
  }>;
  budget_highlights: Array<{
    category_id: number;
    category_name: string;
    budget_amount: number;
    spent: number;
    remaining: number;
    percent: number;
    over_budget: boolean;
    color: string;
    icon: string;
  }>;
};

export type Category = {
  id: number;
  name: string;
  type: CategoryType;
  color: string;
  icon: string;
  is_active: boolean;
};

export type CategoryType = "income" | "expense" | "both";

export type Transaction = {
  id: number;
  type: "income" | "expense";
  category: string;
  amount: number;
  comment: string;
  date: string;
  status: "actual" | "planned";
  money_source: MoneySource;
};

export type TransactionPage = {
  items: Transaction[];
  limit: number;
  offset: number;
  total: number;
};

export type TransactionType = "income" | "expense";
export type MoneySource = "cashless" | "cash";
export type TransactionPeriod = "all" | "month" | "last_month" | "year";
export type SummaryPeriod = TransactionPeriod | "custom";

export type ReconciliationSource = {
  id: number;
  name: string;
  balance: number;
  is_active: boolean;
};

export type ReconciliationHistoryItem = {
  id: number;
  real_balance: number;
  program_balance: number;
  difference: number;
  adjustment_transaction_id: number | null;
  created_at: string;
  updated_at: string | null;
};

export type ReconciliationSummary = {
  program_balance: number;
  real_balance: number;
  difference: number;
  last_reconciliation: ReconciliationHistoryItem | null;
  sources: ReconciliationSource[];
  history: ReconciliationHistoryItem[];
};

export type ReconciliationApplyResponse = {
  message: string;
  reconciliation: ReconciliationHistoryItem;
  adjustment_transaction_id: number | null;
};

export type TransactionCreatePayload = {
  type: TransactionType;
  category_id?: number;
  category_name?: string;
  amount: number;
  comment: string;
  date: string;
  money_source?: MoneySource;
  auto_capital_percent?: number;
  capital_account_id?: number;
  recurring?: {
    enabled: boolean;
    template_name: string;
    day_of_month: number;
    months_ahead: number;
    working_days_only: boolean;
  };
};

export type TransactionUpdatePayload = {
  type?: TransactionType;
  category_id?: number;
  category_name?: string;
  amount?: number;
  comment?: string;
  date?: string;
  money_source?: MoneySource;
};

export type CategoryCreatePayload = {
  name: string;
  type?: CategoryType;
  color?: string;
  icon?: string;
};

export type CategoryUpdatePayload = {
  name?: string;
  type?: CategoryType;
  color?: string;
  icon?: string;
  is_active?: boolean;
};

export type Budget = {
  id: number;
  category_id: number;
  category_name: string;
  amount: number;
  period: string;
};

export type BudgetStatusItem = {
  category_id: number;
  category_name: string;
  icon: string;
  color: string;
  budget_amount: number;
  spent: number;
  remaining: number;
  percent: number;
  over_budget: boolean;
};

export type BudgetCreatePayload = {
  category_id: number;
  amount: number;
  period?: string;
};

export type BudgetUpdatePayload = {
  amount?: number;
  period?: string;
};

export type AccountType = "main" | "cash" | "cashless" | "capital";
export type CapitalPurpose = "cushion" | "investment";

export type Account = {
  id: number;
  name: string;
  type: AccountType;
  balance: number;
  currency: string;
  is_active: boolean;
  is_default: boolean;
  icon: string | null;
  color: string | null;
  family_visible: boolean;
  family_default_target: boolean;
  money_source: MoneySource | null;
  purpose: CapitalPurpose;
};

export type AccountCreatePayload = {
  type?: "capital";
  name: string;
  balance?: number;
  icon?: string;
  color?: string;
  purpose?: CapitalPurpose;
};

export type AccountUpdatePayload = {
  name?: string;
  balance?: number;
  icon?: string;
  color?: string;
  is_default?: boolean;
  family_visible?: boolean;
  family_default_target?: boolean;
  purpose?: CapitalPurpose;
};

export type Transfer = {
  id: number;
  from_account_id: number;
  to_account_id: number;
  amount: number;
  date: string;
  comment: string;
  from_name: string;
  to_name: string;
  is_active: boolean;
};

export type TransferCreatePayload = {
  from_account_id: number;
  to_account_id: number;
  target_owner_user_id?: number;
  amount: number;
  date?: string;
  comment?: string;
};

export type Settings = {
  auto_capital_enabled: boolean;
  auto_capital_percent: number;
  default_capital_account_id: number | null;
  default_money_source: MoneySource;
};

export type SettingsUpdatePayload = {
  auto_capital_enabled?: boolean;
  auto_capital_percent?: number;
  default_money_source?: MoneySource;
};

export type RecurringTemplate = {
  id: number;
  type: "income" | "expense";
  name: string;
  amount: number;
  day_of_month: number;
  category_id: number | null;
  category_name: string | null;
  comment_template: string;
  money_source: MoneySource;
  months_ahead: number;
  working_days_only: boolean;
  is_active: boolean;
};

export type RecurringTemplateCreatePayload = {
  type: "income" | "expense";
  name: string;
  amount: number;
  day_of_month: number;
  category_id?: number;
  comment_template?: string;
  money_source?: MoneySource;
  months_ahead?: number;
  working_days_only?: boolean;
};

export type RecurringTemplateUpdatePayload = {
  type?: "income" | "expense";
  name?: string;
  amount?: number;
  day_of_month?: number;
  category_id?: number | null;
  comment_template?: string;
  money_source?: MoneySource;
  months_ahead?: number;
  working_days_only?: boolean;
  is_active?: boolean;
};

export type AuthUser = {
  id: number;
  email: string;
  email_verified: boolean;
  is_active: boolean;
};

export type AuthResponse = {
  user: AuthUser;
  message: string;
  requires_email_verification?: boolean;
};

export type PasswordResetRequestResponse = {
  message: string;
  reset_token?: string;
};

export type UserSession = {
  id: number;
  ip: string;
  user_agent: string;
  created_at: string;
  expires_at: string;
  is_current: boolean;
};

export type AccountPreferences = {
  theme_mode: "light" | "dark" | "system";
  workspace_mode: "personal" | "family";
  display_name: string;
};

export type AccountBackupInfo = {
  has_backup: boolean;
  created_at: string;
  updated_at: string;
  checksum: string;
};

export type AccountActivityEvent = {
  event_type: string;
  status: "success" | "fail" | "blocked" | string;
  detail: string;
  ip: string;
  user_agent: string;
  created_at: string;
};

export type FamilyRole = "owner" | "member" | "viewer";
export type FamilyInviteRole = "member" | "viewer";

export type FamilyItem = {
  id: number;
  name: string;
  role: FamilyRole;
  status: string;
  created_at: string;
};

export type FamilyMemberItem = {
  user_id: number;
  email: string;
  display_name: string;
  role: FamilyRole;
  status: string;
  joined_at: string;
};

export type FamilyActionResponse = {
  message: string;
};

export type FamilyPendingInvite = {
  invite_id: number;
  family_id: number;
  family_name: string;
  role: FamilyInviteRole;
  invited_by_email: string;
  expires_at: string;
  created_at: string;
};

export type FamilyDashboardResponse = {
  family_id: number;
  family_name: string;
  members_count: number;
  balance: {
    main_balance: number;
    capital_balance: number;
    income: number;
    expense: number;
    difference: number;
  };
  member_money: Array<{
    user_id: number;
    email: string;
    display_name: string;
    main_balance: number;
  }>;
  forecast: DashboardResponse["forecast"];
  capital_accounts: Array<{
    owner_user_id: number;
    owner_email: string;
    owner_display_name: string;
    capital_account_id: number;
    name: string;
    balance: number;
    color: string | null;
    icon: string | null;
    purpose: CapitalPurpose;
    is_visible: boolean;
    is_default_target: boolean;
  }>;
  current_member_capital_target: {
    target_owner_user_id: number | null;
    target_capital_account_id: number | null;
  };
  recent_transactions: Array<{
    id: number;
    type: "income" | "expense";
    category: string;
    amount: number;
    comment: string;
    date: string;
    status: "actual" | "planned";
    money_source: MoneySource;
    owner_user_id: number;
    owner_email: string;
    owner_display_name: string;
  }>;
};

export type FamilyCapitalContributionItem = {
  id: number;
  family_id: number;
  source_user_id: number;
  source_transaction_id: number;
  target_owner_user_id: number;
  target_capital_account_id: number;
  amount: number;
  date: string;
  comment: string;
  source_email: string;
  source_display_name: string;
  target_owner_email: string;
  target_owner_display_name: string;
  target_account_name: string;
};

export type FamilyCapitalContributionListResponse = {
  family_id: number;
  items: FamilyCapitalContributionItem[];
};

export type FamilyTransactionListResponse = {
  family_id: number;
  family_name: string;
  owner_user_id: number | null;
  limit: number;
  offset: number;
  total: number;
  transactions: FamilyDashboardResponse["recent_transactions"];
};

export type FamilyCategoryAuditSeverity = "critical" | "warning" | "info";
export type FamilyCategoryAuditGroupStatus = "confirmed" | "suggested" | "unlinked" | "conflict";

export type FamilyCategoryAuditResponse = {
  family_id: number;
  family_name: string;
  generated_at: string;
  summary: {
    members_count: number;
    active_categories_count: number;
    transaction_categories_count: number;
    findings_count: number;
    critical_count: number;
    warning_count: number;
    info_count: number;
    duplicate_candidates_count: number;
    orphan_transaction_categories_count: number;
    missing_member_categories_count: number;
  };
  members: Array<{
    user_id: number;
    email: string;
    display_name: string;
    active_categories_count: number;
    inactive_categories_count: number;
    transaction_categories_count: number;
    budget_count: number;
    recurring_template_count: number;
  }>;
  category_groups: Array<{
    group_key: string;
    semantic_key: string | null;
    display_name: string;
    category_names: string[];
    owner_names: string[];
    types: string[];
    confirmed_bindings_count: number;
    transaction_count: number;
    planned_transaction_count: number;
    transaction_total: number;
    budget_count: number;
    budget_total: number;
    recurring_count: number;
    status: FamilyCategoryAuditGroupStatus;
  }>;
  findings: Array<{
    severity: FamilyCategoryAuditSeverity;
    code: string;
    title: string;
    description: string;
    group_key: string | null;
    semantic_key: string | null;
    display_name: string | null;
    category_names: string[];
    owner_names: string[];
    affected_transaction_count: number;
    affected_budget_count: number;
    affected_recurring_count: number;
    recommended_action: string;
    can_apply_automatically: boolean;
  }>;
  resolutions: Array<{
    family_id: number;
    code: string;
    group_key: string;
    action: "ignore" | "keep_personal";
    category_names: string[];
    note: string;
  }>;
};

export type FamilyCategoryBindingPreviewPayload = {
  familyId: number;
  semanticKey: string;
  displayName?: string;
  categoryNames: string[];
  categoryType?: string;
};

export type FamilyCategoryAuditResolutionPayload = {
  familyId: number;
  code: string;
  groupKey: string;
  action: "ignore" | "keep_personal";
  categoryNames: string[];
  note?: string;
};

export type FamilyCategoryBindingPreviewResponse = {
  family_id: number;
  semantic_key: string;
  display_name: string;
  type: string;
  candidates: Array<{
    user_id: number;
    owner_name: string;
    local_category_id: number;
    local_category_name: string;
    local_category_type: string;
    transaction_count: number;
    planned_transaction_count: number;
    transaction_total: number;
    budget_count: number;
    recurring_count: number;
    already_bound: boolean;
  }>;
  candidate_count: number;
  already_bound_count: number;
  new_binding_count: number;
  affected_transaction_count: number;
  affected_budget_count: number;
  affected_recurring_count: number;
  can_apply: boolean;
  message: string;
};

export type FamilyCategoryBindingApplyResponse = {
  message: string;
  preview: FamilyCategoryBindingPreviewResponse;
  applied_bindings_count: number;
};

export type CategorySummaryItem = {
  category: string;
  total: number;
  share_percent: number;
  color: string;
  icon: string;
};

export type CategorySummaryResponse = {
  scope: "personal" | "family";
  family_id: number | null;
  family_name: string | null;
  type: "income" | "expense";
  period: SummaryPeriod;
  start_date: string | null;
  end_date: string | null;
  total: number;
  categories_count: number;
  items: CategorySummaryItem[];
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type DuePlannedTransaction = {
  id: number;
  type: "income" | "expense";
  category: string;
  amount: number;
  comment: string;
  date: string;
  template_id: number | null;
  template_name: string | null;
  money_source: MoneySource;
};

type ValidationErrorItem = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
};

type ApiErrorPayload = {
  detail?: string | ValidationErrorItem[];
  message?: string;
};

const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ?? "/api/v1";

function getCookie(name: string): string {
  if (typeof document === "undefined") {
    return "";
  }
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function normalizeValidationMessage(item: ValidationErrorItem): string {
  const field = Array.isArray(item.loc) ? String(item.loc[item.loc.length - 1] ?? "") : "";
  const raw = item.msg ?? "";

  if (field === "email") {
    return "Проверьте email: укажите корректный адрес почты.";
  }
  if (field === "password" || field === "new_password" || field === "current_password") {
    if (raw.toLowerCase().includes("at least 8")) {
      return "Пароль должен быть не короче 8 символов.";
    }
    return "Проверьте пароль: заполните поле корректно.";
  }
  if (field === "token") {
    return "Ссылка или токен больше не действуют. Запросите новую.";
  }
  return raw || "Проверьте правильность заполнения полей.";
}

function fallbackApiErrorMessage(status: number): string {
  if (status === 400) {
    return "Запрос не удалось обработать. Проверьте введенные данные.";
  }
  if (status === 401) {
    return "Неверный email или пароль.";
  }
  if (status === 403) {
    return "Доступ временно недоступен. Проверьте подтверждение email или права доступа.";
  }
  if (status === 404) {
    return "Нужный ресурс не найден.";
  }
  if (status === 409) {
    return "Такая запись уже существует.";
  }
  if (status === 422) {
    return "Проверьте правильность заполнения полей.";
  }
  if (status === 429) {
    return "Слишком много попыток. Подождите немного и попробуйте снова.";
  }
  if (status >= 500) {
    return "Сервис временно недоступен. Попробуйте чуть позже.";
  }
  return "Не удалось выполнить запрос. Попробуйте еще раз.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers ?? {});
  if (!headers.has("Content-Type") && init?.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCookie("finance_csrf");
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers,
    ...init,
  });

  if (!response.ok) {
    let message = fallbackApiErrorMessage(response.status);
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (typeof payload?.detail === "string" && payload.detail.trim()) {
        message = payload.detail;
      } else if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
        message = normalizeValidationMessage(payload.detail[0]);
      } else if (typeof payload?.message === "string" && payload.message.trim()) {
        message = payload.message;
      }
    } catch {
      // noop
    }
    throw new ApiError(response.status, message);
  }

  return response.json() as Promise<T>;
}

export function register(payload: { email: string; password: string }) {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: { email: string; password: string }) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function verifyEmail(payload: { token: string }) {
  return request<AuthResponse>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logout() {
  return request<{ message: string }>("/auth/logout", {
    method: "POST",
  });
}

export function getMe() {
  return request<AuthUser>("/auth/me");
}

export function changePassword(payload: { current_password: string; new_password: string }) {
  return request<{ message: string }>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function requestPasswordReset(payload: { email: string }) {
  return request<PasswordResetRequestResponse>("/auth/password-reset/request", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function confirmPasswordReset(payload: { token: string; new_password: string }) {
  return request<AuthResponse>("/auth/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getActiveSessions(limit = 8) {
  const search = new URLSearchParams();
  search.set("limit", String(limit));
  return request<{ sessions: UserSession[] }>(`/auth/sessions?${search.toString()}`);
}

export function revokeOtherSessions() {
  return request<{ revoked_count: number; message: string }>("/auth/sessions/revoke-others", {
    method: "POST",
  });
}

export function revokeSessionById(sessionId: number) {
  return request<{ revoked_count: number; message: string }>(`/auth/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export function getAccountPreferences() {
  return request<AccountPreferences>("/account/preferences");
}

export function updateAccountPreferences(payload: Partial<AccountPreferences>) {
  return request<AccountPreferences>("/account/preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAccountBackupInfo() {
  return request<AccountBackupInfo>("/account/backup");
}

export function saveAccountBackup() {
  return request<{ message: string; created_at: string; updated_at: string; checksum: string }>(
    "/account/backup/save",
    {
      method: "POST",
    },
  );
}

export function restoreAccountBackup() {
  return request<{ message: string }>("/account/backup/restore", {
    method: "POST",
  });
}

export function resetAllAccountData(payload: { confirm_text: string }) {
  return request<{ message: string }>("/account/reset-all", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function requestAccountDelete() {
  return request<{ message: string }>("/account/delete/request", {
    method: "POST",
  });
}

export function confirmAccountDelete(payload: { token: string }) {
  return request<{ message: string }>("/auth/account-delete/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAccountActivity(limit = 15) {
  const search = new URLSearchParams();
  search.set("limit", String(limit));
  return request<{ events: AccountActivityEvent[] }>(`/account/activity?${search.toString()}`);
}

export function getMyFamilies() {
  return request<{ families: FamilyItem[] }>("/families/me");
}

export function createFamily(payload: { name: string }) {
  return request<FamilyItem>("/families", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getFamilyMembers(familyId: number) {
  return request<{ members: FamilyMemberItem[] }>(`/families/${familyId}/members`);
}

export function getFamilyDashboard(familyId: number) {
  return request<FamilyDashboardResponse>(`/families/${familyId}/dashboard`);
}

export function getFamilyCapitalHistory(familyId: number) {
  return request<FamilyCapitalContributionListResponse>(`/families/${familyId}/capital-history`);
}

export function updateFamilyCapitalTarget(payload: {
  familyId: number;
  targetOwnerUserId: number | null;
  targetCapitalAccountId: number | null;
}) {
  return request<FamilyDashboardResponse["current_member_capital_target"]>(`/families/${payload.familyId}/capital-target`, {
    method: "PUT",
    body: JSON.stringify({
      target_owner_user_id: payload.targetOwnerUserId,
      target_capital_account_id: payload.targetCapitalAccountId,
    }),
  });
}

export function getFamilyTransactions(params: {
  familyId: number;
  ownerUserId?: number;
  limit?: number;
  offset?: number;
  period?: TransactionPeriod;
  includePlanned?: boolean;
}) {
  const search = new URLSearchParams();
  if (params.ownerUserId !== undefined && params.ownerUserId > 0) {
    search.set("owner_user_id", String(params.ownerUserId));
  }
  search.set("limit", String(params.limit ?? 80));
  search.set("offset", String(params.offset ?? 0));
  search.set("period", params.period ?? "all");
  search.set("include_planned", params.includePlanned ? "true" : "false");
  return request<FamilyTransactionListResponse>(`/families/${params.familyId}/transactions?${search.toString()}`);
}

export function getFamilyCategoryAudit(familyId: number) {
  return request<FamilyCategoryAuditResponse>(`/families/${familyId}/categories/audit`);
}

function familyCategoryBindingPayload(payload: FamilyCategoryBindingPreviewPayload) {
  return {
    semantic_key: payload.semanticKey,
    display_name: payload.displayName,
    category_names: payload.categoryNames,
    category_type: payload.categoryType,
  };
}

export function previewFamilyCategoryBinding(payload: FamilyCategoryBindingPreviewPayload) {
  return request<FamilyCategoryBindingPreviewResponse>(`/families/${payload.familyId}/categories/bindings/preview`, {
    method: "POST",
    body: JSON.stringify(familyCategoryBindingPayload(payload)),
  });
}

export function applyFamilyCategoryBinding(payload: FamilyCategoryBindingPreviewPayload) {
  return request<FamilyCategoryBindingApplyResponse>(`/families/${payload.familyId}/categories/bindings`, {
    method: "POST",
    body: JSON.stringify(familyCategoryBindingPayload(payload)),
  });
}

export function resolveFamilyCategoryAuditItem(payload: FamilyCategoryAuditResolutionPayload) {
  return request<{ message: string; family_id: number; code: string; group_key: string; action: "ignore" | "keep_personal" }>(
    `/families/${payload.familyId}/categories/audit/resolutions`,
    {
      method: "POST",
      body: JSON.stringify({
        code: payload.code,
        group_key: payload.groupKey,
        action: payload.action,
        category_names: payload.categoryNames,
        note: payload.note,
      }),
    },
  );
}

export function deleteFamilyCategoryAuditResolution(payload: FamilyCategoryAuditResolutionPayload) {
  return request<FamilyActionResponse>(`/families/${payload.familyId}/categories/audit/resolutions`, {
    method: "DELETE",
    body: JSON.stringify({
      code: payload.code,
      group_key: payload.groupKey,
      action: payload.action,
      category_names: payload.categoryNames,
      note: payload.note,
    }),
  });
}

export function createFamilyInvite(payload: { family_id: number; email: string; role: FamilyInviteRole }) {
  return request<{ message: string; family_id: number; email: string; role: FamilyInviteRole; expires_at: string; invite_token?: string }>(
    `/families/${payload.family_id}/invites`,
    {
      method: "POST",
      body: JSON.stringify({
        email: payload.email,
        role: payload.role,
      }),
    },
  );
}

export function acceptFamilyInvite(payload: { token: string }) {
  return request<{ message: string; family_id: number; family_name: string; role: FamilyRole }>("/families/invites/accept", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPendingFamilyInvites() {
  return request<{ invites: FamilyPendingInvite[] }>("/families/invites/pending");
}

export function acceptFamilyInviteById(inviteId: number) {
  return request<{ message: string; family_id: number; family_name: string; role: FamilyRole }>(`/families/invites/${inviteId}/accept`, {
    method: "POST",
  });
}

export function declineFamilyInviteById(inviteId: number) {
  return request<FamilyActionResponse>(`/families/invites/${inviteId}/decline`, {
    method: "POST",
  });
}

export function updateFamilyMemberRole(payload: { family_id: number; user_id: number; role: FamilyInviteRole }) {
  return request<FamilyActionResponse>(`/families/${payload.family_id}/members/${payload.user_id}/role`, {
    method: "PATCH",
    body: JSON.stringify({
      role: payload.role,
    }),
  });
}

export function removeFamilyMember(payload: { family_id: number; user_id: number }) {
  return request<FamilyActionResponse>(`/families/${payload.family_id}/members/${payload.user_id}`, {
    method: "DELETE",
  });
}

export function getDashboard() {
  return request<DashboardResponse>("/dashboard");
}

export function getTransactions(params?: {
  limit?: number;
  offset?: number;
  period?: TransactionPeriod;
  includePlanned?: boolean;
}) {
  const search = new URLSearchParams();
  search.set("limit", String(params?.limit ?? 20));
  search.set("offset", String(params?.offset ?? 0));
  search.set("period", params?.period ?? "all");
  search.set("include_planned", params?.includePlanned === false ? "false" : "true");
  return request<Transaction[]>(`/transactions?${search.toString()}`);
}

export function getTransactionsPage(params?: {
  limit?: number;
  offset?: number;
  period?: TransactionPeriod;
  includePlanned?: boolean;
}) {
  const search = new URLSearchParams();
  search.set("limit", String(params?.limit ?? 20));
  search.set("offset", String(params?.offset ?? 0));
  search.set("period", params?.period ?? "all");
  search.set("include_planned", params?.includePlanned === false ? "false" : "true");
  return request<TransactionPage>(`/transactions/page?${search.toString()}`);
}

export function getCategorySummary(params?: {
  type?: "income" | "expense";
  period?: SummaryPeriod;
  startDate?: string;
  endDate?: string;
  familyId?: number;
}) {
  const search = new URLSearchParams();
  search.set("type", params?.type ?? "expense");
  search.set("period", params?.period ?? "month");
  if (params?.startDate) {
    search.set("start_date", params.startDate);
  }
  if (params?.endDate) {
    search.set("end_date", params.endDate);
  }
  if (params?.familyId !== undefined) {
    search.set("family_id", String(params.familyId));
  }
  return request<CategorySummaryResponse>(`/reports/category-summary?${search.toString()}`);
}

export function getCategories() {
  return request<Category[]>("/categories");
}

export function createCategory(payload: CategoryCreatePayload) {
  return request<Category>("/categories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCategory(categoryId: number, payload: CategoryUpdatePayload) {
  return request<Category>(`/categories/${categoryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCategory(categoryId: number) {
  return request<{ message: string }>(`/categories/${categoryId}`, {
    method: "DELETE",
  });
}

export function getBudgets() {
  return request<Budget[]>("/budgets");
}

export function getBudgetStatus(params?: { familyId?: number }) {
  const search = new URLSearchParams();
  if (params?.familyId !== undefined) {
    search.set("family_id", String(params.familyId));
  }
  const suffix = search.size ? `?${search.toString()}` : "";
  return request<BudgetStatusItem[]>(`/budgets/status${suffix}`);
}

export function createBudget(payload: BudgetCreatePayload) {
  return request<Budget>("/budgets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateBudget(budgetId: number, payload: BudgetUpdatePayload) {
  return request<Budget>(`/budgets/${budgetId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteBudget(budgetId: number) {
  return request<{ message: string }>(`/budgets/${budgetId}`, {
    method: "DELETE",
  });
}

export function getAccounts() {
  return request<Account[]>("/accounts");
}

export function createAccount(payload: AccountCreatePayload) {
  return request<Account>("/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAccount(accountId: number, payload: AccountUpdatePayload) {
  return request<Account>(`/accounts/${accountId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAccount(accountId: number) {
  return request<{ message: string }>(`/accounts/${accountId}`, {
    method: "DELETE",
  });
}

export function getTransfers(params?: { accountId?: number; limit?: number }) {
  const search = new URLSearchParams();
  search.set("limit", String(params?.limit ?? 50));
  if (params?.accountId !== undefined) {
    search.set("account_id", String(params.accountId));
  }
  return request<Transfer[]>(`/transfers?${search.toString()}`);
}

export function createTransfer(payload: TransferCreatePayload) {
  return request<Transfer>("/transfers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSettings() {
  return request<Settings>("/settings");
}

export function updateSettings(payload: SettingsUpdatePayload) {
  return request<Settings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getRecurringTemplates(params?: { type?: "income" | "expense" }) {
  const search = new URLSearchParams();
  if (params?.type) {
    search.set("type", params.type);
  }
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return request<RecurringTemplate[]>(`/recurring-templates${suffix}`);
}

export function createRecurringTemplate(payload: RecurringTemplateCreatePayload) {
  return request<RecurringTemplate>("/recurring-templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRecurringTemplate(templateId: number, payload: RecurringTemplateUpdatePayload) {
  return request<RecurringTemplate>(`/recurring-templates/${templateId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteRecurringTemplate(templateId: number) {
  return request<{ message: string }>(`/recurring-templates/${templateId}`, {
    method: "DELETE",
  });
}

export function getDuePlannedTransactions() {
  return request<DuePlannedTransaction[]>("/recurring-templates/due");
}

export function executeDuePlannedTransactions() {
  return request<{ executed_count: number; message: string }>("/recurring-templates/execute-due", {
    method: "POST",
  });
}

export function createTransaction(payload: TransactionCreatePayload) {
  return request<{ id: number; message: string; transaction: Transaction }>("/transactions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteTransaction(transactionId: number) {
  return request<{ message: string }>(`/transactions/${transactionId}`, {
    method: "DELETE",
  });
}

export function updateTransaction(transactionId: number, payload: TransactionUpdatePayload) {
  return request<Transaction>(`/transactions/${transactionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getReconciliationSummary() {
  return request<ReconciliationSummary>("/reconciliation");
}

export function createReconciliationSource(payload: { name: string; balance: number }) {
  return request<ReconciliationSource>("/reconciliation/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateReconciliationSource(sourceId: number, payload: { name?: string; balance?: number }) {
  return request<ReconciliationSource>(`/reconciliation/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteReconciliationSource(sourceId: number) {
  return request<{ message: string }>(`/reconciliation/sources/${sourceId}`, {
    method: "DELETE",
  });
}

export function applyReconciliation() {
  return request<ReconciliationApplyResponse>("/reconciliation/apply", {
    method: "POST",
  });
}
