import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  applyReconciliation,
  getAccountPreferences,
  getFamilyDashboard,
  getFamilyMembers,
  getFamilyTransactions,
  getMe,
  getMyFamilies,
  createAccount,
  createReconciliationSource,
  createTransaction,
  deleteReconciliationSource,
  deleteTransaction,
  getAccounts,
  getCategories,
  getReconciliationSummary,
  getSettings,
  getTransactionsPage,
  updateAccount,
  updateReconciliationSource,
  updateSettings,
  type ReconciliationHistoryItem,
  type Transaction,
  type TransactionPage,
  type TransactionPeriod,
  type TransactionType,
} from "../lib/api";
import { AutoCapitalSetupModal } from "../lib/AutoCapitalSetupModal";
import { evaluateAmountExpression } from "../lib/amountExpression";

const PERIOD_OPTIONS: Array<{ value: TransactionPeriod; label: string }> = [
  { value: "all", label: "Все" },
  { value: "month", label: "Этот месяц" },
  { value: "last_month", label: "Прошлый месяц" },
  { value: "year", label: "Этот год" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50];

type FeedTransaction = Transaction & {
  owner_user_id?: number;
  owner_email?: string;
  owner_display_name?: string;
};

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function formatReconciliationDate(value: string) {
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function ownerChipStyle(ownerUserId: number) {
  const hue = Math.abs(ownerUserId * 57) % 360;
  return {
    borderColor: `hsla(${hue}, 70%, 56%, 0.45)`,
    background: `hsla(${hue}, 70%, 56%, 0.14)`,
    color: `hsl(${hue}, 80%, 72%)`,
  };
}

export function TransactionsPageNext() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<TransactionPeriod>("month");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [transactionsScope, setTransactionsScope] = useState<"all" | "mine" | `user:${number}`>("all");
  const [type, setType] = useState<TransactionType>("expense");
  const [showPlanned, setShowPlanned] = useState(false);
  const [categoryId, setCategoryId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [date, setDate] = useState(getToday);
  const [isRecurring, setIsRecurring] = useState(false);
  const [recurringName, setRecurringName] = useState("");
  const [recurringNameTouched, setRecurringNameTouched] = useState(false);
  const [recurringMonthsAhead, setRecurringMonthsAhead] = useState("12");
  const [recurringWorkingDaysOnly, setRecurringWorkingDaysOnly] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const [newSourceName, setNewSourceName] = useState("");
  const [newSourceBalance, setNewSourceBalance] = useState("");
  const [reconciliationError, setReconciliationError] = useState<string | null>(null);
  const [reconciliationMessage, setReconciliationMessage] = useState<string | null>(null);
  const [sourceDrafts, setSourceDrafts] = useState<Record<number, { name: string; balance: string }>>({});
  const [pendingIncomePayload, setPendingIncomePayload] = useState<Parameters<typeof createTransaction>[0] | null>(null);
  const [autoCapitalModalOpen, setAutoCapitalModalOpen] = useState(false);
  const [autoCapitalAccountName, setAutoCapitalAccountName] = useState("Копилка");
  const [autoCapitalDontAskAgain, setAutoCapitalDontAskAgain] = useState(false);
  const [autoCapitalError, setAutoCapitalError] = useState<string | null>(null);
  const [autoCapitalBusy, setAutoCapitalBusy] = useState(false);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: getAccounts,
  });

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const me = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });

  const families = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const preferences = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    retry: false,
  });

  const reconciliationSummary = useQuery({
    queryKey: ["reconciliation"],
    queryFn: getReconciliationSummary,
  });

  const selectedFamilyId = families.data?.families?.[0]?.id ?? null;
  const useFamilyFeed = selectedFamilyId !== null && preferences.data?.workspace_mode === "family";
  const pageOffset = page * pageSize;

  const familyMembers = useQuery({
    queryKey: ["families", selectedFamilyId, "members"],
    queryFn: () => getFamilyMembers(selectedFamilyId as number),
    enabled: useFamilyFeed,
    retry: false,
  });

  const scopedOwnerUserId = useMemo(() => {
    if (transactionsScope === "mine") {
      return me.data?.id ?? 0;
    }
    if (transactionsScope.startsWith("user:")) {
      const parsed = Number(transactionsScope.slice(5));
      return Number.isFinite(parsed) ? parsed : 0;
    }
    return 0;
  }, [me.data?.id, transactionsScope]);

  const transactions = useQuery({
    queryKey: ["transactions", "page", period, page, pageSize, showPlanned],
    queryFn: () => getTransactionsPage({ limit: pageSize, offset: pageOffset, period, includePlanned: showPlanned }),
    placeholderData: keepPreviousData,
    enabled: !useFamilyFeed,
  });

  const familyTransactions = useQuery({
    queryKey: ["families", selectedFamilyId, "transactions", period, page, pageSize, showPlanned, scopedOwnerUserId],
    queryFn: () =>
      getFamilyTransactions({
        familyId: selectedFamilyId as number,
        ownerUserId: scopedOwnerUserId > 0 ? scopedOwnerUserId : undefined,
        limit: pageSize,
        offset: pageOffset,
        period,
        includePlanned: showPlanned,
      }),
    placeholderData: keepPreviousData,
    enabled: useFamilyFeed,
    retry: false,
  });

  const filteredCategories = useMemo(() => {
    return (categories.data ?? []).filter((item) => item.type === type || item.type === "both");
  }, [categories.data, type]);

  const selectedCategoryName = useMemo(() => {
    return filteredCategories.find((item) => String(item.id) === categoryId)?.name ?? "";
  }, [categoryId, filteredCategories]);

  const defaultCapitalAccount = useMemo(() => {
    const capitalAccounts = (accounts.data ?? []).filter((item) => item.type === "capital" && item.is_active);
    const defaultAccountId = settings.data?.default_capital_account_id ?? null;
    return capitalAccounts.find((item) => item.id === defaultAccountId) ?? capitalAccounts.find((item) => item.is_default) ?? null;
  }, [accounts.data, settings.data?.default_capital_account_id]);

  const recurringSuggestedName = useMemo(() => {
    return comment.trim() || selectedCategoryName;
  }, [comment, selectedCategoryName]);

  useEffect(() => {
    if (isRecurring && !recurringNameTouched) {
      setRecurringName(recurringSuggestedName);
    }
  }, [isRecurring, recurringNameTouched, recurringSuggestedName]);

  useEffect(() => {
    const sources = reconciliationSummary.data?.sources ?? [];
    setSourceDrafts((current) => {
      const next: Record<number, { name: string; balance: string }> = {};
      for (const source of sources) {
        const existing = current[source.id];
        next[source.id] = {
          name: existing?.name ?? source.name,
          balance: existing?.balance ?? String(source.balance),
        };
      }
      return next;
    });
  }, [reconciliationSummary.data?.sources]);

  useEffect(() => {
    setPage(0);
  }, [period, showPlanned, useFamilyFeed, selectedFamilyId, pageSize, scopedOwnerUserId]);

  useEffect(() => {
    if (!useFamilyFeed) {
      setTransactionsScope("all");
    }
  }, [useFamilyFeed]);

  useEffect(() => {
    setTransactionsScope("all");
  }, [selectedFamilyId]);

  const transactionPage = useMemo<TransactionPage | null>(() => {
    if (useFamilyFeed) {
      return null;
    }
    return transactions.data ?? null;
  }, [transactions.data, useFamilyFeed]);

  const rawTransactions = useMemo<FeedTransaction[]>(() => {
    if (useFamilyFeed) {
      return (familyTransactions.data?.transactions ?? []).map((item) => ({
        ...item,
      }));
    }
    return ((transactionPage?.items ?? []) as Transaction[]).map((item) => ({
      ...item,
    }));
  }, [useFamilyFeed, familyTransactions.data?.transactions, transactionPage?.items]);

  const visibleTransactions = useMemo(() => rawTransactions, [rawTransactions]);
  const totalTransactions = useMemo(() => {
    if (useFamilyFeed) {
      return familyTransactions.data?.total ?? 0;
    }
    return transactionPage?.total ?? 0;
  }, [familyTransactions.data?.total, transactionPage?.total, useFamilyFeed]);
  const totalPages = Math.max(1, Math.ceil(totalTransactions / pageSize));
  const hasNextPage = page + 1 < totalPages;

  useEffect(() => {
    if (page >= totalPages) {
      setPage(Math.max(totalPages - 1, 0));
    }
  }, [page, totalPages]);

  const createMutation = useMutation({
    mutationFn: createTransaction,
    onSuccess: async () => {
      setAmount("");
      setComment("");
      setIsRecurring(false);
      setRecurringName("");
      setRecurringNameTouched(false);
      setRecurringMonthsAhead("12");
      setRecurringWorkingDaysOnly(true);
      setFormError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        queryClient.invalidateQueries({ queryKey: ["reconciliation"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "transactions"] }),
      ]);
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        queryClient.invalidateQueries({ queryKey: ["reconciliation"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "transactions"] }),
      ]);
    },
  });

  const createSourceMutation = useMutation({
    mutationFn: createReconciliationSource,
    onSuccess: async () => {
      setNewSourceName("");
      setNewSourceBalance("");
      setReconciliationError(null);
      setReconciliationMessage("Источник сверки добавлен.");
      await queryClient.invalidateQueries({ queryKey: ["reconciliation"] });
    },
    onError: (error: Error) => {
      setReconciliationMessage(null);
      setReconciliationError(error.message);
    },
  });

  const updateSourceMutation = useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: number; payload: { name?: string; balance?: number } }) =>
      updateReconciliationSource(sourceId, payload),
    onSuccess: async () => {
      setReconciliationError(null);
      await queryClient.invalidateQueries({ queryKey: ["reconciliation"] });
    },
    onError: (error: Error) => {
      setReconciliationMessage(null);
      setReconciliationError(error.message);
    },
  });

  const deleteSourceMutation = useMutation({
    mutationFn: deleteReconciliationSource,
    onSuccess: async () => {
      setReconciliationError(null);
      setReconciliationMessage("Источник сверки удален.");
      await queryClient.invalidateQueries({ queryKey: ["reconciliation"] });
    },
    onError: (error: Error) => {
      setReconciliationMessage(null);
      setReconciliationError(error.message);
    },
  });

  const applyReconciliationMutation = useMutation({
    mutationFn: applyReconciliation,
    onSuccess: async (response) => {
      setReconciliationError(null);
      setReconciliationMessage(response.message);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["reconciliation"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
      ]);
    },
    onError: (error: Error) => {
      setReconciliationMessage(null);
      setReconciliationError(error.message);
    },
  });

  const autoCapitalEnabled = Boolean(settings.data?.auto_capital_enabled && (settings.data?.auto_capital_percent ?? 0) > 0);

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

      await createMutation.mutateAsync({
        ...pendingIncomePayload,
        auto_capital_percent: 0,
        capital_account_id: undefined,
      });
      resetAutoCapitalModal();
    } catch (error) {
      setAutoCapitalError(error instanceof Error ? error.message : "Не удалось сохранить доход без автоотчислений.");
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
      setAutoCapitalError("Укажите название счета для автоотчислений.");
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

      await createMutation.mutateAsync({
        ...pendingIncomePayload,
        capital_account_id: createdAccount.id,
      });
      resetAutoCapitalModal();
    } catch (error) {
      setAutoCapitalError(error instanceof Error ? error.message : "Не удалось создать счет для автоотчислений.");
      setAutoCapitalBusy(false);
    }
  }

  const reconciliationDifference = reconciliationSummary.data?.difference ?? 0;
  const reconciliationDifferenceText =
    reconciliationDifference > 0
      ? `Фактических денег на ${formatMoney(Math.abs(reconciliationDifference))} больше`
      : reconciliationDifference < 0
        ? `Фактических денег на ${formatMoney(Math.abs(reconciliationDifference))} меньше`
        : "Фактический баланс совпадает с программой";

  function updateSourceDraft(sourceId: number, field: "name" | "balance", value: string) {
    setSourceDrafts((current) => ({
      ...current,
      [sourceId]: {
        name: field === "name" ? value : current[sourceId]?.name ?? "",
        balance: field === "balance" ? value : current[sourceId]?.balance ?? "",
      },
    }));
  }

  function commitSourceChanges(sourceId: number, initialName: string, initialBalance: number) {
    const draft = sourceDrafts[sourceId];
    if (!draft) {
      return;
    }
    const nextName = draft.name.trim();
    const normalizedBalance = Number(draft.balance.replace(",", ".").trim());
    const updates: { name?: string; balance?: number } = {};

    if (nextName && nextName !== initialName) {
      updates.name = nextName;
    }
    if (!Number.isNaN(normalizedBalance) && normalizedBalance !== initialBalance) {
      updates.balance = normalizedBalance;
    }
    if (Object.keys(updates).length === 0) {
      return;
    }

    setReconciliationMessage(null);
    setReconciliationError(null);
    updateSourceMutation.mutate({ sourceId, payload: updates });
  }

  function submitNewSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newSourceName.trim();
    if (!name) {
      setReconciliationMessage(null);
      setReconciliationError("Введите название источника.");
      return;
    }
    const balance = Number(newSourceBalance.replace(",", ".").trim() || "0");
    if (Number.isNaN(balance)) {
      setReconciliationMessage(null);
      setReconciliationError("Введите корректную сумму источника.");
      return;
    }
    createSourceMutation.mutate({ name, balance });
  }

  function renderHistoryItem(item: ReconciliationHistoryItem) {
    const differenceClass =
      item.difference > 0 ? "reconciliation-diff positive" : item.difference < 0 ? "reconciliation-diff negative" : "reconciliation-diff";
    const differenceLabel =
      item.difference > 0 ? `+${formatMoney(item.difference)}` : item.difference < 0 ? `-${formatMoney(Math.abs(item.difference))}` : formatMoney(0);

    return (
      <article className="reconciliation-history-item" key={item.id}>
        <div className="reconciliation-history-main">
          <strong>{formatReconciliationDate(item.created_at)}</strong>
          <span>Факт: {formatMoney(item.real_balance)}</span>
          <span>Программа: {formatMoney(item.program_balance)}</span>
        </div>
        <div className="reconciliation-history-meta">
          <strong className={differenceClass}>{differenceLabel}</strong>
          {item.adjustment_transaction_id ? <span>Корректировка #{item.adjustment_transaction_id}</span> : <span>Без корректировки</span>}
        </div>
      </article>
    );
  }

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const normalizedAmount = evaluateAmountExpression(amount);
    if (!categoryId) {
      setFormError("Выбери категорию.");
      return;
    }
    if (normalizedAmount === null || normalizedAmount <= 0) {
      setFormError("Укажи сумму больше нуля.");
      return;
    }
    if (isRecurring) {
      const normalizedMonthsAhead = Number(recurringMonthsAhead);
      if (!normalizedMonthsAhead || normalizedMonthsAhead < 1 || normalizedMonthsAhead > 24) {
        setFormError("Горизонт планирования должен быть от 1 до 24 месяцев.");
        return;
      }
    }

    const dayOfMonth = Number(date.split("-")[2] || "1");
    const templateName = recurringName.trim() || recurringSuggestedName;

    const payload: Parameters<typeof createTransaction>[0] = {
      type,
      category_id: Number(categoryId),
      amount: normalizedAmount,
      comment,
      date,
      auto_capital_percent: type === "income" && autoCapitalEnabled ? settings.data?.auto_capital_percent : undefined,
      capital_account_id: type === "income" ? defaultCapitalAccount?.id : undefined,
      recurring: isRecurring
        ? {
            enabled: true,
            template_name: templateName,
            day_of_month: dayOfMonth,
            months_ahead: Number(recurringMonthsAhead),
            working_days_only: recurringWorkingDaysOnly,
          }
        : undefined,
    };

    if (await maybeInterceptIncomeSubmission(payload)) {
      return;
    }

    createMutation.mutate(payload);
  }

  return (
    <main className="page-stack transactions-page-stack">
      <AutoCapitalSetupModal
        accountName={autoCapitalAccountName}
        busy={autoCapitalBusy || createMutation.isPending}
        dontAskAgain={autoCapitalDontAskAgain}
        error={autoCapitalError}
        onAccountNameChange={setAutoCapitalAccountName}
        onClose={resetAutoCapitalModal}
        onCreateNow={() => void handleAutoCapitalCreateNow()}
        onDontAskAgainChange={setAutoCapitalDontAskAgain}
        onSkip={() => void handleAutoCapitalSkip()}
        open={autoCapitalModalOpen}
        percent={settings.data?.auto_capital_percent ?? 0}
      />
      <div className="transactions-layout transactions-layout-stack">
        <section className="panel panel-form">
        <div className="panel-header">
          <h2>Новая транзакция</h2>
          <span>{type === "income" ? "Доход" : "Расход"}</span>
        </div>

        <form className="transaction-form" onSubmit={submitForm}>
          <div className="toggle-row">
            <button
              className={type === "expense" ? "toggle active" : "toggle"}
              onClick={() => setType("expense")}
              type="button"
            >
              Расход
            </button>
            <button
              className={type === "income" ? "toggle active" : "toggle"}
              onClick={() => setType("income")}
              type="button"
            >
              Доход
            </button>
          </div>

          <label className="field">
            <span>Категория</span>
            <select onChange={(event) => setCategoryId(event.target.value)} value={categoryId}>
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
                onChange={(event) => setAmount(event.target.value)}
                placeholder="0"
                value={amount}
              />
            </label>

            <label className="field">
              <span>Дата</span>
              <div className="date-shell">
                <input
                  className="date-input"
                  onClick={(event) => {
                    (event.currentTarget as HTMLInputElement & { showPicker?: () => void }).showPicker?.();
                  }}
                  onChange={(event) => setDate(event.target.value)}
                  type="date"
                  value={date}
                />
              </div>
            </label>
          </div>

          <label className="field">
            <span>Комментарий</span>
            <input
              onChange={(event) => setComment(event.target.value)}
              placeholder="Например, Магнит или Зарплата"
              value={comment}
            />
          </label>

          <label className="filter-check">
            <input
              checked={isRecurring}
              onChange={(event) => {
                const checked = event.target.checked;
                setIsRecurring(checked);
                if (checked) {
                  setRecurringNameTouched(false);
                  setRecurringName(recurringSuggestedName);
                } else {
                  setRecurringNameTouched(false);
                }
              }}
              type="checkbox"
            />
            <span>Повторяющаяся операция</span>
          </label>

          {isRecurring && (
            <>
              <p className="muted">
                После сохранения эта операция появится и в истории, и в разделе{" "}
                <strong>Планирование</strong>.
              </p>

              <label className="field">
                <span>Название шаблона</span>
                <input
                  onChange={(event) => {
                    setRecurringName(event.target.value);
                    setRecurringNameTouched(true);
                  }}
                  placeholder="Например, Основная зарплата"
                  value={recurringName}
                />
              </label>

              <div className="field-row">
                <label className="field">
                  <span>Повторять каждого</span>
                  <input disabled value={`${Number(date.split("-")[2] || "1")} числа`} />
                </label>

                <label className="field">
                  <span>Планировать вперёд</span>
                  <input
                    inputMode="numeric"
                    max="24"
                    min="1"
                    onChange={(event) => setRecurringMonthsAhead(event.target.value)}
                    type="number"
                    value={recurringMonthsAhead}
                  />
                </label>
              </div>

              <label className="filter-check">
                <input
                  checked={recurringWorkingDaysOnly}
                  onChange={(event) => setRecurringWorkingDaysOnly(event.target.checked)}
                  type="checkbox"
                />
                <span>Переносить на рабочий день</span>
              </label>
            </>
          )}

          {formError && <p className="form-error">{formError}</p>}

          <button className="primary-button" disabled={createMutation.isPending} type="submit">
            {createMutation.isPending ? "Сохраняем..." : "Добавить транзакцию"}
          </button>
        </form>
        </section>

        <section className="panel reconciliation-panel">
          <div className="panel-header">
            <h2>Сверка денег</h2>
            <span>
              {reconciliationSummary.data?.last_reconciliation
                ? `Последняя: ${formatReconciliationDate(reconciliationSummary.data.last_reconciliation.created_at)}`
                : "Сверок пока не было"}
            </span>
          </div>

          <div className="summary-grid summary-grid-3 reconciliation-summary-grid">
            <article className="summary-card reconciliation-stat-card">
              <span>Баланс в программе</span>
              <strong>{formatMoney(reconciliationSummary.data?.program_balance ?? 0)}</strong>
            </article>
            <article className="summary-card reconciliation-stat-card">
              <span>Фактический баланс</span>
              <strong>{formatMoney(reconciliationSummary.data?.real_balance ?? 0)}</strong>
            </article>
            <article className="summary-card reconciliation-stat-card">
              <span>Разница</span>
              <strong className={reconciliationDifference > 0 ? "money plus" : reconciliationDifference < 0 ? "money minus" : ""}>
                {reconciliationDifference > 0
                  ? `+${formatMoney(reconciliationDifference)}`
                  : reconciliationDifference < 0
                    ? `-${formatMoney(Math.abs(reconciliationDifference))}`
                    : formatMoney(0)}
              </strong>
            </article>
          </div>

          <p className="reconciliation-note">{reconciliationDifferenceText}</p>

          <form className="reconciliation-add-form" onSubmit={submitNewSource}>
            <label className="field">
              <span>Источник</span>
              <input onChange={(event) => setNewSourceName(event.target.value)} placeholder="Наличные, карта, банк" value={newSourceName} />
            </label>
            <label className="field">
              <span>Сумма</span>
              <input inputMode="decimal" onChange={(event) => setNewSourceBalance(event.target.value)} placeholder="0" value={newSourceBalance} />
            </label>
            <button className="primary-button" disabled={createSourceMutation.isPending} type="submit">
              {createSourceMutation.isPending ? "Добавляем..." : "Добавить источник"}
            </button>
          </form>

          <div className="reconciliation-sources">
            {(reconciliationSummary.data?.sources ?? []).map((source) => {
              const draft = sourceDrafts[source.id] ?? { name: source.name, balance: String(source.balance) };
              return (
                <article className="reconciliation-source-row" key={source.id}>
                  <label className="field">
                    <span>Название</span>
                    <input
                      onBlur={() => commitSourceChanges(source.id, source.name, source.balance)}
                      onChange={(event) => updateSourceDraft(source.id, "name", event.target.value)}
                      value={draft.name}
                    />
                  </label>
                  <label className="field">
                    <span>Сумма</span>
                    <input
                      inputMode="decimal"
                      onBlur={() => commitSourceChanges(source.id, source.name, source.balance)}
                      onChange={(event) => updateSourceDraft(source.id, "balance", event.target.value)}
                      value={draft.balance}
                    />
                  </label>
                  <button
                    className="ghost-button"
                    disabled={deleteSourceMutation.isPending}
                    onClick={() => deleteSourceMutation.mutate(source.id)}
                    type="button"
                  >
                    Удалить
                  </button>
                </article>
              );
            })}

            {!reconciliationSummary.isLoading && !reconciliationSummary.data?.sources.length && (
              <p className="empty">Добавьте источники фактических денег для сверки: наличные, карты, счета в банке.</p>
            )}
          </div>

          <div className="reconciliation-actions">
            <button
              className="primary-button"
              disabled={applyReconciliationMutation.isPending || reconciliationSummary.isLoading}
              onClick={() => applyReconciliationMutation.mutate()}
              type="button"
            >
              {applyReconciliationMutation.isPending ? "Сверяем..." : "Пересчитать и сохранить сверку"}
            </button>
            {reconciliationMessage ? <p className="form-status form-status-success">{reconciliationMessage}</p> : null}
            {reconciliationError ? <p className="form-error">{reconciliationError}</p> : null}
          </div>

          <div className="reconciliation-history">
            <div className="panel-header">
              <h3>История сверок</h3>
              <span>{reconciliationSummary.data?.history.length ?? 0}</span>
            </div>
            <div className="reconciliation-history-list">
              {(reconciliationSummary.data?.history ?? []).map(renderHistoryItem)}
              {!reconciliationSummary.isLoading && !reconciliationSummary.data?.history.length && (
                <p className="empty">История сверок появится после первого сохранения.</p>
              )}
            </div>
          </div>
        </section>

        <section className="panel panel-list">
        <div className="panel-header">
          <h2>История транзакций</h2>
          <div className="toolbar-group">
            {selectedFamilyId !== null ? <span>{useFamilyFeed ? "Совместные операции семьи" : "Личные операции"}</span> : null}
            <label className="filter-check">
              <input
                checked={showPlanned}
                onChange={(event) => setShowPlanned(event.target.checked)}
                type="checkbox"
              />
              <span>Показывать неисполненные</span>
            </label>
            {useFamilyFeed ? (
              <label className="field field-inline field-compact">
                <span>Участник</span>
                <select
                  onChange={(event) => {
                    const value = event.target.value;
                    if (value === "all" || value === "mine" || value.startsWith("user:")) {
                      setTransactionsScope(value as "all" | "mine" | `user:${number}`);
                    }
                  }}
                  value={transactionsScope}
                >
                  <option value="all">Все участники</option>
                  <option value="mine">Только мои</option>
                  {(familyMembers.data?.members ?? []).map((member) => (
                    <option key={member.user_id} value={`user:${member.user_id}`}>
                      {member.display_name || member.email}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <select
              className="period-select"
              onChange={(event) => setPeriod(event.target.value as TransactionPeriod)}
              value={period}
            >
              {PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <label className="field field-inline field-compact">
              <span>Строк на странице</span>
              <select onChange={(event) => setPageSize(Number(event.target.value))} value={pageSize}>
                {PAGE_SIZE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="transaction-table">
          {visibleTransactions.map((item) => (
            <article className="transaction-row" key={`${item.owner_user_id ?? "self"}-${item.id}`}>
              <div className="transaction-main">
                <div className="transaction-title-row">
                  <strong>{item.category}</strong>
                  {item.status === "planned" && <span className="status-chip">Не исполнено</span>}
                </div>
                <p>{item.comment || "Без комментария"}</p>
                {useFamilyFeed && (item.owner_display_name || item.owner_email) ? (
                  <p className="muted">Участник: {item.owner_display_name || item.owner_email}</p>
                ) : null}
              </div>
              <div className="transaction-meta">
                <span className="transaction-date">{item.date}</span>
                <strong className={item.type === "income" ? "money plus" : "money minus"}>
                  {formatMoney(item.amount)}
                </strong>
              </div>
              {!useFamilyFeed || item.owner_user_id === me.data?.id ? (
                <button
                  className="ghost-button"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(item.id)}
                  type="button"
                >
                  Удалить
                </button>
              ) : (
                <span className="muted">Только просмотр</span>
              )}
            </article>
          ))}

          {!visibleTransactions.length && (
            <p className="empty">
              {(useFamilyFeed ? familyTransactions.isLoading : transactions.isLoading)
                ? "Загружаем транзакции..."
                : showPlanned
                  ? "Транзакций пока нет для выбранного периода."
                  : "Исполненных транзакций пока нет для выбранного периода."}
            </p>
          )}
        </div>
        <div className="toolbar-group toolbar-group-between">
          <button
            className="ghost-button"
            disabled={page === 0}
            onClick={() => setPage((current) => Math.max(current - 1, 0))}
            type="button"
          >
            Назад
          </button>
          <span className="muted">Страница {page + 1}</span>
          <span className="muted">из {totalPages}</span>
          <button
            className="ghost-button"
            disabled={!hasNextPage}
            onClick={() => setPage((current) => current + 1)}
            type="button"
          >
            Вперед
          </button>
        </div>
        </section>
      </div>
    </main>
  );
}
