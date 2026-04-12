import { NavLink, Route, Routes } from "react-router-dom";

import { AccountsPage } from "./pages/AccountsPage";
import { BudgetsPage } from "./pages/BudgetsPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { DashboardPage } from "./pages/DashboardPage";
import { RecurringPage } from "./pages/RecurringPage";
import { TransactionsPage } from "./pages/TransactionsPage";

export default function AppShell() {
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
            to="/budgets"
          >
            Бюджеты
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/accounts"
          >
            Счета
          </NavLink>
          <NavLink
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            to="/recurring"
          >
            Регулярные
          </NavLink>
        </div>
      </nav>

      <Routes>
        <Route element={<DashboardPage />} path="/" />
        <Route element={<TransactionsPage />} path="/transactions" />
        <Route element={<CategoriesPage />} path="/categories" />
        <Route element={<BudgetsPage />} path="/budgets" />
        <Route element={<AccountsPage />} path="/accounts" />
        <Route element={<RecurringPage />} path="/recurring" />
      </Routes>
    </div>
  );
}
