import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  getAccountPreferences,
  getCategorySummary,
  getMyFamilies,
  type SummaryPeriod,
} from "../lib/api";

const PERIOD_OPTIONS: Array<{ value: SummaryPeriod; label: string }> = [
  { value: "month", label: "Этот месяц" },
  { value: "last_month", label: "Прошлый месяц" },
  { value: "year", label: "Этот год" },
  { value: "all", label: "Все время" },
  { value: "custom", label: "Произвольный период" },
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(value);
}

function getCurrentMonthStart() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}-01`;
}

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

export function SummaryPage() {
  const [summaryType, setSummaryType] = useState<"expense" | "income">("expense");
  const [period, setPeriod] = useState<SummaryPeriod>("month");
  const [startDate, setStartDate] = useState(getCurrentMonthStart);
  const [endDate, setEndDate] = useState(getToday);

  const preferencesQuery = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: getAccountPreferences,
    retry: false,
  });

  const familiesQuery = useQuery({
    queryKey: ["families", "me"],
    queryFn: getMyFamilies,
    retry: false,
  });

  const selectedFamilyId = familiesQuery.data?.families?.[0]?.id ?? null;
  const useFamilyScope = selectedFamilyId !== null && preferencesQuery.data?.workspace_mode === "family";

  const summaryQuery = useQuery({
    queryKey: ["reports", "category-summary", summaryType, period, startDate, endDate, useFamilyScope, selectedFamilyId],
    queryFn: () =>
      getCategorySummary({
        type: summaryType,
        period,
        startDate: period === "custom" ? startDate : undefined,
        endDate: period === "custom" ? endDate : undefined,
        familyId: useFamilyScope ? (selectedFamilyId as number) : undefined,
      }),
  });

  const topCategory = useMemo(() => summaryQuery.data?.items[0] ?? null, [summaryQuery.data?.items]);

  return (
    <main className="page-stack">
      <section className="panel summary-report-panel">
        <div className="panel-header">
          <h2>Сводка по категориям</h2>
          <span>
            {useFamilyScope
              ? `Семья${summaryQuery.data?.family_name ? ` • ${summaryQuery.data.family_name}` : ""}`
              : "Личный режим"}
          </span>
        </div>

        <div className="summary-report-controls">
          <div className="toggle-row">
            <button
              className={summaryType === "expense" ? "toggle active" : "toggle"}
              onClick={() => setSummaryType("expense")}
              type="button"
            >
              Расходы
            </button>
            <button
              className={summaryType === "income" ? "toggle active" : "toggle"}
              onClick={() => setSummaryType("income")}
              type="button"
            >
              Доходы
            </button>
          </div>

          <div className="toolbar-group">
            <label className="field field-inline field-compact">
              <span>Период</span>
              <select onChange={(event) => setPeriod(event.target.value as SummaryPeriod)} value={period}>
                {PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            {period === "custom" ? (
              <>
                <label className="field field-inline field-compact">
                  <span>С</span>
                  <input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} />
                </label>
                <label className="field field-inline field-compact">
                  <span>По</span>
                  <input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} />
                </label>
              </>
            ) : null}
          </div>
        </div>

        <div className="summary-grid summary-grid-3">
          <article className="summary-card summary-card-main">
            <span>{summaryType === "expense" ? "Всего потрачено" : "Всего получено"}</span>
            <strong>{formatMoney(summaryQuery.data?.total ?? 0)}</strong>
          </article>
          <article className="summary-card">
            <span>Категорий в сводке</span>
            <strong>{summaryQuery.data?.categories_count ?? 0}</strong>
          </article>
          <article className="summary-card">
            <span>Крупнейшая категория</span>
            <strong>{topCategory ? topCategory.category : "Пока нет данных"}</strong>
          </article>
        </div>

        <div className="summary-report-list">
          {summaryQuery.data?.items.map((item, index) => (
            <article className="summary-report-item" key={`${item.category}-${index}`}>
              <div className="summary-report-item-head">
                <div className="summary-report-item-main">
                  <span className="summary-report-rank">{index + 1}</span>
                  <span className="summary-report-icon" style={{ backgroundColor: item.color }}>
                    {item.icon}
                  </span>
                  <div>
                    <strong>{item.category}</strong>
                    <p>{item.share_percent.toFixed(2)}% от общей суммы</p>
                  </div>
                </div>
                <strong className={summaryType === "income" ? "money plus" : "money minus"}>{formatMoney(item.total)}</strong>
              </div>
              <div className="summary-report-bar-shell">
                <div
                  className="summary-report-bar-fill"
                  style={{ width: `${Math.min(item.share_percent, 100)}%`, backgroundColor: item.color }}
                />
              </div>
            </article>
          ))}

          {!summaryQuery.data?.items.length ? (
            <p className="empty">
              {summaryQuery.isLoading
                ? "Загружаем сводку..."
                : "Для выбранного периода пока нет операций по категориям."}
            </p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
