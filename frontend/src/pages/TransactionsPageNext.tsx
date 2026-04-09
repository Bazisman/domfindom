import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createTransaction,
  deleteTransaction,
  getCategories,
  getTransactions,
  type TransactionPeriod,
  type TransactionType,
} from "../lib/api";

const PERIOD_OPTIONS: Array<{ value: TransactionPeriod; label: string }> = [
  { value: "all", label: "Все" },
  { value: "month", label: "Этот месяц" },
  { value: "last_month", label: "Прошлый месяц" },
  { value: "year", label: "Этот год" },
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

export function TransactionsPageNext() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<TransactionPeriod>("all");
  const [type, setType] = useState<TransactionType>("expense");
  const [showPlanned, setShowPlanned] = useState(false);
  const [categoryId, setCategoryId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [date, setDate] = useState(getToday);
  const [isRecurring, setIsRecurring] = useState(false);
  const [recurringName, setRecurringName] = useState("");
  const [recurringNameTouched, setRecurringNameTouched] = useState(false);
  const [recurringMonthsAhead, setRecurringMonthsAhead] = useState("12");
  const [recurringWorkingDaysOnly, setRecurringWorkingDaysOnly] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const transactions = useQuery({
    queryKey: ["transactions", period],
    queryFn: () => getTransactions({ limit: 100, period }),
    placeholderData: keepPreviousData,
  });

  const filteredCategories = useMemo(() => {
    return (categories.data ?? []).filter((item) => item.type === type || item.type === "both");
  }, [categories.data, type]);

  const selectedCategoryName = useMemo(() => {
    return filteredCategories.find((item) => String(item.id) === categoryId)?.name ?? "";
  }, [categoryId, filteredCategories]);

  const recurringSuggestedName = useMemo(() => {
    return comment.trim() || selectedCategoryName;
  }, [comment, selectedCategoryName]);

  useEffect(() => {
    if (isRecurring && !recurringNameTouched) {
      setRecurringName(recurringSuggestedName);
    }
  }, [isRecurring, recurringNameTouched, recurringSuggestedName]);

  const visibleTransactions = useMemo(() => {
    const items = transactions.data ?? [];
    if (showPlanned) {
      return items;
    }
    return items.filter((item) => item.status !== "planned");
  }, [showPlanned, transactions.data]);

  const createMutation = useMutation({
    mutationFn: createTransaction,
    onSuccess: async () => {
      setAmount("");
      setComment("");
      setCategoryId("");
      setIsRecurring(false);
      setRecurringName("");
      setRecurringNameTouched(false);
      setRecurringMonthsAhead("12");
      setRecurringWorkingDaysOnly(true);
      setFormError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
      ]);
    },
    onError: (error: Error) => {
      setFormError(error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["transactions"] }),
        queryClient.invalidateQueries({ queryKey: ["recurring-templates"] }),
      ]);
    },
  });

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const normalizedAmount = Number(amount.replace(",", "."));
    if (!categoryId) {
      setFormError("Выбери категорию.");
      return;
    }
    if (!normalizedAmount || normalizedAmount <= 0) {
      setFormError("Укажи сумму больше нуля.");
      return;
    }
    if (isRecurring) {
      const normalizedMonthsAhead = Number(recurringMonthsAhead);
      if (!normalizedMonthsAhead || normalizedMonthsAhead < 1 || normalizedMonthsAhead > 24) {
        setFormError("Горизонт планирования должен быть от 1 до 24 месяцев.");
        return;
      }
    }

    const dayOfMonth = Number(date.split("-")[2] || "1");
    const templateName = recurringName.trim() || recurringSuggestedName;

    createMutation.mutate({
      type,
      category_id: Number(categoryId),
      amount: normalizedAmount,
      comment,
      date,
      recurring: isRecurring
        ? {
            enabled: true,
            template_name: templateName,
            day_of_month: dayOfMonth,
            months_ahead: Number(recurringMonthsAhead),
            working_days_only: recurringWorkingDaysOnly,
          }
        : undefined,
    });
  }

  return (
    <main className="transactions-layout">
      <section className="panel panel-form">
        <div className="panel-header">
          <h2>Новая транзакция</h2>
          <span>{type === "income" ? "Доход" : "Расход"}</span>
        </div>

        <form className="transaction-form" onSubmit={submitForm}>
          <div className="toggle-row">
            <button
              className={type === "expense" ? "toggle active" : "toggle"}
              onClick={() => setType("expense")}
              type="button"
            >
              Расход
            </button>
            <button
              className={type === "income" ? "toggle active" : "toggle"}
              onClick={() => setType("income")}
              type="button"
            >
              Доход
            </button>
          </div>

          <label className="field">
            <span>Категория</span>
            <select onChange={(event) => setCategoryId(event.target.value)} value={categoryId}>
              <option value="">Выбери категорию</option>
              {filteredCategories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <div className="field-row">
            <label className="field">
              <span>Сумма</span>
              <input
                inputMode="decimal"
                onChange={(event) => setAmount(event.target.value)}
                placeholder="0"
                value={amount}
              />
            </label>

            <label className="field">
              <span>Дата</span>
              <input onChange={(event) => setDate(event.target.value)} type="date" value={date} />
            </label>
          </div>

          <label className="field">
            <span>Комментарий</span>
            <input
              onChange={(event) => setComment(event.target.value)}
              placeholder="Например, Магнит или Зарплата"
              value={comment}
            />
          </label>

          <label className="filter-check">
            <input
              checked={isRecurring}
              onChange={(event) => {
                const checked = event.target.checked;
                setIsRecurring(checked);
                if (checked) {
                  setRecurringNameTouched(false);
                  setRecurringName(recurringSuggestedName);
                } else {
                  setRecurringNameTouched(false);
                }
              }}
              type="checkbox"
            />
            <span>Повторяющаяся операция</span>
          </label>

          {isRecurring && (
            <>
              <p className="muted">
                После сохранения эта операция появится и в истории, и в разделе{" "}
                <strong>Планирование</strong>.
              </p>

              <label className="field">
                <span>Название шаблона</span>
                <input
                  onChange={(event) => {
                    setRecurringName(event.target.value);
                    setRecurringNameTouched(true);
                  }}
                  placeholder="Например, Основная зарплата"
                  value={recurringName}
                />
              </label>

              <div className="field-row">
                <label className="field">
                  <span>Повторять каждого</span>
                  <input disabled value={`${Number(date.split("-")[2] || "1")} числа`} />
                </label>

                <label className="field">
                  <span>Планировать вперёд</span>
                  <input
                    inputMode="numeric"
                    max="24"
                    min="1"
                    onChange={(event) => setRecurringMonthsAhead(event.target.value)}
                    type="number"
                    value={recurringMonthsAhead}
                  />
                </label>
              </div>

              <label className="filter-check">
                <input
                  checked={recurringWorkingDaysOnly}
                  onChange={(event) => setRecurringWorkingDaysOnly(event.target.checked)}
                  type="checkbox"
                />
                <span>Переносить на рабочий день</span>
              </label>
            </>
          )}

          {formError && <p className="form-error">{formError}</p>}

          <button className="primary-button" disabled={createMutation.isPending} type="submit">
            {createMutation.isPending ? "Сохраняем..." : "Добавить транзакцию"}
          </button>
        </form>
      </section>

      <section className="panel panel-list">
        <div className="panel-header">
          <h2>История транзакций</h2>
          <div className="toolbar-group">
            <label className="filter-check">
              <input
                checked={showPlanned}
                onChange={(event) => setShowPlanned(event.target.checked)}
                type="checkbox"
              />
              <span>Показывать неисполненные</span>
            </label>
            <select
              className="period-select"
              onChange={(event) => setPeriod(event.target.value as TransactionPeriod)}
              value={period}
            >
              {PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="transaction-table">
          {visibleTransactions.map((item) => (
            <article className="transaction-row" key={item.id}>
              <div className="transaction-main">
                <div className="transaction-title-row">
                  <strong>{item.category}</strong>
                  {item.status === "planned" && <span className="status-chip">Не исполнено</span>}
                </div>
                <p>{item.comment || "Без комментария"}</p>
              </div>
              <div className="transaction-meta">
                <span className="transaction-date">{item.date}</span>
                <strong className={item.type === "income" ? "money plus" : "money minus"}>
                  {formatMoney(item.amount)}
                </strong>
              </div>
              <button
                className="ghost-button"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(item.id)}
                type="button"
              >
                Удалить
              </button>
            </article>
          ))}

          {!visibleTransactions.length && (
            <p className="empty">
              {transactions.isLoading
                ? "Загружаем транзакции..."
                : showPlanned
                  ? "Транзакций пока нет для выбранного периода."
                  : "Исполненных транзакций пока нет для выбранного периода."}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
