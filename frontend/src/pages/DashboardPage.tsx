import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createTransaction, getCategories, getDashboard } from "../lib/api";

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getQueryErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error) {
    return `${fallback}: ${error.message}`;
  }
  return fallback;
}

export function DashboardPage() {
  const queryClient = useQueryClient();

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const [quickCategoryId, setQuickCategoryId] = useState<number | null>(null);
  const [quickAmount, setQuickAmount] = useState("");
  const [quickType, setQuickType] = useState<"income" | "expense">("expense");
  const [quickError, setQuickError] = useState<string | null>(null);
  const [quickSuccess, setQuickSuccess] = useState<string | null>(null);

  const visibleTransactions = dashboard.data?.recent_transactions ?? [];
  const receivedIncome = dashboard.data?.balance.income ?? 0;
  const pendingIncome = dashboard.data?.forecast.planned_income ?? 0;
  const totalIncomePreview = receivedIncome + pendingIncome;

  const executedExpense = dashboard.data?.balance.expense ?? 0;
  const pendingExpense = dashboard.data?.forecast.combined_pending_expense ?? 0;
  const totalExpensePreview = executedExpense + pendingExpense;

  const selectedCategory = useMemo(
    () => categories.data?.find((item) => item.id === quickCategoryId) ?? null,
    [categories.data, quickCategoryId],
  );

  const quickEntryMutation = useMutation({
    mutationFn: createTransaction,
    onSuccess: async () => {
      setQuickSuccess("Операция добавлена");
      setQuickError(null);
      setQuickAmount("");
      setQuickCategoryId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["budgets"] }),
      ]);
    },
    onError: (error: Error) => {
      setQuickSuccess(null);
      setQuickError(error.message);
    },
  });

  function handleCategoryClick(categoryId: number) {
    const clickedCategory = categories.data?.find((item) => item.id === categoryId);
    const nextType = clickedCategory?.type === "income" ? "income" : "expense";
    setQuickError(null);
    setQuickSuccess(null);
    setQuickAmount("");
    setQuickType(nextType);
    setQuickCategoryId((current) => (current === categoryId ? null : categoryId));
  }

  function handleCancelQuickEntry() {
    setQuickCategoryId(null);
    setQuickAmount("");
    setQuickError(null);
    setQuickSuccess(null);
  }

  function submitQuickEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuickError(null);
    setQuickSuccess(null);

    if (!selectedCategory) {
      setQuickError("Выбери категорию.");
      return;
    }

    const amount = Number(quickAmount.replace(",", "."));
    if (!amount || amount <= 0) {
      setQuickError("Укажи сумму больше нуля.");
      return;
    }

    const transactionType =
      selectedCategory.type === "both"
        ? quickType
        : selectedCategory.type === "income"
          ? "income"
          : "expense";
    const today = new Date().toISOString().slice(0, 10);

    quickEntryMutation.mutate({
      type: transactionType,
      category_id: selectedCategory.id,
      amount,
      comment: `Быстрый ввод: ${selectedCategory.name}`,
      date: today,
    });
  }

  return (
    <>
      <header className="hero">
        <div className="hero-copy">
          <h1>Домашняя бухгалтерия в браузере</h1>
          <p className="hero-text">
            Главный экран проекта: баланс, транзакции, категории и прогноз конца месяца.
          </p>
        </div>
        <div className="hero-note">
          <span className="note-label">API</span>
          <strong>
            {dashboard.isSuccess
              ? "подключено"
              : dashboard.isError
                ? "ошибка подключения"
                : "ожидание backend"}
          </strong>
          {dashboard.isError && (
            <p className="empty">
              {getQueryErrorMessage(dashboard.error, "Не удалось загрузить dashboard")}
            </p>
          )}
        </div>
      </header>

      <main className="grid">
        <section className="panel panel-balance">
          <p className="panel-label">Текущий баланс</p>
          <h2>{dashboard.data ? formatMoney(dashboard.data.balance.main_balance) : "—"}</h2>
          <div className="stats-row">
            <div>
              <span>Доход за месяц (всего)</span>
              <strong>{dashboard.data ? formatMoney(totalIncomePreview) : "—"}</strong>
              <p className="stat-note">
                Получено: {formatMoney(receivedIncome)} · Не получено: {formatMoney(pendingIncome)}
              </p>
            </div>
            <div>
              <span>Расход за месяц (всего)</span>
              <strong>{dashboard.data ? formatMoney(totalExpensePreview) : "—"}</strong>
              <p className="stat-note">
                Исполнено: {formatMoney(executedExpense)} · Запланировано: {formatMoney(pendingExpense)}
              </p>
            </div>
          </div>
        </section>

        <section className="panel">
          <p className="panel-label">Баланс на конец месяца</p>
          <h2>{dashboard.data ? formatMoney(dashboard.data.forecast.projected_balance) : "—"}</h2>
          <p className="muted">
            {dashboard.data ? `До ${dashboard.data.forecast.end_date}` : "Нужен backend на FastAPI"}
          </p>
          <div className="forecast-breakdown">
            <p className="stat-note">
              Всего доходов: {formatMoney(totalIncomePreview)} (получено {formatMoney(receivedIncome)} + не
              получено {formatMoney(pendingIncome)})
            </p>
            <p className="stat-note">
              Всего расходов: {formatMoney(totalExpensePreview)} (исполнено {formatMoney(executedExpense)} +
              запланировано {formatMoney(pendingExpense)})
            </p>
          </div>
        </section>

        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Последние транзакции</h3>
          </div>
          <div className="list">
            {visibleTransactions.map((item) => (
              <article className="list-item" key={item.id}>
                <div>
                  <strong>{item.category}</strong>
                  <p>{item.comment || "Без комментария"}</p>
                </div>
                <div className={item.type === "income" ? "money plus" : "money minus"}>
                  {formatMoney(item.amount)}
                </div>
              </article>
            ))}
            {!visibleTransactions.length && (
              <p className="empty">
                {dashboard.isError
                  ? getQueryErrorMessage(dashboard.error, "Не удалось загрузить транзакции")
                  : "Исполненные транзакции появятся после запуска backend API."}
              </p>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3>Категории</h3>
          </div>
          <div className="chips">
            {categories.data?.map((category) => (
              <button
                className={quickCategoryId === category.id ? "chip chip-action active" : "chip chip-action"}
                key={category.id}
                onClick={() => handleCategoryClick(category.id)}
                style={{ borderColor: category.color }}
                type="button"
              >
                {category.name}
              </button>
            ))}
            {!categories.data?.length && (
              <p className="empty">
                {categories.isError
                  ? getQueryErrorMessage(categories.error, "Не удалось загрузить категории")
                  : "Категории будут загружаться из API."}
              </p>
            )}
          </div>

          {selectedCategory && (
            <form className="quick-entry-form" onSubmit={submitQuickEntry}>
              {selectedCategory.type === "both" && (
                <div className="toggle-row quick-entry-type">
                  <button
                    className={quickType === "expense" ? "toggle active" : "toggle"}
                    onClick={() => setQuickType("expense")}
                    type="button"
                  >
                    Расход
                  </button>
                  <button
                    className={quickType === "income" ? "toggle active" : "toggle"}
                    onClick={() => setQuickType("income")}
                    type="button"
                  >
                    Доход
                  </button>
                </div>
              )}

              <label className="field">
                <span>Сумма для {selectedCategory.name}</span>
                <input
                  autoFocus
                  inputMode="decimal"
                  onChange={(event) => setQuickAmount(event.target.value)}
                  placeholder="0"
                  value={quickAmount}
                />
              </label>
              <div className="action-row">
                <button className="primary-button" disabled={quickEntryMutation.isPending} type="submit">
                  {quickEntryMutation.isPending ? "Вносим..." : "Внести"}
                </button>
                <button
                  className="ghost-button"
                  disabled={quickEntryMutation.isPending}
                  onClick={handleCancelQuickEntry}
                  type="button"
                >
                  Отмена
                </button>
              </div>
              {quickError && <p className="form-error">{quickError}</p>}
            </form>
          )}

          {quickSuccess && <p className="form-status form-status-success">{quickSuccess}</p>}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3>Бюджетные акценты</h3>
          </div>
          <div className="list">
            {dashboard.data?.budget_highlights.map((item) => (
              <article className="list-item" key={item.category_id}>
                <div>
                  <strong>{item.category_name}</strong>
                  <p>{Math.round(item.percent)}% от лимита</p>
                </div>
                <div className={item.over_budget ? "money minus" : "money"}>
                  {formatMoney(item.remaining)}
                </div>
              </article>
            ))}
            {!dashboard.data?.budget_highlights.length && (
              <p className="empty">
                {dashboard.isError
                  ? getQueryErrorMessage(dashboard.error, "Не удалось загрузить бюджеты")
                  : "Бюджеты будут показаны после запуска API."}
              </p>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
