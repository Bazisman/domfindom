import { useEffect, useRef } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getMe, logout } from "./lib/api";
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
  const { data: currentUser } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
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

  async function onLogout() {
    await logout();
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    navigate("/login", { replace: true });
  }

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
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/security">
            Безопасность
          </NavLink>
        </div>
        <div className="topbar-user">
          <span>{currentUser?.email ?? ""}</span>
          <button className="btn btn-ghost" onClick={onLogout} type="button">
            Выйти
          </button>
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
