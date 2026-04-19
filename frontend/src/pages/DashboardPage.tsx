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
  const [pendingIncomePayload, setPendingIncomePayload] = useState<Parameters<typeof createTransaction>[0] | null>(null);
  const [autoCapitalModalOpen, setAutoCapitalModalOpen] = useState(false);
  const [autoCapitalAccountName, setAutoCapitalAccountName] = useState("РљРѕРїРёР»РєР°");
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
  const showFamilyBalanceSlide = useFamilyFeed && familyBalance !== undefined;
  const showFamilyForecastSlide = useFamilyFeed && familyForecast !== undefined;
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
      setQuickSuccess("РћРїРµСЂР°С†РёСЏ РґРѕР±Р°РІР»РµРЅР°");
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
    setAutoCapitalAccountName("РљРѕРїРёР»РєР°");
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
    setAutoCapitalAccountName("РљРѕРїРёР»РєР°");
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
      setAutoCapitalError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ РґРѕС…РѕРґ Р±РµР· Р°РІС‚РѕРѕС‚С‡РёСЃР»РµРЅРёР№.");
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
      setAutoCapitalError("РЈРєР°Р¶РёС‚Рµ РЅР°Р·РІР°РЅРёРµ СЃС‡РµС‚Р° РґР»СЏ Р°РІС‚РѕРѕС‚С‡РёСЃР»РµРЅРёР№.");
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
      setAutoCapitalError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ СЃС‡РµС‚ РґР»СЏ Р°РІС‚РѕРѕС‚С‡РёСЃР»РµРЅРёР№.");
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
    setActiveBalanceSlide(0);
    setIndicatorBalanceSlide(0);
    balanceLogicalIndexRef.current = 0;
    setBalanceDragOffset(0);
  }, [selectedFamilyId, showFamilyBalanceSlide]);

  useEffect(() => {
    if (forecastSettleFrameRef.current !== null) {
      window.cancelAnimationFrame(forecastSettleFrameRef.current);
      forecastSettleFrameRef.current = null;
    }
    forecastSettleStartRef.current = null;
    forecastDragStateRef.current = null;
    setActiveForecastSlide(0);
    setIndicatorForecastSlide(0);
    forecastLogicalIndexRef.current = 0;
    setForecastDragOffset(0);
  }, [selectedFamilyId, showFamilyForecastSlide]);

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
      setQuickError("Р’С‹Р±РµСЂРё РєР°С‚РµРіРѕСЂРёСЋ.");
      return;
    }

    const amount = evaluateAmountExpression(quickAmount);
    if (amount === null || amount <= 0) {
      setQuickError("РЈРєР°Р¶Рё СЃСѓРјРјСѓ Р±РѕР»СЊС€Рµ РЅСѓР»СЏ.");
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
      comment: `Р‘С‹СЃС‚СЂС‹Р№ РІРІРѕРґ: ${selectedCategory.name}`,
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
        <p className="panel-label">РўРµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ</p>
        <h2>{dashboard.data?.balance.main_balance !== undefined ? formatMoney(dashboard.data.balance.main_balance) : "вЂ”"}</h2>
        <div className="stats-row">
          <div>
            <span>Р”РѕС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕР»СѓС‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong>{dashboard.data ? `${formatMoney(personalReceivedIncome)} / ${formatMoney(personalExpectedIncomeTotal)}` : "вЂ”"}</strong>
            <p className="stat-note">Р•С‰Рµ РїРѕСЃС‚СѓРїРёС‚: {formatMoney(personalRemainingIncome)}</p>
          </div>
          <div>
            <span>Р Р°СЃС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕС‚СЂР°С‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong className={personalIsExpenseOverPlan ? "money minus" : undefined}>
              {dashboard.data ? `${formatMoney(personalExecutedExpense)} / ${formatMoney(personalPlannedExpenseTotal)}` : "вЂ”"}
            </strong>
            <p className={personalIsExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
              {personalRemainingExpense >= 0
                ? `Р•С‰Рµ РїСЂРµРґСЃС‚РѕРёС‚ РїРѕС‚СЂР°С‚РёС‚СЊ: ${formatMoney(personalRemainingExpense)}`
                : `РџРµСЂРµСЂР°СЃС…РѕРґ: ${formatMoney(Math.abs(personalRemainingExpense))}`}
            </p>
          </div>
        </div>
      </article>
    );
  }

  function renderFamilyBalanceSlide(key: string) {
    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">РўРµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ СЃРµРјСЊРё</p>
        <h2>{familyBalance ? formatMoney(familyBalance.main_balance) : "вЂ”"}</h2>
        <div className="stats-row">
          <div>
            <span>Р”РѕС…РѕРґ СЃРµРјСЊРё</span>
            <strong className="money plus">{familyBalance ? formatMoney(familyBalance.income) : "вЂ”"}</strong>
            <p className="stat-note">РЎСѓРјРјР° РїРѕ РІСЃРµРј СѓС‡Р°СЃС‚РЅРёРєР°Рј СЃРµРјСЊРё</p>
          </div>
          <div>
            <span>Р Р°СЃС…РѕРґ СЃРµРјСЊРё</span>
            <strong className="money minus">{familyBalance ? formatMoney(familyBalance.expense) : "вЂ”"}</strong>
            <p className="stat-note">
              {familyDashboardQuery.data?.family_name
                ? `${familyDashboardQuery.data.family_name}: ${familyDashboardQuery.data.members_count ?? 0} СѓС‡Р°СЃС‚.`
                : "РЎРµРјРµР№РЅС‹Р№ СЂРµР¶РёРј"}
            </p>
          </div>
        </div>
      </article>
    );
  }

  function renderPersonalForecastSlide(key: string) {
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
        <p className="panel-label">Р›РёС‡РЅС‹Р№ Р±Р°Р»Р°РЅСЃ РЅР° РєРѕРЅРµС† РјРµСЃСЏС†Р°</p>
        <h2>{personalForecast ? formatMoney(personalForecast.projected_balance) : "вЂ”"}</h2>
        <div className="stats-row">
          <div>
            <span>Р”РѕС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕР»СѓС‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong>{personalForecast ? `${formatMoney(personalReceivedIncome)} / ${formatMoney(personalExpectedIncomeTotal)}` : "вЂ”"}</strong>
            <p className="stat-note">Р•С‰Рµ РїРѕСЃС‚СѓРїРёС‚: {formatMoney(personalRemainingIncome)}</p>
          </div>
          <div>
            <span>Р Р°СЃС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕС‚СЂР°С‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong className={personalIsExpenseOverPlan ? "money minus" : undefined}>
              {personalForecast ? `${formatMoney(personalExecutedExpense)} / ${formatMoney(personalPlannedExpenseTotal)}` : "вЂ”"}
            </strong>
            <p className={personalIsExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
              {personalRemainingExpense >= 0
                ? `Р•С‰Рµ РїСЂРµРґСЃС‚РѕРёС‚ РїРѕС‚СЂР°С‚РёС‚СЊ: ${formatMoney(personalRemainingExpense)}`
                : `РџРµСЂРµСЂР°СЃС…РѕРґ: ${formatMoney(Math.abs(personalRemainingExpense))}`}
            </p>
          </div>
        </div>
      </article>
    );
  }

  function renderFamilyForecastSlide(key: string) {
    const familyReceivedIncome = familyBalance?.income ?? 0;
    const familyPendingIncome = familyForecast?.planned_income ?? 0;
    const familyExpectedIncomeTotal = familyReceivedIncome + familyPendingIncome;
    const familyExecutedExpense = familyBalance?.expense ?? 0;
    const familyPlannedExpenseTotal =
      (familyForecast?.total_budgets ?? familyForecast?.monthly_budget ?? 0) +
      (familyForecast?.planned_expense ?? 0);
    const familyIsExpenseOverPlan = familyExecutedExpense > familyPlannedExpenseTotal;
    const familyRemainingIncome = Math.max(familyExpectedIncomeTotal - familyReceivedIncome, 0);
    const familyRemainingExpense = familyPlannedExpenseTotal - familyExecutedExpense;

    return (
      <article className="balance-slide" key={key}>
        <p className="panel-label">РћР±С‰РёР№ Р±Р°Р»Р°РЅСЃ РЅР° РєРѕРЅРµС† РјРµСЃСЏС†Р°</p>
        <h2>{familyForecast ? formatMoney(familyForecast.projected_balance) : "вЂ”"}</h2>
        <div className="stats-row">
          <div>
            <span>Р”РѕС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕР»СѓС‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong>{familyForecast ? `${formatMoney(familyReceivedIncome)} / ${formatMoney(familyExpectedIncomeTotal)}` : "вЂ”"}</strong>
            <p className="stat-note">Р•С‰Рµ РїРѕСЃС‚СѓРїРёС‚: {formatMoney(familyRemainingIncome)}</p>
          </div>
          <div>
            <span>Р Р°СЃС…РѕРґ Р·Р° РјРµСЃСЏС† (РїРѕС‚СЂР°С‡РµРЅРѕ / РїР»Р°РЅ)</span>
            <strong className={familyIsExpenseOverPlan ? "money minus" : undefined}>
              {familyForecast ? `${formatMoney(familyExecutedExpense)} / ${formatMoney(familyPlannedExpenseTotal)}` : "вЂ”"}
            </strong>
            <p className={familyIsExpenseOverPlan ? "stat-note stat-note-alert" : "stat-note"}>
              {familyRemainingExpense >= 0
                ? `Р•С‰Рµ РїСЂРµРґСЃС‚РѕРёС‚ РїРѕС‚СЂР°С‚РёС‚СЊ: ${formatMoney(familyRemainingExpense)}`
                : `РџРµСЂРµСЂР°СЃС…РѕРґ: ${formatMoney(Math.abs(familyRemainingExpense))}`}
            </p>
          </div>
        </div>
      </article>
    );
  }

  return (
    <>
      <header className="hero">
        <div className="hero-copy">
          <h1>Р”РѕРјР°С€РЅСЏСЏ Р±СѓС…РіР°Р»С‚РµСЂРёСЏ</h1>
          <p className="hero-text">
            РљРѕСЂРѕС‚РєРёР№ РѕР±Р·РѕСЂ РјРµСЃСЏС†Р°: С‚РµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ, С„Р°РєС‚ Рё РїР»Р°РЅ РїРѕ РґРѕС…РѕРґР°Рј Рё СЂР°СЃС…РѕРґР°Рј, Р±С‹СЃС‚СЂС‹Р№ РІРІРѕРґ.
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
              <div className="balance-carousel-nav" aria-label="РџРµСЂРµРєР»СЋС‡РµРЅРёРµ РєР°СЂС‚РѕС‡РµРє Р±Р°Р»Р°РЅСЃР°">
                <button
                  aria-label="Р›РёС‡РЅС‹Р№ Р±Р°Р»Р°РЅСЃ"
                  className={indicatorBalanceSlide === 0 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => handleBalanceDotClick(0)}
                  type="button"
                />
                <button
                  aria-label="Р‘Р°Р»Р°РЅСЃ СЃРµРјСЊРё"
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
              <div className="balance-carousel-nav" aria-label="Переключение прогноза на конец месяца">
                <button
                  aria-label="Личный прогноз"
                  className={indicatorForecastSlide === 0 ? "balance-carousel-dot active" : "balance-carousel-dot"}
                  onClick={() => handleForecastDotClick(0)}
                  type="button"
                />
                <button
                  aria-label="Семейный прогноз"
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
            <h3>Р‘С‹СЃС‚СЂС‹Р№ РІРІРѕРґ РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј</h3>
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
                  ? getQueryErrorMessage(categories.error, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РєР°С‚РµРіРѕСЂРёРё")
                  : "РљР°С‚РµРіРѕСЂРёРё РїРѕРєР° РЅРµ РґРѕР±Р°РІР»РµРЅС‹."}
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
                    Р Р°СЃС…РѕРґ
                  </button>
                  <button
                    className={quickType === "income" ? "toggle active" : "toggle"}
                    onClick={() => setQuickType("income")}
                    type="button"
                  >
                    Р”РѕС…РѕРґ
                  </button>
                </div>
              )}

              <label className="field">
                <span>РЎСѓРјРјР° РґР»СЏ {selectedCategory.name}</span>
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
                  {quickEntryMutation.isPending ? "Р’РЅРѕСЃРёРј..." : "Р’РЅРµСЃС‚Рё"}
                </button>
                <button
                  className="ghost-button"
                  disabled={quickEntryMutation.isPending}
                  onClick={handleCancelQuickEntry}
                  type="button"
                >
                  РћС‚РјРµРЅР°
                </button>
              </div>
              {quickError && <p className="form-error">{quickError}</p>}
            </form>
          )}

          {quickSuccess && <p className="form-status form-status-success">{quickSuccess}</p>}
        </section>

        <section className="panel panel-full">
          <div className="panel-header">
            <h3>РџРѕСЃР»РµРґРЅРёРµ С‚СЂР°РЅР·Р°РєС†РёРё</h3>
            {selectedFamilyId !== null ? <span>{useFamilyFeed ? "РЎРѕРІРјРµСЃС‚РЅС‹Рµ РѕРїРµСЂР°С†РёРё СЃРµРјСЊРё" : "Р›РёС‡РЅС‹Рµ РѕРїРµСЂР°С†РёРё"}</span> : null}
          </div>
          <div className="list">
            {visibleTransactions.map((item) => (
              <article className="list-item" key={`${item.owner_user_id ?? "self"}-${item.id}`}>
                <div>
                  <strong>{item.category}</strong>
                  <p>{item.comment || "Р‘РµР· РєРѕРјРјРµРЅС‚Р°СЂРёСЏ"}</p>
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
                      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ С‚СЂР°РЅР·Р°РєС†РёРё",
                    )
                  : "РџРѕРєР° РЅРµС‚ РёСЃРїРѕР»РЅРµРЅРЅС‹С… С‚СЂР°РЅР·Р°РєС†РёР№ Р·Р° РІС‹Р±СЂР°РЅРЅС‹Р№ РїРµСЂРёРѕРґ."}
              </p>
            )}
          </div>
        </section>
      </main>
    </>
  );
}


