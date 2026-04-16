import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  getAccountActivity,
  getAccountPreferences,
  getActiveSessions,
  revokeOtherSessions,
  revokeSessionById,
  updateAccountPreferences,
} from "../lib/api";

const SESSIONS_LIMIT = 8;
const ACTIVITY_LIMIT = 15;

export function SecurityPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [sessionsMessage, setSessionsMessage] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);


  const preferencesQuery = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
  });

  useEffect(() => {
    setDisplayName(preferencesQuery.data?.display_name ?? "");
  }, [preferencesQuery.data?.display_name]);

  const sessionsQuery = useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: () => getActiveSessions(SESSIONS_LIMIT),
    refetchInterval: 30_000,
  });
  const activityQuery = useQuery({
    queryKey: ["auth", "activity"],
    queryFn: () => getAccountActivity(ACTIVITY_LIMIT),
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



  const profileMutation = useMutation({
    mutationFn: updateAccountPreferences,
    onSuccess: async () => {
      setProfileMessage("Имя профиля сохранено.");
      await queryClient.invalidateQueries({ queryKey: ["account", "preferences"] });
    },
    onError: (mutationError: Error) => {
      setProfileMessage(mutationError.message);
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

  function formatEventType(type: string) {
    const labels: Record<string, string> = {
      register: "Регистрация",
      login: "Вход",
      logout: "Выход",
      change_password: "Смена пароля",
      password_reset_request: "Запрос сброса пароля",
      password_reset_confirm: "Подтверждение сброса пароля",
      backup_save: "Сохранение резервной копии",
      backup_restore: "Восстановление из резервной копии",
      reset_all_data: "Сброс всех данных",
    };
    return labels[type] ?? type;
  }

  function formatEventStatus(status: string) {
    if (status === "success") return "Успешно";
    if (status === "fail") return "Ошибка";
    if (status === "blocked") return "Заблокировано";
    return status;
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



  function onProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileMessage(null);
    profileMutation.mutate({
      display_name: displayName.trim(),
    });
  }

  return (
    <main className="grid">
      <section className="panel panel-form panel-wide">
        <div className="panel-header">
          <h2>Профиль</h2>
          <span>Персонализация имени для семейного бюджета</span>
        </div>

        <form className="transaction-form" onSubmit={onProfileSubmit}>
          <label className="field">
            <span>Ваше имя</span>
            <input
              disabled={profileMutation.isPending || preferencesQuery.isLoading}
              maxLength={80}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Например, Максим"
              value={displayName}
            />
          </label>

          {profileMessage ? <p className="form-status">{profileMessage}</p> : null}

          <button className="primary-button" disabled={profileMutation.isPending} type="submit">
            {profileMutation.isPending ? "Сохраняем..." : "Сохранить имя"}
          </button>
        </form>
      </section>

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

      <section className="panel panel-wide">
        <div className="panel-header">
          <h3>Журнал действий</h3>
          <span>Последние события безопасности и данных</span>
        </div>

        {activityQuery.isLoading ? <p className="muted">Загружаем журнал...</p> : null}
        {activityQuery.isError ? <p className="form-error">Не удалось загрузить журнал действий.</p> : null}

        {!activityQuery.isLoading && !activityQuery.isError && (
          <div className="list">
            {(activityQuery.data?.events ?? []).map((event, index) => (
              <article className="list-item" key={`${event.created_at}-${event.event_type}-${index}`}>
                <div>
                  <strong>{formatEventType(event.event_type)}</strong>
                  <p>
                    Статус:{" "}
                    <span className={event.status === "success" ? "money plus" : "money minus"}>
                      {formatEventStatus(event.status)}
                    </span>
                  </p>
                  <p>Время: {formatDate(event.created_at)}</p>
                  <p>IP: {event.ip || "неизвестно"}</p>
                  {event.detail ? <p>Детали: {event.detail}</p> : null}
                </div>
              </article>
            ))}
            {(activityQuery.data?.events ?? []).length === 0 ? (
              <p className="muted">Событий пока нет.</p>
            ) : null}
          </div>
        )}
      </section>
    </main>
  );
}
