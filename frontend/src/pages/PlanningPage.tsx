import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createBudget,
  createRecurringTemplate,
  deleteBudget,
  deleteRecurringTemplate,
  getAccountPreferences,
  getBudgetStatus,
  getBudgets,
  getCategories,
  getDashboard,
  getDuePlannedTransactions,
  getFamilyDashboard,
  getMyFamilies,
  getRecurringTemplates,
  updateBudget,
  updateRecurringTemplate,
  type TransactionType,
} from "../lib/api";

const PERIOD_OPTIONS = [
  { value: "daily", label: "В день" },
  { value: "monthly", label: "В месяц" },
  { value: "yearly", label: "В год" },
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getBudgetInitialForm() {
  return {
    categoryId: "",
    amount: "",
    period: "monthly",
  };
}

function padDatePart(value: number) {
  return String(value).padStart(2, "0");
}

function getCurrentMonthDate(dayOfMonth?: number) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const today = now.getDate();
  const lastDayOfMonth = new Date(year, month + 1, 0).getDate();
  const rawDay = dayOfMonth ?? today;
  const safeDay = Math.min(Math.max(rawDay, 1), lastDayOfMonth);

  return `${year}-${padDatePart(month + 1)}-${padDatePart(safeDay)}`;
}

function getDayOfMonthFromDate(dateValue: string) {
  const parts = dateValue.split("-");
  return Number(parts[2] ?? "");
}

function getRecurringInitialForm() {
  return {
    type: "expense" as TransactionType,
    name: "",
    amount: "",
    selectedDate: getCurrentMonthDate(),
    categoryId: "",
    commentTemplate: "",
    monthsAhead: "12",
    workingDaysOnly: true,
  };
}

