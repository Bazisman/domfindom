from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote


AUTH_TABLES = [
    "users",
    "families",
    "family_memberships",
    "family_invites",
    "family_capital_accounts",
    "family_capital_member_settings",
    "family_capital_contributions",
    "family_categories",
    "family_category_bindings",
    "family_category_audit_resolutions",
]


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(db_path.resolve()))}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn: sqlite3.Connection) -> Set[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    if table not in table_names(conn):
        return 0
    row = conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()
    return int(row["count"]) if row else 0


def id_set(conn: sqlite3.Connection, table: str) -> Set[int]:
    if table not in table_names(conn):
        return set()
    rows = conn.execute(f'SELECT id FROM "{table}"').fetchall()
    return {int(row["id"]) for row in rows if row["id"] is not None}


def user_finance_db(root: Path, users_dir: str, user_id: int) -> Path:
    return root / users_dir / str(user_id) / "finance.db"


def load_finance_ids(root: Path, users_dir: str, user_ids: Set[int]) -> Dict[int, Dict[str, Set[int]]]:
    result: Dict[int, Dict[str, Set[int]]] = {}
    for user_id in sorted(user_ids):
        db_path = user_finance_db(root, users_dir, user_id)
        if not db_path.exists():
            result[user_id] = {"exists": set(), "categories": set(), "capital_accounts": set(), "transactions": set()}
            continue
        with open_readonly(db_path) as conn:
            result[user_id] = {
                "exists": {1},
                "categories": id_set(conn, "categories"),
                "capital_accounts": id_set(conn, "capital_accounts"),
                "transactions": id_set(conn, "transactions"),
            }
    return result


def issue(code: str, table: str, row_id: Optional[int], detail: Dict[str, Any]) -> Dict[str, Any]:
    return {"code": code, "table": table, "row_id": row_id, "detail": detail}


def validate_auth(root: Path, auth_db: str, users_dir: str) -> Dict[str, Any]:
    auth_path = root / auth_db
    report: Dict[str, Any] = {
        "source_root": str(root),
        "auth_db": str(auth_path),
        "counts": {},
        "warnings": [],
        "issues": [],
    }
    if not auth_path.exists():
        report["issues"].append(issue("missing_auth_db", "auth", None, {}))
        return report

    with open_readonly(auth_path) as conn:
        names = table_names(conn)
        report["counts"] = {table: count_rows(conn, table) for table in AUTH_TABLES}
        users = id_set(conn, "users")
        families = id_set(conn, "families")
        family_categories = id_set(conn, "family_categories")
        finance_ids = load_finance_ids(root, users_dir, users)

        for user_id in sorted(users):
            if not user_finance_db(root, users_dir, user_id).exists():
                report["issues"].append(issue("missing_user_finance_db", "users", user_id, {"user_id": user_id}))

        if "families" in names:
            for row in conn.execute("SELECT id, owner_user_id FROM families").fetchall():
                if int(row["owner_user_id"]) not in users:
                    report["issues"].append(
                        issue("missing_family_owner_user", "families", int(row["id"]), {"owner_user_id": row["owner_user_id"]})
                    )

        if "family_memberships" in names:
            for row in conn.execute("SELECT id, family_id, user_id, invited_by_user_id FROM family_memberships").fetchall():
                row_id = int(row["id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_membership_family", "family_memberships", row_id, {"family_id": row["family_id"]}))
                if int(row["user_id"]) not in users:
                    report["issues"].append(issue("missing_membership_user", "family_memberships", row_id, {"user_id": row["user_id"]}))
                if row["invited_by_user_id"] is not None and int(row["invited_by_user_id"]) not in users:
                    report["issues"].append(
                        issue("missing_membership_inviter", "family_memberships", row_id, {"invited_by_user_id": row["invited_by_user_id"]})
                    )

        if "family_invites" in names:
            for row in conn.execute("SELECT id, family_id, invited_by_user_id FROM family_invites").fetchall():
                row_id = int(row["id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_invite_family", "family_invites", row_id, {"family_id": row["family_id"]}))
                if int(row["invited_by_user_id"]) not in users:
                    report["issues"].append(issue("missing_invite_inviter", "family_invites", row_id, {"invited_by_user_id": row["invited_by_user_id"]}))

        if "family_categories" in names:
            for row in conn.execute("SELECT id, family_id, created_by_user_id FROM family_categories").fetchall():
                row_id = int(row["id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_family_category_family", "family_categories", row_id, {"family_id": row["family_id"]}))
                if row["created_by_user_id"] is not None and int(row["created_by_user_id"]) not in users:
                    report["issues"].append(
                        issue("missing_family_category_creator", "family_categories", row_id, {"created_by_user_id": row["created_by_user_id"]})
                    )

        if "family_category_bindings" in names:
            for row in conn.execute("SELECT id, family_id, family_category_id, user_id, local_category_id, confirmed_by_user_id FROM family_category_bindings").fetchall():
                row_id = int(row["id"])
                user_id = int(row["user_id"])
                local_category_id = int(row["local_category_id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_binding_family", "family_category_bindings", row_id, {"family_id": row["family_id"]}))
                if int(row["family_category_id"]) not in family_categories:
                    report["issues"].append(
                        issue("missing_binding_family_category", "family_category_bindings", row_id, {"family_category_id": row["family_category_id"]})
                    )
                if user_id not in users:
                    report["issues"].append(issue("missing_binding_user", "family_category_bindings", row_id, {"user_id": user_id}))
                elif local_category_id not in finance_ids.get(user_id, {}).get("categories", set()):
                    report["issues"].append(
                        issue("missing_binding_local_category", "family_category_bindings", row_id, {"user_id": user_id, "local_category_id": local_category_id})
                    )
                if row["confirmed_by_user_id"] is not None and int(row["confirmed_by_user_id"]) not in users:
                    report["issues"].append(
                        issue("missing_binding_confirmer", "family_category_bindings", row_id, {"confirmed_by_user_id": row["confirmed_by_user_id"]})
                    )

        if "family_capital_accounts" in names:
            for row in conn.execute("SELECT id, family_id, owner_user_id, capital_account_id FROM family_capital_accounts").fetchall():
                row_id = int(row["id"])
                owner_user_id = int(row["owner_user_id"])
                capital_account_id = int(row["capital_account_id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_family_capital_family", "family_capital_accounts", row_id, {"family_id": row["family_id"]}))
                if owner_user_id not in users:
                    report["issues"].append(issue("missing_family_capital_owner", "family_capital_accounts", row_id, {"owner_user_id": owner_user_id}))
                elif capital_account_id not in finance_ids.get(owner_user_id, {}).get("capital_accounts", set()):
                    report["issues"].append(
                        issue("missing_family_capital_account", "family_capital_accounts", row_id, {"owner_user_id": owner_user_id, "capital_account_id": capital_account_id})
                    )

        if "family_capital_member_settings" in names:
            for row in conn.execute("SELECT family_id, user_id, target_owner_user_id, target_capital_account_id FROM family_capital_member_settings").fetchall():
                row_id = None
                user_id = int(row["user_id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_capital_setting_family", "family_capital_member_settings", row_id, {"family_id": row["family_id"]}))
                if user_id not in users:
                    report["issues"].append(issue("missing_capital_setting_user", "family_capital_member_settings", row_id, {"user_id": user_id}))
                if row["target_owner_user_id"] is not None:
                    owner_user_id = int(row["target_owner_user_id"])
                    target_capital_account_id = row["target_capital_account_id"]
                    if owner_user_id not in users:
                        report["issues"].append(
                            issue("missing_capital_setting_target_owner", "family_capital_member_settings", row_id, {"target_owner_user_id": owner_user_id})
                        )
                    elif target_capital_account_id is not None and int(target_capital_account_id) not in finance_ids.get(owner_user_id, {}).get("capital_accounts", set()):
                        report["issues"].append(
                            issue(
                                "missing_capital_setting_target_account",
                                "family_capital_member_settings",
                                row_id,
                                {"target_owner_user_id": owner_user_id, "target_capital_account_id": int(target_capital_account_id)},
                            )
                        )

        if "family_capital_contributions" in names:
            for row in conn.execute("SELECT id, family_id, source_user_id, source_transaction_id, target_owner_user_id, target_capital_account_id FROM family_capital_contributions").fetchall():
                row_id = int(row["id"])
                source_user_id = int(row["source_user_id"])
                target_owner_user_id = int(row["target_owner_user_id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(issue("missing_contribution_family", "family_capital_contributions", row_id, {"family_id": row["family_id"]}))
                if source_user_id not in users:
                    report["issues"].append(issue("missing_contribution_source_user", "family_capital_contributions", row_id, {"source_user_id": source_user_id}))
                elif int(row["source_transaction_id"]) not in finance_ids.get(source_user_id, {}).get("transactions", set()):
                    report["warnings"].append(
                        issue(
                            "orphan_contribution_source_transaction",
                            "family_capital_contributions",
                            row_id,
                            {"source_user_id": source_user_id, "source_transaction_id": row["source_transaction_id"]},
                        )
                    )
                if target_owner_user_id not in users:
                    report["issues"].append(
                        issue("missing_contribution_target_owner", "family_capital_contributions", row_id, {"target_owner_user_id": target_owner_user_id})
                    )
                elif int(row["target_capital_account_id"]) not in finance_ids.get(target_owner_user_id, {}).get("capital_accounts", set()):
                    report["issues"].append(
                        issue(
                            "missing_contribution_target_capital_account",
                            "family_capital_contributions",
                            row_id,
                            {"target_owner_user_id": target_owner_user_id, "target_capital_account_id": row["target_capital_account_id"]},
                        )
                    )

        if "family_category_audit_resolutions" in names:
            for row in conn.execute("SELECT id, family_id, resolved_by_user_id FROM family_category_audit_resolutions").fetchall():
                row_id = int(row["id"])
                if int(row["family_id"]) not in families:
                    report["issues"].append(
                        issue("missing_audit_resolution_family", "family_category_audit_resolutions", row_id, {"family_id": row["family_id"]})
                    )
                if row["resolved_by_user_id"] is not None and int(row["resolved_by_user_id"]) not in users:
                    report["issues"].append(
                        issue("missing_audit_resolution_user", "family_category_audit_resolutions", row_id, {"resolved_by_user_id": row["resolved_by_user_id"]})
                    )

    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# SQLite Family Migration Preflight", "", f"Source root: `{report['source_root']}`", ""]
    lines.extend(["| Table | Rows |", "| --- | ---: |"])
    for table, count in report["counts"].items():
        lines.append(f"| `{table}` | {count} |")
    lines.extend(["", f"Warnings: `{len(report.get('warnings', []))}`", f"Issues: `{len(report['issues'])}`", ""])
    if report.get("warnings"):
        lines.extend(["| Warning | Table | Row | Detail |", "| --- | --- | ---: | --- |"])
        for item in report["warnings"]:
            lines.append(
                f"| `{item['code']}` | `{item['table']}` | {item['row_id']} | `{json.dumps(item['detail'], ensure_ascii=False)}` |"
            )
        lines.append("")
    if report["issues"]:
        lines.extend(["| Code | Table | Row | Detail |", "| --- | --- | ---: | --- |"])
        for item in report["issues"]:
            lines.append(
                f"| `{item['code']}` | `{item['table']}` | {item['row_id']} | `{json.dumps(item['detail'], ensure_ascii=False)}` |"
            )
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only preflight for SQLite family links before PostgreSQL ETL.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    report = validate_auth(Path(args.source_root).resolve(), args.auth_db, args.users_dir)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
