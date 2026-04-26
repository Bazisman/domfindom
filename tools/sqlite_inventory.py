from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote


EXPECTED_AUTH_COLUMNS = {
    "users": {"id", "email", "password_hash", "email_verified", "is_active", "created_at", "updated_at"},
    "sessions": {"id", "user_id", "token_hash", "expires_at", "ip", "user_agent", "created_at", "revoked_at"},
    "user_preferences": {"user_id", "theme_mode", "workspace_mode", "display_name", "updated_at"},
    "families": {"id", "name", "owner_user_id", "created_at", "updated_at", "archived_at"},
    "family_memberships": {
        "id",
        "family_id",
        "user_id",
        "role",
        "status",
        "invited_by_user_id",
        "created_at",
        "updated_at",
    },
    "family_categories": {
        "id",
        "family_id",
        "semantic_key",
        "display_name",
        "type",
        "is_active",
        "created_by_user_id",
        "created_at",
        "updated_at",
    },
    "family_category_bindings": {
        "id",
        "family_id",
        "family_category_id",
        "user_id",
        "local_category_id",
        "local_category_name",
        "local_category_type",
        "status",
        "confirmed_by_user_id",
        "created_at",
        "updated_at",
    },
}


EXPECTED_FINANCE_COLUMNS = {
    "transactions": {
        "id",
        "type",
        "category",
        "amount",
        "comment",
        "date",
        "money_source",
        "created_at",
        "status",
        "executed_at",
        "template_id",
    },
    "accounts": {"id", "name", "type", "balance", "currency", "is_active", "created_at", "updated_at"},
    "transfers": {
        "id",
        "from_account_id",
        "to_account_id",
        "amount",
        "transaction_id",
        "date",
        "comment",
        "is_active",
        "created_at",
    },
    "categories": {"id", "name", "type", "color", "icon", "is_active", "created_at", "updated_at"},
    "budgets": {"id", "category_id", "amount", "period"},
    "capital_accounts": {
        "id",
        "name",
        "balance",
        "currency",
        "icon",
        "color",
        "is_default",
        "is_active",
        "created_at",
        "updated_at",
    },
    "app_settings": {"key", "value", "updated_at"},
    "reconciliation_sources": {"id", "name", "balance", "is_active", "created_at", "updated_at"},
    "reconciliations": {
        "id",
        "real_balance",
        "program_balance",
        "difference",
        "adjustment_transaction_id",
        "created_at",
        "updated_at",
    },
    "recurring_templates": {
        "id",
        "type",
        "name",
        "amount",
        "day_of_month",
        "category_id",
        "comment_template",
        "money_source",
        "months_ahead",
        "working_days_only",
        "is_active",
        "created_at",
        "updated_at",
    },
}


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(db_path.resolve()))}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def classify_db(db_path: Path, auth_db_path: Path, root_finance_path: Optional[Path], users_root: Path) -> str:
    resolved = db_path.resolve()
    if resolved == auth_db_path.resolve():
        return "auth"
    if root_finance_path and resolved == root_finance_path.resolve():
        return "legacy_root_finance"
    try:
        resolved.relative_to(users_root.resolve())
    except ValueError:
        return "unknown"
    return "user_finance"


def table_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        row = conn.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
    except sqlite3.DatabaseError:
        return None
    return int(row["count"]) if row else None


def expected_columns_for(db_kind: str, table_name: str) -> Set[str]:
    if db_kind == "auth":
        return EXPECTED_AUTH_COLUMNS.get(table_name, set())
    if db_kind in {"user_finance", "legacy_root_finance"}:
        return EXPECTED_FINANCE_COLUMNS.get(table_name, set())
    return set()


