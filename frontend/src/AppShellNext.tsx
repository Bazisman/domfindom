import { useEffect, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAccountBackupInfo,
  getAccountPreferences,
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
import { PlanningPage } from "./pages/PlanningPage";
import { SecurityPage } from "./pages/SecurityPage";
import { TransactionsPageNext } from "./pages/TransactionsPageNext";

export default function AppShellNext() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const topbarLinksRef = useRef<HTMLDivElement | null>(null);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [themeMode, setThemeMode] = useState<"light" | "dark" | "system">("system");
  const [accountMessage, setAccountMessage] = useState("");
  const [accountError, setAccountError] = useState("");
  const [busyAction, setBusyAction] = useState<"" | "save" | "restore" | "reset">("");
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
    const saved = preferencesQuery.data?.theme_mode;
    if (saved === "light" || saved === "dark" || saved === "system") {
      setThemeMode(saved);
      return;
    }
    const localValue = window.localStorage.getItem("finance_theme_mode");
    if (localValue === "light" || localValue === "dark" || localValue === "system") {
      setThemeMode(localValue);
      return;
    }
    setThemeMode("system");
  }, [preferencesQuery.data?.theme_mode]);

  useEffect(() => {
    const root = document.documentElement;
    const preferDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effectiveTheme = themeMode === "system" ? (preferDark ? "dark" : "light") : themeMode;
    root.setAttribute("data-theme", effectiveTheme);
    window.localStorage.setItem("finance_theme_mode", themeMode);
  }, [themeMode]);

  useEffect(() => {
    function onDocumentClick(event: MouseEvent) {
      if (!isAccountMenuOpen) {
        return;
      }
      const node = event.target as Node;
      if (accountMenuRef.current && !accountMenuRef.current.contains(node)) {
        setIsAccountMenuOpen(false);
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsAccountMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", onDocumentClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onDocumentClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [isAccountMenuOpen]);

  useEffect(() => {
    setIsAccountMenuOpen(false);
  }, [location.pathname]);

  async function onLogout() {
    const confirmed = window.confirm("Выйти из аккаунта?");
    if (!confirmed) {
      return;
    }
    await logout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    navigate("/login", { replace: true });
  }

  async function onThemeChange(nextTheme: "light" | "dark" | "system") {
    setThemeMode(nextTheme);
    setAccountError("");
    try {
      await updateAccountPreferences({ theme_mode: nextTheme });
      await queryClient.invalidateQueries({ queryKey: ["account", "preferences"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось сохранить тему.");
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

  async function onRestoreBackup() {
    if (!backupInfoQuery.data?.has_backup) {
      setAccountError("Сначала создайте резервную копию.");
      return;
    }
    const confirmed = window.confirm("Восстановить данные из последней резервной копии?");
    if (!confirmed) {
      return;
    }
    setBusyAction("restore");
    setAccountError("");
    setAccountMessage("");
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
    }
  }

  async function onResetAllData() {
    const confirmed = window.confirm("Это удалит все финансовые данные. Продолжить?");
    if (!confirmed) {
      return;
    }
    const confirmationWord = window.prompt("Введите СБРОС для подтверждения");
    if ((confirmationWord ?? "").trim().toUpperCase() !== "СБРОС") {
      setAccountError("Подтверждение не выполнено.");
      return;
    }
    setBusyAction("reset");
    setAccountError("");
    setAccountMessage("");
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
    }
  }

  const userEmail = currentUser?.email ?? "";
  const displayName = userEmail ? userEmail.split("@")[0] : "Профиль";
  const initials = displayName.slice(0, 2).toUpperCase();

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
        </div>
        <div className="account-menu" ref={accountMenuRef}>
          <button
            aria-expanded={isAccountMenuOpen}
            aria-haspopup="menu"
            className="account-trigger"
            onClick={() => setIsAccountMenuOpen((prev) => !prev)}
            type="button"
          >
            <span className="account-trigger-avatar">{initials || "U"}</span>
            <span className="account-trigger-label">Аккаунт</span>
          </button>

          <div
            className={isAccountMenuOpen ? "account-overlay open" : "account-overlay"}
            onClick={() => setIsAccountMenuOpen(false)}
          />

          <div className={isAccountMenuOpen ? "account-dropdown open" : "account-dropdown"} role="menu">
            <div className="account-dropdown-head">
              <strong>{displayName || "Пользователь"}</strong>
              <span title={userEmail}>{userEmail || "email не указан"}</span>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Тема приложения</p>
              <div className="account-theme-row">
                <button
                  className={themeMode === "light" ? "account-pill active" : "account-pill"}
                  onClick={() => void onThemeChange("light")}
                  type="button"
                >
                  Светлая
                </button>
                <button
                  className={themeMode === "dark" ? "account-pill active" : "account-pill"}
                  onClick={() => void onThemeChange("dark")}
                  type="button"
                >
                  Тёмная
                </button>
                <button
                  className={themeMode === "system" ? "account-pill active" : "account-pill"}
                  onClick={() => void onThemeChange("system")}
                  type="button"
                >
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
              <p className="account-dropdown-title">Данные</p>
              <button className="account-action" disabled={busyAction !== ""} onClick={() => void onSaveBackup()} type="button">
                {busyAction === "save" ? "Сохраняем..." : "Сохранить данные (1 слот)"}
              </button>
              <button
                className="account-action"
                disabled={busyAction !== "" || !backupInfoQuery.data?.has_backup}
                onClick={() => void onRestoreBackup()}
                type="button"
              >
                {busyAction === "restore" ? "Восстанавливаем..." : "Восстановить данные"}
              </button>
              <button className="account-action danger" disabled={busyAction !== ""} onClick={() => void onResetAllData()} type="button">
                {busyAction === "reset" ? "Очищаем..." : "Обнулить данные"}
              </button>
            </div>

            {backupInfoQuery.data?.has_backup ? (
              <p className="account-meta">Последняя копия: {backupInfoQuery.data.updated_at || "дата неизвестна"}</p>
            ) : (
              <p className="account-meta">Резервная копия ещё не создана.</p>
            )}

            {accountMessage ? <p className="account-feedback success">{accountMessage}</p> : null}
            {accountError ? <p className="account-feedback error">{accountError}</p> : null}

            <button className="account-action danger" onClick={onLogout} type="button">
              Выйти
            </button>
          </div>
        </div>
      </nav>

      <Routes>
        <Route element={<DashboardPage />} path="/" />
        <Route element={<TransactionsPageNext />} path="/transactions" />
        <Route element={<CategoriesPage />} path="/categories" />
        <Route element={<PlanningPage />} path="/planning" />
        <Route element={<AccountsPage />} path="/accounts" />
        <Route element={<SecurityPage />} path="/security" />
        <Route element={<Navigate replace to="/planning" />} path="/budgets" />
        <Route element={<Navigate replace to="/planning" />} path="/recurring" />
      </Routes>
    </div>
  );
}
