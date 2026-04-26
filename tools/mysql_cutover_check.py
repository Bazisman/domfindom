from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mysql_schema import MYSQL_TABLES, mysql_connect


RUNTIME_WRITE_GROUPS = {
    "auth_and_sessions": "auth users, sessions, verification tokens and account lifecycle still use SQLite auth.db",
    "transactions": "transaction create/update/delete still commits to SQLite core first; MySQL is shadow-write only",
    "accounts_and_capital": "daily account, capital account and transfer balance mutations still commit to SQLite core first",
    "categories_budgets_recurring": "category, budget and recurring-template mutations still commit to SQLite core first",
    "reconciliation_settings": "reconciliation sources and user finance settings still commit to SQLite core/auth first",
}


def env_bool(env: Dict[str, str], name: str) -> bool:
    return (env.get(name, "").strip().lower() in {"1", "true", "yes", "on"})


def run_step(command: Sequence[str], env: Dict[str, str]) -> Dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def step_summary(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "command": step["command"],
        "returncode": step["returncode"],
        "stderr_tail": str(step.get("stderr") or "")[-1200:],
    }


def parse_json_stdout(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(str(step.get("stdout") or "{}"))
    except json.JSONDecodeError:
        return None


def check_python_dependencies() -> Dict[str, Any]:
    modules = ("pymysql", "cryptography")
    missing: List[str] = []
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return {"status": "ok" if not missing else "blocked", "missing": missing}


def check_database_connection(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return {"status": "blocked", "reason": "FINANCE_APP_MYSQL_DATABASE_URL is empty"}
    try:
        with mysql_connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS database_name, USER() AS user_name, VERSION() AS version")
                row = cursor.fetchone()
        return {"status": "ok", "database": row["database_name"], "user": row["user_name"], "version": row["version"]}
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)}


