import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRecurringTemplate,
  deleteRecurringTemplate,
  executeDuePlannedTransactions,
  getCategories,
  getDuePlannedTransactions,
  getRecurringTemplates,
  getSettings,
  updateRecurringTemplate,
  type MoneySource,
  type TransactionType,
} from "../lib/api";

const MONEY_SOURCE_OPTIONS: Array<{ value: MoneySource; label: string }> = [
  { value: "cashless", label: "Безнал" },
  { value: "cash", label: "Наличные" },
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getInitialForm() {
  return {
    type: "expense" as TransactionType,
    name: "",
    amount: "",
    dayOfMonth: "1",
    categoryId: "",
    commentTemplate: "",
    moneySource: "cashless" as MoneySource,
    monthsAhead: "12",
    workingDaysOnly: true,
  };
}

export function RecurringPage() {
  const queryClient = useQueryClient();
  const [editingTemplateId, setEditingTemplateId] = useState<number | null>(null);
  const [form, setForm] = useState(getInitialForm);
  const [formError, setFormError] = useState<string | null>(null);
  const formPanelRef = useRef<HTMLElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const recurringTemplates = useQuery({
    queryKey: ["recurring-templates"],
    queryFn: () => getRecurringTemplates(),
  });

  const dueTransactions = useQuery({
    queryKey: ["recurring-templates", "due"],
    queryFn: getDuePlannedTransactions,
  });

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const filteredCategories = useMemo(() => {
    return (categories.data ?? []).filter((item) => item.type === form.type || item.type === "both");
  }, [categories.data, form.type]);

  useEffect(() => {
    if (editingTemplateId === null && settings.data?.default_money_source) {
      setForm((current) => ({ ...current, moneySource: settings.data.default_money_source }));
    }
  }, [editingTemplateId, settings.data?.default_money_source]);

  const createMutation = useMutation({
    mutationFn: createRecurringTemplate,
    onSuccess: async () => {
      resetForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => setFormError(error.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ templateId, payload }: { templateId: number; payload: Parameters<typeof updateRecurringTemplate>[1] }) =>
      updateRecurringTemplate(templateId, payload),
    onSuccess: async () => {
      resetForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => setFormError(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteRecurringTemplate,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => setFormError(error.message),
  });

  const executeMutation = useMutation({
    mutationFn: executeDuePlannedTransactions,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["recurring-templates", "due"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => setFormError(error.message),
  });

  function resetForm() {
    setEditingTemplateId(null);
    setForm(getInitialForm());
    setFormError(null);
  }

  function moveToEditForm() {
    requestAnimationFrame(() => {
      formPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        nameInputRef.current?.focus();
        nameInputRef.current?.select();
      }, 180);
    });
  }

  function startEdit(templateId: number) {
    const template = recurringTemplates.data?.find((item) => item.id === templateId);
    if (!template) {
      return;
    }

    setEditingTemplateId(template.id);
    setForm({
      type: template.type,
      name: template.name,
      amount: String(template.amount),
      dayOfMonth: String(template.day_of_month),
      categoryId: template.category_id ? String(template.category_id) : "",
      commentTemplate: template.comment_template,
      moneySource: template.money_source,
      monthsAhead: String(template.months_ahead),
      workingDaysOnly: template.working_days_only,
    });
    setFormError(null);
    moveToEditForm();
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const amount = Number(form.amount.replace(",", "."));
    const dayOfMonth = Number(form.dayOfMonth);
    const monthsAhead = Number(form.monthsAhead);
    const categoryId = form.categoryId ? Number(form.categoryId) : undefined;

    if (!form.name.trim()) {
      setFormError("Укажи название регулярной операции.");
      return;
    }
    if (!amount || amount <= 0) {
      setFormError("Укажи сумму больше нуля.");
      return;
    }
    if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 31) {
      setFormError("День месяца должен быть от 1 до 31.");
      return;
    }
    if (!monthsAhead || monthsAhead < 1 || monthsAhead > 24) {
      setFormError("Горизонт планирования должен быть от 1 до 24 месяцев.");
      return;
    }

    const payload = {
      type: form.type,
      name: form.name.trim(),
      amount,
      day_of_month: dayOfMonth,
      category_id: categoryId,
      comment_template: form.commentTemplate,
      money_source: form.moneySource,
      months_ahead: monthsAhead,
      working_days_only: form.workingDaysOnly,
    };

    if (editingTemplateId !== null) {
      updateMutation.mutate({ templateId: editingTemplateId, payload });
      return;
    }

    createMutation.mutate(payload);
  }

  return (
    <main className="categories-layout">
      <section
        className={editingTemplateId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
        ref={formPanelRef}
      >
        <div className="panel-header">
          <h2>{editingTemplateId ? "Редактирование шаблона" : "Новая регулярная операция"}</h2>
        </div>

        <form className="transaction-form" onSubmit={submitForm}>
          {editingTemplateId !== null && (
            <div className="editing-banner" role="status">
              <strong>Сейчас редактируется:</strong> {form.name || "шаблон"}
            </div>
          )}

          <div className="toggle-row">
            <button
              className={form.type === "expense" ? "toggle active" : "toggle"}
              onClick={() => setForm((current) => ({ ...current, type: "expense", categoryId: "" }))}
              type="button"
            >
              Расход
            </button>
            <button
              className={form.type === "income" ? "toggle active" : "toggle"}
              onClick={() => setForm((current) => ({ ...current, type: "income", categoryId: "" }))}
              type="button"
            >
              Доход
            </button>
          </div>

          <div className="toggle-row">
            {MONEY_SOURCE_OPTIONS.map((option) => (
              <button
                className={form.moneySource === option.value ? "toggle active" : "toggle"}
                key={option.value}
                onClick={() => setForm((current) => ({ ...current, moneySource: option.value }))}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>

          <label className="field">
            <span>Название</span>
            <input
              ref={nameInputRef}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Например, Зарплата или Ипотека"
              value={form.name}
            />
          </label>

          <label className="field">
            <span>Категория</span>
            <select
              onChange={(event) => setForm((current) => ({ ...current, categoryId: event.target.value }))}
              value={form.categoryId}
            >
              <option value="">Выбери категорию</option>
              {filteredCategories.map((item) => (
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
                onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}
                placeholder="0"
                value={form.amount}
              />
            </label>

            <label className="field">
              <span>День месяца</span>
              <input
                inputMode="numeric"
                max="31"
                min="1"
                onChange={(event) => setForm((current) => ({ ...current, dayOfMonth: event.target.value }))}
                type="number"
                value={form.dayOfMonth}
              />
            </label>
          </div>

          <div className="field-row">
            <label className="field">
              <span>Планировать вперёд</span>
              <input
                inputMode="numeric"
                max="24"
                min="1"
                onChange={(event) => setForm((current) => ({ ...current, monthsAhead: event.target.value }))}
                type="number"
                value={form.monthsAhead}
              />
            </label>

            <label className="field">
              <span>Только рабочие дни</span>
              <select
                onChange={(event) =>
                  setForm((current) => ({ ...current, workingDaysOnly: event.target.value === "true" }))
                }
                value={String(form.workingDaysOnly)}
              >
                <option value="true">Да</option>
                <option value="false">Нет</option>
              </select>
            </label>
          </div>

          <label className="field">
            <span>Комментарий</span>
            <input
              onChange={(event) => setForm((current) => ({ ...current, commentTemplate: event.target.value }))}
              placeholder="Например, Основная зарплата"
              value={form.commentTemplate}
            />
          </label>

          {formError && <p className="form-error">{formError}</p>}

          <div className="action-row">
            <button
              className="primary-button"
              disabled={createMutation.isPending || updateMutation.isPending}
              type="submit"
            >
              {editingTemplateId
                ? updateMutation.isPending
                  ? "Сохраняем..."
                  : "Сохранить шаблон"
                : createMutation.isPending
                  ? "Создаём..."
                  : "Добавить шаблон"}
            </button>

            {editingTemplateId !== null && (
              <button className="ghost-button" onClick={resetForm} type="button">
                Отмена
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="panel panel-list">
        <div className="panel-header">
          <h2>Регулярные операции</h2>
          <button
            className="primary-button"
            disabled={executeMutation.isPending}
            onClick={() => executeMutation.mutate()}
            type="button"
          >
            {executeMutation.isPending ? "Исполняем..." : "Исполнить просроченные"}
          </button>
        </div>

        {!!dueTransactions.data?.length && (
          <div className="list">
            {dueTransactions.data.map((item) => (
              <article className="list-item" key={item.id}>
                <div>
                  <strong>{item.template_name || item.category}</strong>
                  <p>{item.comment || "Без комментария"} · {item.money_source === "cash" ? "Наличные" : "Безнал"}</p>
                </div>
                <div className={item.type === "income" ? "money plus" : "money minus"}>
                  {formatMoney(item.amount)}
                </div>
              </article>
            ))}
          </div>
        )}

        <div className="category-card-grid">
          {(recurringTemplates.data ?? []).map((item) => (
            <article className="budget-card" key={item.id}>
              <div className="category-card-main">
                <div>
                  <strong>{item.name}</strong>
                  <p>
                    {item.type === "income" ? "Доход" : "Расход"} {formatMoney(item.amount)} · {item.money_source === "cash" ? "Наличные" : "Безнал"} {item.category_name ? `• ${item.category_name}` : ""}
                  </p>
                </div>
              </div>

              <div className="budget-meta">
                <span>
                  Каждый месяц {item.day_of_month} числа
                </span>
                <span>{item.working_days_only ? "С переносом на рабочий день" : "Без переноса"}</span>
              </div>

              <div className="category-card-actions">
                <button className="ghost-button" onClick={() => startEdit(item.id)} type="button">
                  Изменить
                </button>
                <button
                  className="ghost-button"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(item.id)}
                  type="button"
                >
                  Удалить
                </button>
              </div>
            </article>
          ))}

          {!recurringTemplates.data?.length && (
            <p className="empty">
              {recurringTemplates.isLoading ? "Загружаем шаблоны..." : "Регулярные операции пока не настроены."}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
