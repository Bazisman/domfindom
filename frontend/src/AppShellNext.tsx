import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acceptFamilyInvite,
  createFamily,
  createFamilyInvite,
  getAccountBackupInfo,
  getAccountPreferences,
  getFamilyMembers,
  getMyFamilies,
  getMe,
  logout,
  removeFamilyMember,
  resetAllAccountData,
  restoreAccountBackup,
  saveAccountBackup,
  updateFamilyMemberRole,
  updateAccountPreferences,
} from "./lib/api";
import { AccountsPage } from "./pages/AccountsPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { PlanningPage } from "./pages/PlanningPage";
import { SecurityPage } from "./pages/SecurityPage";
import { TransactionsPageNext } from "./pages/TransactionsPageNext";

type BusyAction = "" | "save" | "restore" | "reset" | "logout";
type ConfirmAction = "logout" | "restore" | "reset" | null;
type FamilyBusyAction = "" | "create" | "invite" | "join" | "member_update" | "member_remove";

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
  const accountMenuRef = useRef<HTMLDivElement | null>(null);

  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [themeMode, setThemeMode] = useState<"light" | "dark" | "system">("system");
  const [accountMessage, setAccountMessage] = useState("");
  const [accountError, setAccountError] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>("");
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [resetConfirmText, setResetConfirmText] = useState("");
  const [familyBusyAction, setFamilyBusyAction] = useState<FamilyBusyAction>("");
  const [familyBusyUserId, setFamilyBusyUserId] = useState<number | null>(null);
  const [familyName, setFamilyName] = useState("");
  const [selectedFamilyId, setSelectedFamilyId] = useState<number | null>(null);
  const [inviteToken, setInviteToken] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "accountant" | "member" | "viewer">("member");

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

  const familyMembersQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "members"],
    queryFn: () => getFamilyMembers(selectedFamilyId as number),
    enabled: selectedFamilyId !== null,
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
  }, [isAccountMenuOpen, busyAction]);

  useEffect(() => {
    setIsAccountMenuOpen(false);
    setConfirmAction(null);
    setResetConfirmText("");
  }, [location.pathname]);

  useEffect(() => {
    const firstFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
    if (selectedFamilyId === null && firstFamilyId !== null) {
      setSelectedFamilyId(firstFamilyId);
      return;
    }
    if (selectedFamilyId !== null) {
      const exists = (familiesQuery.data?.families ?? []).some((item) => item.id === selectedFamilyId);
      if (!exists) {
        setSelectedFamilyId(firstFamilyId);
      }
    }
  }, [familiesQuery.data?.families, selectedFamilyId]);

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

  async function onCreateFamily() {
    const trimmed = familyName.trim();
    if (!trimmed) {
      setAccountError("Введите название семьи.");
      return;
    }
    setFamilyBusyAction("create");
    setAccountError("");
    setAccountMessage("");
    try {
      const created = await createFamily({ name: trimmed });
      setFamilyName("");
      setSelectedFamilyId(created.id);
      setAccountMessage(`Семейный бюджет "${created.name}" создан.`);
      await queryClient.invalidateQueries({ queryKey: ["families", "me"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось создать семейный бюджет.");
    } finally {
      setFamilyBusyAction("");
    }
  }

  async function onInviteToFamily() {
    if (selectedFamilyId === null) {
      setAccountError("Сначала выберите семейный бюджет.");
      return;
    }
    const email = inviteEmail.trim().toLowerCase();
    if (!email) {
      setAccountError("Введите email участника.");
      return;
    }
    setFamilyBusyAction("invite");
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await createFamilyInvite({
        family_id: selectedFamilyId,
        email,
        role: inviteRole,
      });
      setInviteEmail("");
      setAccountMessage(response.message);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["families", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] }),
      ]);
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось отправить приглашение.");
    } finally {
      setFamilyBusyAction("");
    }
  }

  async function onAcceptFamilyInvite() {
    const token = inviteToken.trim();
    if (!token) {
      setAccountError("Введите токен приглашения.");
      return;
    }
    setFamilyBusyAction("join");
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await acceptFamilyInvite({ token });
      setInviteToken("");
      setAccountMessage(response.message);
      setSelectedFamilyId(response.family_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["families", "me"] }),
        queryClient.invalidateQueries({ queryKey: ["families", response.family_id, "members"] }),
      ]);
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось подключиться к семейному бюджету.");
    } finally {
      setFamilyBusyAction("");
    }
  }

  async function onUpdateMemberRole(memberUserId: number, role: "admin" | "accountant" | "member" | "viewer") {
    if (selectedFamilyId === null) {
      setAccountError("Сначала выберите семейный бюджет.");
      return;
    }
    setFamilyBusyAction("member_update");
    setFamilyBusyUserId(memberUserId);
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await updateFamilyMemberRole({
        family_id: selectedFamilyId,
        user_id: memberUserId,
        role,
      });
      setAccountMessage(response.message);
      await queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось обновить роль участника.");
    } finally {
      setFamilyBusyAction("");
      setFamilyBusyUserId(null);
    }
  }

  async function onRemoveMember(memberUserId: number) {
    if (selectedFamilyId === null) {
      setAccountError("Сначала выберите семейный бюджет.");
      return;
    }
    setFamilyBusyAction("member_remove");
    setFamilyBusyUserId(memberUserId);
    setAccountError("");
    setAccountMessage("");
    try {
      const response = await removeFamilyMember({
        family_id: selectedFamilyId,
        user_id: memberUserId,
      });
      setAccountMessage(response.message);
      await queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] });
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "Не удалось исключить участника.");
    } finally {
      setFamilyBusyAction("");
      setFamilyBusyUserId(null);
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
  const selectedFamily = (familiesQuery.data?.families ?? []).find((item) => item.id === selectedFamilyId) ?? null;
  const canManageFamilyMembers = selectedFamily?.role === "owner" || selectedFamily?.role === "admin";

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

          <div className={isAccountMenuOpen ? "account-overlay open" : "account-overlay"} onClick={() => setIsAccountMenuOpen(false)} />

          <div className={isAccountMenuOpen ? "account-dropdown open" : "account-dropdown"} role="menu">
            <div className="account-dropdown-head">
              <strong>{displayName || "Пользователь"}</strong>
              <span title={userEmail}>{userEmail || "email не указан"}</span>
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
              <p className="account-dropdown-title">Семейный бюджет</p>
              <label className="account-field">
                <span>Вступить по токену приглашения</span>
                <input
                  autoComplete="off"
                  disabled={familyBusyAction !== ""}
                  onChange={(event) => setInviteToken(event.target.value)}
                  placeholder="Вставьте токен приглашения"
                  value={inviteToken}
                />
              </label>
              <button className="account-action" disabled={familyBusyAction !== ""} onClick={() => void onAcceptFamilyInvite()} type="button">
                {familyBusyAction === "join" ? "Подключаем..." : "Подключиться к семье"}
              </button>

              {(familiesQuery.data?.families ?? []).length === 0 ? (
                <>
                  <label className="account-field">
                    <span>Название семьи</span>
                    <input
                      disabled={familyBusyAction !== ""}
                      maxLength={120}
                      onChange={(event) => setFamilyName(event.target.value)}
                      placeholder="Например, Семья Петровых"
                      value={familyName}
                    />
                  </label>
                  <button className="account-action" disabled={familyBusyAction !== ""} onClick={() => void onCreateFamily()} type="button">
                    {familyBusyAction === "create" ? "Создаем..." : "Создать семейный бюджет"}
                  </button>
                </>
              ) : (
                <>
                  <label className="account-field">
                    <span>Выбранная семья</span>
                    <select
                      disabled={familyBusyAction !== ""}
                      onChange={(event) => setSelectedFamilyId(Number(event.target.value))}
                      value={selectedFamilyId ?? ""}
                    >
                      {(familiesQuery.data?.families ?? []).map((family) => (
                        <option key={family.id} value={family.id}>
                          {family.name} ({family.role})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="account-field">
                    <span>Email участника</span>
                    <input
                      autoComplete="off"
                      disabled={familyBusyAction !== "" || !canManageFamilyMembers}
                      onChange={(event) => setInviteEmail(event.target.value)}
                      placeholder="user@example.com"
                      value={inviteEmail}
                    />
                  </label>
                  <label className="account-field">
                    <span>Роль</span>
                    <select
                      disabled={familyBusyAction !== "" || !canManageFamilyMembers}
                      onChange={(event) => setInviteRole(event.target.value as "admin" | "accountant" | "member" | "viewer")}
                      value={inviteRole}
                    >
                      <option value="member">Участник</option>
                      <option value="viewer">Только просмотр</option>
                      <option value="accountant">Бухгалтер</option>
                      <option value="admin">Администратор</option>
                    </select>
                  </label>
                  <button
                    className="account-action"
                    disabled={familyBusyAction !== "" || !canManageFamilyMembers}
                    onClick={() => void onInviteToFamily()}
                    type="button"
                  >
                    {familyBusyAction === "invite" ? "Отправляем..." : "Пригласить в семью"}
                  </button>
                  {selectedFamilyId !== null ? (
                    <>
                      <p className="account-meta">Участников: {(familyMembersQuery.data?.members ?? []).length}</p>
                      {!canManageFamilyMembers ? <p className="account-meta">У вас роль только для участия без управления составом.</p> : null}
                      <div className="family-members-list">
                        {(familyMembersQuery.data?.members ?? []).map((member) => {
                          const isSelf = member.user_id === currentUser?.id;
                          const canManageThisMember =
                            canManageFamilyMembers &&
                            !isSelf &&
                            member.role !== "owner" &&
                            !(selectedFamily?.role === "admin" && member.role === "admin");
                          return (
                            <div className="family-member-item" key={member.user_id}>
                              <div className="family-member-main">
                                <strong>{member.email}</strong>
                                <span>{member.role}</span>
                              </div>
                              <div className="family-member-controls">
                                <select
                                  disabled={!canManageThisMember || familyBusyAction !== ""}
                                  onChange={(event) =>
                                    void onUpdateMemberRole(
                                      member.user_id,
                                      event.target.value as "admin" | "accountant" | "member" | "viewer",
                                    )
                                  }
                                  value={member.role === "owner" ? "member" : member.role}
                                >
                                  <option value="member">Участник</option>
                                  <option value="viewer">Просмотр</option>
                                  <option value="accountant">Бухгалтер</option>
                                  <option value="admin">Админ</option>
                                </select>
                                <button
                                  className="account-action danger"
                                  disabled={!canManageThisMember || familyBusyAction !== ""}
                                  onClick={() => void onRemoveMember(member.user_id)}
                                  type="button"
                                >
                                  {familyBusyAction === "member_remove" && familyBusyUserId === member.user_id ? "Исключаем..." : "Исключить"}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  ) : null}
                </>
              )}
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
        <Route element={<SecurityPage />} path="/security" />
        <Route element={<Navigate replace to="/planning" />} path="/budgets" />
        <Route element={<Navigate replace to="/planning" />} path="/recurring" />
      </Routes>
    </div>
  );
}
