import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError, acceptFamilyInvite, confirmPasswordReset, login, register, requestPasswordReset, verifyEmail } from "../lib/api";

type AuthMode = "login" | "register" | "reset_request" | "reset_confirm";

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tokenFromUrl = searchParams.get("reset_token");
  const emailVerifyTokenFromUrl = searchParams.get("verify_email_token");
  const familyInviteTokenFromUrl = searchParams.get("family_invite_token");
  const hasTokenFromUrl = Boolean(tokenFromUrl);

  useEffect(() => {
    if (tokenFromUrl && tokenFromUrl !== resetToken) {
      setResetToken(tokenFromUrl);
      setMode("reset_confirm");
      setMessage("Ссылка для сброса получена. Укажите новый пароль.");
      setError(null);
    }
  }, [tokenFromUrl, resetToken]);

  useEffect(() => {
    async function runEmailVerification(token: string) {
      setLoading(true);
      setError(null);
      setMessage("Подтверждаем email...");
      try {
        const response = await verifyEmail({ token });
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/", { replace: true });
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          setError("Не удалось подтвердить email");
        }
      } finally {
        setLoading(false);
      }
    }

    if (emailVerifyTokenFromUrl) {
      void runEmailVerification(emailVerifyTokenFromUrl);
    }
  }, [emailVerifyTokenFromUrl, navigate, queryClient]);

  const title = useMemo(() => {
    if (mode === "login") {
      return "Вход";
    }
    if (mode === "register") {
      return "Регистрация";
    }
    if (mode === "reset_request") {
      return "Восстановление пароля";
    }
    return "Подтверждение нового пароля";
  }, [mode]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (mode === "reset_confirm") {
      if (!resetToken.trim()) {
        setError("Токен сброса не найден. Откройте ссылку из письма заново.");
        return;
      }
      if (newPassword.length < 8) {
        setError("Новый пароль должен быть не короче 8 символов.");
        return;
      }
      const hasUpper = /[A-Z]/.test(newPassword);
      const hasLower = /[a-z]/.test(newPassword);
      const hasDigit = /\d/.test(newPassword);
      if (!(hasUpper && hasLower && hasDigit)) {
        setError("Пароль должен содержать заглавные и строчные буквы, а также цифры.");
        return;
      }
    }
    setLoading(true);
    try {
      if (mode === "login") {
        const response = await login({ email, password });
        if (familyInviteTokenFromUrl) {
          try {
            await acceptFamilyInvite({ token: familyInviteTokenFromUrl });
            void queryClient.invalidateQueries({ queryKey: ["families", "me"] });
            void queryClient.invalidateQueries({ queryKey: ["families", "invites", "pending"] });
          } catch {
            // do not block login if invite token is invalid/expired
          }
        }
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/", { replace: true });
      } else if (mode === "register") {
        const response = await register({ email, password });
        if (response.requires_email_verification) {
          setPassword("");
          setMessage(response.message || "Проверьте почту и подтвердите email.");
          setMode("login");
          return;
        }
        if (familyInviteTokenFromUrl) {
          try {
            await acceptFamilyInvite({ token: familyInviteTokenFromUrl });
            void queryClient.invalidateQueries({ queryKey: ["families", "me"] });
            void queryClient.invalidateQueries({ queryKey: ["families", "invites", "pending"] });
          } catch {
            // do not block registration if invite token is invalid/expired
          }
        }
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/", { replace: true });
      } else if (mode === "reset_request") {
        const response = await requestPasswordReset({ email });
        if (response.reset_token) {
          setResetToken(response.reset_token);
          setMode("reset_confirm");
          setMessage("Токен сброса создан. Укажите новый пароль.");
        } else {
          setMessage(response.message);
        }
      } else {
        const response = await confirmPasswordReset({ token: resetToken, new_password: newPassword });
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        setMode("login");
        setPassword("");
        setNewPassword("");
        setResetToken("");
        navigate("/", { replace: true });
      }
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.message === "Invalid credentials" || e.message === "Неверный email или пароль") {
          setError("Неверный email или пароль");
        } else {
          setError(e.message);
        }
      } else {
        setError("Не удалось выполнить запрос");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <h1>{title}</h1>
        <p className="auth-subtitle">Личный защищенный доступ к вашим финансам</p>
        <form className="auth-form" onSubmit={onSubmit}>
          {(mode === "login" || mode === "register" || mode === "reset_request") && (
            <label>
              Email
              <input
                autoComplete="email"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
          )}
          {(mode === "login" || mode === "register") && (
            <label>
              Пароль
              <input
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
          )}
          {mode === "reset_confirm" && (
            <>
              {!hasTokenFromUrl && (
                <label>
                  Токен сброса
                  <input
                    autoComplete="off"
                    onChange={(event) => setResetToken(event.target.value)}
                    required
                    type="text"
                    value={resetToken}
                  />
                </label>
              )}
              <label>
                Новый пароль
                <input
                  autoComplete="new-password"
                  minLength={8}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                  type="password"
                  value={newPassword}
                />
              </label>
              <p className="muted">Минимум 8 символов, заглавные и строчные буквы, цифры.</p>
            </>
          )}
          {error ? <div className="auth-error">{error}</div> : null}
          {message ? <div className="auth-message">{message}</div> : null}
          <button className="btn btn-primary auth-submit" disabled={loading} type="submit">
            {loading
              ? "Подождите..."
              : mode === "login"
                ? "Войти"
                : mode === "register"
                  ? "Создать аккаунт"
                  : mode === "reset_request"
                    ? "Запросить сброс"
                    : "Сохранить новый пароль"}
          </button>
        </form>
        <div className="auth-links">
          <button
            className="auth-switch"
            onClick={() => {
              setMessage(null);
              setError(null);
              setMode(mode === "login" ? "register" : "login");
            }}
            type="button"
          >
            {mode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
          </button>
          {mode !== "reset_request" && mode !== "reset_confirm" && (
            <button
              className="auth-switch"
              onClick={() => {
                setMessage(null);
                setError(null);
                setMode("reset_request");
              }}
              type="button"
            >
              Забыли пароль?
            </button>
          )}
          {(mode === "reset_request" || mode === "reset_confirm") && (
            <button
              className="auth-switch"
              onClick={() => {
                setMessage(null);
                setError(null);
                setMode("login");
                setResetToken("");
                navigate("/login", { replace: true });
              }}
              type="button"
            >
              Вернуться ко входу
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
