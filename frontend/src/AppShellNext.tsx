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
    return "РґР°С‚Р° РЅРµРёР·РІРµСЃС‚РЅР°";
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

function familyRoleLabel(role: "owner" | "member" | "viewer"): string {
  if (role === "owner") {
    return "Р’Р»Р°РґРµР»РµС†";
  }
  if (role === "viewer") {
    return "РўРѕР»СЊРєРѕ РїСЂРѕСЃРјРѕС‚СЂ";
  }
  return "РџРѕРјРѕС‰РЅРёРє";
}

export default function AppShellNext() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const topbarLinksRef = useRef<HTMLDivElement | null>(null);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  const notificationsRef = useRef<HTMLDivElement | null>(null);

  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
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
  const pendingInvites = pendingInvitesQuery.data?.invites ?? [];
  const pendingInvitesCount = pendingInvites.length;
  const showFamilyTab = workspaceMode === "family" && hasFamily;

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
      const clickedInsideAccount = Boolean(accountMenuRef.current && accountMenuRef.current.contains(node));
      const clickedInsideNotifications = Boolean(notificationsRef.current && notificationsRef.current.contains(node));
      if (!clickedInsideAccount) {
        setIsAccountMenuOpen(false);
      }
      if (!clickedInsideNotifications) {
        setIsNotificationsOpen(false);
      }
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsAccountMenuOpen(false);
        setIsNotificationsOpen(false);
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
      setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ С‚РµРјСѓ.");
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
        setAccountMessage("РЎРЅР°С‡Р°Р»Р° РїСЂРёРјРёС‚Рµ РїСЂРёРіР»Р°С€РµРЅРёРµ РІ СЃРµРјСЊСЋ РёР»Рё СЃРѕР·РґР°Р№С‚Рµ СЃРµРјРµР№РЅС‹Р№ Р±СЋРґР¶РµС‚.");
      }
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЂРµР¶РёРј.");
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
      setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРёРЅСЏС‚СЊ РїСЂРёРіР»Р°С€РµРЅРёРµ.");
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
      setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєР»РѕРЅРёС‚СЊ РїСЂРёРіР»Р°С€РµРЅРёРµ.");
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
      setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЂРµР·РµСЂРІРЅСѓСЋ РєРѕРїРёСЋ.");
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
        setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ РІРѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ РґР°РЅРЅС‹Рµ.");
      } finally {
        setBusyAction("");
        setConfirmAction(null);
      }
      return;
    }

    if (confirmAction === "reset") {
      const normalized = resetConfirmText.trim().toUpperCase();
      if (normalized !== "РЎР‘Р РћРЎ") {
        setAccountError("Р’РІРµРґРёС‚Рµ РЎР‘Р РћРЎ РґР»СЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ.");
        return;
      }

      setBusyAction("reset");
      try {
        const response = await resetAllAccountData({ confirm_text: "РЎР‘Р РћРЎ" });
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
        setAccountError(error instanceof Error ? error.message : "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‡РёСЃС‚РёС‚СЊ РґР°РЅРЅС‹Рµ.");
      } finally {
        setBusyAction("");
        setConfirmAction(null);
        setResetConfirmText("");
      }
    }
  }

  const userEmail = currentUser?.email ?? "";
  const displayName = userEmail ? userEmail.split("@")[0] : "РџСЂРѕС„РёР»СЊ";
  const initials = displayName.slice(0, 2).toUpperCase();

  const confirmTitle = useMemo(() => {
    if (confirmAction === "logout") {
      return "РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РІС‹С…РѕРґР°";
    }
    if (confirmAction === "restore") {
      return "Р’РѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ РґР°РЅРЅС‹Рµ";
    }
    if (confirmAction === "reset") {
      return "РћР±РЅСѓР»РёС‚СЊ РґР°РЅРЅС‹Рµ";
    }
    return "";
  }, [confirmAction]);

  const confirmText = useMemo(() => {
    if (confirmAction === "logout") {
      return "Р’С‹ РґРµР№СЃС‚РІРёС‚РµР»СЊРЅРѕ С…РѕС‚РёС‚Рµ РІС‹Р№С‚Рё РёР· Р°РєРєР°СѓРЅС‚Р°?";
    }
    if (confirmAction === "restore") {
      return "РўРµРєСѓС‰РёРµ РґР°РЅРЅС‹Рµ Р±СѓРґСѓС‚ Р·Р°РјРµРЅРµРЅС‹ РїРѕСЃР»РµРґРЅРµР№ СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРµР№.";
    }
    if (confirmAction === "reset") {
      return "Р‘СѓРґСѓС‚ СѓРґР°Р»РµРЅС‹ РІСЃРµ С„РёРЅР°РЅСЃРѕРІС‹Рµ РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ. Р­С‚Рѕ РґРµР№СЃС‚РІРёРµ РЅРµРѕР±СЂР°С‚РёРјРѕ.";
    }
    return "";
  }, [confirmAction]);

  const confirmButtonLabel = useMemo(() => {
    if (confirmAction === "logout") {
      return "Р’С‹Р№С‚Рё";
    }
    if (confirmAction === "restore") {
      return "Р’РѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ";
    }
    if (confirmAction === "reset") {
      return "РћР±РЅСѓР»РёС‚СЊ";
    }
    return "РџРѕРґС‚РІРµСЂРґРёС‚СЊ";
  }, [confirmAction]);

  const resetAllowed = confirmAction !== "reset" || resetConfirmText.trim().toUpperCase() === "РЎР‘Р РћРЎ";

  return (
    <div className="shell">
      <nav className="topbar">
        <div className="topbar-links" ref={topbarLinksRef}>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} end to="/">
            Р“Р»Р°РІРЅР°СЏ
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/transactions">
            РўСЂР°РЅР·Р°РєС†РёРё
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/categories">
            РљР°С‚РµРіРѕСЂРёРё
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/planning">
            РџР»Р°РЅРёСЂРѕРІР°РЅРёРµ
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/accounts">
            РЎС‡РµС‚Р°
          </NavLink>
          {showFamilyTab ? (
            <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/family">
              РЎРµРјСЊСЏ
            </NavLink>
          ) : null}
        </div>

        <div className="notifications-menu" ref={notificationsRef}>
          <button
            aria-expanded={isNotificationsOpen}
            aria-haspopup="menu"
            className="notification-trigger"
            onClick={() => {
              setIsAccountMenuOpen(false);
              setIsNotificationsOpen((prev) => !prev);
            }}
            type="button"
          >
            <span className="notification-icon" aria-hidden="true">
              рџ””
            </span>
            {pendingInvitesCount > 0 ? <span className="notification-badge">{pendingInvitesCount}</span> : null}
          </button>
          <div
            className={isNotificationsOpen ? "account-overlay open" : "account-overlay"}
            onClick={() => setIsNotificationsOpen(false)}
          />
          <div className={isNotificationsOpen ? "notifications-dropdown open" : "notifications-dropdown"} role="menu">
            <div className="account-dropdown-head">
              <strong>РЈРІРµРґРѕРјР»РµРЅРёСЏ</strong>
              <span>{pendingInvitesCount > 0 ? `РќРѕРІС‹С… РїСЂРёРіР»Р°С€РµРЅРёР№: ${pendingInvitesCount}` : "РќРѕРІС‹С… РїСЂРёРіР»Р°С€РµРЅРёР№ РЅРµС‚"}</span>
            </div>
            {pendingInvitesCount === 0 ? (
              <p className="account-meta">РЎРµР№С‡Р°СЃ Р·РґРµСЃСЊ РїСѓСЃС‚Рѕ.</p>
            ) : (
              <div className="account-dropdown-section">
                {pendingInvites.map((invite) => (
                  <div className="family-member-item" key={invite.invite_id}>
                    <div className="family-member-main">
                      <strong>{invite.family_name}</strong>
                      <span>РћС‚: {invite.invited_by_email}</span>
                      <span>Р РѕР»СЊ: {familyRoleLabel(invite.role)}</span>
                    </div>
                    <div className="family-member-controls">
                      <button
                        className="account-action"
                        disabled={inviteAction !== ""}
                        onClick={() => void onAcceptInvite(invite.invite_id)}
                        type="button"
                      >
                        {inviteAction === "accept" && inviteBusyId === invite.invite_id ? "РџСЂРёРЅРёРјР°РµРј..." : "РџСЂРёРЅСЏС‚СЊ"}
                      </button>
                      <button
                        className="account-action danger"
                        disabled={inviteAction !== ""}
                        onClick={() => void onDeclineInvite(invite.invite_id)}
                        type="button"
                      >
                        {inviteAction === "decline" && inviteBusyId === invite.invite_id ? "РћС‚РєР»РѕРЅСЏРµРј..." : "РћС‚РєР»РѕРЅРёС‚СЊ"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="account-menu" ref={accountMenuRef}>
          <button
            aria-expanded={isAccountMenuOpen}
            aria-haspopup="menu"
            className="account-trigger"
            onClick={() => {
              setIsNotificationsOpen(false);
              setIsAccountMenuOpen((prev) => !prev);
            }}
            type="button"
          >
            <span className="account-trigger-avatar">{initials || "U"}</span>
            <span className="account-trigger-label">РђРєРєР°СѓРЅС‚</span>
          </button>

          <div className={isAccountMenuOpen ? "account-overlay open" : "account-overlay"} onClick={() => setIsAccountMenuOpen(false)} />

          <div className={isAccountMenuOpen ? "account-dropdown open" : "account-dropdown"} role="menu">
            <div className="account-dropdown-head">
              <strong>{displayName || "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ"}</strong>
              <span title={userEmail}>{userEmail || "email РЅРµ СѓРєР°Р·Р°РЅ"}</span>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">Р РµР¶РёРј</p>
              <div className="account-theme-row">
                <button
                  className={workspaceMode === "personal" ? "account-pill active" : "account-pill"}
                  onClick={() => void onWorkspaceChange("personal")}
                  type="button"
                >
                  Р›РёС‡РЅС‹Р№
                </button>
                <button
                  className={workspaceMode === "family" ? "account-pill active" : "account-pill"}
                  onClick={() => void onWorkspaceChange("family")}
                  type="button"
                >
                  РЎРѕРІРјРµСЃС‚РЅС‹Р№
                </button>
              </div>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">РўРµРјР° РїСЂРёР»РѕР¶РµРЅРёСЏ</p>
              <div className="account-theme-row">
                <button className={themeMode === "light" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("light")} type="button">
                  РЎРІРµС‚Р»Р°СЏ
                </button>
                <button className={themeMode === "dark" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("dark")} type="button">
                  РўС‘РјРЅР°СЏ
                </button>
                <button className={themeMode === "system" ? "account-pill active" : "account-pill"} onClick={() => void onThemeChange("system")} type="button">
                  РЎРёСЃС‚РµРјР°
                </button>
              </div>
            </div>

            {pendingInvitesCount > 0 ? (
              <div className="account-dropdown-section">
                <p className="account-dropdown-title">РџСЂРёРіР»Р°С€РµРЅРёСЏ</p>
                {pendingInvites.map((invite) => (
                  <div className="family-member-item" key={invite.invite_id}>
                    <div className="family-member-main">
                      <strong>{invite.family_name}</strong>
                      <span>РћС‚: {invite.invited_by_email}</span>
                      <span>Р РѕР»СЊ: {familyRoleLabel(invite.role)}</span>
                    </div>
                    <div className="family-member-controls">
                      <button
                        className="account-action"
                        disabled={inviteAction !== ""}
                        onClick={() => void onAcceptInvite(invite.invite_id)}
                        type="button"
                      >
                        {inviteAction === "accept" && inviteBusyId === invite.invite_id ? "РџСЂРёРЅРёРјР°РµРј..." : "РџСЂРёРЅСЏС‚СЊ"}
                      </button>
                      <button
                        className="account-action danger"
                        disabled={inviteAction !== ""}
                        onClick={() => void onDeclineInvite(invite.invite_id)}
                        type="button"
                      >
                        {inviteAction === "decline" && inviteBusyId === invite.invite_id ? "РћС‚РєР»РѕРЅСЏРµРј..." : "РћС‚РєР»РѕРЅРёС‚СЊ"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">РЈРїСЂР°РІР»РµРЅРёРµ</p>
              <NavLink className="account-action" onClick={() => setIsAccountMenuOpen(false)} to="/security">
                РќР°СЃС‚СЂРѕР№РєРё Рё Р±РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ
              </NavLink>
            </div>

            <div className="account-dropdown-section">
              <p className="account-dropdown-title">РњРѕРё РґР°РЅРЅС‹Рµ</p>
              <button className="account-action" disabled={busyAction !== ""} onClick={() => void onSaveBackup()} type="button">
                {busyAction === "save" ? "РЎРѕС…СЂР°РЅСЏРµРј..." : "РЎРѕС…СЂР°РЅРёС‚СЊ РґР°РЅРЅС‹Рµ (1 СЃР»РѕС‚)"}
              </button>
              <button
                className="account-action"
                disabled={busyAction !== "" || !backupInfoQuery.data?.has_backup}
                onClick={() => openConfirm("restore")}
                type="button"
              >
                Р’РѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ РґР°РЅРЅС‹Рµ
              </button>
              <button className="account-action danger" disabled={busyAction !== ""} onClick={() => openConfirm("reset")} type="button">
                РћР±РЅСѓР»РёС‚СЊ РґР°РЅРЅС‹Рµ
              </button>
            </div>

            {backupInfoQuery.data?.has_backup ? (
              <p className="account-meta">РџРѕСЃР»РµРґРЅСЏСЏ РєРѕРїРёСЏ: {formatBackupTimestamp(backupInfoQuery.data.updated_at || "")}</p>
            ) : (
              <p className="account-meta">Р РµР·РµСЂРІРЅР°СЏ РєРѕРїРёСЏ РµС‰С‘ РЅРµ СЃРѕР·РґР°РЅР°.</p>
            )}

            {busyAction !== "" ? <p className="account-meta">Р’С‹РїРѕР»РЅСЏРµРј РѕРїРµСЂР°С†РёСЋ...</p> : null}
            {accountMessage ? <p className="account-feedback success">{accountMessage}</p> : null}
            {accountError ? <p className="account-feedback error">{accountError}</p> : null}

            <button className="account-action danger" disabled={busyAction !== ""} onClick={() => openConfirm("logout")} type="button">
              Р’С‹Р№С‚Рё
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
                <span>Р’РІРµРґРёС‚Рµ РЎР‘Р РћРЎ РґР»СЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ</span>
                <input
                  autoComplete="off"
                  onChange={(event) => setResetConfirmText(event.target.value)}
                  placeholder="РЎР‘Р РћРЎ"
                  value={resetConfirmText}
                />
              </label>
            ) : null}

            <div className="confirm-actions">
              <button className="account-action" disabled={busyAction !== ""} onClick={closeConfirm} type="button">
                РћС‚РјРµРЅР°
              </button>
              <button
                className="account-action danger"
                disabled={busyAction !== "" || !resetAllowed}
                onClick={() => void runConfirmedAction()}
                type="button"
              >
                {busyAction !== "" ? "РџРѕРґРѕР¶РґРёС‚Рµ..." : confirmButtonLabel}
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
