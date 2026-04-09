import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { AccountsPage } from "./pages/AccountsPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { PlanningPage } from "./pages/PlanningPage";
import { TransactionsPageNext } from "./pages/TransactionsPageNext";

export default function AppShellNext() {
  return (
    <div className="shell">
      <nav className="topbar">
        <div className="topbar-links">
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            end
            to="/"
          >
            Главная
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/transactions"
          >
            Транзакции
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/categories"
          >
            Категории
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/planning"
          >
            Планирование
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/accounts"
          >
            Счета
          </NavLink>
        </div>
      </nav>

      <Routes>
        <Route element={<DashboardPage />} path="/" />
        <Route element={<TransactionsPageNext />} path="/transactions" />
        <Route element={<CategoriesPage />} path="/categories" />
        <Route element={<PlanningPage />} path="/planning" />
        <Route element={<AccountsPage />} path="/accounts" />
        <Route element={<Navigate replace to="/planning" />} path="/budgets" />
        <Route element={<Navigate replace to="/planning" />} path="/recurring" />
      </Routes>
    </div>
  );
}
