import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import AppShellNext from "./AppShellNext";
import { ApiError, getMe } from "./lib/api";
import { LoginPage } from "./pages/LoginPage";
import "./styles.css";


const queryClient = new QueryClient();

function RequireAuth({ children }: { children: React.ReactElement }) {
  const location = useLocation();
  const { data, isLoading, error } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });

  if (isLoading) {
    return <div className="auth-loading">Проверяем сессию...</div>;
  }

  if (error instanceof ApiError && error.status === 401) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  if (!data) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  return children;
}

function AppRouter() {
  return (
    <Routes>
      <Route element={<LoginPage />} path="/login" />
      <Route
        element={(
          <RequireAuth>
            <AppShellNext />
          </RequireAuth>
        )}
        path="/*"
      />
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
