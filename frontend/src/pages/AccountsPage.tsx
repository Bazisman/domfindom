import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAccount,
  createTransfer,
  deleteAccount,
  getAccountPreferences,
  getAccounts,
  getFamilyCapitalHistory,
  getFamilyDashboard,
  getMe,
  getMyFamilies,
  getSettings,
  getTransfers,
  updateAccount,
  updateFamilyCapitalTarget,
  updateSettings,
  type Account,
} from "../lib/api";

const ACCOUNT_COLORS = [
  "#ff9800",
  "#1d8f61",
  "#3578e5",
  "#9b51e0",
  "#c15445",
  "#0ea5a8",
];

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

function getInitialAccountForm() {
  return {
    name: "",
    balance: "",
    color: ACCOUNT_COLORS[0],
  };
}

export function AccountsPage() {
  const queryClient = useQueryClient();
  const [editingAccountId, setEditingAccountId] = useState<number | null>(null);
  const [accountForm, setAccountForm] = useState(getInitialAccountForm);
  const [transferForm, setTransferForm] = useState({
    fromAccountId: "",
    toAccountId: "",
    amount: "",
    date: getToday(),
    comment: "",
  });
  const [accountError, setAccountError] = useState<string | null>(null);
  const [transferError, setTransferError] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSavedNotice, setSettingsSavedNotice] = useState(false);
  const [autoCapitalEnabled, setAutoCapitalEnabled] = useState(true);
  const [autoCapitalPercent, setAutoCapitalPercent] = useState("10");
  const [selectedTargetKey, setSelectedTargetKey] = useState("");
  const [savingAutoCapitalTargetKey, setSavingAutoCapitalTargetKey] = useState<string | null>(null);
  const [settingsHydrated, setSettingsHydrated] = useState(false);
  const lastSavedSettingsRef = useRef<{ enabled: boolean; percent: string } | null>(null);
  const lastRequestedSettingsRef = useRef<{ enabled: boolean; percent: string } | null>(null);
  const settingsSavedNoticeTimeoutRef = useRef<number | null>(null);
  const accountFormPanelRef = useRef<HTMLElement | null>(null);
  const accountNameInputRef = useRef<HTMLInputElement | null>(null);
  const me = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });
  const isReady = me.status === "success" && Boolean(me.data?.id);

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: getAccounts,
    enabled: isReady,
    retry: 2,
    refetchOnMount: "always",
  });

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    enabled: isReady,
    retry: 2,
    refetchOnMount: "always",
  });

  const families = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    enabled: isReady,
    retry: 2,
    refetchOnMount: "always",
  });

  const preferences = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    enabled: isReady,
    retry: 2,
    refetchOnMount: "always",
  });

  const transfers = useQuery({
    queryKey: ["transfers", "all"],
    queryFn: () => getTransfers({ limit: 20 }),
    enabled: isReady,
    retry: 2,
    refetchOnMount: "always",
  });

  const accountsError = accounts.error instanceof Error ? accounts.error.message : null;
  const transfersError = transfers.error instanceof Error ? transfers.error.message : null;
  const isAccountsPending = me.isPending || (isReady && accounts.isPending);
  const isTransfersPending = me.isPending || (isReady && transfers.isPending);
  const selectedFamilyId = families.data?.families?.[0]?.id ?? null;

  const familyDashboard = useQuery({
    queryKey: ["families", selectedFamilyId, "dashboard", "accounts-page"],
    queryFn: () => getFamilyDashboard(selectedFamilyId as number),
    enabled: isReady && selectedFamilyId !== null,
    retry: 2,
    refetchOnMount: "always",
  });

  const familyCapitalHistory = useQuery({
    queryKey: ["families", selectedFamilyId, "capital-history"],
    queryFn: () => getFamilyCapitalHistory(selectedFamilyId as number),
    enabled: isReady && selectedFamilyId !== null,
    retry: 2,
    refetchOnMount: "always",
  });

  const capitalAccounts = useMemo(
    () => (accounts.data ?? []).filter((item) => item.type === "capital"),
    [accounts.data],
  );

  const cashlessAccount = useMemo(
    () => (accounts.data ?? []).find((item) => item.money_source === "cashless" || item.id === 1) ?? null,
    [accounts.data],
  );

  const cashAccount = useMemo(
    () => (accounts.data ?? []).find((item) => item.money_source === "cash" || item.id === 2) ?? null,
    [accounts.data],
  );

  const dailyBalance = (cashlessAccount?.balance ?? 0) + (cashAccount?.balance ?? 0);

  const ownCapital = useMemo(
    () => capitalAccounts.filter((item) => item.is_active).reduce((sum, account) => sum + account.balance, 0),
    [capitalAccounts],
  );

  const transferAccounts = useMemo(
    () => (accounts.data ?? []).filter((item) => item.is_active),
    [accounts.data],
  );
  const selectedTransferFromAccount = useMemo(
    () => transferAccounts.find((account) => String(account.id) === transferForm.fromAccountId) ?? null,
    [transferAccounts, transferForm.fromAccountId],
  );
  const selectedTransferToAccount = useMemo(
    () => transferAccounts.find((account) => String(account.id) === transferForm.toAccountId) ?? null,
    [transferAccounts, transferForm.toAccountId],
  );
  const transferMeaning = useMemo(() => {
    if (!selectedTransferFromAccount || !selectedTransferToAccount) {
      return null;
    }
    const fromIsDaily = selectedTransferFromAccount.type !== "capital";
    const toIsDaily = selectedTransferToAccount.type !== "capital";
    if (fromIsDaily && !toIsDaily) {
      return "Это не расход: деньги уйдут из трат в подушку.";
    }
    if (!fromIsDaily && toIsDaily) {
      return "Деньги вернутся из подушки в траты.";
    }
    if (fromIsDaily && toIsDaily) {
      return "Это просто перенос между деньгами на руках.";
    }
    return "Это перенос между подушками.";
  }, [selectedTransferFromAccount, selectedTransferToAccount]);

  const defaultPersonalCapitalAccount = useMemo(
    () =>
      capitalAccounts.find((account) => account.id === settings.data?.default_capital_account_id) ??
      capitalAccounts.find((account) => account.is_default) ??
      null,
    [capitalAccounts, settings.data?.default_capital_account_id],
  );
  const familyTarget = useMemo(() => {
    const target = familyDashboard.data?.current_member_capital_target;
    if (!target?.target_owner_user_id || !target?.target_capital_account_id) {
      return null;
    }
    return (
      familyDashboard.data?.capital_accounts.find(
        (item) =>
          item.owner_user_id === target.target_owner_user_id &&
          item.capital_account_id === target.target_capital_account_id,
      ) ?? null
    );
  }, [familyDashboard.data]);
  const familyVisibleAccounts = familyDashboard.data?.capital_accounts ?? [];
  const familyCapitalBalance = familyDashboard.data?.balance.capital_balance ?? 0;
  const familyDailyBalance = familyDashboard.data?.balance.main_balance ?? 0;
  const familyForecastBalance = familyDashboard.data?.forecast.projected_balance ?? null;
  const familyModeEnabled = selectedFamilyId !== null && preferences.data?.workspace_mode === "family";
  const personalCashOnHand = dailyBalance;
  const personalTotalVisibleMoney = dailyBalance + ownCapital;
  const visibleEmergencyMoney = familyModeEnabled ? familyCapitalBalance : ownCapital;
  const visibleDailyMoney = familyModeEnabled ? familyDailyBalance : dailyBalance;
  const moneyPlaces = useMemo(() => {
    const places: Array<{
      key: string;
      name: string;
      tone: string;
      balance: number;
      color: string;
    }> = [];
    if (cashlessAccount) {
      places.push({
        key: `daily:${cashlessAccount.id}`,
        name: cashlessAccount.name || "Для трат",
        tone: "Мои деньги на каждый день",
        balance: cashlessAccount.balance,
        color: cashlessAccount.color ?? "#3578e5",
      });
    }
    if (cashAccount) {
      places.push({
        key: `daily:${cashAccount.id}`,
        name: cashAccount.name || "Наличные",
        tone: "Деньги на руках",
        balance: cashAccount.balance,
        color: cashAccount.color ?? "#1d8f61",
      });
    }
    capitalAccounts
      .filter((account) => account.is_active)
      .forEach((account) => {
        places.push({
          key: `personal:${account.id}`,
          name: account.name,
          tone: "Моя подушка",
          balance: account.balance,
          color: account.color ?? "#5f6b76",
        });
      });
    familyVisibleAccounts.forEach((account) => {
      const ownerLabel = account.owner_display_name || account.owner_email || "Семья";
      places.push({
        key: `family:${account.owner_user_id}:${account.capital_account_id}`,
        name: account.name,
        tone: `Подушка семьи · ${ownerLabel}`,
        balance: account.balance,
        color: account.color ?? "#5f6b76",
      });
    });
    return places;
  }, [capitalAccounts, cashAccount, cashlessAccount, familyVisibleAccounts]);
  const personalAccountsPublishedToFamily = useMemo(
    () =>
      new Set(
        familyVisibleAccounts
          .filter((account) => account.owner_user_id === me.data?.id)
          .map((account) => account.capital_account_id),
      ),
    [familyVisibleAccounts, me.data?.id],
  );
  const autoCapitalTargetOptions = useMemo(
    () => [
      ...capitalAccounts
        .filter((account) => account.is_active && !personalAccountsPublishedToFamily.has(account.id))
        .map((account) => ({
          key: `personal:${account.id}`,
          label: account.name,
          description: "Личная подушка",
        })),
      ...familyVisibleAccounts.map((account) => ({
        key: `family:${account.owner_user_id}:${account.capital_account_id}`,
        label: account.name,
        description: `Подушка семьи · ${account.owner_display_name || account.owner_email || "Семья"}`,
      })),
    ],
    [capitalAccounts, familyVisibleAccounts, personalAccountsPublishedToFamily],
  );
  const currentAutoCapitalTargetKey = useMemo(() => {
    if (familyTarget) {
      return `family:${familyTarget.owner_user_id}:${familyTarget.capital_account_id}`;
    }
    if (defaultPersonalCapitalAccount) {
      const publishedFamilyAccount = familyVisibleAccounts.find(
        (account) =>
          account.owner_user_id === me.data?.id && account.capital_account_id === defaultPersonalCapitalAccount.id,
      );
      if (publishedFamilyAccount) {
        return `family:${publishedFamilyAccount.owner_user_id}:${publishedFamilyAccount.capital_account_id}`;
      }
      return `personal:${defaultPersonalCapitalAccount.id}`;
    }
    return "";
  }, [defaultPersonalCapitalAccount, familyTarget, familyVisibleAccounts, me.data?.id]);
  const effectiveAutoCapitalTargetKey = savingAutoCapitalTargetKey ?? currentAutoCapitalTargetKey;
  const activeAutoCapitalTarget = useMemo(() => {
    if (effectiveAutoCapitalTargetKey.startsWith("personal:")) {
      const accountId = Number(effectiveAutoCapitalTargetKey.slice("personal:".length));
      const account = capitalAccounts.find((item) => item.id === accountId) ?? null;
      if (!account) {
        return null;
      }
      return {
        key: effectiveAutoCapitalTargetKey,
        name: account.name,
        balance: account.balance,
        color: account.color ?? "#5f6b76",
        tone: "Личная подушка",
      };
    }
    if (effectiveAutoCapitalTargetKey.startsWith("family:")) {
      const [, ownerRaw, accountRaw] = effectiveAutoCapitalTargetKey.split(":");
      const ownerUserId = Number(ownerRaw);
      const capitalAccountId = Number(accountRaw);
      const account =
        familyVisibleAccounts.find(
          (item) => item.owner_user_id === ownerUserId && item.capital_account_id === capitalAccountId,
        ) ?? null;
      if (!account) {
        return null;
      }
      const ownerLabel = account.owner_display_name || account.owner_email || "Семья";
      return {
        key: effectiveAutoCapitalTargetKey,
        name: account.name,
        balance: account.balance,
        color: account.color ?? "#5f6b76",
        tone: `Подушка семьи · ${ownerLabel}`,
      };
    }
    return null;
  }, [capitalAccounts, effectiveAutoCapitalTargetKey, familyVisibleAccounts]);

  useEffect(() => {
    setSelectedTargetKey(effectiveAutoCapitalTargetKey);
  }, [effectiveAutoCapitalTargetKey]);

  useEffect(() => {
    if (!settings.data) {
      return;
    }
    setAutoCapitalEnabled(settings.data.auto_capital_enabled);
    setAutoCapitalPercent(String(settings.data.auto_capital_percent));
    lastSavedSettingsRef.current = {
      enabled: settings.data.auto_capital_enabled,
      percent: String(settings.data.auto_capital_percent),
    };
    lastRequestedSettingsRef.current = {
      enabled: settings.data.auto_capital_enabled,
      percent: String(settings.data.auto_capital_percent),
    };
    setSettingsSavedNotice(false);
    setSettingsHydrated(true);
  }, [settings.data]);

  const createAccountMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async () => {
      resetAccountForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["transfers"] }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ]);
    },
    onError: (error: Error) => {
      setAccountError(error.message);
    },
  });

  const updateAccountMutation = useMutation({
    mutationFn: ({ accountId, payload }: { accountId: number; payload: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(accountId, payload),
    onSuccess: async () => {
      resetAccountForm();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["transfers"] }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ]);
    },
    onError: (error: Error) => {
      setAccountError(error.message);
    },
  });

  const updateFamilyVisibilityMutation = useMutation({
    mutationFn: ({ accountId, familyVisible }: { accountId: number; familyVisible: boolean }) =>
      updateAccount(accountId, { family_visible: familyVisible }),
    onSuccess: async () => {
      setAccountError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard", "accounts-page"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "capital-history"] }),
      ]);
    },
    onError: (error: Error) => {
      setAccountError(error.message);
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: async (_, accountId) => {
      if (editingAccountId === accountId) {
        resetAccountForm();
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["transfers"] }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ]);
    },
    onError: (error: Error) => {
      setAccountError(error.message);
    },
  });

  const createTransferMutation = useMutation({
    mutationFn: createTransfer,
    onSuccess: async () => {
      setTransferForm({
        fromAccountId: "",
        toAccountId: "",
        amount: "",
        date: getToday(),
        comment: "",
      });
      setTransferError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["transfers"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => {
      setTransferError(error.message);
    },
  });

  const updateSettingsMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: async (response) => {
      setAutoCapitalEnabled(response.auto_capital_enabled);
      setAutoCapitalPercent(String(response.auto_capital_percent));
      lastSavedSettingsRef.current = {
        enabled: response.auto_capital_enabled,
        percent: String(response.auto_capital_percent),
      };
      lastRequestedSettingsRef.current = {
        enabled: response.auto_capital_enabled,
        percent: String(response.auto_capital_percent),
      };
      setSettingsError(null);
      setSettingsSavedNotice(true);
      if (settingsSavedNoticeTimeoutRef.current) {
        window.clearTimeout(settingsSavedNoticeTimeoutRef.current);
      }
      settingsSavedNoticeTimeoutRef.current = window.setTimeout(() => {
        setSettingsSavedNotice(false);
      }, 1800);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
    onError: (error: Error) => {
      lastRequestedSettingsRef.current = null;
      setSettingsSavedNotice(false);
      setSettingsError(error.message);
    },
  });

  const updateAutoCapitalTargetMutation = useMutation({
    mutationFn: async (targetKey: string) => {
      if (targetKey.startsWith("personal:")) {
        const accountId = Number(targetKey.slice("personal:".length));
        if (!Number.isFinite(accountId) || accountId <= 0) {
          throw new Error("Не удалось определить личный счет для автоотчислений.");
        }
        if (selectedFamilyId !== null) {
          await updateFamilyCapitalTarget({
            familyId: selectedFamilyId,
            targetOwnerUserId: null,
            targetCapitalAccountId: null,
          });
        }
        return updateAccount(accountId, { is_default: true });
      }

      if (targetKey.startsWith("family:")) {
        if (selectedFamilyId === null) {
          throw new Error("Семейный бюджет не найден.");
        }
        const [, ownerRaw, accountRaw] = targetKey.split(":");
        const ownerUserId = Number(ownerRaw);
        const capitalAccountId = Number(accountRaw);
        if (!Number.isFinite(ownerUserId) || !Number.isFinite(capitalAccountId) || ownerUserId <= 0 || capitalAccountId <= 0) {
          throw new Error("Не удалось определить семейный счет для автоотчислений.");
        }
        return updateFamilyCapitalTarget({
          familyId: selectedFamilyId,
          targetOwnerUserId: ownerUserId,
          targetCapitalAccountId: capitalAccountId,
        });
      }

      throw new Error("Выберите счет для автоотчислений.");
    },
    onSuccess: async () => {
      setSettingsError(null);
      setSettingsSavedNotice(true);
      if (settingsSavedNoticeTimeoutRef.current) {
        window.clearTimeout(settingsSavedNoticeTimeoutRef.current);
      }
      settingsSavedNoticeTimeoutRef.current = window.setTimeout(() => {
        setSettingsSavedNotice(false);
      }, 1800);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard", "accounts-page"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "capital-history"] }),
      ]);
      setSavingAutoCapitalTargetKey(null);
    },
    onError: (error: Error) => {
      setSavingAutoCapitalTargetKey(null);
      setSettingsError(error.message);
    },
  });

  function applySettings(enabled: boolean, percentValue: string) {
    const percent = Number(percentValue.replace(",", "."));
    if (!Number.isInteger(percent) || percent < 0 || percent > 100) {
      setSettingsError("Процент автоотчислений должен быть целым числом от 0 до 100.");
      return;
    }

    const lastSaved = lastSavedSettingsRef.current;
    if (lastSaved && lastSaved.enabled === enabled && lastSaved.percent === String(percent)) {
      setSettingsError(null);
      return;
    }

    const lastRequested = lastRequestedSettingsRef.current;
    if (lastRequested && lastRequested.enabled === enabled && lastRequested.percent === String(percent)) {
      return;
    }

    setSettingsSavedNotice(false);
    lastRequestedSettingsRef.current = {
      enabled,
      percent: String(percent),
    };
    updateSettingsMutation.mutate({
      auto_capital_enabled: enabled,
      auto_capital_percent: percent,
    });
  }

  useEffect(() => {
    return () => {
      if (settingsSavedNoticeTimeoutRef.current) {
        window.clearTimeout(settingsSavedNoticeTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!settingsHydrated) {
      return;
    }

    const normalizedPercent = autoCapitalPercent.trim();
    if (!normalizedPercent) {
      return;
    }

    const lastSaved = lastSavedSettingsRef.current;
    if (
      lastSaved &&
      lastSaved.enabled === autoCapitalEnabled &&
      lastSaved.percent === normalizedPercent
    ) {
      return;
    }

    const lastRequested = lastRequestedSettingsRef.current;
    if (
      lastRequested &&
      lastRequested.enabled === autoCapitalEnabled &&
      lastRequested.percent === normalizedPercent
    ) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      applySettings(autoCapitalEnabled, normalizedPercent);
    }, 400);

    return () => window.clearTimeout(timeoutId);
  }, [autoCapitalEnabled, autoCapitalPercent, settingsHydrated]);

  function resetAccountForm() {
    setEditingAccountId(null);
    setAccountForm(getInitialAccountForm());
    setAccountError(null);
  }

  function moveToAccountEditForm() {
    requestAnimationFrame(() => {
      accountFormPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => {
        accountNameInputRef.current?.focus();
        accountNameInputRef.current?.select();
      }, 180);
    });
  }

  function fillAccountForm(account: Account) {
    if (account.type !== "capital") {
      return;
    }
    setEditingAccountId(account.id);
    setAccountForm({
      name: account.name,
      balance: String(account.balance),
      color: account.color ?? ACCOUNT_COLORS[0],
    });
    setAccountError(null);
    moveToAccountEditForm();
  }

  function submitAccountForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAccountError(null);

    const name = accountForm.name.trim();
    const balance = accountForm.balance ? Number(accountForm.balance.replace(",", ".")) : 0;

    if (!name) {
      setAccountError("Укажи название.");
      return;
    }
    if (Number.isNaN(balance) || balance < 0) {
      setAccountError("Начальный баланс не может быть отрицательным.");
      return;
    }

    if (editingAccountId !== null) {
      updateAccountMutation.mutate({
        accountId: editingAccountId,
        payload: {
          name,
          balance,
          color: accountForm.color,
        },
      });
      return;
    }

    createAccountMutation.mutate({
      name,
      balance,
      color: accountForm.color,
    });
  }

  function submitTransferForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTransferError(null);

    const amount = Number(transferForm.amount.replace(",", "."));
    if (!transferForm.fromAccountId || !transferForm.toAccountId) {
      setTransferError("Выбери, откуда и куда перевести деньги.");
      return;
    }
    if (transferForm.fromAccountId === transferForm.toAccountId) {
      setTransferError("Нужно выбрать два разных места.");
      return;
    }
    if (!amount || amount <= 0) {
      setTransferError("Укажи сумму больше нуля.");
      return;
    }

    createTransferMutation.mutate({
      from_account_id: Number(transferForm.fromAccountId),
      to_account_id: Number(transferForm.toAccountId),
      amount,
      date: transferForm.date,
      comment: transferForm.comment,
    });
  }

  function saveFamilyTarget() {
    if (!selectedTargetKey) {
      setSettingsError("Выберите счет для автоотчислений.");
      return;
    }
    setSettingsSavedNotice(false);
    setSavingAutoCapitalTargetKey(selectedTargetKey);
    updateAutoCapitalTargetMutation.mutate(selectedTargetKey);
  }

  function getAccountTone(account: Account) {
    return account.family_visible ? "В семейной подушке" : "Личная подушка";
  }

  function getTransferAccountLabel(account: Account) {
    if (account.type === "capital") {
      return `Подушка · ${account.name}`;
    }
    return account.money_source === "cash" ? "Наличные" : "Для трат";
  }

  function saveDefaultMoneySource(source: "cashless" | "cash") {
    setSettingsSavedNotice(false);
    updateSettingsMutation.mutate({
      default_money_source: source,
    });
  }

  const defaultCapitalAccountName = activeAutoCapitalTarget?.name ?? "подушка ещё не выбрана";

  return (
    <main className="accounts-layout">
      <section className="accounts-sidebar">
        <section className="panel panel-form">
          <div className="panel-header">
            <h2>Автоотчисления</h2>
          </div>

          <form className="transaction-form auto-capital-form">
            <div className="toggle-row auto-capital-toggle-row">
              <button
                className={autoCapitalEnabled ? "toggle active" : "toggle"}
                onClick={() => {
                  setAutoCapitalEnabled(true);
                  applySettings(true, autoCapitalPercent);
                }}
                type="button"
              >
                Включены
              </button>
              <button
                className={!autoCapitalEnabled ? "toggle active" : "toggle"}
                onClick={() => {
                  setAutoCapitalEnabled(false);
                  applySettings(false, autoCapitalPercent);
                }}
                type="button"
              >
                Выключены
              </button>
            </div>

            <label className="field">
              <span>Процент с дохода</span>
              <input
                inputMode="numeric"
                max="100"
                min="0"
                onChange={(event) => {
                  setAutoCapitalPercent(event.target.value);
                  setSettingsError(null);
                }}
                placeholder="10"
                type="number"
                value={autoCapitalPercent}
              />
            </label>

            <div className="auto-capital-info">
              <div className="auto-capital-info-row">
                <span className="auto-capital-info-label">Текущая цель</span>
                <strong>{defaultCapitalAccountName}</strong>
              </div>

              <div className="auto-capital-info-row">
                <span className="auto-capital-info-label">Тип</span>
                <strong>
                  {activeAutoCapitalTarget?.tone ?? "Не выбрано"}
                </strong>
              </div>
            </div>
            <label className="field">
              <span>Куда откладывать с доходов</span>
              <select
                onChange={(event) => {
                  setSelectedTargetKey(event.target.value);
                  setSettingsError(null);
                }}
                value={selectedTargetKey}
              >
                <option value="">Выбери подушку</option>
                {autoCapitalTargetOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.description + " · " + option.label}
                  </option>
                ))}
              </select>
            </label>

            <p className="auto-capital-note">Это не расход: деньги уходят из трат в подушку.</p>

            <div className="field">
              <span>Основной способ оплаты</span>
              <div className="toggle-row">
                <button
                  className={(settings.data?.default_money_source ?? "cashless") === "cashless" ? "toggle active" : "toggle"}
                  disabled={updateSettingsMutation.isPending}
                  onClick={() => saveDefaultMoneySource("cashless")}
                  type="button"
                >
                  Для трат
                </button>
                <button
                  className={settings.data?.default_money_source === "cash" ? "toggle active" : "toggle"}
                  disabled={updateSettingsMutation.isPending}
                  onClick={() => saveDefaultMoneySource("cash")}
                  type="button"
                >
                  Наличные
                </button>
              </div>
            </div>

            <button
              className="primary-button"
              disabled={
                updateAutoCapitalTargetMutation.isPending ||
                !selectedTargetKey ||
                selectedTargetKey === effectiveAutoCapitalTargetKey
              }
              onClick={saveFamilyTarget}
              type="button"
            >
              {updateAutoCapitalTargetMutation.isPending ? "Сохраняем..." : "Сохранить подушку"}
            </button>
            {settingsError && <p className="form-error">{settingsError}</p>}
            {!settingsError &&
              !updateSettingsMutation.isPending &&
              !updateAutoCapitalTargetMutation.isPending &&
              settingsSavedNotice && (
              <p className="form-status form-status-success">Сохранено</p>
            )}
            {!settingsError && (updateSettingsMutation.isPending || updateAutoCapitalTargetMutation.isPending) && (
              <p className="form-status">Сохраняем настройки...</p>
            )}
          </form>
        </section>

        <section
          className={editingAccountId !== null ? "panel panel-form editing-panel" : "panel panel-form"}
          ref={accountFormPanelRef}
        >
          <div className="panel-header">
            <h2>{editingAccountId !== null ? "Редактирование подушки" : "Новая подушка"}</h2>
          </div>

          <form className="transaction-form" onSubmit={submitAccountForm}>
            {editingAccountId !== null && (
              <div className="editing-banner" role="status">
                <strong>Сейчас редактируется:</strong> {accountForm.name || "подушка"}
              </div>
            )}
            <label className="field">
              <span>Название</span>
              <input
                ref={accountNameInputRef}
                onChange={(event) => setAccountForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Например, Подушка в Сбере"
                value={accountForm.name}
              />
            </label>

            <label className="field">
              <span>{editingAccountId !== null ? "Сколько сейчас" : "Сколько сейчас"}</span>
              <input
                inputMode="decimal"
                onChange={(event) => setAccountForm((current) => ({ ...current, balance: event.target.value }))}
                placeholder="0"
                value={accountForm.balance}
              />
            </label>

            <div className="field">
              <span>Цвет</span>
              <div className="color-grid">
                {ACCOUNT_COLORS.map((color) => (
                  <button
                    aria-label={`Выбрать цвет ${color}`}
                    className={accountForm.color === color ? "color-swatch active" : "color-swatch"}
                    key={color}
                    onClick={() => setAccountForm((current) => ({ ...current, color }))}
                    style={{ backgroundColor: color }}
                    type="button"
                  />
                ))}
              </div>
            </div>

            {accountError && <p className="form-error">{accountError}</p>}

            <div className="action-row">
              <button
                className="primary-button"
                disabled={createAccountMutation.isPending || updateAccountMutation.isPending}
                type="submit"
              >
                {editingAccountId !== null
                  ? updateAccountMutation.isPending
                    ? "Сохраняем..."
                    : "Сохранить"
                  : createAccountMutation.isPending
                    ? "Создаём..."
                    : "Добавить подушку"}
              </button>

              {editingAccountId !== null && (
                <button className="ghost-button" onClick={resetAccountForm} type="button">
                  Отмена
                </button>
              )}
            </div>
          </form>
        </section>

        <section className="panel panel-form">
          <div className="panel-header">
            <h2>Перевод денег</h2>
          </div>

          <form className="transaction-form" onSubmit={submitTransferForm}>
            <div className="field-row">
              <label className="field">
                <span>Откуда</span>
                <select
                  onChange={(event) =>
                    setTransferForm((current) => ({ ...current, fromAccountId: event.target.value }))
                  }
                  value={transferForm.fromAccountId}
                >
                  <option value="">Выбери место</option>
                  {transferAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {getTransferAccountLabel(account)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Куда</span>
                <select
                  onChange={(event) =>
                    setTransferForm((current) => ({ ...current, toAccountId: event.target.value }))
                  }
                  value={transferForm.toAccountId}
                >
                  <option value="">Выбери место</option>
                  {transferAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {getTransferAccountLabel(account)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {transferMeaning && <p className="auto-capital-note">{transferMeaning}</p>}

            <div className="field-row">
              <label className="field">
                <span>Сумма</span>
                <input
                  inputMode="decimal"
                  onChange={(event) => setTransferForm((current) => ({ ...current, amount: event.target.value }))}
                  placeholder="0"
                  value={transferForm.amount}
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
                    onChange={(event) => setTransferForm((current) => ({ ...current, date: event.target.value }))}
                    type="date"
                    value={transferForm.date}
                  />
                </div>
              </label>
            </div>

            <label className="field">
              <span>Комментарий</span>
              <input
                onChange={(event) => setTransferForm((current) => ({ ...current, comment: event.target.value }))}
                placeholder="Например, в подушку"
                value={transferForm.comment}
              />
            </label>

            {transferError && <p className="form-error">{transferError}</p>}

            <button className="primary-button" disabled={createTransferMutation.isPending} type="submit">
              {createTransferMutation.isPending ? "Проводим..." : "Сделать перевод"}
            </button>
          </form>
        </section>
      </section>

      <section className="accounts-main">
        <section className="panel panel-list money-overview-panel">
          <div className="panel-header">
            <h2>{familyModeEnabled ? "Деньги семьи" : "Мои деньги"}</h2>
            <span>{familyModeEnabled ? "Семейный режим включен" : "Личный режим"}</span>
          </div>

          <div className="summary-grid summary-grid-3 accounts-summary-grid money-overview-grid">
            <article className="summary-card summary-card-main account-summary-card account-summary-card-main">
              <p className="panel-label">{familyModeEnabled ? "На жизнь у семьи" : "На жизнь"}</p>
              <h3>{formatMoney(visibleDailyMoney)}</h3>
              <p className="muted">Деньги для обычных покупок и платежей.</p>
            </article>

            {familyModeEnabled && (
              <article className="summary-card account-summary-card">
                <p className="panel-label">К концу месяца</p>
                <h3>{familyForecastBalance === null ? "—" : formatMoney(familyForecastBalance)}</h3>
                <p className="muted">С учетом будущих доходов, трат и отложений.</p>
              </article>
            )}

            <article className="summary-card account-summary-card">
              <p className="panel-label">У меня на руках</p>
              <h3>{formatMoney(personalCashOnHand)}</h3>
              <p className="muted">Мои карты и наличные.</p>
            </article>

            <article className="summary-card account-summary-card">
              <p className="panel-label">{familyModeEnabled ? "Подушка семьи" : "Моя подушка"}</p>
              <h3>{formatMoney(visibleEmergencyMoney)}</h3>
              <p className="muted">Деньги, которые лучше не тратить каждый день.</p>
            </article>

            <article className="summary-card account-summary-card">
              <p className="panel-label">Мои всего</p>
              <h3>{formatMoney(personalTotalVisibleMoney)}</h3>
              <p className="muted">Личные деньги на жизнь и моя подушка.</p>
            </article>
          </div>
        </section>

        <section className="panel panel-list">
          <div className="panel-header">
            <h2>Где лежат деньги</h2>
          </div>

          <div className="category-card-grid">
            {moneyPlaces.map((place) => {
              const isTarget = activeAutoCapitalTarget?.key === place.key;
              return (
                <article className={isTarget ? "account-card account-card-main" : "account-card"} key={place.key}>
                  <div className="category-card-main">
                    <span
                      aria-hidden="true"
                      className="category-dot"
                      style={{ backgroundColor: place.color }}
                    />
                    <div>
                      <strong>{place.name}</strong>
                      <p>{isTarget ? `Сюда откладываем · ${place.tone}` : place.tone}</p>
                    </div>
                  </div>
                  <div className="account-balance">
                    <strong>{formatMoney(place.balance)}</strong>
                  </div>
                </article>
              );
            })}

            {accountsError && <p className="form-error">{accountsError}</p>}

            {!accountsError && !moneyPlaces.length && (
              <p className="empty">{isAccountsPending ? "Загружаем деньги..." : "Деньги пока не найдены."}</p>
            )}
          </div>
        </section>

        <section className="panel panel-list">
          <div className="panel-header">
            <h2>Мои подушки</h2>
          </div>

          {activeAutoCapitalTarget ? (
            <div className="account-section">
              <div className="account-section-header">
                <h3>Куда откладываем</h3>
              </div>

              <article className="account-card account-card-main">
                <div className="category-card-main">
                  <span
                    aria-hidden="true"
                    className="category-dot"
                    style={{ backgroundColor: activeAutoCapitalTarget.color }}
                  />
                  <div>
                    <strong>{activeAutoCapitalTarget.name}</strong>
                    <p>{activeAutoCapitalTarget.tone}</p>
                  </div>
                </div>
                <div className="account-balance">
                  <strong>{formatMoney(activeAutoCapitalTarget.balance)}</strong>
                </div>
              </article>
            </div>
          ) : null}

          <div className="account-section">
            <div className="account-section-header">
              <h3>Подушки</h3>
            </div>

            <div className="category-card-grid">
              {capitalAccounts.map((account) => (
                <article className="account-card" key={account.id}>
                  <div className="category-card-main">
                    <span
                      aria-hidden="true"
                      className="category-dot"
                      style={{ backgroundColor: account.color ?? "#5f6b76" }}
                    />
                    <div>
                      <strong>{account.name}</strong>
                      <p>{getAccountTone(account)}</p>
                    </div>
                  </div>
                  <div className="account-balance">
                    <strong>{formatMoney(account.balance)}</strong>
                  </div>
                  <div className="category-card-actions">
                    {selectedFamilyId !== null && (
                      <button
                        className="ghost-button"
                        disabled={updateFamilyVisibilityMutation.isPending}
                        onClick={() =>
                          updateFamilyVisibilityMutation.mutate({
                            accountId: account.id,
                            familyVisible: !account.family_visible,
                          })
                        }
                        type="button"
                      >
                        {account.family_visible ? "Убрать из семьи" : "Добавить в семью"}
                      </button>
                    )}
                    <button className="ghost-button" onClick={() => fillAccountForm(account)} type="button">
                      Изменить
                    </button>
                    <button
                      className="ghost-button"
                      disabled={deleteAccountMutation.isPending}
                      onClick={() => deleteAccountMutation.mutate(account.id)}
                      type="button"
                    >
                      Отключить
                    </button>
                  </div>
                </article>
              ))}

              {accountsError && <p className="form-error">{accountsError}</p>}

              {!accountsError && !accounts.data?.length && (
                <p className="empty">{isAccountsPending ? "Загружаем деньги..." : "Деньги пока не найдены."}</p>
              )}

              {!!accounts.data?.length && !capitalAccounts.length && (
                <p className="empty">Подушек пока нет.</p>
              )}
            </div>
          </div>
        </section>

        {!!familyVisibleAccounts.length && (
          <section className="panel panel-list">
            <div className="panel-header">
              <h2>История подушки семьи</h2>
            </div>

            <div className="transaction-table">
              {(familyCapitalHistory.data?.items ?? []).map((item) => (
                <article className="transaction-row" key={item.id}>
                  <div className="transaction-main">
                    <strong>
                      {(item.source_display_name || item.source_email || "Участник")} → {item.target_account_name || "Подушка семьи"}
                    </strong>
                    <p>{item.comment || "Отложили в подушку семьи"}</p>
                    <p className="muted">
                      Получатель: {item.target_owner_display_name || item.target_owner_email || "Семья"}
                    </p>
                  </div>
                  <div className="transaction-meta">
                    <span className="transaction-date">{item.date}</span>
                    <strong className="money">{formatMoney(item.amount)}</strong>
                  </div>
                </article>
              ))}

              {!familyCapitalHistory.data?.items?.length && (
                <p className="empty">
                  {familyCapitalHistory.isLoading ? "Загружаем историю подушки..." : "Движений подушки пока нет."}
                </p>
              )}
            </div>
          </section>
        )}

        <section className="panel panel-list">
          <div className="panel-header">
            <h2>Последние переводы</h2>
          </div>

          <div className="transaction-table">
            {(transfers.data ?? []).map((transfer) => (
              <article className="transaction-row" key={transfer.id}>
                <div className="transaction-main">
                  <strong>
                    {transfer.from_name} → {transfer.to_name}
                  </strong>
                  <p>{transfer.comment || "Без комментария"}</p>
                </div>
                <div className="transaction-meta">
                  <span className="transaction-date">{transfer.date}</span>
                  <strong className="money">{formatMoney(transfer.amount)}</strong>
                </div>
              </article>
            ))}

            {transfersError && <p className="form-error">{transfersError}</p>}

            {!transfersError && !transfers.data?.length && (
              <p className="empty">{isTransfersPending ? "Загружаем переводы..." : "Переводов пока нет."}</p>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}