def check_schema_tables(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return {"status": "blocked", "reason": "FINANCE_APP_MYSQL_DATABASE_URL is empty"}
    expected = set(MYSQL_TABLES)
    try:
        with mysql_connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    """
                )
                actual = {str(row.get("table_name") or row.get("TABLE_NAME")) for row in cursor.fetchall()}
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        return {"status": "ok" if not missing else "blocked", "expected": len(expected), "missing": missing, "extra": extra}
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)}


def check_storage_backend(storage_backend: str, allow_mysql_backend: bool) -> Dict[str, Any]:
    if storage_backend == "mysql" and not allow_mysql_backend:
        return {
            "status": "blocked",
            "reason": "runtime MySQL write backend is not wired yet; keep FINANCE_APP_STORAGE_BACKEND=sqlite",
        }
    return {"status": "ok", "storage_backend": storage_backend or "sqlite"}


def check_runtime_adapter_status(allow_mysql_backend: bool, guarded_groups: Sequence[str] = ()) -> Dict[str, Any]:
    guarded = [group for group in guarded_groups if group in RUNTIME_WRITE_GROUPS]
    groups = [group for group in RUNTIME_WRITE_GROUPS if group not in set(guarded)]
    if allow_mysql_backend:
        return {
            "status": "blocked",
            "reason": "allow flag was set, but primary MySQL write adapters are not complete",
            "missing_groups": groups,
            "guarded_groups": guarded,
            "details": RUNTIME_WRITE_GROUPS,
        }
    return {
        "status": "blocked",
        "reason": "primary runtime is still SQLite-first; MySQL is ready only for ETL, reconciliation, shadow-read and shadow-write",
        "missing_groups": groups,
        "guarded_groups": guarded,
        "details": RUNTIME_WRITE_GROUPS,
    }


def check_primary_read_pilot(env: Dict[str, str], database_url: str) -> Dict[str, Any]:
    enabled = env_bool(env, "FINANCE_APP_MYSQL_PRIMARY_READ_PILOT")
    if enabled and not database_url:
        return {"status": "blocked", "enabled": enabled, "reason": "pilot requires FINANCE_APP_MYSQL_DATABASE_URL"}
    return {"status": "ok", "enabled": enabled}


def check_strict_categories_budgets_recurring(env: Dict[str, str], database_url: str) -> Dict[str, Any]:
    enabled = env_bool(env, "FINANCE_APP_MYSQL_STRICT_WRITE_CATEGORIES_BUDGETS_RECURRING")
    shadow_write_enabled = env_bool(env, "FINANCE_APP_MYSQL_SHADOW_WRITE")
    if enabled and not database_url:
        return {"status": "blocked", "enabled": enabled, "reason": "strict write requires FINANCE_APP_MYSQL_DATABASE_URL"}
    if enabled and not shadow_write_enabled:
        return {"status": "blocked", "enabled": enabled, "reason": "strict write requires FINANCE_APP_MYSQL_SHADOW_WRITE=true"}
    return {
        "status": "ok",
        "enabled": enabled,
        "guarded_group": "categories_budgets_recurring",
        "mode": "strict-dual-write" if enabled else "shadow-write-only",
    }


def check_strict_transactions(env: Dict[str, str], database_url: str) -> Dict[str, Any]:
    enabled = env_bool(env, "FINANCE_APP_MYSQL_STRICT_WRITE_TRANSACTIONS")
    shadow_write_enabled = env_bool(env, "FINANCE_APP_MYSQL_SHADOW_WRITE")
    if enabled and not database_url:
        return {"status": "blocked", "enabled": enabled, "reason": "strict transaction write requires FINANCE_APP_MYSQL_DATABASE_URL"}
    if enabled and not shadow_write_enabled:
        return {"status": "blocked", "enabled": enabled, "reason": "strict transaction write requires FINANCE_APP_MYSQL_SHADOW_WRITE=true"}
    return {
        "status": "ok",
        "enabled": enabled,
        "guarded_group": "transactions",
        "mode": "strict-dual-write" if enabled else "shadow-write-only",
    }


def run_json_tool(command: Sequence[str], env: Dict[str, str]) -> Dict[str, Any]:
    step = run_step(command, env)
    parsed = parse_json_stdout(step)
    if step["returncode"] != 0:
        return {"status": "blocked", "step": step_summary(step), "report": parsed}
    return {"status": "ok", "step": step_summary(step), "report": parsed}


def build_report(
    source_root: Path,
    database_url: str,
    auth_db: str,
    root_finance_db: str,
    users_dir: str,
    year: int,
    month: int,
    allow_mysql_backend: bool,
    skip_data_checks: bool,
) -> Dict[str, Any]:
    env = os.environ.copy()
    if database_url:
        env["FINANCE_APP_MYSQL_DATABASE_URL"] = database_url

    strict_categories = check_strict_categories_budgets_recurring(env, database_url)
    strict_transactions = check_strict_transactions(env, database_url)
    guarded_groups = (
        [strict_categories["guarded_group"]]
        if strict_categories.get("status") == "ok" and strict_categories.get("enabled")
        else []
    )
    if strict_transactions.get("status") == "ok" and strict_transactions.get("enabled"):
        guarded_groups.append(strict_transactions["guarded_group"])

    checks: Dict[str, Any] = {
        "python_dependencies": check_python_dependencies(),
        "database_connection": check_database_connection(database_url),
        "schema_tables": check_schema_tables(database_url),
        "storage_backend": check_storage_backend(
            env.get("FINANCE_APP_STORAGE_BACKEND", "sqlite").strip().lower() or "sqlite",
            allow_mysql_backend=allow_mysql_backend,
        ),
        "primary_read_pilot": check_primary_read_pilot(env, database_url),
        "strict_transactions": strict_transactions,
        "strict_categories_budgets_recurring": strict_categories,
        "runtime_adapter": check_runtime_adapter_status(allow_mysql_backend, guarded_groups=guarded_groups),
    }

    if not skip_data_checks:
        checks["reconciliation"] = run_json_tool(
            [
                sys.executable,
                "-B",
                "tools/mysql_reconciliation.py",
                "--source-root",
                str(source_root),
                "--auth-db",
                auth_db,
                "--root-finance-db",
                root_finance_db,
                "--users-dir",
                users_dir,
                "--database-url",
                database_url,
                "--format",
                "json",
            ],
            env,
        )
        checks["read_compare"] = run_json_tool(
            [
                sys.executable,
                "-B",
                "tools/mysql_read_compare.py",
                "--source-root",
                str(source_root),
                "--users-dir",
                users_dir,
                "--database-url",
                database_url,
                "--year",
                str(year),
                "--month",
                str(month),
                "--format",
                "json",
            ],
            env,
        )

    blockers = []
    for name, check in checks.items():
        if check.get("status") != "ok":
            blockers.append(name)
            continue
        report = check.get("report") or {}
        if name == "reconciliation" and int(report.get("failed", 0) or 0) != 0:
            blockers.append(name)
        if name == "read_compare" and int(report.get("failed", 0) or 0) != 0:
            blockers.append(name)

    data_blockers = [item for item in blockers if item != "runtime_adapter"]
    return {
        "source_root": str(source_root.resolve()),
        "checks": checks,
        "ready_for_shadow_read": not data_blockers,
        "ready_for_runtime_mysql": not blockers and allow_mysql_backend,
        "blockers": blockers,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# MySQL Cutover Check", "", f"Source root: `{report['source_root']}`", ""]
    lines.append(f"Ready for shadow read: `{report['ready_for_shadow_read']}`")
    lines.append(f"Ready for runtime mysql: `{report['ready_for_runtime_mysql']}`")
    lines.append(f"Blockers: `{len(report['blockers'])}`")
    lines.extend(["", "| Check | Status | Detail |", "| --- | --- | --- |"])
    for name, check in report["checks"].items():
        detail = ""
        if check.get("missing"):
            detail = "missing: " + ", ".join(check["missing"])
        elif check.get("missing_groups"):
            detail = str(check.get("reason") or "") + "; missing: " + ", ".join(check["missing_groups"])
            if check.get("guarded_groups"):
                detail += "; guarded: " + ", ".join(check["guarded_groups"])
        elif check.get("reason"):
            detail = str(check["reason"])
        elif name == "schema_tables":
            detail = f"expected={check.get('expected')} missing={len(check.get('missing', []))}"
        elif name == "reconciliation" and check.get("report"):
            detail = f"failed={check['report'].get('failed')}"
        elif name == "read_compare" and check.get("report"):
            detail = f"failed={check['report'].get('failed')}"
        elif name == "database_connection":
            detail = f"database={check.get('database')} user={check.get('user')}"
        elif name in {"strict_categories_budgets_recurring", "strict_transactions"}:
            detail = f"enabled={check.get('enabled')} mode={check.get('mode')}"
        lines.append(f"| `{name}` | `{check.get('status')}` | {detail} |")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Check whether MySQL shadow-read or cutover can be enabled.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--database-url", default=os.getenv("FINANCE_APP_MYSQL_DATABASE_URL", ""))
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--allow-mysql-backend", action="store_true")
    parser.add_argument("--skip-data-checks", action="store_true")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    report = build_report(
        source_root=Path(args.source_root),
        database_url=args.database_url,
        auth_db=args.auth_db,
        root_finance_db=args.root_finance_db,
        users_dir=args.users_dir,
        year=args.year,
        month=args.month,
        allow_mysql_backend=args.allow_mysql_backend,
        skip_data_checks=args.skip_data_checks,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["ready_for_shadow_read"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
