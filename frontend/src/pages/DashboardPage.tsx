import { useQuery } from "@tanstack/react-query";

import { getCategories, getDashboard } from "../lib/api";

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getQueryErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error) {
    return `${fallback}: ${error.message}`;
  }
  return fallback;
}

export function DashboardPage() {
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  const visibleTransactions = dashboard.data?.recent_transactions ?? [];

  return (
    <>
      <header className="hero">
        <div className="hero-copy">
          <h1>Домашняя бухгалтерия в браузере</h1>
          <p className="hero-text">
            Главный экран проекта: баланс, транзакции, категории и прогноз конца месяца.
          </p>
        </div>
        <div className="hero-note">
          <span className="note-label">API</span>
          <strong>
            {dashboard.isSuccess
              ? "подключено"
              : dashboard.isError
                ? "ошибка подключения"
                : "ожидание backend"}
          </strong>
          {dashboard.isError && (
            <p className="empty">
              {getQueryErrorMessage(dashboard.error, "Не удалось загрузить dashboard")}
            </p>
          )}
        </div>
      </header>

      <main className="grid">
        <section className="panel panel-balance">
          <p className="panel-label">Текущий баланс</p>
          <h2>{dashboard.data ? formatMoney(dashboard.data.balance.main_balance) : "—"}</h2>
          <div className="stats-row">
            <div>
              <span>Доход за месяц</span>
              <strong>{dashboard.data ? formatMoney(dashboard.data.balance.income) : "—"}</strong>
            </div>
            <div>
              <span>Расход за месяц</span>
              <strong>{dashboard.data ? formatMoney(dashboard.data.balance.expense) : "—"}</strong>
            </div>
          </div>
        </section>

        <section className="panel">
          <p className="panel-label">Баланс на конец месяца</p>
          <h2>{dashboard.data ? formatMoney(dashboard.data.forecast.projected_balance) : "—"}</h2>
          <p className="muted">
            {dashboard.data ? `До ${dashboard.data.forecast.end_date}` : "Нужен backend на FastAPI"}
          </p>
        </section>

        <section className="panel panel-wide">
          <div className="panel-header">
            <h3>Последние транзакции</h3>
          </div>
          <div className="list">
            {visibleTransactions.map((item) => (
              <article className="list-item" key={item.id}>
                <div>
                  <strong>{item.category}</strong>
                  <p>{item.comment || "Без комментария"}</p>
                </div>
                <div className={item.type === "income" ? "money plus" : "money minus"}>
                  {formatMoney(item.amount)}
                </div>
              </article>
            ))}
            {!visibleTransactions.length && (
              <p className="empty">
                {dashboard.isError
                  ? getQueryErrorMessage(dashboard.error, "Не удалось загрузить транзакции")
                  : "Исполненные транзакции появятся после запуска backend API."}
              </p>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3>Категории</h3>
          </div>
          <div className="chips">
            {categories.data?.map((category) => (
              <span className="chip" key={category.id} style={{ borderColor: category.color }}>
                {category.name}
              </span>
            ))}
            {!categories.data?.length && (
              <p className="empty">
                {categories.isError
                  ? getQueryErrorMessage(categories.error, "Не удалось загрузить категории")
                  : "Категории будут загружаться из API."}
              </p>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3>Бюджетные акценты</h3>
          </div>
          <div className="list">
            {dashboard.data?.budget_highlights.map((item) => (
              <article className="list-item" key={item.category_id}>
                <div>
                  <strong>{item.category_name}</strong>
                  <p>{Math.round(item.percent)}% от лимита</p>
                </div>
                <div className={item.over_budget ? "money minus" : "money"}>
                  {formatMoney(item.remaining)}
                </div>
              </article>
            ))}
            {!dashboard.data?.budget_highlights.length && (
              <p className="empty">
                {dashboard.isError
                  ? getQueryErrorMessage(dashboard.error, "Не удалось загрузить бюджеты")
                  : "Бюджеты будут показаны после запуска API."}
              </p>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
