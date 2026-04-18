import { FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
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
  const balanceCarouselRef = useRef<HTMLDivElement | null>(null);
  const balanceDragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startScrollLeft: number;
  } | null>(null);
  const balanceSettleFrameRef = useRef<number | null>(null);
  const balanceSettleStartRef = useRef<number | null>(null);

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
    queryKey: ["families", selectedFamilyId, "dashboard", "home-balance"],
    queryFn: () => getFamilyDashboard(selectedFamilyId as number),
    enabled: useFamilyFeed,
    retry: false,
  });

  const [quickCategoryId, setQuickCategoryId] = useState<number | null>(null);
  const [quickAmount, setQuickAmount] = useState("");
  const [quickType, setQuickType] = useState<"income" | "expense">("expense");
  const [quickError, setQuickError] = useState<string | null>(null);
  const [quickSuccess, setQuickSuccess] = useState<string | null>(null);
  const [activeBalanceSlide, setActiveBalanceSlide] = useState(0);
  const [isBalanceDragging, setIsBalanceDragging] = useState(false);

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
  const familyBalance = familyDashboardQuery.data?.balance;
  const showFamilyBalanceSlide = useFamilyFeed && familyBalance !== undefined;

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
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
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

  useEffect(() => {
    setActiveBalanceSlide(0);
    if (balanceCarouselRef.current) {
      balanceCarouselRef.current.scrollTo({ left: 0, behavior: "auto" });
    }
  }, [showFamilyBalanceSlide, selectedFamilyId]);

  useEffect(() => {
    return () => {
      if (balanceSettleFrameRef.current !== null) {
        window.cancelAnimationFrame(balanceSettleFrameRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const node = balanceCarouselRef.current;
    if (!node || !showFamilyBalanceSlide) {
      return;
    }

    function syncActiveSlide() {
      const track = balanceCarouselRef.current;
      if (!track) {
        return;
      }
      const nextIndex = track.scrollLeft > track.clientWidth * 0.5 ? 1 : 0;
      setActiveBalanceSlide(nextIndex);
    }

    syncActiveSlide();
    node.addEventListener("scroll", syncActiveSlide, { passive: true });
    return () => node.removeEventListener("scroll", syncActiveSlide);
  }, [showFamilyBalanceSlide]);

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

  function handleBalancePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!showFamilyBalanceSlide || event.pointerType !== "mouse") {
      return;
    }
    const track = balanceCarouselRef.current;
    if (!track) {
      return;
    }
    balanceDragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startScrollLeft: track.scrollLeft,
    };
    event.preventDefault();
    setIsBalanceDragging(true);
    track.setPointerCapture(event.pointerId);
  }

  function handleBalancePointerMove(event: PointerEvent<HTMLDivElement>) {
    const track = balanceCarouselRef.current;
    const dragState = balanceDragStateRef.current;
    if (!track || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const deltaX = event.clientX - dragState.startX;
    event.preventDefault();
    track.scrollLeft = dragState.startScrollLeft - deltaX;
  }

  function finishBalanceDrag(event: PointerEvent<HTMLDivElement>) {
    const track = balanceCarouselRef.current;
    const dragState = balanceDragStateRef.current;
    if (!track || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    balanceDragStateRef.current = null;
    setIsBalanceDragging(false);
    if (track.hasPointerCapture(event.pointerId)) {
      track.releasePointerCapture(event.pointerId);
    }
    const slideWidth = track.clientWidth || 1;
    const nextIndex = Math.round(track.scrollLeft / slideWidth);
    const startLeft = track.scrollLeft;
    const targetLeft = nextIndex * slideWidth;
    const delta = targetLeft - startLeft;
    const direction = delta === 0 ? 0 : delta > 0 ? 1 : -1;
    const needsOvershoot = direction !== 0 && Math.abs(delta) < 72;
    const overshootLeft = needsOvershoot ? targetLeft + direction * 28 : targetLeft;
    const firstPhaseDuration = needsOvershoot ? 320 : 720;
    const secondPhaseDuration = needsOvershoot ? 320 : 0;
    const settleTrack = track;
    if (balanceSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(balanceSettleFrameRef.current);
    }
    balanceSettleStartRef.current = null;

    function animateBetween(
      fromLeft: number,
      toLeft: number,
      duration: number,
      timestamp: number,
      onComplete?: () => void,
    ) {
      if (balanceSettleStartRef.current === null) {
        balanceSettleStartRef.current = timestamp;
      }
      const elapsed = timestamp - balanceSettleStartRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      settleTrack.scrollLeft = fromLeft + (toLeft - fromLeft) * eased;

      if (progress < 1) {
        balanceSettleFrameRef.current = window.requestAnimationFrame((nextTimestamp) => {
          animateBetween(fromLeft, toLeft, duration, nextTimestamp, onComplete);
        });
        return;
      }

      settleTrack.scrollLeft = toLeft;
      balanceSettleStartRef.current = null;
      if (onComplete) {
        onComplete();
        return;
      }
      balanceSettleFrameRef.current = null;
    }

    balanceSettleFrameRef.current = window.requestAnimationFrame((timestamp) => {
      animateBetween(startLeft, overshootLeft, firstPhaseDuration, timestamp, () => {
        if (!needsOvershoot) {
          balanceSettleFrameRef.current = null;
          return;
        }
        balanceSettleFrameRef.current = window.requestAnimationFrame((nextTimestamp) => {
          animateBetween(overshootLeft, targetLeft, secondPhaseDuration, nextTimestamp);
        });
      });
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
          <div className="balance-carousel" data-has-family-slide={showFamilyBalanceSlide ? "true" : "false"}>
            <div
              className={isBalanceDragging ? "balance-carousel-track is-dragging" : "balance-carousel-track"}
              onPointerDown={handleBalancePointerDown}
              onPointerMove={handleBalancePointerMove}
              onPointerUp={finishBalanceDrag}
              onPointerCancel={finishBalanceDrag}
              ref={balanceCarouselRef}
            >
              <article className="balance-slide">
                <p className="panel-label">Текущий баланс</p>
                <h2>{dashboard.data ? formatMoney(dashboard.data.balance.main_balance) : "—"}</h2>
                <div className="stats-row">
                  <div>
                    <span>Доход за месяц (получено / план)</span>
                    <strong>
                      {dashboard.data
                        ? `${formatMoney(receivedIncome)} / ${formatMoney(expectedIncomeTotal)}`
                        : "—"}
                    </strong>
                    <p className="stat-note">
                      Еще поступит: {formatMoney(remainingIncome)}
                    </p>
                  </div>
                  <div>
                    <span>Расход за месяц (потрачено / план)</span>
                    <strong className={isExpenseOverPlan ? "money minus" : undefined}>
                      {dashboard.data
                        ? `${formatMoney(executedExpense)} / ${formatMoney(plannedExpenseTotal)}`
                        : "—"}
                    </strong>
                    <p className={isExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
                      {remainingExpense >= 0
                        ? `Еще предстоит потратить: ${formatMoney(remainingExpense)}`
                        : `Перерасход: ${formatMoney(Math.abs(remainingExpense))}`}
                    </p>
                  </div>
                </div>
              </article>

              {showFamilyBalanceSlide ? (
                <article className="balance-slide">
                  <p className="panel-label">Текущий баланс семьи</p>
                  <h2>{formatMoney(familyBalance.main_balance)}</h2>
                  <div className="stats-row">
                    <div>
                      <span>Доход семьи</span>
                      <strong className="money plus">{formatMoney(familyBalance.income)}</strong>
                      <p className="stat-note">
                        Сумма по всем участникам семьи
                      </p>
                    </div>
                    <div>
                      <span>Расход семьи</span>
                      <strong className="money minus">{formatMoney(familyBalance.expense)}</strong>
                      <p className="stat-note">
                        {familyDashboardQuery.data
                          ? `${familyDashboardQuery.data.family_name}: ${familyDashboardQuery.data.members_count} участ.`
                          : "Семейный режим"}
                      </p>
                    </div>
                  </div>
                </article>
              ) : null}
            </div>

            {showFamilyBalanceSlide ? (
              <div className="balance-carousel-nav" aria-label="Переключение карточек баланса">
                <button
                  aria-label="Личный баланс"
                  className={activeBalanceSlide === 0 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => balanceCarouselRef.current?.scrollTo({ left: 0, behavior: "smooth" })}
                  type="button"
                />
                <button
                  aria-label="Баланс семьи"
                  className={activeBalanceSlide === 1 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => balanceCarouselRef.current?.scrollTo({ left: balanceCarouselRef.current.clientWidth, behavior: "smooth" })}
                  type="button"
                />
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <p className="panel-label">Баланс на конец месяца</p>
          <h2>{dashboard.data ? formatMoney(dashboard.data.forecast.projected_balance) : "—"}</h2>
          <p className="muted">{dashboard.data ? `Прогноз на ${forecastMonthLabel}` : "Нужен backend на FastAPI"}</p>
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
