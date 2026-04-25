import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  applyFamilyCategoryBinding,
  createFamily,
  createFamilyInvite,
  deleteFamilyCategoryAuditResolution,
  getAccounts,
  getFamilyCategoryAudit,
  getFamilyDashboard,
  getFamilyMembers,
  getMe,
  getMyFamilies,
  previewFamilyCategoryBinding,
  removeFamilyMember,
  resolveFamilyCategoryAuditItem,
  updateAccount,
  updateFamilyMemberRole,
  type FamilyCategoryAuditResponse,
  type FamilyCategoryBindingPreviewPayload,
  type FamilyCategoryBindingPreviewResponse,
  type FamilyCategoryAuditSeverity,
} from "../lib/api";
import { categoryTypeLabel } from "../lib/labels";

type FamilyBusyAction = "" | "create" | "invite" | "member_update" | "member_remove" | "capital_publish";
type CategoryBindingPayloadWithoutFamily = Omit<FamilyCategoryBindingPreviewPayload, "familyId">;
type CategoryBindingPreviewRequest = FamilyCategoryBindingPreviewPayload & { previewKey?: string };
type CategoryAuditFinding = FamilyCategoryAuditResponse["findings"][number];
type CategoryAuditGroup = FamilyCategoryAuditResponse["category_groups"][number];
type CategoryAuditResolution = FamilyCategoryAuditResponse["resolutions"][number];
type CategoryAuditResolutionAction = "ignore" | "keep_personal";

