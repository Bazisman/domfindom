import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  acceptFamilyInvite,
  confirmAccountDelete,
  confirmPasswordReset,
  login,
  register,
  requestPasswordReset,
  verifyEmail,
} from "../lib/api";

type AuthMode = "login" | "register" | "reset_request" | "reset_confirm";

function validateEmailInput(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) {
    return "Введите email.";
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
    return "Укажите корректный email.";
  }
  return null;
}

function validateStrongPassword(value: string): string | null {
  if (value.length < 8) {
    return "Пароль должен быть не короче 8 символов.";
  }
  const hasUpper = /[A-Z]/.test(value);
  const hasLower = /[a-z]/.test(value);
  const hasDigit = /\d/.test(value);
  if (!(hasUpper && hasLower && hasDigit)) {
    return "Пароль должен содержать заглавные и строчные буквы, а также цифры.";
  }
  return null;
}

function normalizeAuthErrorMessage(message: string, fallback: string): string {
  const normalized = message.trim();
  if (!normalized) {
    return fallback;
  }

  const lower = normalized.toLowerCase();
  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return "Не удалось связаться с сервером. Проверьте интернет и попробуйте снова.";
  }
  if (lower.includes("api error 500")) {
    return "Сервис временно недоступен. Попробуйте чуть позже.";
  }
  if (lower.includes("api error 422")) {
    return "Проверьте правильность заполнения полей.";
  }
  if (lower.includes("invalid credentials")) {
    return "Неверный email или пароль.";
  }

  return normalized;
}

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
  const accountDeleteTokenFromUrl = searchParams.get("account_delete_token");
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
          setError(normalizeAuthErrorMessage(e.message, "Не удалось подтвердить email."));
        } else {
          setError("Не удалось подтвердить email.");
        }
      } finally {
        setLoading(false);
      }
    }

    if (emailVerifyTokenFromUrl) {
      void runEmailVerification(emailVerifyTokenFromUrl);
    }
  }, [emailVerifyTokenFromUrl, navigate, queryClient]);

  useEffect(() => {
    async function runAccountDelete(token: string) {
      setLoading(true);
      setError(null);
      setMessage("Подтверждаем удаление аккаунта...");
      try {
        const response = await confirmAccountDelete({ token });
        queryClient.setQueryData(["auth", "me"], null);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        setMode("login");
        setEmail("");
        setPassword("");
        setNewPassword("");
        setResetToken("");
        setMessage(response.message || "Аккаунт удален.");
        navigate("/login", { replace: true });
      } catch (e) {
        if (e instanceof ApiError) {
          setError(normalizeAuthErrorMessage(e.message, "Не удалось подтвердить удаление аккаунта."));
        } else {
          setError("Не удалось подтвердить удаление аккаунта.");
        }
      } finally {
        setLoading(false);
      }
    }

    if (accountDeleteTokenFromUrl) {
      void runAccountDelete(accountDeleteTokenFromUrl);
    }
  }, [accountDeleteTokenFromUrl, navigate, queryClient]);

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

    if (mode === "login") {
      const emailError = validateEmailInput(email);
      if (emailError) {
        setError(emailError);
        return;
      }
      if (!password.trim()) {
        setError("Введите пароль.");
        return;
      }
    }

    if (mode === "register") {
      const emailError = validateEmailInput(email);
      if (emailError) {
        setError(emailError);
        return;
      }
      const passwordError = validateStrongPassword(password);
      if (passwordError) {
        setError(passwordError);
        return;
      }
    }

    if (mode === "reset_request") {
      const emailError = validateEmailInput(email);
      if (emailError) {
        setError(emailError);
        return;
      }
    }

    if (mode === "reset_confirm") {
      if (!resetToken.trim()) {
        setError("Токен сброса не найден. Откройте ссылку из письма заново.");
        return;
      }
      const passwordError = validateStrongPassword(newPassword);
      if (passwordError) {
        setError(passwordError);
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
            // Do not block login if invite token is invalid or expired.
          }
        }
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/", { replace: true });
        return;
      }

      if (mode === "register") {
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
            // Do not block registration if invite token is invalid or expired.
          }
        }
        queryClient.setQueryData(["auth", "me"], response.user);
        void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
        navigate("/", { replace: true });
        return;
      }

      if (mode === "reset_request") {
        const response = await requestPasswordReset({ email });
        setMessage(response.message || "Ссылка на сброс пароля отправлена на почту.");
        return;
      }

      const response = await confirmPasswordReset({ token: resetToken, new_password: newPassword });
      queryClient.setQueryData(["auth", "me"], response.user);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      setMode("login");
      setPassword("");
      setNewPassword("");
      setResetToken("");
      navigate("/", { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setError(normalizeAuthErrorMessage(e.message, "Не удалось выполнить запрос."));
      } else {
        setError("Не удалось выполнить запрос. Попробуйте еще раз.");
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