def inspect_db(db_path: Path, db_kind: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "path": str(db_path),
        "kind": db_kind,
        "exists": db_path.exists(),
        "tables": [],
        "warnings": [],
        "error": None,
    }
    if not db_path.exists():
        return result

    try:
        with open_readonly(db_path) as conn:
            tables = conn.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            indexes = conn.execute(
                """
                SELECT name, tbl_name, sql
                FROM sqlite_master
                WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
                ORDER BY tbl_name, name
                """
            ).fetchall()
            indexes_by_table: Dict[str, List[Dict[str, str]]] = {}
            for index in indexes:
                indexes_by_table.setdefault(str(index["tbl_name"]), []).append(
                    {"name": str(index["name"]), "sql": str(index["sql"] or "")}
                )

            for table in tables:
                table_name = str(table["name"])
                columns = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
                column_names = {str(column["name"]) for column in columns}
                expected_columns = expected_columns_for(db_kind, table_name)
                missing_columns = sorted(expected_columns - column_names)
                if missing_columns:
                    result["warnings"].append(
                        {
                            "table": table_name,
                            "type": "missing_columns",
                            "columns": missing_columns,
                        }
                    )
                result["tables"].append(
                    {
                        "name": table_name,
                        "row_count": table_count(conn, table_name),
                        "columns": [
                            {
                                "name": str(column["name"]),
                                "type": str(column["type"] or ""),
                                "notnull": bool(column["notnull"]),
                                "default": column["dflt_value"],
                                "pk": int(column["pk"]),
                            }
                            for column in columns
                        ],
                        "indexes": indexes_by_table.get(table_name, []),
                        "sql": str(table["sql"] or ""),
                    }
                )
    except sqlite3.DatabaseError as exc:
        result["error"] = str(exc)

    return result


def discover_databases(root: Path, users_dir: str, auth_db: str, root_finance_db: Optional[str]) -> List[Path]:
    paths = [root / auth_db]
    if root_finance_db:
        root_finance_path = root / root_finance_db
        if root_finance_path not in paths:
            paths.append(root_finance_path)
    user_root = root / users_dir
    if user_root.exists():
        paths.extend(sorted(user_root.glob("*/finance.db")))
    return paths


def render_markdown(inventory: List[Dict[str, Any]]) -> str:
    lines = ["# SQLite Inventory", ""]
    for db in inventory:
        lines.append(f"## `{db['path']}`")
        lines.append("")
        lines.append(f"Kind: `{db['kind']}`")
        if not db["exists"]:
            lines.append("")
            lines.append("Missing.")
            lines.append("")
            continue
        if db["error"]:
            lines.append("")
            lines.append(f"Error: `{db['error']}`")
            lines.append("")
            continue
        lines.append("")
        if db["warnings"]:
            lines.append("Warnings:")
            for warning in db["warnings"]:
                columns = ", ".join(warning.get("columns", []))
                lines.append(f"- `{warning['table']}` {warning['type']}: {columns}")
            lines.append("")
        lines.append("| Table | Rows | Columns |")
        lines.append("| --- | ---: | --- |")
        for table in db["tables"]:
            columns = ", ".join(column["name"] for column in table["columns"])
            lines.append(f"| `{table['name']}` | {table['row_count']} | {columns} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Read-only inventory for current SQLite databases.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--auth-db", default="auth.db", help="Auth database path relative to root.")
    parser.add_argument(
        "--root-finance-db",
        default="finance.db",
        help="Legacy/root finance database path relative to root. Use an empty value to skip.",
    )
    parser.add_argument("--users-dir", default="data/users", help="Users data directory relative to root.")
    parser.add_argument("--format", choices={"json", "markdown"}, default="markdown")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    root_finance_db = args.root_finance_db.strip() or None
    auth_db_path = root / args.auth_db
    root_finance_path = (root / root_finance_db) if root_finance_db else None
    users_root = root / args.users_dir
    inventory = []
    for path in discover_databases(root, args.users_dir, args.auth_db, root_finance_db):
        db_kind = classify_db(path, auth_db_path, root_finance_path, users_root)
        inventory.append(inspect_db(path, db_kind))
    if args.format == "json":
        print(json.dumps(inventory, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
