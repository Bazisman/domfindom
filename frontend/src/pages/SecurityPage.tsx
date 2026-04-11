import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { changePassword } from "../lib/api";

export function SecurityPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

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
    </main>
  );
}
