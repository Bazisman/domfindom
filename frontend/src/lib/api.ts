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
};

export type TransactionType = "income" | "expense";
export type TransactionPeriod = "all" | "month" | "last_month" | "year";

export type TransactionCreatePayload = {
  type: TransactionType;
  category_id?: number;
  category_name?: string;
  amount: number;
  comment: string;
  date: string;
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

export type AccountType = "main" | "capital";

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
};

export type AccountCreatePayload = {
  type?: "capital";
  name: string;
  balance?: number;
  icon?: string;
  color?: string;
};

export type AccountUpdatePayload = {
  name?: string;
  balance?: number;
  icon?: string;
  color?: string;
  is_default?: boolean;
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
  amount: number;
  date?: string;
  comment?: string;
};

export type Settings = {
  auto_capital_enabled: boolean;
  auto_capital_percent: number;
  default_capital_account_id: number | null;
};

export type SettingsUpdatePayload = {
  auto_capital_enabled?: boolean;
  auto_capital_percent?: number;
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
  months_ahead?: number;
  working_days_only?: boolean;
  is_active?: boolean;
};

export type AuthUser = {
  id: number;
  email: string;
  is_active: boolean;
};

export type AuthResponse = {
  user: AuthUser;
  message: string;
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
    let message = `API error ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        message = payload.detail;
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

export function updateAccountPreferences(payload: AccountPreferences) {
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

export function getAccountActivity(limit = 15) {
  const search = new URLSearchParams();
  search.set("limit", String(limit));
  return request<{ events: AccountActivityEvent[] }>(`/account/activity?${search.toString()}`);
}

export function getDashboard() {
  return request<DashboardResponse>("/dashboard");
}

export function getTransactions(params?: {
  limit?: number;
  offset?: number;
  period?: TransactionPeriod;
}) {
  const search = new URLSearchParams();
  search.set("limit", String(params?.limit ?? 20));
  search.set("offset", String(params?.offset ?? 0));
  search.set("period", params?.period ?? "all");
  return request<Transaction[]>(`/transactions?${search.toString()}`);
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

export function getBudgetStatus() {
  return request<BudgetStatusItem[]>("/budgets/status");
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
