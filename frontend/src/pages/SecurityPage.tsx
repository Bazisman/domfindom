import { FormEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { changePassword, getActiveSessions, revokeOtherSessions, revokeSessionById } from "../lib/api";

export function SecurityPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [sessionsMessage, setSessionsMessage] = useState<string | null>(null);

  const sessionsQuery = useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: getActiveSessions,
    refetchInterval: 30_000,
  });

  const sessions = useMemo(() => sessionsQuery.data?.sessions ?? [], [sessionsQuery.data]);

  const changePasswordMutation = useMutation({
    mutationFn: changePassword,
    onSuccess: async (response) => {
      setError(null);
      setMessage(response.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      navigate("/login", { replace: true });
    },
    onError: (mutationError: Error) => {
      setMessage(null);
      setError(mutationError.message);
    },
  });

  const revokeOthersMutation = useMutation({
    mutationFn: revokeOtherSessions,
    onSuccess: async (response) => {
      setSessionsMessage(response.message);
      await sessionsQuery.refetch();
    },
    onError: (mutationError: Error) => {
      setSessionsMessage(mutationError.message);
    },
  });

  const revokeSessionMutation = useMutation({
    mutationFn: revokeSessionById,
    onSuccess: async (response) => {
      setSessionsMessage(response.message);
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      await sessionsQuery.refetch();
      if (/(войдите снова|log in again)/i.test(response.message)) {
        navigate("/login", { replace: true });
      }
    },
    onError: (mutationError: Error) => {
      setSessionsMessage(mutationError.message);
    },
  });

  function formatDate(value: string) {
    const parsed = new Date(value.replace(" ", "T") + "Z");
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(parsed);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setError("Заполните все поля.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Новый пароль должен быть не короче 8 символов.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Подтверждение пароля не совпадает.");
      return;
    }

    changePasswordMutation.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  return (
    <main className="grid">
      <section className="panel panel-form panel-wide">
        <div className="panel-header">
          <h2>Безопасность</h2>
          <span>Смена пароля аккаунта</span>
        </div>

        <form className="transaction-form" onSubmit={onSubmit}>
          <label className="field">
            <span>Текущий пароль</span>
            <input
              autoComplete="current-password"
              onChange={(event) => setCurrentPassword(event.target.value)}
              type="password"
              value={currentPassword}
            />
          </label>

          <label className="field">
            <span>Новый пароль</span>
            <input
              autoComplete="new-password"
              minLength={8}
              onChange={(event) => setNewPassword(event.target.value)}
              type="password"
              value={newPassword}
            />
          </label>

          <label className="field">
            <span>Подтверждение нового пароля</span>
            <input
              autoComplete="new-password"
              minLength={8}
              onChange={(event) => setConfirmPassword(event.target.value)}
              type="password"
              value={confirmPassword}
            />
          </label>

          {error ? <p className="form-error">{error}</p> : null}
          {message ? <p className="form-status form-status-success">{message}</p> : null}

          <button className="primary-button" disabled={changePasswordMutation.isPending} type="submit">
            {changePasswordMutation.isPending ? "Обновляем..." : "Изменить пароль"}
          </button>
        </form>
      </section>

      <section className="panel panel-wide">
        <div className="panel-header">
          <h3>Активные сессии</h3>
          <button
            className="ghost-button"
            disabled={revokeOthersMutation.isPending || sessions.length <= 1}
            onClick={() => revokeOthersMutation.mutate()}
            type="button"
          >
            {revokeOthersMutation.isPending ? "Завершаем..." : "Завершить все остальные"}
          </button>
        </div>

        {sessionsMessage ? <p className="form-status">{sessionsMessage}</p> : null}
        {sessionsQuery.isLoading ? <p className="muted">Загружаем сессии...</p> : null}
        {sessionsQuery.isError ? <p className="form-error">Не удалось загрузить сессии.</p> : null}

        {!sessionsQuery.isLoading && !sessionsQuery.isError && (
          <div className="list">
            {sessions.map((session) => (
              <article className="list-item" key={session.id}>
                <div>
                  <strong>
                    {session.is_current ? "Текущая сессия" : "Сессия"} #{session.id}
                  </strong>
                  <p>IP: {session.ip || "неизвестно"}</p>
                  <p>Agent: {session.user_agent || "не указан"}</p>
                  <p>Создана: {formatDate(session.created_at)}</p>
                  <p>Истекает: {formatDate(session.expires_at)}</p>
                </div>
                <button
                  className="ghost-button"
                  disabled={revokeSessionMutation.isPending && revokeSessionMutation.variables === session.id}
                  onClick={() => revokeSessionMutation.mutate(session.id)}
                  type="button"
                >
                  {session.is_current ? "Выйти с этого устройства" : "Завершить"}
                </button>
              </article>
            ))}
            {sessions.length === 0 ? <p className="muted">Активных сессий не найдено.</p> : null}
          </div>
        )}
      </section>
    </main>
  );
}
