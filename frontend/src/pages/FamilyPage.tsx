import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createFamily,
  createFamilyInvite,
  getFamilyDashboard,
  getFamilyMembers,
  getMe,
  getMyFamilies,
  removeFamilyMember,
  updateFamilyMemberRole,
} from "../lib/api";

type FamilyBusyAction = "" | "create" | "invite" | "member_update" | "member_remove";

function roleLabel(role: "owner" | "member" | "viewer"): string {
  if (role === "owner") {
    return "Владелец";
  }
  if (role === "viewer") {
    return "Только просмотр";
  }
  return "Помощник";
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

export function FamilyPage() {
  const queryClient = useQueryClient();
  const [busyAction, setBusyAction] = useState<FamilyBusyAction>("");
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [familyName, setFamilyName] = useState("");
  const [selectedFamilyId, setSelectedFamilyId] = useState<number | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "viewer">("member");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    retry: false,
  });

  const selectedFamily = useMemo(
    () => (familiesQuery.data?.families ?? []).find((item) => item.id === selectedFamilyId) ?? null,
    [familiesQuery.data?.families, selectedFamilyId],
  );
  const canManageFamilyMembers = selectedFamily?.role === "owner";

  const familyMembersQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "members"],
    queryFn: () => getFamilyMembers(selectedFamilyId as number),
    enabled: selectedFamilyId !== null,
    retry: false,
  });

  const familyDashboardQuery = useQuery({
    queryKey: ["families", selectedFamilyId, "dashboard"],
    queryFn: () => getFamilyDashboard(selectedFamilyId as number),
    enabled: selectedFamilyId !== null,
    retry: false,
  });

  useEffect(() => {
    const firstFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
    if (selectedFamilyId === null && firstFamilyId !== null) {
      setSelectedFamilyId(firstFamilyId);
      return;
    }
    if (selectedFamilyId !== null) {
      const exists = (familiesQuery.data?.families ?? []).some((item) => item.id === selectedFamilyId);
      if (!exists) {
        setSelectedFamilyId(firstFamilyId);
      }
    }
  }, [familiesQuery.data?.families, selectedFamilyId]);

  const createFamilyMutation = useMutation({
    mutationFn: createFamily,
    onSuccess: async (created) => {
      setFamilyName("");
      setSelectedFamilyId(created.id);
      setMessage(`Семейный бюджет "${created.name}" создан.`);
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["families", "me"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
    },
  });

  const inviteMutation = useMutation({
    mutationFn: createFamilyInvite,
    onSuccess: async (response) => {
      setInviteEmail("");
      setMessage(response.message);
      setError("");
      if (selectedFamilyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
    },
  });

  const updateMemberMutation = useMutation({
    mutationFn: updateFamilyMemberRole,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (selectedFamilyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
      setBusyUserId(null);
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: removeFamilyMember,
    onSuccess: async (response) => {
      setMessage(response.message);
      setError("");
      if (selectedFamilyId !== null) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "members"] }),
          queryClient.invalidateQueries({ queryKey: ["families", selectedFamilyId, "dashboard"] }),
        ]);
      }
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      setMessage("");
    },
    onSettled: () => {
      setBusyAction("");
      setBusyUserId(null);
    },
  });

  function onCreateFamily() {
    const trimmed = familyName.trim();
    if (!trimmed) {
      setError("Введите название семьи.");
      setMessage("");
      return;
    }
    setBusyAction("create");
    createFamilyMutation.mutate({ name: trimmed });
  }

  function onInviteToFamily() {
    if (selectedFamilyId === null) {
      setError("Сначала выберите семейный бюджет.");
      setMessage("");
      return;
    }
    const email = inviteEmail.trim().toLowerCase();
    if (!email) {
      setError("Введите email участника.");
      setMessage("");
      return;
    }
    setBusyAction("invite");
    inviteMutation.mutate({ family_id: selectedFamilyId, email, role: inviteRole });
  }

  function onUpdateMemberRole(memberUserId: number, role: "member" | "viewer") {
    if (selectedFamilyId === null) {
      return;
    }
    setBusyAction("member_update");
    setBusyUserId(memberUserId);
    updateMemberMutation.mutate({ family_id: selectedFamilyId, user_id: memberUserId, role });
  }

  function onRemoveMember(memberUserId: number) {
    if (selectedFamilyId === null) {
      return;
    }
    setBusyAction("member_remove");
    setBusyUserId(memberUserId);
    removeMemberMutation.mutate({ family_id: selectedFamilyId, user_id: memberUserId });
  }

  return (
    <main className="grid">
      <section className="panel panel-form panel-wide">
        <div className="panel-header">
          <h2>Семья</h2>
          <span>Управление семейным бюджетом и участниками</span>
        </div>

        {(familiesQuery.data?.families ?? []).length === 0 ? (
          <div className="transaction-form">
            <label className="field">
              <span>Название семьи</span>
              <input
                disabled={busyAction !== ""}
                maxLength={120}
                onChange={(event) => setFamilyName(event.target.value)}
                placeholder="Например, Семья Петровых"
                value={familyName}
              />
            </label>
            <button className="primary-button" disabled={busyAction !== ""} onClick={onCreateFamily} type="button">
              {busyAction === "create" ? "Создаем..." : "Создать семейный бюджет"}
            </button>
          </div>
        ) : (
          <div className="transaction-form">
            <label className="field">
              <span>Выбранная семья</span>
              <select
                disabled={busyAction !== ""}
                onChange={(event) => setSelectedFamilyId(Number(event.target.value))}
                value={selectedFamilyId ?? ""}
              >
                {(familiesQuery.data?.families ?? []).map((family) => (
                  <option key={family.id} value={family.id}>
                    {family.name} ({roleLabel(family.role)})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Email участника</span>
              <input
                autoComplete="off"
                disabled={busyAction !== "" || !canManageFamilyMembers}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="user@example.com"
                value={inviteEmail}
              />
            </label>
            <label className="field">
              <span>Роль</span>
              <select
                disabled={busyAction !== "" || !canManageFamilyMembers}
                onChange={(event) => setInviteRole(event.target.value as "member" | "viewer")}
                value={inviteRole}
              >
                <option value="member">Помощник</option>
                <option value="viewer">Только просмотр</option>
              </select>
            </label>
            <button className="primary-button" disabled={busyAction !== "" || !canManageFamilyMembers} onClick={onInviteToFamily} type="button">
              {busyAction === "invite" ? "Отправляем..." : "Пригласить в семью"}
            </button>
          </div>
        )}

        {message ? <p className="form-status form-status-success">{message}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
      </section>

      {selectedFamilyId !== null ? (
        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Сводка семьи</h3>
            <span>{familyDashboardQuery.data?.family_name ?? "Семейный бюджет"}</span>
          </div>

          <div className="family-summary-grid">
            <article className="list-item">
              <div>
                <strong>Текущий семейный баланс</strong>
                <p>{formatMoney(familyDashboardQuery.data?.balance.main_balance ?? 0)}</p>
              </div>
            </article>
            <article className="list-item">
              <div>
                <strong>Доход за месяц</strong>
                <p className="money plus">{formatMoney(familyDashboardQuery.data?.balance.income ?? 0)}</p>
              </div>
            </article>
            <article className="list-item">
              <div>
                <strong>Расход за месяц</strong>
                <p className="money minus">{formatMoney(familyDashboardQuery.data?.balance.expense ?? 0)}</p>
              </div>
            </article>
          </div>

          <div className="list">
            <h4>Последние операции участников</h4>
            {(familyDashboardQuery.data?.recent_transactions ?? []).map((item) => (
              <article className="list-item" key={`${item.owner_user_id}-${item.id}`}>
                <div>
                  <strong>{item.category}</strong>
                  <p>{item.comment || "Без комментария"}</p>
                </div>
                <div className="family-page-actions">
                  <span className="status-chip">{item.owner_email}</span>
                  <strong className={item.type === "income" ? "money plus" : "money minus"}>{formatMoney(item.amount)}</strong>
                </div>
              </article>
            ))}
            {!familyDashboardQuery.isLoading && (familyDashboardQuery.data?.recent_transactions ?? []).length === 0 ? (
              <p className="muted">Пока нет операций участников.</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {selectedFamilyId !== null ? (
        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Участники семьи</h3>
            <span>Всего: {(familyMembersQuery.data?.members ?? []).length}</span>
          </div>

          <div className="list">
            {(familyMembersQuery.data?.members ?? []).map((member) => {
              const isSelf = member.user_id === meQuery.data?.id;
              const canManageThisMember = canManageFamilyMembers && !isSelf && member.role !== "owner";
              return (
                <article className="list-item" key={member.user_id}>
                  <div>
                    <strong>{member.email}</strong>
                    <p>Роль: {roleLabel(member.role)}</p>
                  </div>
                  <div className="family-page-actions">
                    <select
                      disabled={!canManageThisMember || busyAction !== ""}
                      onChange={(event) =>
                        onUpdateMemberRole(
                          member.user_id,
                          event.target.value as "member" | "viewer",
                        )
                      }
                      value={member.role === "owner" ? "member" : member.role}
                    >
                      <option value="member">Помощник</option>
                      <option value="viewer">Просмотр</option>
                    </select>
                    <button
                      className="ghost-button"
                      disabled={!canManageThisMember || busyAction !== ""}
                      onClick={() => onRemoveMember(member.user_id)}
                      type="button"
                    >
                      {busyAction === "member_remove" && busyUserId === member.user_id ? "Исключаем..." : "Исключить"}
                    </button>
                  </div>
                </article>
              );
            })}
            {!familyMembersQuery.isLoading && (familyMembersQuery.data?.members ?? []).length === 0 ? (
              <p className="muted">Участников пока нет.</p>
            ) : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}
