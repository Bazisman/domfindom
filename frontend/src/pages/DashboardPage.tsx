import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAccountPreferences,
  createTransaction,
  getCategories,
  getDashboard,
  getFamilyDashboard,
  getFamilyTransactions,
  getMyFamilies,
} from "../lib/api";

type RecentFeedItem = {
  id: number;
  type: "income" | "expense";
  category: string;
  amount: number;
  comment: string;
  owner_display_name?: string;
  owner_email?: string;
  owner_user_id?: number;
};

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

function getForecastMonthLabel(endDate: string | undefined) {
  if (!endDate) {
    return "текущий месяц";
  }
  const date = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return "текущий месяц";
  }
  return date.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const quickEntryFormRef = useRef<HTMLFormElement | null>(null);
  const quickAmountInputRef = useRef<HTMLInputElement | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const preferencesQuery = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    retry: false,
  });

  const selectedFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
  const useFamilyFeed = selectedFamilyId !== null && preferencesQuery.data?.workspace_mode === "family";

  const familyTransactionsQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "transactions", "dashboard"],
    queryFn: () =>
      getFamilyTransactions({
        familyId: selectedFamilyId as number,
        limit: 10,
        includePlanned: false,
      }),
    enabled: useFamilyFeed,
    retry: false,
  });

  const familyDashboardQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "dashboard"],
    queryFn: () => getFamilyDashboard(selectedFamilyId as number),
    enabled: useFamilyFeed,
    retry: false,
  });

  const [quickCategoryId, setQuickCategoryId] = useState<number | null>(null);
  const [quickAmount, setQuickAmount] = useState("");
  const [quickType, setQuickType] = useState<"income" | "expense">("expense");
  const [quickError, setQuickError] = useState<string | null>(null);
  const [quickSuccess, setQuickSuccess] = useState<string | null>(null);

  const visibleTransactions = useMemo(() => {
    if (useFamilyFeed) {
      return (familyTransactionsQuery.data?.transactions ?? []).map(
        (item): RecentFeedItem => ({
          id: item.id,
          type: item.type,
          category: item.category,
          amount: item.amount,
          comment: item.comment,
          owner_display_name: item.owner_display_name,
          owner_email: item.owner_email,
          owner_user_id: item.owner_user_id,
        }),
      );
    }
    return (dashboard.data?.recent_transactions ?? []).map(
      (item): RecentFeedItem => ({
        id: item.id,
        type: item.type,
        category: item.category,
        amount: item.amount,
        comment: item.comment,
      }),
    );
  }, [useFamilyFeed, familyTransactionsQuery.data?.transactions, dashboard.data?.recent_transactions]);

  const receivedIncome = dashboard.data?.balance.income ?? 0;
  const pendingIncome = dashboard.data?.forecast.planned_income ?? 0;
  const expectedIncomeTotal = receivedIncome + pendingIncome;

  const executedExpense = dashboard.data?.balance.expense ?? 0;
  const plannedExpenseTotal =
    (dashboard.data?.forecast.total_budgets ?? dashboard.data?.forecast.monthly_budget ?? 0) +
    (dashboard.data?.forecast.planned_expense ?? 0);
  const isExpenseOverPlan = executedExpense > plannedExpenseTotal;
  const remainingIncome = Math.max(expectedIncomeTotal - receivedIncome, 0);
  const remainingExpense = plannedExpenseTotal - executedExpense;
  const forecastMonthLabel = getForecastMonthLabel(dashboard.data?.forecast.end_date);
  const familyBalance = familyDashboardQuery.data?.balance.main_balance ?? 0;
  const familyIncome = familyDashboardQuery.data?.balance.income ?? 0;
  const familyExpense = familyDashboardQuery.data?.balance.expense ?? 0;
  const familyDifference = familyDashboardQuery.data?.balance.difference ?? 0;
  const summaryBalance = useFamilyFeed ? familyBalance : (dashboard.data?.balance.main_balance ?? 0);
  const summaryHasError = useFamilyFeed ? familyDashboardQuery.isError : dashboard.isError;
  const summaryErrorMessage = useFamilyFeed
    ? getQueryErrorMessage(familyDashboardQuery.error, "Не удалось загрузить семейную сводку")
    : getQueryErrorMessage(dashboard.error, "Не удалось загрузить сводку");

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
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["budgets"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "transactions", "dashboard"] }),
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

  useEffect(() => {
    if (!selectedCategory) {
      return;
    }

    const scrollAndFocus = () => {
      quickEntryFormRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      quickAmountInputRef.current?.focus({ preventScroll: true });
      quickAmountInputRef.current?.select();
    };

    const rafId = window.requestAnimationFrame(scrollAndFocus);
    const timeoutId = window.setTimeout(scrollAndFocus, 160);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
    };
  }, [selectedCategory?.id]);

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
          <h1>Домашняя бухгалтерия</h1>
          <p className="hero-text">
            Короткий обзор месяца: текущий баланс, факт и план по доходам и расходам, быстрый ввод.
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="panel panel-balance">
          <p className="panel-label">{useFamilyFeed ? "Текущий семейный баланс" : "Текущий баланс"}</p>
          <h2>{summaryHasError ? "—" : formatMoney(summaryBalance)}</h2>
          <div className="stats-row">
            <div>
              <span>{useFamilyFeed ? "Доход семьи за месяц" : "Доход за месяц (получено / план)"}</span>
              <strong>
                {useFamilyFeed
                  ? formatMoney(familyIncome)
                  : dashboard.data
                    ? `${formatMoney(receivedIncome)} / ${formatMoney(expectedIncomeTotal)}`
                    : "—"}
              </strong>
              <p className="stat-note">
                {useFamilyFeed ? "Фактически получено всеми участниками семьи." : `Еще поступит: ${formatMoney(remainingIncome)}`}
              </p>
            </div>
            <div>
              <span>{useFamilyFeed ? "Расход семьи за месяц" : "Расход за месяц (потрачено / план)"}</span>
              <strong className={useFamilyFeed || isExpenseOverPlan ? "money minus" : undefined}>
                {useFamilyFeed
                  ? formatMoney(familyExpense)
                  : dashboard.data
                    ? `${formatMoney(executedExpense)} / ${formatMoney(plannedExpenseTotal)}`
                    : "—"}
              </strong>
              <p className={useFamilyFeed ? "stat-note" : isExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
                {useFamilyFeed
                  ? "Фактически потрачено всеми участниками семьи."
                  : remainingExpense >= 0
                    ? `Еще предстоит потратить: ${formatMoney(remainingExpense)}`
                    : `Перерасход: ${formatMoney(Math.abs(remainingExpense))}`}
              </p>
            </div>
          </div>
          {summaryHasError ? <p className="empty">{summaryErrorMessage}</p> : null}
        </section>

        <section className="panel">
          <p className="panel-label">{useFamilyFeed ? "Результат семьи за месяц" : "Баланс на конец месяца"}</p>
          <h2 className={useFamilyFeed && familyDifference < 0 ? "money minus" : undefined}>
            {useFamilyFeed ? formatMoney(familyDifference) : dashboard.data ? formatMoney(dashboard.data.forecast.projected_balance) : "—"}
          </h2>
          <p className="muted">
            {useFamilyFeed
              ? "Доходы семьи минус расходы семьи за текущий месяц."
              : dashboard.data
                ? `Прогноз на ${forecastMonthLabel}`
                : "Нужен backend на FastAPI"}
          </p>
        </section>

        <section className="panel panel-full">
          <div className="panel-header">
            <h3>Быстрый ввод по категориям</h3>
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
                  : "Категории пока не добавлены."}
              </p>
            )}
          </div>

          {selectedCategory && (
            <form className="quick-entry-form" onSubmit={submitQuickEntry} ref={quickEntryFormRef}>
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
                  ref={quickAmountInputRef}
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

        <section className="panel panel-full">
          <div className="panel-header">
            <h3>Последние транзакции</h3>
            {selectedFamilyId !== null ? <span>{useFamilyFeed ? "Совместные операции семьи" : "Личные операции"}</span> : null}
          </div>
          <div className="list">
            {visibleTransactions.map((item) => (
              <article className="list-item" key={`${item.owner_user_id ?? "self"}-${item.id}`}>
                <div>
                  <strong>{item.category}</strong>
                  <p>{item.comment || "Без комментария"}</p>
                </div>
                <div className="family-page-actions">
                  {item.owner_display_name || item.owner_email ? (
                    <span className="status-chip">{item.owner_display_name || item.owner_email}</span>
                  ) : null}
                  <div className={item.type === "income" ? "money plus" : "money minus"}>
                    {formatMoney(item.amount)}
                  </div>
                </div>
              </article>
            ))}
            {!visibleTransactions.length && (
              <p className="empty">
                {(useFamilyFeed ? familyTransactionsQuery.isError : dashboard.isError)
                  ? getQueryErrorMessage(
                      useFamilyFeed ? familyTransactionsQuery.error : dashboard.error,
                      "Не удалось загрузить транзакции",
                    )
                  : "Пока нет исполненных транзакций за выбранный период."}
              </p>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
