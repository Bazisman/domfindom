import type { CategoryType, TransactionType } from "./api";

export function categoryTypeLabel(type: CategoryType | string | null | undefined): string {
  if (type === "income") {
    return "Доход";
  }
  if (type === "expense") {
    return "Расход";
  }
  if (type === "both") {
    return "Доход и расход";
  }
  return type || "Не указано";
}

export function transactionTypeLabel(type: TransactionType | string | null | undefined): string {
  if (type === "income") {
    return "Доход";
  }
  if (type === "expense") {
    return "Расход";
  }
  return type || "Не указано";
}
