import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acceptFamilyInviteById,
  declineFamilyInviteById,
  getAccountBackupInfo,
  getAccountPreferences,
  getMyFamilies,
  getPendingFamilyInvites,
  getMe,
  logout,
  resetAllAccountData,
  restoreAccountBackup,
  saveAccountBackup,
  updateAccountPreferences,
} from "./lib/api";
import { AccountsPage } from "./pages/AccountsPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FamilyPage } from "./pages/FamilyPage";
import { PlanningPage } from "./pages/PlanningPage";
import { SecurityPage } from "./pages/SecurityPage";
import { TransactionsPageNext } from "./pages/TransactionsPageNext";

type BusyAction = "" | "save" | "restore" | "reset" | "logout";
type ConfirmAction = "logout" | "restore" | "reset" | null;
type InviteAction = "" | "accept" | "decline";

function formatBackupTimestamp(value: string): string {
  if (!value) {
    return "дата неизвестна";
  }
  const parsed = new Date(value.replace(" ", "T") + "Z");
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export default function AppShellNext() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const topbarLinksRef = useRef<HTMLDivElement | null>(null);
  const notificationsMenuRef = useRef<HTMLDivElement | null>(null);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);

  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [themeMode, setThemeMode] = useState<"light" | "dark" | "system">("system");
  const [workspaceMode, setWorkspaceMode] = useState<"personal" | "family">("personal");
  const [accountMessage, setAccountMessage] = useState("");
  const [accountError, setAccountError] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>("");
  const [inviteAction, setInviteAction] = useState<InviteAction>("");
  const [inviteBusyId, setInviteBusyId] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [resetConfirmText, setResetConfirmText] = useState("");

  const { data: currentUser } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });

  const preferencesQuery = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    retry: false,
  });

  const backupInfoQuery = useQuery({
    queryKey: ["account", "backup"],
    queryFn: getAccountBackupInfo,
    retry: false,
  });

  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const pendingInvitesQuery = useQuery({
    queryKey: ["families", "invites", "pending"],
    queryFn: getPendingFamilyInvites,
    retry: false,
  });

  const hasFamily = (familiesQuery.data?.families ?? []).length > 0;
  const showFamilyTab = workspaceMode === "family" && hasFamily;
  const pendingInvites = pendingInvitesQuery.data?.invites ?? [];
  const hasPendingInvites = pendingInvites.length > 0;

  useEffect(() => {
    const container = topbarLinksRef.current;
    if (!container) {
      return;
    }

    const activeLink = container.querySelector<HTMLAnchorElement>(".nav-link.active");
    if (!activeLink) {
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const activeRect = activeLink.getBoundingClientRect();
    const delta = activeRect.left - containerRect.left - (containerRect.width - activeRect.width) / 2;

    container.scrollTo({
      left: container.scrollLeft + delta,
      behavior: "auto",
    });
  }, [location.pathname]);

  useEffect(() => {
    const savedTheme = preferencesQuery.data?.theme_mode;
    if (savedTheme === "light" || savedTheme === "dark" || savedTheme === "system") {
      setThemeMode(savedTheme);
    } else {
      const localValue = window.localStorage.getItem("finance_theme_mode");
      if (localValue === "light" || localValue === "dark" || localValue === "system") {
        setThemeMode(localValue);
      } else {
        setThemeMode("system");
      }
    }

    const savedWorkspace = preferencesQuery.data?.workspace_mode;
    if (savedWorkspace === "family" || savedWorkspace === "personal") {
      setWorkspaceMode(savedWorkspace);
    }
  }, [preferencesQuery.data?.theme_mode, preferencesQuery.data?.workspace_mode]);

  useEffect(() => {
    const root = document.documentElement;
    const preferDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effectiveTheme = themeMode === "system" ? (preferDark ? "dark" : "light") : themeMode;
    root.setAttribute("data-theme", effectiveTheme);
    window.localStorage.setItem("finance_theme_mode", themeMode);
  }, [themeMode]);

  useEffect(() => {
    function onDocumentClick(event: MouseEvent) {
      if (!isAccountMenuOpen && !isNotificationsOpen) {
        return;
      }
      const node = event.target as Node;
      if (isAccountMenuOpen && accountMenuRef.current && !accountMenuRef.current.contains(node)) {
        setIsAccountMenuOpen(false);
      }
      if (isNotificationsOpen && notificationsMenuRef.current && !notificationsMenuRef.current.contains(node)) {
        setIsNotificationsOpen(false);
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsNotificationsOpen(false);
        setIsAccountMenuOpen(false);
        if (busyAction === "") {
          setConfirmAction(null);
          setResetConfirmText("");
        }
      }
    }

    document.addEventListener("mousedown", onDocumentClick);
    document.addEventListener("keydown", onEscape);

    return () => {
      document.removeEventListener("mousedown", onDocumentClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [isAccountMenuOpen, isNotificationsOpen, busyAction]);

  useEffect(() => {
    setIsNotificationsOpen(false);
    setIsAccountMenuOpen(false);
    setConfirmAction(null);
    setResetConfirmText("");
  }, [location.pathname]);

  useEffect(() => {
    if (!showFamilyTab && location.pathname === "/family") {
      navigate("/", { replace: true });
    }
  }, [showFamilyTab, location.pathname, navigate]);

  async function onThemeChange(nextTheme: "light" | "dark" | "system") {
    setThemeMode(nextTheme);
    setAccountError("");
    try {
      await updateAccountPreferences({ theme_mode: nextTheme, workspace_mode: workspaceMode });
      await queryClient.invalidateQueries({ queryKey: ["account", "preferences"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось сохранить тему.");
    }
  }

  async function onWorkspaceChange(nextMode: "personal" | "family") {
    setWorkspaceMode(nextMode);
    setAccountError("");
    setAccountMessage("");
    try {
      await updateAccountPreferences({ workspace_mode: nextMode, theme_mode: themeMode });
      await queryClient.invalidateQueries({ queryKey: ["account", "preferences"] });
      if (nextMode === "family" && !hasFamily) {
        setAccountMessage("Сначала примите приглашение в семью или создайте семейный бюджет.");
      }
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось сохранить режим.");
    }
  }

  async function onAcceptInvite(inviteId: number) {
    setInviteAction("accept");
    setInviteBusyId(inviteId);
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await acceptFamilyInviteById(inviteId);
      await updateAccountPreferences({ workspace_mode: "family", theme_mode: themeMode });
      setWorkspaceMode("family");
      setAccountMessage(response.message);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["families", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["families", "invites", "pending"] }),
        queryClient.invalidateQueries({ queryKey: ["account", "preferences"] }),
      ]);
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось принять приглашение.");
    } finally {
      setInviteAction("");
      setInviteBusyId(null);
    }
  }

  async function onDeclineInvite(inviteId: number) {
    setInviteAction("decline");
    setInviteBusyId(inviteId);
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await declineFamilyInviteById(inviteId);
      setAccountMessage(response.message);
      await queryClient.invalidateQueries({ queryKey: ["families", "invites", "pending"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось отклонить приглашение.");
    } finally {
      setInviteAction("");
      setInviteBusyId(null);
    }
  }

  async function onSaveBackup() {
    setBusyAction("save");
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await saveAccountBackup();
      setAccountMessage(response.message);
      await queryClient.invalidateQueries({ queryKey: ["account", "backup"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось сохранить резервную копию.");
    } finally {
      setBusyAction("");
    }
  }

  function openConfirm(action: Exclude<ConfirmAction, null>) {
    setAccountError("");
    setAccountMessage("");
    setResetConfirmText("");
    setConfirmAction(action);
  }

  function closeConfirm() {
    if (busyAction !== "") {
      return;
    }
    setConfirmAction(null);
    setResetConfirmText("");
  }

  async function runConfirmedAction() {
    if (confirmAction === null) {
      return;
    }

    if (confirmAction === "logout") {
      setBusyAction("logout");
      try {
        await logout();
        await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/login", { replace: true });
      } finally {
        setBusyAction("");
        setConfirmAction(null);
      }
      return;
    }

    if (confirmAction === "restore") {
      setBusyAction("restore");
      try {
        const response = await restoreAccountBackup();
        setAccountMessage(response.message);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
          queryClient.invalidateQueries({ queryKey: ["transactions"] }),
          queryClient.invalidateQueries({ queryKey: ["categories"] }),
          queryClient.invalidateQueries({ queryKey: ["accounts"] }),
          queryClient.invalidateQueries({ queryKey: ["budgets"] }),
          queryClient.invalidateQueries({ queryKey: ["forecast"] }),
          queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        ]);
      } catch (error) {
        setAccountError(error instanceof Error ? error.message : "Не удалось восстановить данные.");
      } finally {
        setBusyAction("");
        setConfirmAction(null);
      }
      return;
    }

    if (confirmAction === "reset") {
      const normalized = resetConfirmText.trim().toUpperCase();
      if (normalized !== "СБРОС") {
        setAccountError("Введите СБРОС для подтверждения.");
        return;
      }

      setBusyAction("reset");
      try {
        const response = await resetAllAccountData({ confirm_text: "СБРОС" });
        setAccountMessage(response.message);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
          queryClient.invalidateQueries({ queryKey: ["transactions"] }),
          queryClient.invalidateQueries({ queryKey: ["categories"] }),
          queryClient.invalidateQueries({ queryKey: ["accounts"] }),
          queryClient.invalidateQueries({ queryKey: ["budgets"] }),
          queryClient.invalidateQueries({ queryKey: ["forecast"] }),
          queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
        ]);
      } catch (error) {
        setAccountError(error instanceof Error ? error.message : "Не удалось очистить данные.");
      } finally {
        setBusyAction("");
        setConfirmAction(null);
        setResetConfirmText("");
      }
    }
  }

  const userEmail = currentUser?.email ?? "";
  const displayName = userEmail ? userEmail.split("@")[0] : "Профиль";
  const initials = displayName.slice(0, 2).toUpperCase();

  const confirmTitle = useMemo(() => {
    if (confirmAction === "logout") {
      return "Подтверждение выхода";
    }
    if (confirmAction === "restore") {
      return "Восстановить данные";
    }
    if (confirmAction === "reset") {
      return "Обнулить данные";
    }
    return "";
  }, [confirmAction]);

  const confirmText = useMemo(() => {
    if (confirmAction === "logout") {
      return "Вы действительно хотите выйти из аккаунта?";
    }
    if (confirmAction === "restore") {
      return "Текущие данные будут заменены последней резервной копией.";
    }
    if (confirmAction === "reset") {
      return "Будут удалены все финансовые данные пользователя. Это действие необратимо.";
    }
    return "";
  }, [confirmAction]);

  const confirmButtonLabel = useMemo(() => {
    if (confirmAction === "logout") {
      return "Выйти";
    }
    if (confirmAction === "restore") {
      return "Восстановить";
    }
    if (confirmAction === "reset") {
      return "Обнулить";
    }
    return "Подтвердить";
  }, [confirmAction]);

  const resetAllowed = confirmAction !== "reset" || resetConfirmText.trim().toUpperCase() === "СБРОС";

  return (
    <div className="shell">
      <nav className="topbar">
        <div className="topbar-links" ref={topbarLinksRef}>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} end to="/">
            Главная
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/transactions">
            Транзакции
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/categories">
            Категории
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/planning">
            Планирование
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/accounts">
            Счета
          </NavLink>
          {showFamilyTab ? (
            <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/family">
              Семья
            </NavLink>
          ) : null}
        </div>

        <div className="notifications-menu" ref={notificationsMenuRef}>
          <button
            aria-expanded={isNotificationsOpen}
            aria-haspopup="menu"
            className={`notification-trigger${isNotificationsOpen ? " open" : ""}${hasPendingInvites ? " has-unread" : ""}`}
            onClick={() => {
              setIsNotificationsOpen((prev) => !prev);
              setIsAccountMenuOpen(false);
            }}
            title="Уведомления"
            type="button"
          >
            <span className="notification-icon" aria-hidden="true">
              <svg fill="none" height="18" viewBox="0 0 24 24" width="18">
                <path
                  d="M6 9.5a6 6 0 1 1 12 0v4.2l1.4 2.5a1 1 0 0 1-.88 1.5H5.48a1 1 0 0 1-.88-1.5L6 13.7V9.5Z"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.8"
                />
                <path d="M9.5 18.5a2.5 2.5 0 0 0 5 0" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
              </svg>
            </span>
            {hasPendingInvites ? <span className="notification-badge">{pendingInvites.length}</span> : null}
          </button>

          <div className={isNotificationsOpen ? "account-overlay open" : "account-overlay"} onClick={() => setIsNotificationsOpen(false)} />

          <div className={isNotificationsOpen ? "notifications-dropdown open" : "notifications-dropdown"} role="menu">
            <div className="panel-header">
              <h3>Уведомления</h3>
              <span>{hasPendingInvites ? `${pendingInvites.length}` : "0"}</span>
            </div>

            {hasPendingInvites ? (
              pendingInvites.map((invite) => (
                <div className="family-member-item" key={invite.invite_id}>
                  <div className="family-member-main">
                    <strong>{invite.family_name}</strong>
                    <span>От: {invite.invited_by_email}</span>
                    <span>Роль: {invite.role}</span>
                  </div>
                  <div className="family-member-controls">
                    <button
                      className="account-action"
                      disabled={inviteAction !== ""}
                      onClick={() => void onAcceptInvite(invite.invite_id)}
                      type="button"
                    >
                      {inviteAction === "accept" && inviteBusyId === invite.invite_id ? "Принимаем..." : "Принять"}
                    </button>
                    <button
                      className="account-action danger"
                      disabled={inviteAction !== ""}
                      onClick={() => void onDeclineInvite(invite.invite_id)}
                      type="button"
                    >
                      {inviteAction === "decline" && inviteBusyId === invite.invite_id ? "Отклоняем..." : "Отклонить"}
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <p className="account-meta">Пока нет новых приглашений.</p>
            )}
          </div>
        </div>

        <div className="account-menu" ref={accountMenuRef}>
          <button
            aria-expanded={isAccountMenuOpen}
            aria-haspopup="menu"
            className="account-trigger"
            onClick={() => {
              setIsAccountMenuOpen((prev) => !prev);
              setIsNotificationsOpen(false);
            }}
            type="button"
          >
            <span className="account-trigger-avatar">{initials || "U"}</span>
            <span className="account-trigger-label">Аккаунт</span>
          </button>

          <div className={isAccountMenuOpen ? "account-overlay open" : "account-overlay"} onClick={() => setIsAccountMenuOpen(false)} />

          <div className={isAccountMenuOpen ? "account-dropdown open" : "account-dropdown"} role="menu">
            <div className="account-dropdown-head">
              <strong>{displayName || "Пользователь"}</strong>
              <span title={userEmail}>{userEmail || "email не указан"}</span>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Режим</p>
              <div className="account-theme-row">
                <button
                  className={workspaceMode === "personal" ? "account-pill active" : "account-pill"}
                  onClick={() => void onWorkspaceChange("personal")}
                  type="button"
                >
                  Личный
                </button>
                <button
                  className={workspaceMode === "family" ? "account-pill active" : "account-pill"}
                  onClick={() => void onWorkspaceChange("family")}
                  type="button"
                >
                  Совместный
                </button>
              </div>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Тема приложения</p>
              <div className="account-theme-row">
                <button className={themeMode === "light" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("light")} type="button">
                  Светлая
                </button>
                <button className={themeMode === "dark" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("dark")} type="button">
                  Тёмная
                </button>
                <button className={themeMode === "system" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("system")} type="button">
                  Система
                </button>
              </div>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Управление</p>
              <NavLink className="account-action" onClick={() => setIsAccountMenuOpen(false)} to="/security">
                Настройки и безопасность
              </NavLink>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Мои данные</p>
              <button className="account-action" disabled={busyAction !== ""} onClick={() => void onSaveBackup()} type="button">
                {busyAction === "save" ? "Сохраняем..." : "Сохранить данные (1 слот)"}
              </button>
              <button
                className="account-action"
                disabled={busyAction !== "" || !backupInfoQuery.data?.has_backup}
                onClick={() => openConfirm("restore")}
                type="button"
              >
                Восстановить данные
              </button>
              <button className="account-action danger" disabled={busyAction !== ""} onClick={() => openConfirm("reset")} type="button">
                Обнулить данные
              </button>
            </div>

            {backupInfoQuery.data?.has_backup ? (
              <p className="account-meta">Последняя копия: {formatBackupTimestamp(backupInfoQuery.data.updated_at || "")}</p>
            ) : (
              <p className="account-meta">Резервная копия ещё не создана.</p>
            )}

            {busyAction !== "" ? <p className="account-meta">Выполняем операцию...</p> : null}
            {accountMessage ? <p className="account-feedback success">{accountMessage}</p> : null}
            {accountError ? <p className="account-feedback error">{accountError}</p> : null}

            <button className="account-action danger" disabled={busyAction !== ""} onClick={() => openConfirm("logout")} type="button">
              Выйти
            </button>
          </div>
        </div>
      </nav>

      {confirmAction ? (
        <div className="confirm-modal-backdrop" onClick={closeConfirm}>
          <div className="confirm-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <h3>{confirmTitle}</h3>
            <p>{confirmText}</p>

            {confirmAction === "reset" ? (
              <label className="confirm-field">
                <span>Введите СБРОС для подтверждения</span>
                <input
                  autoComplete="off"
                  onChange={(event) => setResetConfirmText(event.target.value)}
                  placeholder="СБРОС"
                  value={resetConfirmText}
                />
              </label>
            ) : null}

            <div className="confirm-actions">
              <button className="account-action" disabled={busyAction !== ""} onClick={closeConfirm} type="button">
                Отмена
              </button>
              <button
                className="account-action danger"
                disabled={busyAction !== "" || !resetAllowed}
                onClick={() => void runConfirmedAction()}
                type="button"
              >
                {busyAction !== "" ? "Подождите..." : confirmButtonLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <Routes>
        <Route element={<DashboardPage />} path="/" />
        <Route element={<TransactionsPageNext />} path="/transactions" />
        <Route element={<CategoriesPage />} path="/categories" />
        <Route element={<PlanningPage />} path="/planning" />
        <Route element={<AccountsPage />} path="/accounts" />
        <Route element={showFamilyTab ? <FamilyPage /> : <Navigate replace to="/" />} path="/family" />
        <Route element={<SecurityPage />} path="/security" />
        <Route element={<Navigate replace to="/planning" />} path="/budgets" />
        <Route element={<Navigate replace to="/planning" />} path="/recurring" />
      </Routes>
    </div>
  );
}
