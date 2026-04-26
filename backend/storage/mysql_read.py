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

    def get_transactions(
        self,
        conn,
        legacy_user_id: int,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["user_id = %s"]
        params: List[Any] = [user_id]
        if start_date:
            filters.append("date >= %s")
            params.append(start_date)
        if end_date:
            filters.append("date <= %s")
            params.append(end_date)
        params.extend([int(limit), int(offset)])
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
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
                WHERE {' AND '.join(filters)}
                ORDER BY date DESC, legacy_local_id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [self._transaction_row(row) for row in rows]

    def get_transaction_by_id(self, conn, legacy_user_id: int, legacy_transaction_id: int) -> Optional[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return None
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
                WHERE user_id = %s AND legacy_local_id = %s
                LIMIT 1
                """,
                (user_id, int(legacy_transaction_id)),
            )
            row = cursor.fetchone()
        return self._transaction_row(row) if row else None

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

    def get_planned_expenses_by_category(self, conn, legacy_user_id: int, end_date: str) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT category, COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                  AND type = 'expense'
                  AND status = 'planned'
                  AND date <= %s
                GROUP BY category
                ORDER BY category
                """,
                (user_id, end_date),
            )
            rows = cursor.fetchall()
        return [{"category": row["category"], "total": from_minor_float(row["total_minor"])} for row in rows]

    def get_category_audit_snapshot(self, conn, legacy_user_id: int) -> Dict[str, List[Dict[str, Any]]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return {"categories": [], "transactions": [], "budgets": [], "recurring_templates": []}

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT legacy_local_id AS id, name, type, color, icon, is_active
                FROM finance_categories
                WHERE user_id = %s
                ORDER BY name
                """,
                (user_id,),
            )
            categories = [
                {
                    "id": int(row["id"]),
                    "name": row["name"],
                    "type": row["type"],
                    "color": row["color"],
                    "icon": row["icon"],
                    "is_active": bool(row["is_active"]),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT type, category, COALESCE(status, 'actual') AS status,
                       COUNT(*) AS count, COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                GROUP BY type, category, COALESCE(status, 'actual')
                ORDER BY type, category
                """,
                (user_id,),
            )
            transactions = [
                {
                    "type": row["type"],
                    "category": row["category"],
                    "status": row["status"],
                    "count": int(row["count"] or 0),
                    "total": from_minor_float(row["total_minor"]),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT b.legacy_local_id AS id,
                       c.legacy_local_id AS category_id,
                       b.amount_minor,
                       b.period,
                       c.name AS category,
                       c.type AS category_type,
                       c.is_active AS category_is_active
                FROM finance_budgets b
                LEFT JOIN finance_categories c ON c.id = b.category_id
                WHERE b.user_id = %s
                ORDER BY c.name
                """,
                (user_id,),
            )
            budgets = [
                {
                    "id": int(row["id"]),
                    "category_id": int(row["category_id"]) if row.get("category_id") is not None else None,
                    "amount": from_minor_float(row["amount_minor"]),
                    "period": row["period"],
                    "category": row.get("category"),
                    "category_type": row.get("category_type"),
                    "category_is_active": bool(row.get("category_is_active")),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT rt.legacy_local_id AS id,
                       rt.type,
                       rt.name,
                       rt.amount_minor,
                       rt.day_of_month,
                       c.legacy_local_id AS category_id,
                       rt.is_active,
                       c.name AS category,
                       c.type AS category_type,
                       c.is_active AS category_is_active
                FROM finance_recurring_templates rt
                LEFT JOIN finance_categories c ON c.id = rt.category_id
                WHERE rt.user_id = %s
                ORDER BY rt.type, rt.name
                """,
                (user_id,),
            )
            recurring_templates = [
                {
                    "id": int(row["id"]),
                    "type": row["type"],
                    "name": row["name"],
                    "amount": from_minor_float(row["amount_minor"]),
                    "day_of_month": int(row["day_of_month"] or 0),
                    "category_id": int(row["category_id"]) if row.get("category_id") is not None else None,
                    "is_active": bool(row["is_active"]),
                    "category": row.get("category"),
                    "category_type": row.get("category_type"),
                    "category_is_active": bool(row.get("category_is_active")),
                }
                for row in cursor.fetchall()
            ]

        return {
            "categories": categories,
            "transactions": transactions,
            "budgets": budgets,
            "recurring_templates": recurring_templates,
        }

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

    def get_accounts(self, conn, legacy_user_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["user_id = %s"]
        params: List[Any] = [user_id]
        if not include_inactive:
            filters.append("is_active = TRUE")
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT legacy_local_id AS id, name, type, balance_minor, currency, is_active
                FROM finance_accounts
                WHERE {' AND '.join(filters)}
                ORDER BY
                    CASE legacy_local_id
                        WHEN 1 THEN 1
                        WHEN 2 THEN 2
                        ELSE 3
                    END,
                    name
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "type": row["type"],
                "balance": from_minor_float(row["balance_minor"]),
                "currency": row["currency"],
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    def get_capital_accounts(self, conn, legacy_user_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["user_id = %s"]
        params: List[Any] = [user_id]
        if not include_inactive:
            filters.append("is_active = TRUE")
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT legacy_local_id AS id, name, balance_minor, currency, icon, color, is_active, is_default
                FROM finance_capital_accounts
                WHERE {' AND '.join(filters)}
                ORDER BY is_default DESC, name
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "balance": from_minor_float(row["balance_minor"]),
                "currency": row["currency"],
                "icon": row["icon"],
                "color": row["color"],
                "is_active": bool(row["is_active"]),
                "is_default": bool(row["is_default"]),
            }
            for row in rows
        ]

    def get_default_capital_account(self, conn, legacy_user_id: int) -> Optional[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT legacy_local_id AS id, name, balance_minor, icon, color
                FROM finance_capital_accounts
                WHERE user_id = %s
                  AND is_default = TRUE
                  AND is_active = TRUE
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "balance": from_minor_float(row["balance_minor"]),
            "icon": row["icon"],
            "color": row["color"],
        }

    def get_total_capital(self, conn, legacy_user_id: int) -> float:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return 0.0
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(balance_minor), 0) AS total_minor
                FROM finance_capital_accounts
                WHERE user_id = %s
                  AND is_active = TRUE
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return from_minor_float(row["total_minor"] if row else 0)

    def get_categories(
        self,
        conn,
        legacy_user_id: int,
        trans_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["user_id = %s"]
        params: List[Any] = [user_id]
        if not include_inactive:
            filters.append("is_active = TRUE")
        if trans_type and trans_type != "both":
            filters.append("type IN (%s, 'both')")
            params.append(trans_type)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT legacy_local_id AS id, name, type, color, icon, is_active
                FROM finance_categories
                WHERE {' AND '.join(filters)}
                ORDER BY name
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "type": row["type"],
                "color": row["color"],
                "icon": row["icon"],
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    def get_budgets(self, conn, legacy_user_id: int) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    b.legacy_local_id AS id,
                    c.legacy_local_id AS category_id,
                    c.name AS category,
                    c.icon,
                    c.color,
                    b.amount_minor,
                    b.period
                FROM finance_budgets b
                JOIN finance_categories c ON b.category_id = c.id
                WHERE b.user_id = %s
                ORDER BY c.name
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "category_id": int(row["category_id"]),
                "category": row["category"],
                "icon": row.get("icon"),
                "color": row.get("color"),
                "amount": from_minor_float(row["amount_minor"]),
                "period": row["period"],
            }
            for row in rows
        ]

    @staticmethod
    def _budget_monthly_limit(amount: float, period: Optional[str], year: int, month: int) -> float:
        import calendar

        normalized = str(period or "monthly").lower()
        if normalized == "daily":
            return float(amount) * calendar.monthrange(int(year), int(month))[1]
        if normalized == "weekly":
            return float(amount) * 4
        if normalized == "yearly":
            return float(amount) / 12
        return float(amount)

    def get_budget_report(self, conn, legacy_user_id: int, month: Optional[str] = None) -> List[Dict[str, Any]]:
        from datetime import datetime

        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        year, month_num = map(int, month.split("-"))
        start_date = f"{year}-{month_num:02d}-01"
        if month_num == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month_num + 1:02d}-01"

        report = []
        budgets = self.get_budgets(conn, legacy_user_id)
        with conn.cursor() as cursor:
            for budget in budgets:
                budget_amount = self._budget_monthly_limit(
                    budget.get("amount") or 0,
                    budget.get("period"),
                    year,
                    month_num,
                )
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                    FROM finance_transactions
                    WHERE user_id = %s
                      AND type = 'expense'
                      AND category = %s
                      AND status = 'actual'
                      AND date >= %s
                      AND date < %s
                    """,
                    (user_id, budget["category"], start_date, end_date),
                )
                spent = from_minor_float(cursor.fetchone()["total_minor"])
                percent = (spent / budget_amount * 100) if budget_amount > 0 else 0
                report.append(
                    {
                        "category_id": budget["category_id"],
                        "category": budget["category"],
                        "budget": budget_amount,
                        "spent": spent,
                        "remaining": budget_amount - spent,
                        "percent": percent,
                        "status": "OK" if spent <= budget_amount else "ПРЕВЫШЕНИЕ",
                    }
                )
        return report

    def get_budget_status(self, conn, legacy_user_id: int, category_id: Optional[int] = None) -> List[Dict[str, Any]]:
        import calendar
        from datetime import datetime

        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []

        today = datetime.now()
        start_of_month = today.replace(day=1).strftime("%Y-%m-%d")
        end_of_month = today.strftime("%Y-%m-%d")
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        remaining_days_including_today = max(days_in_month - today.day + 1, 0)

        result = []
        budgets = self.get_budgets(conn, legacy_user_id)
        with conn.cursor() as cursor:
            for budget in budgets:
                normalized_period = str(budget.get("period") or "monthly").lower()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(amount_minor), 0) AS spent_minor
                    FROM finance_transactions
                    WHERE user_id = %s
                      AND type = 'expense'
                      AND category = %s
                      AND date >= %s
                      AND date <= %s
                      AND status = 'actual'
                    """,
                    (user_id, budget["category"], start_of_month, end_of_month),
                )
                spent = from_minor_float(cursor.fetchone()["spent_minor"])
                if normalized_period == "daily":
                    budget_amount = spent + (float(budget.get("amount") or 0) * remaining_days_including_today)
                else:
                    budget_amount = self._budget_monthly_limit(
                        budget.get("amount") or 0,
                        budget.get("period"),
                        today.year,
                        today.month,
                    )
                remaining = budget_amount - spent
                result.append(
                    {
                        "category_id": budget["category_id"],
                        "category_name": budget["category"],
                        "icon": budget.get("icon"),
                        "color": budget.get("color"),
                        "budget_amount": round(budget_amount, 2),
                        "spent": round(spent, 2),
                        "remaining": round(remaining, 2),
                        "percent": round((spent / budget_amount * 100) if budget_amount > 0 else 0, 1),
                        "over_budget": remaining < 0,
                    }
                )
        if category_id is not None:
            result = [item for item in result if int(item["category_id"]) == int(category_id)]
        return result

    def get_reconciliation_sources(self, conn, legacy_user_id: int) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT legacy_local_id AS id, name, balance_minor, is_active
                FROM finance_reconciliation_sources
                WHERE user_id = %s AND is_active = TRUE
                ORDER BY name
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "balance": from_minor_float(row["balance_minor"]),
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    def get_total_real_balance(self, conn, legacy_user_id: int) -> float:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return 0.0
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(balance_minor), 0) AS total_minor
                FROM finance_reconciliation_sources
                WHERE user_id = %s AND is_active = TRUE
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return from_minor_float(row["total_minor"] if row else 0)

    def get_app_setting(self, conn, legacy_user_id: int, key: str, default: Optional[str] = None) -> Optional[str]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return default
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT value
                FROM finance_app_settings
                WHERE user_id = %s AND `key` = %s
                LIMIT 1
                """,
                (user_id, str(key)),
            )
            row = cursor.fetchone()
        return str(row["value"]) if row else default

    def get_auto_capital_settings(self, conn, legacy_user_id: int) -> Dict[str, Any]:
        enabled_raw = self.get_app_setting(conn, legacy_user_id, "auto_capital_enabled", "1")
        percent_raw = self.get_app_setting(conn, legacy_user_id, "auto_capital_percent", "10")
        try:
            percent = int(percent_raw or 10)
        except (TypeError, ValueError):
            percent = 10
        return {
            "enabled": str(enabled_raw) == "1",
            "percent": max(0, min(percent, 100)),
        }

    def get_default_money_source(self, conn, legacy_user_id: int) -> str:
        from core_money import MONEY_SOURCE_CASHLESS, normalize_money_source

        return normalize_money_source(
            self.get_app_setting(conn, legacy_user_id, "default_money_source", MONEY_SOURCE_CASHLESS)
        )

    def get_recurring_templates(self, conn, legacy_user_id: int, template_type: Optional[str] = None) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["rt.user_id = %s", "rt.is_active = TRUE"]
        params: List[Any] = [user_id]
        if template_type:
            filters.append("rt.type = %s")
            params.append(template_type)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    rt.legacy_local_id AS id,
                    rt.type,
                    rt.name,
                    rt.amount_minor,
                    rt.day_of_month,
                    c.legacy_local_id AS category_id,
                    c.name AS category_name,
                    rt.comment_template,
                    rt.money_source,
                    rt.months_ahead,
                    rt.working_days_only,
                    rt.is_active,
                    DATE_FORMAT(rt.created_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS created_at
                FROM finance_recurring_templates rt
                LEFT JOIN finance_categories c ON c.id = rt.category_id
                WHERE {' AND '.join(filters)}
                ORDER BY rt.day_of_month
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "type": row["type"],
                "name": row["name"],
                "amount": from_minor_float(row["amount_minor"]),
                "day_of_month": int(row["day_of_month"]),
                "category_id": int(row["category_id"]) if row.get("category_id") is not None else None,
                "category_name": row.get("category_name"),
                "comment_template": row.get("comment_template"),
                "money_source": row.get("money_source") or "cashless",
                "months_ahead": int(row.get("months_ahead") or 12),
                "working_days_only": bool(row.get("working_days_only")),
                "is_active": bool(row.get("is_active")),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]

    def get_planned_transactions_due(self, conn, legacy_user_id: int) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    t.legacy_local_id AS id,
                    t.type,
                    t.category,
                    t.amount_minor,
                    COALESCE(t.comment, '') AS comment,
                    DATE_FORMAT(t.date, '%%Y-%%m-%%d') AS date,
                    t.money_source,
                    t.template_id,
                    rt.name AS template_name
                FROM finance_transactions t
                LEFT JOIN finance_recurring_templates rt ON rt.legacy_local_id = t.template_id
                    AND rt.user_id = t.user_id
                WHERE t.user_id = %s
                  AND t.status = 'planned'
                  AND t.date <= CURDATE()
                ORDER BY t.date ASC, t.legacy_local_id ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "type": row["type"],
                "category": row["category"],
                "amount": from_minor_float(row["amount_minor"]),
                "comment": row["comment"] or "",
                "date": str(row["date"]),
                "money_source": row.get("money_source") or "cashless",
                "template_id": row.get("template_id"),
                "template_name": row.get("template_name"),
            }
            for row in rows
        ]

    def get_transfers_history(
        self,
        conn,
        legacy_user_id: int,
        account_id: Optional[int] = None,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return []
        filters = ["t.user_id = %s"]
        params: List[Any] = [user_id]
        if account_id is not None:
            filters.append("(t.legacy_from_account_id = %s OR t.legacy_to_account_id = %s)")
            params.extend([int(account_id), int(account_id)])
        if not include_inactive:
            filters.append("t.is_active = TRUE")
        params.append(int(limit))
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    t.legacy_local_id AS id,
                    t.legacy_from_account_id AS from_account_id,
                    t.legacy_to_account_id AS to_account_id,
                    t.amount_minor,
                    DATE_FORMAT(t.date, '%%Y-%%m-%%d') AS date,
                    COALESCE(t.comment, '') AS comment,
                    t.is_active,
                    COALESCE(fa.name, fca.name, 'Неизвестный') AS from_name,
                    COALESCE(ta.name, tca.name, 'Неизвестный') AS to_name
                FROM finance_transfers t
                LEFT JOIN finance_accounts fa ON t.from_daily_account_id = fa.id
                LEFT JOIN finance_capital_accounts fca ON t.from_capital_account_id = fca.id
                LEFT JOIN finance_accounts ta ON t.to_daily_account_id = ta.id
                LEFT JOIN finance_capital_accounts tca ON t.to_capital_account_id = tca.id
                WHERE {' AND '.join(filters)}
                ORDER BY t.date DESC, t.legacy_local_id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": int(row["id"]),
                "from_account_id": int(row["from_account_id"]),
                "to_account_id": int(row["to_account_id"]),
                "amount": from_minor_float(row["amount_minor"]),
                "date": str(row["date"]),
                "comment": row["comment"] or "",
                "is_active": bool(row["is_active"]),
                "from_name": row["from_name"],
                "to_name": row["to_name"],
            }
            for row in rows
        ]

    def get_projected_balance(self, conn, legacy_user_id: int, end_date: Optional[str] = None) -> Dict[str, Any]:
        import calendar
        from datetime import datetime

        user_id = self.get_user_id_by_legacy(conn, legacy_user_id)
        if user_id is None:
            return {
                "current_balance": 0,
                "planned_income": 0,
                "planned_expense": 0,
                "executed_planned_income": 0,
                "executed_planned_expense": 0,
                "monthly_budget": 0,
                "total_budgets": 0,
                "current_expenses": 0,
                "budget_remaining": 0,
                "combined_pending_expense": 0,
                "combined_executed_expense": 0,
                "projected": 0,
                "projected_balance": 0,
                "end_date": end_date or "",
            }
        if not end_date:
            now = datetime.now()
            end_date = f"{now.year}-{now.month:02d}-{calendar.monthrange(now.year, now.month)[1]:02d}"

        today = datetime.now().strftime("%Y-%m-%d")
        reference = datetime.strptime(today, "%Y-%m-%d")
        days_in_month = calendar.monthrange(reference.year, reference.month)[1]
        remaining_days_including_today = max(days_in_month - reference.day + 1, 0)
        remaining_days_after_today = max(days_in_month - reference.day, 0)
        start_of_month = today[:8] + "01"

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(balance_minor), 0) AS total_minor
                FROM finance_accounts
                WHERE user_id = %s
                  AND legacy_local_id IN (1, 2)
                  AND is_active = TRUE
                """,
                (user_id,),
            )
            current_balance = from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                  AND status = 'actual'
                  AND type = 'income'
                  AND date >= %s
                  AND date <= %s
                """,
                (user_id, start_of_month, today),
            )
            actual_income = from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                  AND status = 'actual'
                  AND type = 'expense'
                  AND date >= %s
                  AND date <= %s
                """,
                (user_id, start_of_month, today),
            )
            actual_expense = from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transfers
                WHERE user_id = %s
                  AND is_active = TRUE
                  AND to_capital_account_id IS NOT NULL
                  AND date >= %s
                  AND date <= %s
                """,
                (user_id, start_of_month, today),
            )
            actual_expense += from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                  AND status = 'planned'
                  AND type = 'income'
                  AND date <= %s
                """,
                (user_id, end_date),
            )
            planned_income = from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM finance_transactions
                WHERE user_id = %s
                  AND status = 'planned'
                  AND type = 'expense'
                  AND date <= %s
                """,
                (user_id, end_date),
            )
            planned_expense = from_minor_float(cursor.fetchone()["total_minor"])

            cursor.execute(
                """
                SELECT b.amount_minor, b.period, c.name AS category_name
                FROM finance_budgets b
                JOIN finance_categories c ON b.category_id = c.id
                WHERE b.user_id = %s
                """,
                (user_id,),
            )
            budgets = cursor.fetchall()

            total_budgets = 0.0
            current_expenses = 0.0
            budget_remaining = 0.0
            for budget in budgets:
                period = str(budget.get("period") or "monthly").lower()
                amount = from_minor_float(budget["amount_minor"])
                if period == "daily":
                    monthly_amount = amount * days_in_month
                elif period == "weekly":
                    monthly_amount = amount * 4
                elif period == "yearly":
                    monthly_amount = amount / 12
                else:
                    monthly_amount = amount
                total_budgets += monthly_amount

                cursor.execute(
                    """
                    SELECT COALESCE(SUM(amount_minor), 0) AS spent_minor
                    FROM finance_transactions
                    WHERE user_id = %s
                      AND type = 'expense'
                      AND category = %s
                      AND date >= %s
                      AND date <= %s
                      AND status = 'actual'
                    """,
                    (user_id, budget["category_name"], start_of_month, today),
                )
                spent = from_minor_float(cursor.fetchone()["spent_minor"])
                current_expenses += spent

                if period == "daily":
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(amount_minor), 0) AS spent_today_minor
                        FROM finance_transactions
                        WHERE user_id = %s
                          AND type = 'expense'
                          AND category = %s
                          AND date = %s
                          AND status = 'actual'
                        """,
                        (user_id, budget["category_name"], today),
                    )
                    spent_today = from_minor_float(cursor.fetchone()["spent_today_minor"])
                    days_to_reserve = remaining_days_after_today if spent_today > 0 else remaining_days_including_today
                    budget_remaining += max(amount * days_to_reserve, 0.0)
                else:
                    budget_remaining += max(monthly_amount - spent, 0.0)

        combined_pending_expense = planned_expense + budget_remaining
        combined_executed_expense = actual_expense
        projected_balance = actual_income + planned_income - actual_expense - planned_expense - budget_remaining
        return {
            "current_balance": round(current_balance, 2),
            "planned_income": round(planned_income, 2),
            "planned_expense": round(planned_expense, 2),
            "executed_planned_income": round(actual_income, 2),
            "executed_planned_expense": round(actual_expense, 2),
            "monthly_budget": round(total_budgets, 2),
            "total_budgets": round(total_budgets, 2),
            "current_expenses": round(current_expenses, 2),
            "budget_remaining": round(budget_remaining, 2),
            "combined_pending_expense": round(combined_pending_expense, 2),
            "combined_executed_expense": round(combined_executed_expense, 2),
            "projected": round(projected_balance, 2),
            "projected_balance": round(projected_balance, 2),
            "end_date": end_date,
        }

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
