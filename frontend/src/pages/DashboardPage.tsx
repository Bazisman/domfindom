import { FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAccountPreferences,
  createAccount,
  createTransaction,
  getAccounts,
  getCategories,
  getDashboard,
  getFamilyDashboard,
  getFamilyTransactions,
  getSettings,
  getMyFamilies,
  updateAccount,
  updateSettings,
} from "../lib/api";
import { AutoCapitalSetupModal } from "../lib/AutoCapitalSetupModal";
import { evaluateAmountExpression } from "../lib/amountExpression";

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

function normalizeCarouselIndex(index: number, length: number) {
  return ((index % length) + length) % length;
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const quickEntryFormRef = useRef<HTMLFormElement | null>(null);
  const quickAmountInputRef = useRef<HTMLInputElement | null>(null);
  const balanceCarouselRef = useRef<HTMLDivElement | null>(null);
  const forecastCarouselRef = useRef<HTMLDivElement | null>(null);
  const balanceDragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startOffset: number;
    lastClientX: number;
    lastDirection: -1 | 0 | 1;
  } | null>(null);
  const forecastDragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startOffset: number;
    lastClientX: number;
    lastDirection: -1 | 0 | 1;
  } | null>(null);
  const balanceSettleFrameRef = useRef<number | null>(null);
  const balanceSettleStartRef = useRef<number | null>(null);
  const forecastSettleFrameRef = useRef<number | null>(null);
  const forecastSettleStartRef = useRef<number | null>(null);
  const balanceLogicalIndexRef = useRef(0);
  const forecastLogicalIndexRef = useRef(0);

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: getAccounts,
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
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
  const showFamilyCards = selectedFamilyId !== null;

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
    enabled: showFamilyCards,
    retry: false,
  });

  const [quickCategoryId, setQuickCategoryId] = useState<number | null>(null);
  const [quickAmount, setQuickAmount] = useState("");
  const [quickType, setQuickType] = useState<"income" | "expense">("expense");
  const [quickError, setQuickError] = useState<string | null>(null);
  const [quickSuccess, setQuickSuccess] = useState<string | null>(null);
  const [pendingIncomePayload, setPendingIncomePayload] = useState<Parameters<typeof createTransaction>[0] | null>(null);
  const [autoCapitalModalOpen, setAutoCapitalModalOpen] = useState(false);
  const [autoCapitalAccountName, setAutoCapitalAccountName] = useState("Копилка");
  const [autoCapitalDontAskAgain, setAutoCapitalDontAskAgain] = useState(false);
  const [autoCapitalError, setAutoCapitalError] = useState<string | null>(null);
  const [autoCapitalBusy, setAutoCapitalBusy] = useState(false);
  const [activeBalanceSlide, setActiveBalanceSlide] = useState(0);
  const [indicatorBalanceSlide, setIndicatorBalanceSlide] = useState(0);
  const [activeForecastSlide, setActiveForecastSlide] = useState(0);
  const [indicatorForecastSlide, setIndicatorForecastSlide] = useState(0);
  const [isBalanceDragging, setIsBalanceDragging] = useState(false);
  const [balanceDragOffset, setBalanceDragOffset] = useState(0);
  const [isForecastDragging, setIsForecastDragging] = useState(false);
  const [forecastDragOffset, setForecastDragOffset] = useState(0);

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

  const personalForecast = dashboard.data?.forecast;
  const personalBalance = dashboard.data?.balance;
  const familyForecast = familyDashboardQuery.data?.forecast;
  const familyBalance = familyDashboardQuery.data?.balance;
  const familyMemberMoney = familyDashboardQuery.data?.member_money ?? [];
  const personalCushionBalance = useMemo(
    () =>
      (accountsQuery.data ?? [])
        .filter((account) => account.type === "capital" && account.is_active && account.purpose !== "investment")
        .reduce((sum, account) => sum + account.balance, 0),
    [accountsQuery.data],
  );
  const personalInvestmentBalance = useMemo(
    () =>
      (accountsQuery.data ?? [])
        .filter((account) => account.type === "capital" && account.is_active && account.purpose === "investment")
        .reduce((sum, account) => sum + account.balance, 0),
    [accountsQuery.data],
  );
  const showFamilyBalanceSlide = showFamilyCards && familyBalance !== undefined;
  const showFamilyForecastSlide = showFamilyCards && familyForecast !== undefined;
  const desktopBalanceSlides = useMemo(
    () =>
      showFamilyBalanceSlide
        ? [
            normalizeCarouselIndex(activeBalanceSlide - 1, 2),
            normalizeCarouselIndex(activeBalanceSlide, 2),
            normalizeCarouselIndex(activeBalanceSlide + 1, 2),
          ]
        : [0],
    [activeBalanceSlide, showFamilyBalanceSlide],
  );
  const desktopForecastSlides = useMemo(
    () =>
      showFamilyForecastSlide
        ? [
            normalizeCarouselIndex(activeForecastSlide - 1, 2),
            normalizeCarouselIndex(activeForecastSlide, 2),
            normalizeCarouselIndex(activeForecastSlide + 1, 2),
          ]
        : [0],
    [activeForecastSlide, showFamilyForecastSlide],
  );

  const selectedCategory = useMemo(
    () => categories.data?.find((item) => item.id === quickCategoryId) ?? null,
    [categories.data, quickCategoryId],
  );

  const defaultCapitalAccount = useMemo(() => {
    const capitalAccounts = (accountsQuery.data ?? []).filter((item) => item.type === "capital" && item.is_active);
    const defaultAccountId = settingsQuery.data?.default_capital_account_id ?? null;
    return capitalAccounts.find((item) => item.id === defaultAccountId) ?? capitalAccounts.find((item) => item.is_default) ?? null;
  }, [accountsQuery.data, settingsQuery.data?.default_capital_account_id]);

  const quickEntryMutation = useMutation({
    mutationFn: createTransaction,
    onSuccess: async () => {
      setQuickSuccess("Операция добавлена");
      setQuickError(null);
      setQuickAmount("");
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

  const autoCapitalEnabled = Boolean(settingsQuery.data?.auto_capital_enabled && (settingsQuery.data?.auto_capital_percent ?? 0) > 0);

  function resetAutoCapitalModal() {
    setAutoCapitalModalOpen(false);
    setPendingIncomePayload(null);
    setAutoCapitalAccountName("Копилка");
    setAutoCapitalDontAskAgain(false);
    setAutoCapitalError(null);
    setAutoCapitalBusy(false);
  }

  async function maybeInterceptIncomeSubmission(payload: Parameters<typeof createTransaction>[0]) {
    if (payload.type !== "income") {
      return false;
    }

    const [latestSettings, latestAccounts, latestPreferences, latestFamilies] = await Promise.all([
      queryClient.fetchQuery({
        queryKey: ["settings"],
        queryFn: getSettings,
      }),
      queryClient.fetchQuery({
        queryKey: ["accounts"],
        queryFn: getAccounts,
      }),
      queryClient.fetchQuery({
        queryKey: ["account", "preferences"],
        queryFn: getAccountPreferences,
      }),
      queryClient.fetchQuery({
        queryKey: ["families", "me"],
        queryFn: getMyFamilies,
      }),
    ]);

    const latestAutoCapitalEnabled = Boolean(latestSettings.auto_capital_enabled && (latestSettings.auto_capital_percent ?? 0) > 0);
    const latestCapitalAccounts = latestAccounts.filter((item) => item.type === "capital" && item.is_active);
    const latestDefaultCapitalAccount =
      latestCapitalAccounts.find((item) => item.id === latestSettings.default_capital_account_id) ??
      latestCapitalAccounts.find((item) => item.is_default) ??
      null;

    if (!latestAutoCapitalEnabled) {
      return false;
    }

    const latestFamilyId = latestFamilies.families?.[0]?.id ?? null;
    if (latestPreferences.workspace_mode === "family" && latestFamilyId !== null) {
      const latestFamilyDashboard = await queryClient.fetchQuery({
        queryKey: ["families", latestFamilyId, "dashboard"],
        queryFn: () => getFamilyDashboard(latestFamilyId),
      });
      const target = latestFamilyDashboard.current_member_capital_target;
      const hasFamilyTarget = Boolean(
        target.target_owner_user_id &&
          target.target_capital_account_id &&
          latestFamilyDashboard.capital_accounts.some(
            (item) =>
              item.owner_user_id === target.target_owner_user_id &&
              item.capital_account_id === target.target_capital_account_id &&
              item.is_visible,
          ),
      );
      if (hasFamilyTarget) {
        return false;
      }
    }

    if (latestDefaultCapitalAccount) {
      return false;
    }

    setPendingIncomePayload({
      ...payload,
      auto_capital_percent: latestSettings.auto_capital_percent,
      capital_account_id: undefined,
    });
    setAutoCapitalModalOpen(true);
    setAutoCapitalAccountName("Копилка");
    setAutoCapitalDontAskAgain(false);
    setAutoCapitalError(null);
    return true;
  }

  async function handleAutoCapitalSkip() {
    if (!pendingIncomePayload) {
      resetAutoCapitalModal();
      return;
    }

    setAutoCapitalBusy(true);
    setAutoCapitalError(null);

    try {
      if (autoCapitalDontAskAgain) {
        await updateSettings({
          auto_capital_enabled: false,
        });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["settings"] }),
          queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        ]);
      }

      await quickEntryMutation.mutateAsync({
        ...pendingIncomePayload,
        auto_capital_percent: 0,
        capital_account_id: undefined,
      });
      resetAutoCapitalModal();
    } catch (error) {
      setAutoCapitalError(error instanceof Error ? error.message : "Не удалось сохранить доход без откладывания.");
      setAutoCapitalBusy(false);
    }
  }

  async function handleAutoCapitalCreateNow() {
    if (!pendingIncomePayload) {
      resetAutoCapitalModal();
      return;
    }

    const accountName = autoCapitalAccountName.trim();
    if (!accountName) {
      setAutoCapitalError("Укажите название подушки.");
      return;
    }

    setAutoCapitalBusy(true);
    setAutoCapitalError(null);

    try {
      const createdAccount = await createAccount({
        name: accountName,
      });
      await updateAccount(createdAccount.id, { is_default: true });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ]);

      await quickEntryMutation.mutateAsync({
        ...pendingIncomePayload,
        capital_account_id: createdAccount.id,
      });
      resetAutoCapitalModal();
    } catch (error) {
      setAutoCapitalError(error instanceof Error ? error.message : "Не удалось создать подушку.");
      setAutoCapitalBusy(false);
    }
  }

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
    if (balanceSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(balanceSettleFrameRef.current);
      balanceSettleFrameRef.current = null;
    }
    balanceSettleStartRef.current = null;
    balanceDragStateRef.current = null;
    const preferredSlide = useFamilyFeed && showFamilyBalanceSlide ? 1 : 0;
    setActiveBalanceSlide(preferredSlide);
    setIndicatorBalanceSlide(preferredSlide);
    balanceLogicalIndexRef.current = preferredSlide;
    setBalanceDragOffset(0);
  }, [selectedFamilyId, showFamilyBalanceSlide, useFamilyFeed]);

  useEffect(() => {
    if (forecastSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(forecastSettleFrameRef.current);
      forecastSettleFrameRef.current = null;
    }
    forecastSettleStartRef.current = null;
    forecastDragStateRef.current = null;
    const preferredSlide = useFamilyFeed && showFamilyForecastSlide ? 1 : 0;
    setActiveForecastSlide(preferredSlide);
    setIndicatorForecastSlide(preferredSlide);
    forecastLogicalIndexRef.current = preferredSlide;
    setForecastDragOffset(0);
  }, [selectedFamilyId, showFamilyForecastSlide, useFamilyFeed]);

  useEffect(() => {
    return () => {
      if (balanceSettleFrameRef.current !== null) {
        window.cancelAnimationFrame(balanceSettleFrameRef.current);
      }
      if (forecastSettleFrameRef.current !== null) {
        window.cancelAnimationFrame(forecastSettleFrameRef.current);
      }
    };
  }, []);

  async function submitQuickEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuickError(null);
    setQuickSuccess(null);

    if (!selectedCategory) {
      setQuickError("Выбери категорию.");
      return;
    }

    const amount = evaluateAmountExpression(quickAmount);
    if (amount === null || amount <= 0) {
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

    const payload: Parameters<typeof createTransaction>[0] = {
      type: transactionType,
      category_id: selectedCategory.id,
      amount,
      comment: `Быстрый ввод: ${selectedCategory.name}`,
      date: today,
      auto_capital_percent: transactionType === "income" && autoCapitalEnabled ? settingsQuery.data?.auto_capital_percent : undefined,
      capital_account_id: transactionType === "income" ? defaultCapitalAccount?.id : undefined,
    };

    if (await maybeInterceptIncomeSubmission(payload)) {
      return;
    }

    quickEntryMutation.mutate(payload);
  }

  function handleBalancePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!showFamilyBalanceSlide) {
      return;
    }
    const viewport = balanceCarouselRef.current;
    if (!viewport) {
      return;
    }
    if (balanceSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(balanceSettleFrameRef.current);
      balanceSettleFrameRef.current = null;
      setActiveBalanceSlide(indicatorBalanceSlide);
      balanceLogicalIndexRef.current = indicatorBalanceSlide;
      setBalanceDragOffset(0);
    }
    balanceSettleStartRef.current = null;
    balanceDragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startOffset: balanceDragOffset,
      lastClientX: event.clientX,
      lastDirection: 0,
    };
    event.preventDefault();
    setIsBalanceDragging(true);
    viewport.setPointerCapture(event.pointerId);
  }

  function handleBalancePointerMove(event: PointerEvent<HTMLDivElement>) {
    const viewport = balanceCarouselRef.current;
    const dragState = balanceDragStateRef.current;
    if (!viewport || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const deltaX = event.clientX - dragState.startX;
    const stepX = event.clientX - dragState.lastClientX;
    if (stepX !== 0) {
      dragState.lastDirection = stepX < 0 ? 1 : -1;
      dragState.lastClientX = event.clientX;
    }
    event.preventDefault();
    const maxOffset = Math.max((viewport.clientWidth || 1) * 0.92, 1);
    const nextOffset = dragState.startOffset + deltaX;
    setBalanceDragOffset(Math.max(-maxOffset, Math.min(maxOffset, nextOffset)));
  }

  function animateDesktopBalanceFlight(direction: -1 | 0 | 1) {
    const viewport = balanceCarouselRef.current;
    if (!viewport) {
      return;
    }
    const width = viewport.clientWidth || 1;
    const startOffset = balanceDragOffset;
    const targetOffset = direction === 0 ? 0 : direction > 0 ? -width : width;
    const nextIndex =
      direction === 0 ? balanceLogicalIndexRef.current : normalizeCarouselIndex(balanceLogicalIndexRef.current + direction, 2);
    if (direction !== 0) {
      setIndicatorBalanceSlide(nextIndex);
    }
    if (balanceSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(balanceSettleFrameRef.current);
    }
    balanceSettleStartRef.current = null;

    function animate(timestamp: number) {
      if (balanceSettleStartRef.current === null) {
        balanceSettleStartRef.current = timestamp;
      }
      const elapsed = timestamp - balanceSettleStartRef.current;
      const progress = Math.min(elapsed / 760, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setBalanceDragOffset(startOffset + (targetOffset - startOffset) * eased);

      if (progress < 1) {
        balanceSettleFrameRef.current = window.requestAnimationFrame(animate);
        return;
      }

      balanceLogicalIndexRef.current = nextIndex;
      setActiveBalanceSlide(nextIndex);
      setIndicatorBalanceSlide(nextIndex);
      setBalanceDragOffset(0);
      balanceSettleFrameRef.current = null;
      balanceSettleStartRef.current = null;
    }

    balanceSettleFrameRef.current = window.requestAnimationFrame(animate);
  }

  function finishBalanceDrag(event: PointerEvent<HTMLDivElement>) {
    const viewport = balanceCarouselRef.current;
    const dragState = balanceDragStateRef.current;
    if (!viewport || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    balanceDragStateRef.current = null;
    setIsBalanceDragging(false);
    if (viewport.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId);
    }
    const totalDeltaX = event.clientX - dragState.startX;
    const direction =
      dragState.lastDirection !== 0
        ? dragState.lastDirection
        : totalDeltaX <= -6
          ? 1
          : totalDeltaX >= 6
            ? -1
            : 0;
    animateDesktopBalanceFlight(direction);
  }

  function handleBalanceDotClick(logicalIndex: number) {
    if (!showFamilyBalanceSlide) {
      return;
    }
    const nextDirection = logicalIndex === normalizeCarouselIndex(activeBalanceSlide + 1, 2) ? 1 : -1;
    animateDesktopBalanceFlight(logicalIndex === activeBalanceSlide ? 0 : nextDirection);
  }

  function handleForecastPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!showFamilyForecastSlide) {
      return;
    }
    const viewport = forecastCarouselRef.current;
    if (!viewport) {
      return;
    }
    if (forecastSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(forecastSettleFrameRef.current);
      forecastSettleFrameRef.current = null;
      setActiveForecastSlide(indicatorForecastSlide);
      forecastLogicalIndexRef.current = indicatorForecastSlide;
      setForecastDragOffset(0);
    }
    forecastSettleStartRef.current = null;
    forecastDragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startOffset: forecastDragOffset,
      lastClientX: event.clientX,
      lastDirection: 0,
    };
    event.preventDefault();
    setIsForecastDragging(true);
    viewport.setPointerCapture(event.pointerId);
  }

  function handleForecastPointerMove(event: PointerEvent<HTMLDivElement>) {
    const viewport = forecastCarouselRef.current;
    const dragState = forecastDragStateRef.current;
    if (!viewport || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const deltaX = event.clientX - dragState.startX;
    const stepX = event.clientX - dragState.lastClientX;
    if (stepX !== 0) {
      dragState.lastDirection = stepX < 0 ? 1 : -1;
      dragState.lastClientX = event.clientX;
    }
    event.preventDefault();
    const maxOffset = Math.max((viewport.clientWidth || 1) * 0.92, 1);
    const nextOffset = dragState.startOffset + deltaX;
    setForecastDragOffset(Math.max(-maxOffset, Math.min(maxOffset, nextOffset)));
  }

  function animateDesktopForecastFlight(direction: -1 | 0 | 1) {
    const viewport = forecastCarouselRef.current;
    if (!viewport) {
      return;
    }
    const width = viewport.clientWidth || 1;
    const startOffset = forecastDragOffset;
    const targetOffset = direction === 0 ? 0 : direction > 0 ? -width : width;
    const nextIndex =
      direction === 0 ? forecastLogicalIndexRef.current : normalizeCarouselIndex(forecastLogicalIndexRef.current + direction, 2);
    if (direction !== 0) {
      setIndicatorForecastSlide(nextIndex);
    }
    if (forecastSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(forecastSettleFrameRef.current);
    }
    forecastSettleStartRef.current = null;

    function animate(timestamp: number) {
      if (forecastSettleStartRef.current === null) {
        forecastSettleStartRef.current = timestamp;
      }
      const elapsed = timestamp - forecastSettleStartRef.current;
      const progress = Math.min(elapsed / 760, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setForecastDragOffset(startOffset + (targetOffset - startOffset) * eased);

      if (progress < 1) {
        forecastSettleFrameRef.current = window.requestAnimationFrame(animate);
        return;
      }

      forecastLogicalIndexRef.current = nextIndex;
      setActiveForecastSlide(nextIndex);
      setIndicatorForecastSlide(nextIndex);
      setForecastDragOffset(0);
      forecastSettleFrameRef.current = null;
      forecastSettleStartRef.current = null;
    }

    forecastSettleFrameRef.current = window.requestAnimationFrame(animate);
  }

  function finishForecastDrag(event: PointerEvent<HTMLDivElement>) {
    const viewport = forecastCarouselRef.current;
    const dragState = forecastDragStateRef.current;
    if (!viewport || !dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    forecastDragStateRef.current = null;
    setIsForecastDragging(false);
    if (viewport.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId);
    }
    const totalDeltaX = event.clientX - dragState.startX;
    const direction =
      dragState.lastDirection !== 0
        ? dragState.lastDirection
        : totalDeltaX <= -6
          ? 1
          : totalDeltaX >= 6
            ? -1
            : 0;
    animateDesktopForecastFlight(direction);
  }

  function handleForecastDotClick(logicalIndex: number) {
    if (!showFamilyForecastSlide) {
      return;
    }
    const nextDirection = logicalIndex === normalizeCarouselIndex(activeForecastSlide + 1, 2) ? 1 : -1;
    animateDesktopForecastFlight(logicalIndex === activeForecastSlide ? 0 : nextDirection);
  }

  function renderPersonalBalanceSlide(key: string) {
    const personalReceivedIncome = personalBalance?.income ?? 0;
    const personalPendingIncome = personalForecast?.planned_income ?? 0;
    const personalExpectedIncomeTotal = personalReceivedIncome + personalPendingIncome;
    const personalExecutedExpense = personalBalance?.expense ?? 0;
    const personalPlannedExpenseTotal =
      (personalForecast?.total_budgets ?? personalForecast?.monthly_budget ?? 0) +
      (personalForecast?.planned_expense ?? 0);
    const personalIsExpenseOverPlan = personalExecutedExpense > personalPlannedExpenseTotal;
    const personalRemainingIncome = Math.max(personalExpectedIncomeTotal - personalReceivedIncome, 0);
    const personalRemainingExpense = personalPlannedExpenseTotal - personalExecutedExpense;
    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">Мои деньги</p>
        <h2>{dashboard.data?.balance.main_balance !== undefined ? formatMoney(dashboard.data.balance.main_balance) : "—"}</h2>
        <div className="money-breakdown-list" aria-label="Мои деньги по местам">
          <div className="money-breakdown-item">
            <span>На руках</span>
            <strong>{personalBalance ? formatMoney(personalBalance.main_balance) : "—"}</strong>
          </div>
          <div className="money-breakdown-item">
            <span>Моя подушка</span>
            <strong>{formatMoney(personalCushionBalance)}</strong>
          </div>
          <div className="money-breakdown-item">
            <span>Мои инвестиции</span>
            <strong>{formatMoney(personalInvestmentBalance)}</strong>
          </div>
        </div>
        <div className="stats-row">
          <div>
            <span>Доход за месяц (получено / план)</span>
            <strong>{dashboard.data ? `${formatMoney(personalReceivedIncome)} / ${formatMoney(personalExpectedIncomeTotal)}` : "—"}</strong>
            <p className="stat-note">Еще поступит: {formatMoney(personalRemainingIncome)}</p>
          </div>
          <div>
            <span>Расход за месяц (потрачено / план)</span>
            <strong className={personalIsExpenseOverPlan ? "money minus" : undefined}>
              {dashboard.data ? `${formatMoney(personalExecutedExpense)} / ${formatMoney(personalPlannedExpenseTotal)}` : "—"}
            </strong>
            <p className={personalIsExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
              {personalRemainingExpense >= 0
                ? `Еще предстоит потратить: ${formatMoney(personalRemainingExpense)}`
                : `Перерасход: ${formatMoney(Math.abs(personalRemainingExpense))}`}
            </p>
          </div>
        </div>
      </article>
    );
  }

  function renderFamilyBalanceSlide(key: string) {
    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">Деньги семьи</p>
        <h2>{familyBalance ? formatMoney(familyBalance.main_balance) : "—"}</h2>
        <div className="money-breakdown-list" aria-label="Деньги семьи по местам">
          <div className="money-breakdown-item">
            <span>На руках</span>
            <strong>{familyBalance ? formatMoney(familyBalance.main_balance) : "—"}</strong>
          </div>
          <div className="money-breakdown-item">
            <span>Подушка семьи</span>
            <strong>{familyBalance ? formatMoney(familyBalance.cushion_balance) : "—"}</strong>
          </div>
          <div className="money-breakdown-item">
            <span>Инвестиции семьи</span>
            <strong>{familyBalance ? formatMoney(familyBalance.investment_balance) : "—"}</strong>
          </div>
        </div>
        {!!familyMemberMoney.length && (
          <div className="family-money-list" aria-label="Деньги на руках у участников">
            {familyMemberMoney.map((member) => (
              <div className="family-money-item" key={member.user_id}>
                <span>{member.display_name || member.email}</span>
                <strong>{formatMoney(member.main_balance)}</strong>
              </div>
            ))}
          </div>
        )}
        <div className="stats-row">
          <div>
            <span>Доход семьи</span>
            <strong className="money plus">{familyBalance ? formatMoney(familyBalance.income) : "—"}</strong>
            <p className="stat-note">Сумма по всем участникам семьи</p>
          </div>
          <div>
            <span>Расход семьи</span>
            <strong className="money minus">{familyBalance ? formatMoney(familyBalance.expense) : "—"}</strong>
            <p className="stat-note">
              {familyDashboardQuery.data?.family_name
                ? `${familyDashboardQuery.data.family_name}: ${familyDashboardQuery.data.members_count ?? 0} участ.`
                : "Семейный режим"}
            </p>
          </div>
        </div>
      </article>
    );
  }

  function renderPersonalForecastSlide(key: string) {
    const personalForecastMonthLabel = getForecastMonthLabel(personalForecast?.end_date);

    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">Мой остаток на конец месяца</p>
        <h2>{personalForecast ? formatMoney(personalForecast.projected_balance) : "—"}</h2>
        <p className="stat-note">{personalForecast ? `На конец ${personalForecastMonthLabel}` : "Личный режим"}</p>
      </article>
    );
  }

  function renderFamilyForecastSlide(key: string) {
    const familyForecastMonthLabel = getForecastMonthLabel(familyForecast?.end_date);

    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">Остаток семьи на конец месяца</p>
        <h2>{familyForecast ? formatMoney(familyForecast.projected_balance) : "—"}</h2>
        <p className="stat-note">{familyForecast ? `На конец ${familyForecastMonthLabel}` : "Семейный режим"}</p>
      </article>
    );
  }

  return (
    <>
      <header className="hero">
        <div className="hero-copy">
          <h1>Домашняя бухгалтерия</h1>
          <p className="hero-text">
            Короткий обзор: сколько денег есть сейчас, сколько останется в конце месяца и что уже произошло.
          </p>
        </div>
      </header>

      <AutoCapitalSetupModal
        accountName={autoCapitalAccountName}
        busy={autoCapitalBusy || quickEntryMutation.isPending}
        dontAskAgain={autoCapitalDontAskAgain}
        error={autoCapitalError}
        onAccountNameChange={setAutoCapitalAccountName}
        onClose={resetAutoCapitalModal}
        onCreateNow={() => void handleAutoCapitalCreateNow()}
        onDontAskAgainChange={setAutoCapitalDontAskAgain}
        onSkip={() => void handleAutoCapitalSkip()}
        open={autoCapitalModalOpen}
        percent={settingsQuery.data?.auto_capital_percent ?? 0}
      />

      <main className="grid">
        <section className="panel panel-balance">
          <div className="balance-carousel" data-has-family-slide={showFamilyBalanceSlide ? "true" : "false"}>
            {showFamilyBalanceSlide ? (
              <div
                className="balance-carousel-viewport"
                onPointerDown={handleBalancePointerDown}
                onPointerMove={handleBalancePointerMove}
                onPointerUp={finishBalanceDrag}
                onPointerCancel={finishBalanceDrag}
                ref={balanceCarouselRef}
              >
                <div
                  className={isBalanceDragging ? "balance-carousel-track is-desktop is-dragging" : "balance-carousel-track is-desktop"}
                  style={{ transform: `translate3d(calc(-100% + ${balanceDragOffset}px), 0, 0)` }}
                >
                  {desktopBalanceSlides.map((slideIndex, index) =>
                    slideIndex === 0
                      ? renderPersonalBalanceSlide(`desktop-balance-${index}`)
                      : renderFamilyBalanceSlide(`desktop-balance-${index}`),
                  )}
                </div>
              </div>
            ) : (
              renderPersonalBalanceSlide("balance-personal-single")
            )}

            {showFamilyBalanceSlide ? (
              <div className="balance-carousel-nav" aria-label="Переключение карточек денег">
                <button
                  aria-label="Мои деньги"
                  className={indicatorBalanceSlide === 0 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => handleBalanceDotClick(0)}
                  type="button"
                />
                <button
                  aria-label="Деньги семьи"
                  className={indicatorBalanceSlide === 1 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => handleBalanceDotClick(1)}
                  type="button"
                />
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel panel-balance">
          <div className="balance-carousel" data-has-family-slide={showFamilyForecastSlide ? "true" : "false"}>
            {showFamilyForecastSlide ? (
              <div
                className="balance-carousel-viewport"
                onPointerDown={handleForecastPointerDown}
                onPointerMove={handleForecastPointerMove}
                onPointerUp={finishForecastDrag}
                onPointerCancel={finishForecastDrag}
                ref={forecastCarouselRef}
              >
                <div
                  className={isForecastDragging ? "balance-carousel-track is-desktop is-dragging" : "balance-carousel-track is-desktop"}
                  style={{ transform: `translate3d(calc(-100% + ${forecastDragOffset}px), 0, 0)` }}
                >
                  {desktopForecastSlides.map((slideIndex, index) =>
                    slideIndex === 0
                      ? renderPersonalForecastSlide(`desktop-forecast-${index}`)
                      : renderFamilyForecastSlide(`desktop-forecast-${index}`),
                  )}
                </div>
              </div>
            ) : (
              renderPersonalForecastSlide("forecast-personal-single")
            )}

            {showFamilyForecastSlide ? (
              <div className="balance-carousel-nav" aria-label="Переключение карточек остатка">
                  <button
                    aria-label="Мой остаток на конец месяца"
                    className={indicatorForecastSlide === 0 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                    onClick={() => handleForecastDotClick(0)}
                    type="button"
                  />
                  <button
                    aria-label="Остаток семьи на конец месяца"
                    className={indicatorForecastSlide === 1 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                    onClick={() => handleForecastDotClick(1)}
                    type="button"
                  />
                </div>
            ) : null}
          </div>
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