function roleLabel(role: "owner" | "member" | "viewer"): string {
  if (role === "owner") {
    return "Владелец";
  }
  if (role === "viewer") {
    return "Только просмотр";
  }
  return "Помощник";
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function auditSeverityLabel(severity: FamilyCategoryAuditSeverity): string {
  if (severity === "critical") {
    return "Критично";
  }
  if (severity === "warning") {
    return "Внимание";
  }
  return "Инфо";
}

function formatAuditDate(value: string | undefined): string {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function customSemanticKeyForAuditItem(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return `custom.${hash.toString(36)}`;
}

function normalizeAuditCategoryName(value: string): string {
  return value.trim().toLocaleLowerCase("ru-RU");
}

function auditFindingIgnoreLabel(finding: CategoryAuditFinding): string {
  if (finding.code === "semantic_duplicate_candidate") {
    return "Не связывать";
  }
  if (finding.code === "category_type_conflict") {
    return "Оставить раздельно";
  }
  return "Не проверять";
}

function auditFindingDisplayTitle(finding: CategoryAuditFinding): string {
  if (finding.code === "category_type_conflict") {
    return "Один смысл, разные типы";
  }
  if (finding.code === "semantic_duplicate_candidate") {
    return "Можно связать категории";
  }
  if (finding.code === "missing_member_category") {
    return "Категория есть не у всех";
  }
  return finding.title;
}

function auditFindingDisplayText(finding: CategoryAuditFinding): string {
  const names = finding.category_names.join(", ");
  const displayName = finding.display_name || finding.category_names[0] || "категория";
  if (finding.code === "category_type_conflict") {
    return `"${names}" используются по-разному. Выберите: считать их одной семейной категорией или оставить отдельно.`;
  }
  if (finding.code === "semantic_duplicate_candidate") {
    return `"${names}" похожи на одну семейную категорию "${displayName}". Можно связать их для семейных отчетов или оставить как разные категории.`;
  }
  if (finding.code === "missing_member_category") {
    return `"${displayName}" есть только у части семьи. Если это личная категория, ее можно оставить без семейной связи.`;
  }
  return finding.description;
}

export function FamilyPage() {
  const queryClient = useQueryClient();
  const [busyAction, setBusyAction] = useState<FamilyBusyAction>("");
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [familyName, setFamilyName] = useState("");
  const [selectedFamilyId, setSelectedFamilyId] = useState<number | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "viewer">("member");
  const [categoryBindingPreview, setCategoryBindingPreview] = useState<FamilyCategoryBindingPreviewResponse | null>(null);
  const [categoryBindingPayload, setCategoryBindingPayload] = useState<CategoryBindingPayloadWithoutFamily | null>(null);
  const [activeCategoryPreviewKey, setActiveCategoryPreviewKey] = useState<string | null>(null);
  const [pendingResolutionKey, setPendingResolutionKey] = useState<string | null>(null);
  const [pendingResolutionFinding, setPendingResolutionFinding] = useState<CategoryAuditFinding | null>(null);
  const [pendingResolutionAction, setPendingResolutionAction] = useState<CategoryAuditResolutionAction>("ignore");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: getAccounts,
    retry: false,
  });

  const fallbackFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
  const familyId = selectedFamilyId ?? fallbackFamilyId;

  const selectedFamily = useMemo(
    () => (familiesQuery.data?.families ?? []).find((item) => item.id === familyId) ?? null,
    [familiesQuery.data?.families, familyId],
  );
  const canManageFamilyMembers = selectedFamily?.role === "owner";

  const familyMembersQuery = useQuery({
    queryKey: ["families", familyId, "members"],
    queryFn: () => getFamilyMembers(familyId as number),
    enabled: familyId !== null,
    retry: false,
  });

  const familyDashboardQuery = useQuery({
    queryKey: ["families", familyId, "dashboard"],
    queryFn: () => getFamilyDashboard(familyId as number),
    enabled: familyId !== null,
    retry: false,
  });

  const familyCategoryAuditQuery = useQuery({
    queryKey: ["families", familyId, "categories", "audit"],
    queryFn: () => getFamilyCategoryAudit(familyId as number),
    enabled: familyId !== null,
    retry: false,
  });

  const capitalAccounts = useMemo(
    () => (accountsQuery.data ?? []).filter((item) => item.type === "capital" && item.is_active),
    [accountsQuery.data],
  );

  const publishedAccountKeys = useMemo(
    () =>
      new Set(
        (familyDashboardQuery.data?.capital_accounts ?? [])
          .filter((item) => item.owner_user_id === meQuery.data?.id)
          .map((item) => `${item.owner_user_id}:${item.capital_account_id}`),
      ),
    [familyDashboardQuery.data?.capital_accounts, meQuery.data?.id],
  );
  const categoryAudit = familyCategoryAuditQuery.data;
  const auditFindings = categoryAudit?.findings ?? [];
  const duplicateCandidateCount = auditFindings.filter((finding) => finding.code === "semantic_duplicate_candidate").length;
  const typeConflictCount = auditFindings.filter((finding) => finding.code === "category_type_conflict").length;
  const actionableFindingCount = auditFindings.filter((finding) => finding.severity !== "info").length;
  const syncReadyGroups = (categoryAudit?.category_groups ?? []).filter((item) => item.status !== "unlinked").slice(0, 6);

  useEffect(() => {
    if (selectedFamilyId !== null) {
      const exists = (familiesQuery.data?.families ?? []).some((item) => item.id === selectedFamilyId);
      if (!exists) {
        setSelectedFamilyId(fallbackFamilyId);
      }
    }
  }, [familiesQuery.data?.families, selectedFamilyId, fallbackFamilyId]);

  useEffect(() => {
    setCategoryBindingPreview(null);
    setCategoryBindingPayload(null);
    setActiveCategoryPreviewKey(null);
    setPendingResolutionKey(null);
    setPendingResolutionFinding(null);
  }, [familyId]);

  const createFamilyMutation = useMutation({
    mutationFn: createFamily,
    onSuccess: async (created) => {
      setFamilyName("");
      setSelectedFamilyId(created.id);
      setMessage(`Семейный бюджет "${created.name}" создан.`);
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["families", "me"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
    },
  });

  const inviteMutation = useMutation({
    mutationFn: createFamilyInvite,
    onSuccess: async (response) => {
      setInviteEmail("");
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
    },
  });

  const updateMemberMutation = useMutation({
    mutationFn: updateFamilyMemberRole,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
      setBusyUserId(null);
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: removeFamilyMember,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", familyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
      setBusyUserId(null);
    },
  });

  const publishCapitalMutation = useMutation({
    mutationFn: ({ accountId, familyVisible, familyDefaultTarget }: { accountId: number; familyVisible: boolean; familyDefaultTarget?: boolean }) =>
      updateAccount(accountId, {
        family_visible: familyVisible,
        family_default_target: familyDefaultTarget,
      }),
    onSuccess: async () => {
      setMessage("Настройки семейного капитала обновлены.");
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["families", familyId, "dashboard"] }),
      ]);
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
    },
  });

  const categoryBindingPreviewMutation = useMutation({
    mutationFn: (payload: CategoryBindingPreviewRequest) => previewFamilyCategoryBinding(payload),
    onSuccess: (response, variables) => {
      setCategoryBindingPreview(response);
      setCategoryBindingPayload({
        semanticKey: variables.semanticKey,
        displayName: variables.displayName,
        categoryNames: variables.categoryNames,
        categoryType: variables.categoryType,
      });
      setActiveCategoryPreviewKey(variables.previewKey ?? null);
      setMessage("");
      setError("");
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
  });

  const categoryBindingApplyMutation = useMutation({
    mutationFn: applyFamilyCategoryBinding,
    onSuccess: async (response) => {
      setCategoryBindingPreview(response.preview);
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await queryClient.invalidateQueries({ queryKey: ["families", familyId, "categories", "audit"] });
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
  });

  const categoryAuditResolutionMutation = useMutation({
    mutationFn: resolveFamilyCategoryAuditItem,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await queryClient.invalidateQueries({ queryKey: ["families", familyId, "categories", "audit"] });
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
  });

  const deleteCategoryAuditResolutionMutation = useMutation({
    mutationFn: deleteFamilyCategoryAuditResolution,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (familyId !== null) {
        await queryClient.invalidateQueries({ queryKey: ["families", familyId, "categories", "audit"] });
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
  });

  function onCreateFamily() {
    const trimmed = familyName.trim();
    if (!trimmed) {
      setError("Введите название семьи.");
      setMessage("");
      return;
    }
    setBusyAction("create");
    createFamilyMutation.mutate({ name: trimmed });
  }

  function onInviteToFamily() {
    if (familyId === null) {
      setError("Сначала выберите семейный бюджет.");
      setMessage("");
      return;
    }
    const email = inviteEmail.trim().toLowerCase();
    if (!email) {
      setError("Введите email участника.");
      setMessage("");
      return;
    }
    setBusyAction("invite");
    inviteMutation.mutate({ family_id: familyId, email, role: inviteRole });
  }

  function onUpdateMemberRole(memberUserId: number, role: "member" | "viewer") {
    if (familyId === null) {
      return;
    }
    setBusyAction("member_update");
    setBusyUserId(memberUserId);
    updateMemberMutation.mutate({ family_id: familyId, user_id: memberUserId, role });
  }

  function onRemoveMember(memberUserId: number) {
    if (familyId === null) {
      return;
    }
    setBusyAction("member_remove");
    setBusyUserId(memberUserId);
    removeMemberMutation.mutate({ family_id: familyId, user_id: memberUserId });
  }

  function toggleFamilyCapital(accountId: number, familyVisible: boolean) {
    setBusyAction("capital_publish");
    publishCapitalMutation.mutate({
      accountId,
      familyVisible,
      familyDefaultTarget: familyVisible ? undefined : false,
    });
  }

  function makeDefaultFamilyCapital(accountId: number) {
    setBusyAction("capital_publish");
    publishCapitalMutation.mutate({ accountId, familyVisible: true, familyDefaultTarget: true });
  }

  function previewCategoryBinding(payload: CategoryBindingPayloadWithoutFamily, previewKey: string) {
    if (familyId === null) {
      return;
    }
    setActiveCategoryPreviewKey(previewKey);
    categoryBindingPreviewMutation.mutate({
      familyId,
      ...payload,
      previewKey,
    });
  }

  function applyCategoryBinding() {
    if (familyId === null || categoryBindingPayload === null) {
      return;
    }
    categoryBindingApplyMutation.mutate({
      familyId,
      ...categoryBindingPayload,
    });
  }

  function findAuditGroupForFinding(finding: CategoryAuditFinding): CategoryAuditGroup | null {
    const groups = categoryAudit?.category_groups ?? [];
    if (finding.group_key) {
      const group = groups.find((item) => item.group_key === finding.group_key);
      if (group) {
        return group;
      }
    }
    const findingNames = new Set(finding.category_names.map(normalizeAuditCategoryName).filter(Boolean));
    if (!findingNames.size) {
      return null;
    }
    return groups.find((group) => group.category_names.some((name) => findingNames.has(normalizeAuditCategoryName(name)))) ?? null;
  }

  function previewAuditFindingBinding(finding: CategoryAuditFinding, previewKey: string, categoryType?: "income" | "expense" | "both") {
    const group = findAuditGroupForFinding(finding);
    const categoryNames = group?.category_names.length ? group.category_names : finding.category_names;
    if (!categoryNames.length) {
      setError("Для предпросмотра не нашлось категорий.");
      setMessage("");
      return;
    }
    previewCategoryBinding(
      {
        semanticKey:
          finding.semantic_key ??
          group?.semantic_key ??
          customSemanticKeyForAuditItem(`${finding.code}|${finding.group_key ?? ""}|${categoryNames.join("|")}`),
        displayName: finding.display_name ?? group?.display_name ?? categoryNames[0],
        categoryNames,
        categoryType,
      },
      previewKey,
    );
  }

  function previewAuditGroupAsBoth(group: CategoryAuditGroup, previewKey: string) {
    previewCategoryBinding(
      {
        semanticKey: group.semantic_key ?? customSemanticKeyForAuditItem(`${group.group_key}|${group.category_names.join("|")}`),
        displayName: group.display_name,
        categoryNames: group.category_names,
        categoryType: "both",
      },
      previewKey,
    );
  }

  function resolveAuditFinding(finding: CategoryAuditFinding, action: CategoryAuditResolutionAction) {
    if (familyId === null) {
      return;
    }
    const group = findAuditGroupForFinding(finding);
    const groupKey = finding.group_key ?? group?.group_key;
    if (!groupKey) {
      setError("У этого замечания пока нет безопасного ключа для решения.");
      setMessage("");
      return;
    }
    categoryAuditResolutionMutation.mutate({
      familyId,
      code: finding.code,
      groupKey,
      action,
      categoryNames: finding.category_names,
      note: action === "keep_personal" ? "Оставлено личной категорией в мастере аудита." : "Скрыто владельцем семьи в мастере аудита.",
    });
    setPendingResolutionKey(null);
    setPendingResolutionFinding(null);
  }

  function openResolutionConfirm(finding: CategoryAuditFinding, previewKey: string, action: CategoryAuditResolutionAction) {
    setCategoryBindingPreview(null);
    setActiveCategoryPreviewKey(null);
    setPendingResolutionKey(previewKey);
    setPendingResolutionFinding(finding);
    setPendingResolutionAction(action);
  }

  function undoAuditResolution(resolution: CategoryAuditResolution) {
    if (familyId === null) {
      return;
    }
    deleteCategoryAuditResolutionMutation.mutate({
      familyId,
      code: resolution.code,
      groupKey: resolution.group_key,
      action: resolution.action,
      categoryNames: resolution.category_names,
      note: resolution.note,
    });
  }

  return (
    <main className="grid family-page">
      <section className="panel panel-form panel-wide">
        <div className="panel-header">
          <h2>Семья</h2>
          <span>Управление семейным бюджетом и участниками</span>
        </div>

        {(familiesQuery.data?.families ?? []).length === 0 ? (
          <form
            className="transaction-form"
            onSubmit={(event) => {
              event.preventDefault();
              onCreateFamily();
            }}
          >
            <label className="field">
              <span>Название семьи</span>
              <input
                disabled={busyAction !== ""}
                maxLength={120}
                onChange={(event) => setFamilyName(event.target.value)}
                placeholder="Например, Семья Петровых"
                value={familyName}
              />
            </label>
            <button className="primary-button" disabled={busyAction !== ""} type="submit">
              {busyAction === "create" ? "Создаем..." : "Создать семейный бюджет"}
            </button>
          </form>
        ) : (
          <div className="transaction-form">
            <label className="field">
              <span>Выбранная семья</span>
              <select
                disabled={busyAction !== ""}
                onChange={(event) => setSelectedFamilyId(Number(event.target.value))}
                value={familyId ?? ""}
              >
                {(familiesQuery.data?.families ?? []).map((family) => (
                  <option key={family.id} value={family.id}>
                    {family.name} ({roleLabel(family.role)})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Email участника</span>
              <input
                autoComplete="off"
                disabled={busyAction !== "" || !canManageFamilyMembers}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="user@example.com"
                value={inviteEmail}
              />
            </label>
            <label className="field">
              <span>Роль</span>
              <select
                disabled={busyAction !== "" || !canManageFamilyMembers}
                onChange={(event) => setInviteRole(event.target.value as "member" | "viewer")}
                value={inviteRole}
              >
                <option value="member">Помощник</option>
                <option value="viewer">Только просмотр</option>
              </select>
            </label>
            <button className="primary-button" disabled={busyAction !== "" || !canManageFamilyMembers} onClick={onInviteToFamily} type="button">
              {busyAction === "invite" ? "Отправляем..." : "Пригласить в семью"}
            </button>
          </div>
        )}

        {message ? <p className="form-status form-status-success">{message}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
      </section>

      {familyId !== null ? (
        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Сводка семьи</h3>
            <span>{familyDashboardQuery.data?.family_name ?? "Семейный бюджет"}</span>
          </div>

          <div className="family-summary-grid">
            <article className="list-item">
              <div>
                <strong>Текущий семейный баланс</strong>
                <p>{formatMoney(familyDashboardQuery.data?.balance.main_balance ?? 0)}</p>
              </div>
            </article>
            <article className="list-item">
              <div>
                <strong>Семейный капитал</strong>
                <p>{formatMoney(familyDashboardQuery.data?.balance.capital_balance ?? 0)}</p>
              </div>
            </article>
            <article className="list-item">
              <div>
                <strong>Доход за месяц</strong>
                <p className="money plus">{formatMoney(familyDashboardQuery.data?.balance.income ?? 0)}</p>
              </div>
            </article>
            <article className="list-item">
              <div>
                <strong>Расход за месяц</strong>
                <p className="money minus">{formatMoney(familyDashboardQuery.data?.balance.expense ?? 0)}</p>
              </div>
            </article>
          </div>
        </section>
      ) : null}

      {familyId !== null ? (
        <section className="panel panel-wide family-category-audit-panel">
          <div className="panel-header">
            <div>
              <h3>Аудит категорий</h3>
              <span>
                Проверка без изменений данных
                {categoryAudit?.generated_at ? ` • ${formatAuditDate(categoryAudit.generated_at)}` : ""}
              </span>
            </div>
            <button
              className="ghost-button"
              disabled={familyCategoryAuditQuery.isFetching}
              onClick={() => void familyCategoryAuditQuery.refetch()}
              type="button"
            >
              {familyCategoryAuditQuery.isFetching ? "Проверяем..." : "Обновить"}
            </button>
          </div>

          {familyCategoryAuditQuery.isError ? (
            <p className="form-error">Не удалось выполнить аудит категорий.</p>
          ) : null}

          <div className="category-audit-focus">
            <strong>
              {actionableFindingCount > 0
                ? `Нужно разобрать ${actionableFindingCount} ${actionableFindingCount === 1 ? "решение" : "решений"}`
                : "Критичных решений сейчас нет"}
            </strong>
            <p>
              {actionableFindingCount > 0
                ? "Начните с одинаковых смыслов и разных типов. Справочные категории, которые есть не у всех, можно оставить личными."
                : "Остальные пункты ниже помогают подготовить семейные категории без переименования личной истории."}
            </p>
          </div>

          <div className="family-summary-grid">
            <article className="list-item audit-summary-card">
              <div>
                <strong>Нужно решить</strong>
                <p>{actionableFindingCount}</p>
              </div>
            </article>
            <article className="list-item audit-summary-card">
              <div>
                <strong>Критичных</strong>
                <p className={categoryAudit?.summary.critical_count ? "money minus" : ""}>
                  {categoryAudit?.summary.critical_count ?? 0}
                </p>
              </div>
            </article>
            <article className="list-item audit-summary-card">
              <div>
                <strong>Можно связать</strong>
                <p>{duplicateCandidateCount}</p>
              </div>
            </article>
            <article className="list-item audit-summary-card">
              <div>
                <strong>Разные типы</strong>
                <p>{typeConflictCount}</p>
              </div>
            </article>
            <article className="list-item audit-summary-card">
              <div>
                <strong>Только у части семьи</strong>
                <p>{categoryAudit?.summary.missing_member_categories_count ?? 0}</p>
              </div>
            </article>
            <article className="list-item audit-summary-card">
              <div>
                <strong>Категорий в истории</strong>
                <p>{categoryAudit?.summary.transaction_categories_count ?? 0}</p>
              </div>
            </article>
          </div>

          <div className="category-audit-columns">
            <div className="list category-audit-list">
              <div className="category-audit-subheader">
                <strong>Очередь решений</strong>
                <span>{auditFindings.length}</span>
              </div>
              {auditFindings.slice(0, 8).map((finding, index) => {
                const previewKey = `finding:${finding.code}:${finding.group_key ?? index}`;
                const showPreview = activeCategoryPreviewKey === previewKey && categoryBindingPreview !== null;
                const showResolutionConfirm = pendingResolutionKey === previewKey && pendingResolutionFinding !== null;
                return (
                  <article className="list-item category-audit-finding" key={`${finding.code}-${index}`}>
                    <div>
                      <div className="transaction-title-row">
                        <strong>{auditFindingDisplayTitle(finding)}</strong>
                        <span className={`audit-severity-chip audit-severity-${finding.severity}`}>
                          {auditSeverityLabel(finding.severity)}
                        </span>
                      </div>
                      <p>{auditFindingDisplayText(finding)}</p>
                    </div>
                    <div className="family-page-actions category-audit-tags">
                      {finding.category_names.slice(0, 3).map((name) => (
                        <span className="audit-category-chip" key={name}>
                          {name}
                        </span>
                      ))}
                      {finding.code === "semantic_duplicate_candidate" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryBindingPreviewMutation.isPending}
                          onClick={() => previewAuditFindingBinding(finding, previewKey)}
                          type="button"
                        >
                          Связать
                        </button>
                      ) : null}
                      {finding.code === "category_type_conflict" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryBindingPreviewMutation.isPending}
                          onClick={() => previewAuditFindingBinding(finding, previewKey, "both")}
                          type="button"
                        >
                          Это одна категория
                        </button>
                      ) : null}
                      {finding.code === "missing_member_category" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryAuditResolutionMutation.isPending}
                          onClick={() => openResolutionConfirm(finding, previewKey, "keep_personal")}
                          type="button"
                        >
                          Оставить личной
                        </button>
                      ) : null}
                      {finding.group_key && finding.code !== "missing_member_category" && finding.severity !== "critical" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryAuditResolutionMutation.isPending}
                          onClick={() => openResolutionConfirm(finding, previewKey, "ignore")}
                          type="button"
                        >
                          {auditFindingIgnoreLabel(finding)}
                        </button>
                      ) : null}
                    </div>
                    {showResolutionConfirm ? (
                      <div className="category-binding-preview category-binding-preview-inline category-resolution-confirm">
                        <div className="category-audit-subheader">
                          <div>
                            <strong>
                              {pendingResolutionAction === "keep_personal" ? "Оставить личной" : "Не связывать категории"}
                            </strong>
                            <p>
                              {pendingResolutionAction === "keep_personal"
                                ? "Эта категория останется личной и не будет участвовать в семейной синхронизации."
                                : "Эти категории останутся раздельными. Подсказка исчезнет из аудита, но решение можно будет отменить ниже."}
                            </p>
                          </div>
                        </div>
                        <div className="family-page-actions category-binding-actions">
                          <button
                            className="ghost-button"
                            onClick={() => {
                              setPendingResolutionKey(null);
                              setPendingResolutionFinding(null);
                            }}
                            type="button"
                          >
                            Вернуться
                          </button>
                          <button
                            className="primary-button"
                            disabled={categoryAuditResolutionMutation.isPending || !canManageFamilyMembers}
                            onClick={() => resolveAuditFinding(pendingResolutionFinding, pendingResolutionAction)}
                            type="button"
                          >
                            {categoryAuditResolutionMutation.isPending ? "Сохраняем..." : "Да, оставить так"}
                          </button>
                        </div>
                      </div>
                    ) : null}
                    {showPreview ? (
                      <div className="category-binding-preview category-binding-preview-inline">
                        <div className="category-audit-subheader">
                          <div>
                            <strong>Шаг 2. Подтвердить семейную связь</strong>
                            <p>Вы выбрали: {categoryBindingPreview.display_name} будет одной семейной категорией.</p>
                          </div>
                          <span>{categoryBindingPreview.message}</span>
                        </div>
                        <div className="family-summary-grid">
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>Новых связей</strong>
                              <p>{categoryBindingPreview.new_binding_count}</p>
                            </div>
                          </article>
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>Тип связи</strong>
                              <p>{categoryTypeLabel(categoryBindingPreview.type)}</p>
                            </div>
                          </article>
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>История</strong>
                              <p>{categoryBindingPreview.affected_transaction_count}</p>
                            </div>
                          </article>
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>Бюджетов</strong>
                              <p>{categoryBindingPreview.affected_budget_count}</p>
                            </div>
                          </article>
                        </div>
                        <div className="list category-audit-list">
                          {categoryBindingPreview.candidates.map((candidate) => (
                            <article className="list-item category-audit-group" key={`${candidate.user_id}-${candidate.local_category_id}`}>
                              <div>
                                <strong>{candidate.local_category_name}</strong>
                                <p>{candidate.owner_name}</p>
                                <p className="muted">
                                  История: {candidate.transaction_count}
                                  {candidate.planned_transaction_count > 0 ? `, плановых: ${candidate.planned_transaction_count}` : ""}, бюджетов: {candidate.budget_count},
                                  шаблонов: {candidate.recurring_count}
                                </p>
                              </div>
                              <div className="family-page-actions category-audit-tags">
                                <span className="audit-category-chip">{categoryTypeLabel(candidate.local_category_type)}</span>
                                {candidate.already_bound ? <span className="audit-severity-chip audit-severity-info">Уже связано</span> : null}
                              </div>
                            </article>
                          ))}
                        </div>
                        <div className="family-page-actions category-binding-actions">
                          <button
                            className="ghost-button"
                            onClick={() => {
                              setCategoryBindingPreview(null);
                              setActiveCategoryPreviewKey(null);
                            }}
                            type="button"
                          >
                            Вернуться к решению
                          </button>
                          <button
                            className="primary-button"
                            disabled={!categoryBindingPreview.can_apply || categoryBindingApplyMutation.isPending || !canManageFamilyMembers}
                            onClick={applyCategoryBinding}
                            type="button"
                          >
                            {categoryBindingApplyMutation.isPending ? "Подтверждаем..." : "Да, связать категории"}
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
              {!familyCategoryAuditQuery.isLoading && !(categoryAudit?.findings ?? []).length ? (
                <p className="muted">Аудит не нашел проблем. Категории выглядят аккуратно.</p>
              ) : null}
            </div>

            <div className="list category-audit-list">
              <div className="category-audit-subheader">
                <strong>Что уже распознано по смыслу</strong>
                <span>{syncReadyGroups.length}</span>
              </div>
              {syncReadyGroups.map((group) => {
                const previewKey = `group:${group.group_key}`;
                const showPreview = activeCategoryPreviewKey === previewKey && categoryBindingPreview !== null;
                return (
                  <article className="list-item category-audit-group" key={group.group_key}>
                    <div>
                      <strong>{group.display_name}</strong>
                      <p>{group.category_names.join(", ")}</p>
                      <p className="muted">{group.owner_names.join(", ")}</p>
                    </div>
                    <div className="family-page-actions category-audit-tags">
                      <span
                        className={`audit-severity-chip ${
                          group.status === "conflict" ? "audit-severity-warning" : group.status === "confirmed" ? "audit-severity-info" : "audit-severity-info"
                        }`}
                      >
                        {group.status === "conflict" ? "Конфликт" : group.status === "confirmed" ? "Связано" : "Кандидат"}
                      </span>
                      {group.confirmed_bindings_count > 0 ? <span className="audit-category-chip">Связей: {group.confirmed_bindings_count}</span> : null}
                      {group.budget_count > 0 ? <span className="audit-category-chip">Бюджеты: {group.budget_count}</span> : null}
                      {group.recurring_count > 0 ? <span className="audit-category-chip">Шаблоны: {group.recurring_count}</span> : null}
                      {group.status === "conflict" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryBindingPreviewMutation.isPending}
                          onClick={() => previewAuditGroupAsBoth(group, previewKey)}
                          type="button"
                        >
                          Доход и расход
                        </button>
                      ) : null}
                      {group.semantic_key && group.status !== "conflict" && group.status !== "confirmed" ? (
                        <button
                          className="ghost-button"
                          disabled={!canManageFamilyMembers || categoryBindingPreviewMutation.isPending}
                          onClick={() =>
                            previewCategoryBinding(
                              {
                                semanticKey: group.semantic_key as string,
                                displayName: group.display_name,
                                categoryNames: group.category_names,
                              },
                              previewKey,
                            )
                          }
                          type="button"
                        >
                          Проверить связь
                        </button>
                      ) : null}
                    </div>
                    {showPreview ? (
                      <div className="category-binding-preview category-binding-preview-inline">
                        <div className="category-audit-subheader">
                          <div>
                            <strong>Подтвердить семейную связь</strong>
                            <p>{categoryBindingPreview.display_name} станет общей смысловой категорией для семьи.</p>
                          </div>
                          <span>{categoryBindingPreview.message}</span>
                        </div>
                        <div className="family-summary-grid">
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>Новых связей</strong>
                              <p>{categoryBindingPreview.new_binding_count}</p>
                            </div>
                          </article>
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>Тип связи</strong>
                              <p>{categoryTypeLabel(categoryBindingPreview.type)}</p>
                            </div>
                          </article>
                          <article className="list-item audit-summary-card">
                            <div>
                              <strong>История</strong>
                              <p>{categoryBindingPreview.affected_transaction_count}</p>
                            </div>
                          </article>
                        </div>
                        <div className="family-page-actions category-binding-actions">
                          <button className="ghost-button" onClick={() => setCategoryBindingPreview(null)} type="button">
                            Закрыть
                          </button>
                          <button
                            className="primary-button"
                            disabled={!categoryBindingPreview.can_apply || categoryBindingApplyMutation.isPending || !canManageFamilyMembers}
                            onClick={applyCategoryBinding}
                            type="button"
                          >
                            {categoryBindingApplyMutation.isPending ? "Подтверждаем..." : "Да, связать категории"}
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
              {!familyCategoryAuditQuery.isLoading && !syncReadyGroups.length ? (
                <p className="muted">Пока нет групп, которые программа может уверенно подсветить для связи.</p>
              ) : null}
            </div>
          </div>

          {(categoryAudit?.resolutions ?? []).length ? (
            <div className="list category-audit-list category-audit-resolutions">
              <div className="category-audit-subheader">
                <strong>Уже принятые решения</strong>
                <span>{categoryAudit?.resolutions.length ?? 0}</span>
              </div>
              {(categoryAudit?.resolutions ?? []).map((resolution) => (
                <article className="list-item category-audit-group" key={`${resolution.code}-${resolution.group_key}-${resolution.action}`}>
                  <div>
                    <strong>{resolution.action === "keep_personal" ? "Оставлено личной" : "Оставлено раздельно"}</strong>
                    <p>{resolution.category_names.length ? resolution.category_names.join(", ") : resolution.group_key}</p>
                    <p className="muted">Можно отменить решение и снова разобрать этот пункт.</p>
                  </div>
                  <div className="family-page-actions category-audit-tags">
                    <button
                      className="ghost-button"
                      disabled={!canManageFamilyMembers || deleteCategoryAuditResolutionMutation.isPending}
                      onClick={() => undoAuditResolution(resolution)}
                      type="button"
                    >
                      Вернуть в аудит
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {familyId !== null ? (
        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Семейный капитал</h3>
            <span>Общие накопительные счета для семьи</span>
          </div>

          <div className="transaction-form">
            <label className="field">
              <span>Мой счет для публикации семье</span>
              <div className="list">
                {capitalAccounts.map((account) => {
                  const accountKey = `${meQuery.data?.id ?? 0}:${account.id}`;
                  const isPublished = publishedAccountKeys.has(accountKey);
                  return (
                    <article className="list-item" key={account.id}>
                      <div>
                        <strong>{account.name}</strong>
                        <p>{formatMoney(account.balance)}</p>
                      </div>
                      <div className="family-page-actions">
                        <button
                          className="ghost-button"
                          disabled={busyAction === "capital_publish"}
                          onClick={() => toggleFamilyCapital(account.id, !isPublished)}
                          type="button"
                        >
                          {isPublished ? "Убрать из семьи" : "Показывать семье"}
                        </button>
                        {isPublished && !account.family_default_target ? (
                          <button
                            className="ghost-button"
                            disabled={busyAction === "capital_publish"}
                            onClick={() => makeDefaultFamilyCapital(account.id)}
                            type="button"
                          >
                            Семейный по умолчанию
                          </button>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
                {!capitalAccounts.length ? <p className="muted">У вас пока нет активных счетов капитала.</p> : null}
              </div>
            </label>

          </div>

          <div className="list">
            {(familyDashboardQuery.data?.capital_accounts ?? []).map((account) => (
              <article className="list-item" key={`${account.owner_user_id}-${account.capital_account_id}`}>
                <div>
                  <strong>{account.name}</strong>
                  <p>{account.owner_display_name || account.owner_email}</p>
                </div>
                <div className="family-page-actions">
                  {account.is_default_target ? <span className="status-chip">По умолчанию</span> : null}
                  <strong>{formatMoney(account.balance)}</strong>
                </div>
              </article>
            ))}
            {!familyDashboardQuery.isLoading && !(familyDashboardQuery.data?.capital_accounts ?? []).length ? (
              <p className="muted">Семейные счета капитала пока не настроены.</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {familyId !== null ? (
        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Участники семьи</h3>
            <span>Всего: {(familyMembersQuery.data?.members ?? []).length}</span>
          </div>

          <div className="list">
            {(familyMembersQuery.data?.members ?? []).map((member) => {
              const isSelf = member.user_id === meQuery.data?.id;
              const canManageThisMember = canManageFamilyMembers && !isSelf && member.role !== "owner";
              return (
                <article className="list-item family-member-list-item" key={member.user_id}>
                  <div className="family-member-card-main">
                    <div className="family-member-card-title">
                      <strong>{member.display_name || member.email}</strong>
                      {member.role === "owner" ? <span className="family-role-badge">Владелец</span> : null}
                    </div>
                    {member.display_name ? <p>{member.email}</p> : null}
                    <p>Роль: {roleLabel(member.role)}</p>
                  </div>

                  <div className="family-page-actions">
                    {canManageThisMember ? (
                      <>
                        <button
                          className="ghost-button"
                          disabled={busyAction === "member_update" && busyUserId === member.user_id}
                          onClick={() => onUpdateMemberRole(member.user_id, member.role === "viewer" ? "member" : "viewer")}
                          type="button"
                        >
                          {member.role === "viewer" ? "Сделать помощником" : "Только просмотр"}
                        </button>
                        <button
                          className="ghost-button"
                          disabled={busyAction === "member_remove" && busyUserId === member.user_id}
                          onClick={() => onRemoveMember(member.user_id)}
                          type="button"
                        >
                          Исключить
                        </button>
                      </>
                    ) : (
                      <span className="status-chip">{isSelf ? "Это вы" : roleLabel(member.role)}</span>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
    </main>
  );
}
