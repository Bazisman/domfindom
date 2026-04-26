from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.money_minor import from_minor_float
from tools.mysql_schema import mysql_connect


class MySqlReadRepository:
    """Read-only MySQL adapter used for migration parity checks."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return mysql_connect(self.database_url)

    def get_user_id_by_legacy(self, conn, legacy_user_id: int) -> Optional[int]:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM auth_users WHERE legacy_sqlite_user_id = %s",
                (int(legacy_user_id),),
            )
            row = cursor.fetchone()
        return int(row["id"]) if row else None

    def get_balance(self, conn, legacy_user_id: int) -> Dict[str, float]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return {"main_balance": 0.0, "income": 0.0, "expense": 0.0}
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE((
                        SELECT SUM(balance_minor)
                        FROM finance_accounts
                        WHERE user_id = %s
                          AND legacy_local_id IN (1, 2)
                          AND is_active = TRUE
                    ), 0) AS main_balance_minor,
                    COALESCE((
                        SELECT SUM(amount_minor)
                        FROM finance_transactions
                        WHERE user_id = %s
                          AND type = 'income'
                          AND status = 'actual'
                    ), 0) AS income_minor,
                    COALESCE((
                        SELECT SUM(amount_minor)
                        FROM finance_transactions
                        WHERE user_id = %s
                          AND type = 'expense'
                          AND status = 'actual'
                    ), 0) AS expense_minor
                """,
                (user_id, user_id, user_id),
            )
            row = cursor.fetchone()
        return {
            "main_balance": from_minor_float(row["main_balance_minor"]),
            "income": from_minor_float(row["income_minor"]),
            "expense": from_minor_float(row["expense_minor"]),
        }

    def get_transactions(self, conn, legacy_user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    legacy_local_id AS id,
                    DATE_FORMAT(date, '%%Y-%%m-%%d') AS date,
                    type,
                    category,
                    amount_minor,
                    COALESCE(comment, '') AS comment,
                    money_source,
                    status,
                    template_id
                FROM finance_transactions
                WHERE user_id = %s
                ORDER BY date DESC, legacy_local_id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, int(limit), int(offset)),
            )
            rows = cursor.fetchall()
        return [self._transaction_row(row) for row in rows]

    def get_category_totals(
        self,
        conn,
        legacy_user_id: int,
        transaction_type: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        params: List[Any] = [user_id, transaction_type]
        filters = ["user_id = %s", "type = %s", "status = 'actual'"]
        if start_date:
            filters.append("date >= %s")
            params.append(start_date)
        if end_date:
            filters.append("date <= %s")
            params.append(end_date)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT category, COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE {' AND '.join(filters)}
                GROUP BY category
                ORDER BY total_minor DESC, category ASC
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [{"category": row["category"], "total": from_minor_float(row["total_minor"])} for row in rows]

    def get_monthly_stats(self, conn, legacy_user_id: int, year: int, month: int) -> Dict[str, Any]:
        import calendar

        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        income = sum(item["total"] for item in self.get_category_totals(conn, legacy_user_id, "income", start_date, end_date))
        expense = sum(item["total"] for item in self.get_category_totals(conn, legacy_user_id, "expense", start_date, end_date))
        capital = self.get_capital_contributions_total(conn, legacy_user_id, start_date, end_date)
        return {
            "income": round(income, 2),
            "expense": round(expense, 2),
            "capital": round(capital, 2),
            "year": int(year),
            "month": int(month),
        }

    def get_capital_contributions_total(
        self,
        conn,
        legacy_user_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> float:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return 0.0
        params: List[Any] = [user_id]
        filters = [
            "user_id = %s",
            "is_active = TRUE",
            "to_capital_account_id IS NOT NULL",
        ]
        if start_date:
            filters.append("date >= %s")
            params.append(start_date)
        if end_date:
            filters.append("date <= %s")
            params.append(end_date)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transfers
                WHERE {' AND '.join(filters)}
                """,
                tuple(params),
            )
            row = cursor.fetchone()
        return from_minor_float(row["total_minor"] if row else 0)

    def _transaction_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "date": str(row["date"]),
            "type": str(row["type"]),
            "category": str(row["category"]),
            "amount": from_minor_float(row["amount_minor"]),
            "comment": str(row["comment"] or ""),
            "money_source": str(row["money_source"] or "cashless"),
            "status": str(row["status"] or "actual"),
            "template_id": row["template_id"],
        }