export function PlanningPage() {
  const queryClient = useQueryClient();
  const currentMonthMinDate = getCurrentMonthDate(1);
  const currentMonthMaxDate = getCurrentMonthDate(31);

  const [editingBudgetId, setEditingBudgetId] = useState<number | null>(null);
  const [budgetForm, setBudgetForm] = useState(getBudgetInitialForm);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [useFamilyBudgetScope, setUseFamilyBudgetScope] = useState(false);
  const budgetFormPanelRef = useRef<HTMLElement | null>(null);
  const budgetAmountInputRef = useRef<HTMLInputElement | null>(null);

  const [editingTemplateId, setEditingTemplateId] = useState<number | null>(null);
  const [recurringForm, setRecurringForm] = useState(getRecurringInitialForm);
  const [recurringError, setRecurringError] = useState<string | null>(null);
  const recurringFormPanelRef = useRef<HTMLElement | null>(null);
  const recurringNameInputRef = useRef<HTMLInputElement | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  const preferencesQuery = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    retry: false,
  });

  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const selectedFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
  const useFamilyWorkspace = selectedFamilyId !== null && preferencesQuery.data?.workspace_mode === "family";

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const familyDashboardQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "dashboard", "planning-forecast"],
    queryFn: () => getFamilyDashboard(selectedFamilyId as number),
    enabled: useFamilyWorkspace,
    retry: false,
  });

  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: getBudgets,
  });

  const budgetStatus = useQuery({
    queryKey: ["budgets", "status", useFamilyBudgetScope, selectedFamilyId],
    queryFn: () =>
      getBudgetStatus({
        familyId: useFamilyBudgetScope ? (selectedFamilyId as number) : undefined,
      }),
  });

  const recurringTemplates = useQuery({
    queryKey: ["recurring-templates"],
    queryFn: () => getRecurringTemplates(),
  });

  const dueTransactions = useQuery({
    queryKey: ["recurring-templates", "due"],
    queryFn: getDuePlannedTransactions,
  });

  const executeRecurringMutation = {
    isPending: false,
    mutate: () => undefined,
  };

  const availableBudgetCategories = useMemo(() => {
    const expenseCategories = (categories.data ?? []).filter(
      (item) => item.type === "expense" || item.type === "both",
    );
    const budgetedCategoryIds = new Set((budgets.data ?? []).map((item) => item.category_id));

    if (editingBudgetId !== null) {
      const editedBudget = budgets.data?.find((item) => item.id === editingBudgetId);
      if (editedBudget) {
        budgetedCategoryIds.delete(editedBudget.category_id);
      }
    }

    return expenseCategories.filter((item) => !budgetedCategoryIds.has(item.id));
  }, [budgets.data, categories.data, editingBudgetId]);

  const recurringCategories = useMemo(() => {
    return (categories.data ?? []).filter(
      (item) => item.type === recurringForm.type || item.type === "both",
    );
  }, [categories.data, recurringForm.type]);

  const activeForecast = useFamilyWorkspace ? familyDashboardQuery.data?.forecast : dashboard.data?.forecast;

  const familyBudgetAvailable = selectedFamilyId !== null;

  useEffect(() => {
    if (!familyBudgetAvailable) {
      setUseFamilyBudgetScope(false);
      return;
    }
    setUseFamilyBudgetScope(preferencesQuery.data?.workspace_mode === "family");
  }, [familyBudgetAvailable, preferencesQuery.data?.workspace_mode]);

  async function refreshPlanningData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["budgets"] }),
      queryClient.invalidateQueries({ queryKey: ["budgets", "status"] }),
      queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
      queryClient.invalidateQueries({ queryKey: ["transactions"] }),
      queryClient.invalidateQueries({ queryKey: ["accounts"] }),
    ]);
  }

  const createBudgetMutation = useMutation({
    mutationFn: createBudget,
    onSuccess: async () => {
      resetBudgetForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setBudgetError(error.message),
  });

  const updateBudgetMutation = useMutation({
    mutationFn: ({
      budgetId,
      amount,
      period,
    }: {
      budgetId: number;
      amount: number;
      period: string;
    }) => updateBudget(budgetId, { amount, period }),
    onSuccess: async () => {
      resetBudgetForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setBudgetError(error.message),
  });

  const deleteBudgetMutation = useMutation({
    mutationFn: deleteBudget,
    onSuccess: async () => {
      resetBudgetForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setBudgetError(error.message),
  });

  const createRecurringMutation = useMutation({
    mutationFn: createRecurringTemplate,
    onSuccess: async () => {
      resetRecurringForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setRecurringError(error.message),
  });

  const updateRecurringMutation = useMutation({
    mutationFn: ({
      templateId,
      payload,
    }: {
      templateId: number;
      payload: Parameters<typeof updateRecurringTemplate>[1];
    }) => updateRecurringTemplate(templateId, payload),
    onSuccess: async () => {
      resetRecurringForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setRecurringError(error.message),
  });

  const deleteRecurringMutation = useMutation({
    mutationFn: deleteRecurringTemplate,
    onSuccess: async () => {
      resetRecurringForm();
      await refreshPlanningData();
    },
    onError: (error: Error) => setRecurringError(error.message),
  });

  function resetBudgetForm() {
    setEditingBudgetId(null);
    setBudgetForm(getBudgetInitialForm());
    setBudgetError(null);
  }

  function resetRecurringForm() {
    setEditingTemplateId(null);
    setRecurringForm(getRecurringInitialForm());
    setRecurringError(null);
  }

  function moveToRecurringEditForm() {
    requestAnimationFrame(() => {
      recurringFormPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        recurringNameInputRef.current?.focus();
        recurringNameInputRef.current?.select();
      }, 180);
    });
  }

  function moveToBudgetEditForm() {
    requestAnimationFrame(() => {
      budgetFormPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        budgetAmountInputRef.current?.focus();
        budgetAmountInputRef.current?.select();
      }, 180);
    });
  }

  function startBudgetEdit(budgetId: number) {
    const budget = budgets.data?.find((item) => item.id === budgetId);
    if (!budget) {
      return;
    }

    setEditingBudgetId(budget.id);
    setBudgetForm({
      categoryId: String(budget.category_id),
      amount: String(budget.amount),
      period: budget.period,
    });
    setBudgetError(null);
    moveToBudgetEditForm();
  }

  function startRecurringEdit(templateId: number) {
    const template = recurringTemplates.data?.find((item) => item.id === templateId);
    if (!template) {
      return;
    }

    setEditingTemplateId(template.id);
    setRecurringForm({
      type: template.type,
      name: template.name,
      amount: String(template.amount),
      selectedDate: getCurrentMonthDate(template.day_of_month),
      categoryId: template.category_id ? String(template.category_id) : "",
      commentTemplate: template.comment_template,
      monthsAhead: String(template.months_ahead),
      workingDaysOnly: template.working_days_only,
    });
    setRecurringError(null);
    moveToRecurringEditForm();
  }

  function submitBudgetForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBudgetError(null);

    const amount = Number(budgetForm.amount.replace(",", "."));
    if (!budgetForm.categoryId) {
      setBudgetError("Выбери категорию.");
      return;
    }
    if (!amount || amount <= 0) {
      setBudgetError("Укажи сумму больше нуля.");
      return;
    }

    if (editingBudgetId !== null) {
      updateBudgetMutation.mutate({
        budgetId: editingBudgetId,
        amount,
        period: budgetForm.period,
      });
      return;
    }

    createBudgetMutation.mutate({
      category_id: Number(budgetForm.categoryId),
      amount,
      period: budgetForm.period,
    });
  }

  function submitRecurringForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRecurringError(null);

    const amount = Number(recurringForm.amount.replace(",", "."));
    const dayOfMonth = getDayOfMonthFromDate(recurringForm.selectedDate);
    const monthsAhead = Number(recurringForm.monthsAhead);
    const categoryId = recurringForm.categoryId ? Number(recurringForm.categoryId) : undefined;

    if (!recurringForm.name.trim()) {
      setRecurringError("Укажи название регулярной операции.");
      return;
    }
    if (!amount || amount <= 0) {
      setRecurringError("Укажи сумму больше нуля.");
      return;
    }
    if (!recurringForm.selectedDate) {
      setRecurringError("Выбери дату в текущем месяце.");
      return;
    }
    if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 31) {
      setRecurringError("День месяца должен быть от 1 до 31.");
      return;
    }
    if (!monthsAhead || monthsAhead < 1 || monthsAhead > 24) {
      setRecurringError("Горизонт планирования должен быть от 1 до 24 месяцев.");
      return;
    }

    const payload = {
      type: recurringForm.type,
      name: recurringForm.name.trim(),
      amount,
      day_of_month: dayOfMonth,
      category_id: categoryId,
      comment_template: recurringForm.commentTemplate.trim(),
      months_ahead: monthsAhead,
      working_days_only: recurringForm.workingDaysOnly,
    };

    if (editingTemplateId !== null) {
      updateRecurringMutation.mutate({ templateId: editingTemplateId, payload });
      return;
    }

    createRecurringMutation.mutate(payload);
  }

  return (
    <main className="planning-page">
      <section className="panel planning-summary-panel">
        <div className="panel-header">
          <h2>Планирование</h2>
          <span>Будущие деньги</span>
        </div>

        <div className="summary-grid summary-grid-3 planning-summary-grid">
          <article className="summary-card summary-card-main planning-summary-card planning-summary-main">
            <span className="panel-label">Прогноз на конец месяца</span>
            <h3>{formatMoney(activeForecast?.projected_balance ?? 0)}</h3>
            <p className="muted">
              До {activeForecast?.end_date ?? "конца месяца"}
            </p>
          </article>

          <article className="summary-card planning-summary-card">
            <span className="panel-label">Запланированные доходы</span>
            <strong className="money plus">
              {formatMoney(
                (activeForecast?.planned_income ?? 0) +
                  (activeForecast?.executed_planned_income ?? 0),
              )}
            </strong>
            <div className="planning-summary-stats">
              <div className="planning-summary-stat">
                <span className="muted">Не исполнено</span>
                <strong className="money plus">
                  {formatMoney(activeForecast?.planned_income ?? 0)}
                </strong>
              </div>
              <div className="planning-summary-stat">
                <span className="muted">Исполнено</span>
                <strong className="money">
                  {formatMoney(activeForecast?.executed_planned_income ?? 0)}
                </strong>
              </div>
            </div>
          </article>

          <article className="summary-card planning-summary-card">
            <span className="panel-label">Запланированные расходы</span>
            <strong className="money minus">
              {formatMoney(activeForecast?.combined_pending_expense ?? 0)}
            </strong>
            <div className="planning-summary-stats">
              <div className="planning-summary-stat">
                <span className="muted">Не исполнено</span>
                <strong className="money minus">
                  {formatMoney(activeForecast?.combined_pending_expense ?? 0)}
                </strong>
              </div>
              <div className="planning-summary-stat">
                <span className="muted">Исполнено</span>
                <strong className="money">
                  {formatMoney(activeForecast?.combined_executed_expense ?? 0)}
                </strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="planning-section">
        <div className="planning-section-head">
          <div>
            <h2>Регулярные операции</h2>
            <p className="muted">Доходы и расходы, которые повторяются из месяца в месяц.</p>
          </div>

          {false && <button
            className="primary-button"
            disabled={executeRecurringMutation.isPending}
            onClick={() => executeRecurringMutation.mutate()}
            type="button"
          >
            {executeRecurringMutation.isPending ? "Исполняем..." : "Исполнить просроченные"}
          </button>}
        </div>

        <>
          <section
            className={editingTemplateId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
            ref={recurringFormPanelRef}
          >
            <div className="panel-header">
              <h2>{editingTemplateId ? "Редактирование шаблона" : "Новая регулярная операция"}</h2>
            </div>

            <form className="transaction-form" onSubmit={submitRecurringForm}>
              {editingTemplateId !== null && (
                <div className="editing-banner" role="status">
                  <strong>Сейчас редактируется:</strong> {recurringForm.name || "шаблон"}
                </div>
              )}

              <div className="toggle-row">
                <button
                  className={recurringForm.type === "expense" ? "toggle active" : "toggle"}
                  onClick={() =>
                    setRecurringForm((current) => ({ ...current, type: "expense", categoryId: "" }))
                  }
                  type="button"
                >
                  Расход
                </button>
                <button
                  className={recurringForm.type === "income" ? "toggle active" : "toggle"}
                  onClick={() =>
                    setRecurringForm((current) => ({ ...current, type: "income", categoryId: "" }))
                  }
                  type="button"
                >
                  Доход
                </button>
              </div>

              <label className="field">
                <span>Название</span>
                <input
                  ref={recurringNameInputRef}
                  onChange={(event) =>
                    setRecurringForm((current) => ({ ...current, name: event.target.value }))
                  }
                  placeholder="Например, Зарплата или Ипотека"
                  value={recurringForm.name}
                />
              </label>

              <label className="field">
                <span>Категория</span>
                <select
                  onChange={(event) =>
                    setRecurringForm((current) => ({ ...current, categoryId: event.target.value }))
                  }
                  value={recurringForm.categoryId}
                >
                  <option value="">Выбери категорию</option>
                  {recurringCategories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="field-row">
                <label className="field">
                  <span>Сумма</span>
                  <input
                    inputMode="decimal"
                    onChange={(event) =>
                      setRecurringForm((current) => ({ ...current, amount: event.target.value }))
                    }
                    placeholder="0"
                    value={recurringForm.amount}
                  />
                </label>

                <label className="field">
                  <span>Дата в текущем месяце</span>
                  <div className="date-shell">
                    <input
                    className="date-input"
                    onClick={(event) => {
                      (event.currentTarget as HTMLInputElement & { showPicker?: () => void }).showPicker?.();
                    }}
                    max={currentMonthMaxDate}
                    min={currentMonthMinDate}
                    onChange={(event) =>
                      setRecurringForm((current) => ({
                        ...current,
                        selectedDate: event.target.value,
                      }))
                    }
                    type="date"
                    value={recurringForm.selectedDate}
                    />
                  </div>
                </label>
              </div>

              <div className="field-row">
                <label className="field">
                  <span>Планировать вперёд</span>
                  <input
                    inputMode="numeric"
                    max="24"
                    min="1"
                    onChange={(event) =>
                      setRecurringForm((current) => ({ ...current, monthsAhead: event.target.value }))
                    }
                    type="number"
                    value={recurringForm.monthsAhead}
                  />
                </label>

                <label className="field">
                  <span>Только рабочие дни</span>
                  <select
                    onChange={(event) =>
                      setRecurringForm((current) => ({
                        ...current,
                        workingDaysOnly: event.target.value === "true",
                      }))
                    }
                    value={String(recurringForm.workingDaysOnly)}
                  >
                    <option value="true">Да</option>
                    <option value="false">Нет</option>
                  </select>
                </label>
              </div>

              <label className="field">
                <span>Комментарий</span>
                <input
                  onChange={(event) =>
                    setRecurringForm((current) => ({
                      ...current,
                      commentTemplate: event.target.value,
                    }))
                  }
                  placeholder="Например, Основная зарплата"
                  value={recurringForm.commentTemplate}
                />
              </label>

              {recurringError && <p className="form-error">{recurringError}</p>}

              <div className="action-row">
                <button
                  className="primary-button"
                  disabled={createRecurringMutation.isPending || updateRecurringMutation.isPending}
                  type="submit"
                >
                  {editingTemplateId
                    ? updateRecurringMutation.isPending
                      ? "Сохраняем..."
                      : "Сохранить"
                    : createRecurringMutation.isPending
                      ? "Создаём..."
                      : "Добавить"}
                </button>

                {editingTemplateId !== null && (
                  <button className="ghost-button" onClick={resetRecurringForm} type="button">
                    Отмена
                  </button>
                )}
              </div>
            </form>
          </section>

          <section className="panel panel-list">
            {!!dueTransactions.data?.length && (
              <div className="planning-due-block">
                <div className="panel-header">
                  <h3>К исполнению сейчас</h3>
                </div>

                <div className="list">
                  {dueTransactions.data.map((item) => (
                    <article className="list-item" key={item.id}>
                      <div>
                        <strong>{item.template_name || item.category}</strong>
                        <p>{item.comment || "Без комментария"}</p>
                      </div>
                      <div className={item.type === "income" ? "money plus" : "money minus"}>
                        {formatMoney(item.amount)}
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            )}

            <div className="panel-header">
              <h2>Шаблоны регулярных операций</h2>
            </div>

            <div className="category-card-grid">
              {(recurringTemplates.data ?? []).map((item) => (
                <article className="budget-card" key={item.id}>
                  <div className="category-card-main">
                    <div>
                      <strong>{item.name}</strong>
                      <p>
                        {item.type === "income" ? "Доход" : "Расход"} {formatMoney(item.amount)}
                        {item.category_name ? ` • ${item.category_name}` : ""}
                      </p>
                    </div>
                  </div>

                  <div className="budget-meta">
                    <span>Каждый месяц {item.day_of_month} числа</span>
                    <span>
                      {item.working_days_only ? "С переносом на рабочий день" : "Без переноса"}
                    </span>
                  </div>

                  <div className="category-card-actions">
                    <button className="ghost-button" onClick={() => startRecurringEdit(item.id)} type="button">
                      Изменить
                    </button>
                    <button
                      className="ghost-button"
                      disabled={deleteRecurringMutation.isPending}
                      onClick={() => deleteRecurringMutation.mutate(item.id)}
                      type="button"
                    >
                      Удалить
                    </button>
                  </div>
                </article>
              ))}

              {!recurringTemplates.data?.length && (
                <p className="empty">
                  {recurringTemplates.isLoading
                    ? "Загружаем шаблоны..."
                    : "Регулярные операции пока не настроены."}
                </p>
              )}
            </div>
          </section>
        </>
      </section>

      <section className="planning-section">
        <div className="planning-section-head">
          <div>
            <h2>Бюджеты</h2>
            <p className="muted">Лимиты по категориям и сколько ещё можно потратить.</p>
          </div>
        </div>

        <>
          <section
            className={editingBudgetId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
            ref={budgetFormPanelRef}
          >
            <div className="panel-header">
              <h2>{editingBudgetId ? "Редактирование бюджета" : "Новый бюджет"}</h2>
            </div>

            <form className="transaction-form" onSubmit={submitBudgetForm}>
              {editingBudgetId !== null && (
                <div className="editing-banner" role="status">
                  <strong>Сейчас редактируется:</strong> {budgets.data?.find((item) => item.id === editingBudgetId)?.category_name ?? "бюджет"}
                </div>
              )}
              <label className="field">
                <span>Категория</span>
                <select
                  disabled={editingBudgetId !== null}
                  onChange={(event) =>
                    setBudgetForm((current) => ({ ...current, categoryId: event.target.value }))
                  }
                  value={budgetForm.categoryId}
                >
                  <option value="">Выбери категорию</option>
                  {availableBudgetCategories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="field-row">
                <label className="field">
                  <span>Лимит</span>
                  <input
                    ref={budgetAmountInputRef}
                    inputMode="decimal"
                    onChange={(event) =>
                      setBudgetForm((current) => ({ ...current, amount: event.target.value }))
                    }
                    placeholder="0"
                    value={budgetForm.amount}
                  />
                </label>

                <label className="field">
                  <span>Период</span>
                  <select
                    onChange={(event) =>
                      setBudgetForm((current) => ({ ...current, period: event.target.value }))
                    }
                    value={budgetForm.period}
                  >
                    {PERIOD_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {budgetError && <p className="form-error">{budgetError}</p>}

              <div className="action-row">
                <button
                  className="primary-button"
                  disabled={createBudgetMutation.isPending || updateBudgetMutation.isPending}
                  type="submit"
                >
                  {editingBudgetId
                    ? updateBudgetMutation.isPending
                      ? "Сохраняем..."
                      : "Сохранить"
                    : createBudgetMutation.isPending
                      ? "Создаём..."
                      : "Добавить"}
                </button>

                {editingBudgetId !== null && (
                  <button className="ghost-button" onClick={resetBudgetForm} type="button">
                    Отмена
                  </button>
                )}
              </div>
            </form>
          </section>

          <section className="panel panel-list">
            <div className="panel-header">
              <h2>Статус бюджетов</h2>
            </div>

            {familyBudgetAvailable ? (
              <label className="field field-inline field-compact">
                <span>Семейный бюджет</span>
                <input
                  checked={useFamilyBudgetScope}
                  onChange={(event) => setUseFamilyBudgetScope(event.target.checked)}
                  type="checkbox"
                />
              </label>
            ) : null}

            {useFamilyBudgetScope ? (
              <p className="muted">В статусе бюджетов учитываются траты всех участников семьи.</p>
            ) : null}

            <div className="category-card-grid">
              {(budgetStatus.data ?? []).map((item) => {
                const budget = budgets.data?.find((entry) => entry.category_id === item.category_id);
                return (
                  <article className="budget-card" key={item.category_id}>
                    <div className="category-card-main">
                      <span
                        aria-hidden="true"
                        className="category-dot"
                        style={{ backgroundColor: item.color }}
                      />
                      <div>
                        <strong>{item.category_name}</strong>
                        <p>
                          Потрачено {formatMoney(item.spent)} из {formatMoney(item.budget_amount)}
                        </p>
                      </div>
                    </div>

                    <div className="budget-progress">
                      <div className="budget-progress-track">
                        <div
                          className={item.over_budget ? "budget-progress-fill over" : "budget-progress-fill"}
                          style={{ width: `${Math.min(item.percent, 100)}%` }}
                        />
                      </div>
                      <div className="budget-meta">
                        <span>{Math.round(item.percent)}%</span>
                        <div>
                          <span>Осталось</span>
                          <strong className={item.over_budget ? "money minus" : "money"}>
                            {formatMoney(item.remaining)}
                          </strong>
                        </div>
                      </div>
                    </div>

                    {budget && (
                      <div className="category-card-actions">
                        <button className="ghost-button" onClick={() => startBudgetEdit(budget.id)} type="button">
                          Изменить
                        </button>
                        <button
                          className="ghost-button"
                          disabled={deleteBudgetMutation.isPending}
                          onClick={() => deleteBudgetMutation.mutate(budget.id)}
                          type="button"
                        >
                          Удалить
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}

              {!budgetStatus.data?.length && (
                <p className="empty">
                  {budgetStatus.isLoading ? "Загружаем бюджеты..." : "Бюджеты пока не настроены."}
                </p>
              )}
            </div>
          </section>
        </>
      </section>
    </main>
  );
}
