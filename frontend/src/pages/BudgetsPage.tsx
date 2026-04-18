import { useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createBudget,
  deleteBudget,
  getBudgetStatus,
  getBudgets,
  getCategories,
  updateBudget,
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

function getInitialFormState() {
  return {
    categoryId: "",
    amount: "",
    period: "monthly",
  };
}

export function BudgetsPage() {
  const queryClient = useQueryClient();
  const [editingBudgetId, setEditingBudgetId] = useState<number | null>(null);
  const [formState, setFormState] = useState(getInitialFormState);
  const [formError, setFormError] = useState<string | null>(null);
  const formPanelRef = useRef<HTMLElement | null>(null);
  const amountInputRef = useRef<HTMLInputElement | null>(null);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: getBudgets,
  });

  const budgetStatus = useQuery({
    queryKey: ["budgets", "status"],
    queryFn: getBudgetStatus,
  });

  const availableCategories = useMemo(() => {
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

  const createMutation = useMutation({
    mutationFn: createBudget,
    onSuccess: async () => {
      resetForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["budgets"] }),
      ]);
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const updateMutation = useMutation({
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
      resetForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["budgets"] }),
      ]);
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBudget,
    onSuccess: async () => {
      resetForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["budgets"] }),
      ]);
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  function resetForm() {
    setEditingBudgetId(null);
    setFormState(getInitialFormState());
    setFormError(null);
  }

  function moveToEditForm() {
    requestAnimationFrame(() => {
      formPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        amountInputRef.current?.focus();
        amountInputRef.current?.select();
      }, 180);
    });
  }

  function startEdit(budgetId: number) {
    const budget = budgets.data?.find((item) => item.id === budgetId);
    if (!budget) {
      return;
    }

    setEditingBudgetId(budget.id);
    setFormState({
      categoryId: String(budget.category_id),
      amount: String(budget.amount),
      period: budget.period,
    });
    setFormError(null);
    moveToEditForm();
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const amount = Number(formState.amount.replace(",", "."));
    if (!formState.categoryId) {
      setFormError("Выбери категорию.");
      return;
    }
    if (!amount || amount <= 0) {
      setFormError("Укажи сумму больше нуля.");
      return;
    }

    if (editingBudgetId !== null) {
      updateMutation.mutate({
        budgetId: editingBudgetId,
        amount,
        period: formState.period,
      });
      return;
    }

    createMutation.mutate({
      category_id: Number(formState.categoryId),
      amount,
      period: formState.period,
    });
  }

  return (
    <main className="categories-layout">
      <section
        className={editingBudgetId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
        ref={formPanelRef}
      >
        <div className="panel-header">
          <h2>{editingBudgetId ? "Редактирование бюджета" : "Новый бюджет"}</h2>
          <span>{editingBudgetId ? "Лимит" : "План"}</span>
        </div>

        <form className="transaction-form" onSubmit={submitForm}>
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
                setFormState((current) => ({ ...current, categoryId: event.target.value }))
              }
              value={formState.categoryId}
            >
              <option value="">Выбери категорию</option>
              {availableCategories.map((item) => (
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
                ref={amountInputRef}
                inputMode="decimal"
                onChange={(event) =>
                  setFormState((current) => ({ ...current, amount: event.target.value }))
                }
                placeholder="0"
                value={formState.amount}
              />
            </label>

            <label className="field">
              <span>Период</span>
              <select
                onChange={(event) =>
                  setFormState((current) => ({ ...current, period: event.target.value }))
                }
                value={formState.period}
              >
                {PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {formError && <p className="form-error">{formError}</p>}

          <div className="action-row">
            <button
              className="primary-button"
              disabled={createMutation.isPending || updateMutation.isPending}
              type="submit"
            >
              {editingBudgetId
                ? updateMutation.isPending
                  ? "Сохраняем..."
                  : "Сохранить бюджет"
                : createMutation.isPending
                  ? "Создаём..."
                  : "Добавить бюджет"}
            </button>

            {editingBudgetId !== null && (
              <button className="ghost-button" onClick={resetForm} type="button">
                Отмена
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="panel panel-list">
        <div className="panel-header">
          <h2>Статус бюджетов</h2>        </div>

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
                    <button className="ghost-button" onClick={() => startEdit(budget.id)} type="button">
                      Изменить
                    </button>
                    <button
                      className="ghost-button"
                      disabled={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(budget.id)}
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
              {budgetStatus.isLoading
                ? "Загружаем бюджеты..."
                : "Бюджеты пока не настроены."}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}

