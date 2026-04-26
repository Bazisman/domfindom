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

from tools.sqlite_to_postgres_etl import normalize_psycopg_url


EXPECTED_REVISION = "20260425_0001"


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
    modules = ("sqlalchemy", "alembic", "psycopg")
    missing: List[str] = []
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    return {"status": "ok" if not missing else "blocked", "missing": missing}


def check_database_connection(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return {"status": "blocked", "reason": "FINANCE_APP_DATABASE_URL is empty"}
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(normalize_psycopg_url(database_url), row_factory=dict_row) as conn:
            row = conn.execute("SELECT current_database() AS database, current_user AS user").fetchone()
        return {"status": "ok", "database": row["database"], "user": row["user"]}
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)}


def check_alembic_revision(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return {"status": "blocked", "reason": "FINANCE_APP_DATABASE_URL is empty"}
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(normalize_psycopg_url(database_url), row_factory=dict_row) as conn:
            row = conn.execute("SELECT version_num FROM public.alembic_version").fetchone()
        actual = row["version_num"] if row else None
        return {
            "status": "ok" if actual == EXPECTED_REVISION else "blocked",
            "expected": EXPECTED_REVISION,
            "actual": actual,
        }
    except Exception as exc:
        return {"status": "blocked", "expected": EXPECTED_REVISION, "reason": str(exc)}


def check_storage_backend(storage_backend: str, allow_postgres_backend: bool) -> Dict[str, Any]:
    if storage_backend == "postgres" and not allow_postgres_backend:
        return {
            "status": "blocked",
            "reason": "runtime PostgreSQL write backend is not wired yet; keep FINANCE_APP_STORAGE_BACKEND=sqlite",
        }
    return {"status": "ok", "storage_backend": storage_backend or "sqlite"}


def run_json_tool(command: Sequence[str], env: Dict[str, str], name: str) -> Dict[str, Any]:
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
    allow_postgres_backend: bool,
    skip_data_checks: bool,
) -> Dict[str, Any]:
    env = os.environ.copy()
    if database_url:
        env["FINANCE_APP_DATABASE_URL"] = database_url

    checks: Dict[str, Any] = {
        "python_dependencies": check_python_dependencies(),
        "database_connection": check_database_connection(database_url),
        "alembic_revision": check_alembic_revision(database_url),
        "storage_backend": check_storage_backend(
            env.get("FINANCE_APP_STORAGE_BACKEND", "sqlite").strip().lower() or "sqlite",
            allow_postgres_backend=allow_postgres_backend,
        ),
    }

    if not skip_data_checks:
        checks["family_preflight"] = run_json_tool(
            [
                sys.executable,
                "-B",
                "tools/sqlite_family_preflight.py",
                "--source-root",
                str(source_root),
                "--auth-db",
                auth_db,
                "--users-dir",
                users_dir,
                "--format",
                "json",
            ],
            env,
            "family_preflight",
        )
        checks["reconciliation"] = run_json_tool(
            [
                sys.executable,
                "-B",
                "tools/postgres_reconciliation.py",
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
            "reconciliation",
        )
        checks["read_compare"] = run_json_tool(
            [
                sys.executable,
                "-B",
                "tools/postgres_read_compare.py",
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
            "read_compare",
        )

    blockers = []
    for name, check in checks.items():
        if check.get("status") != "ok":
            blockers.append(name)
            continue
        report = check.get("report") or {}
        if name == "family_preflight" and report.get("issues"):
            blockers.append(name)
        if name == "reconciliation" and int(report.get("failed", 0) or 0) != 0:
            blockers.append(name)
        if name == "read_compare" and int(report.get("failed", 0) or 0) != 0:
            blockers.append(name)

    return {
        "source_root": str(source_root.resolve()),
        "expected_revision": EXPECTED_REVISION,
        "checks": checks,
        "ready_for_runtime_postgres": not blockers and allow_postgres_backend,
        "ready_for_shadow_read": not blockers,
        "blockers": blockers,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# PostgreSQL Cutover Check", "", f"Source root: `{report['source_root']}`", ""]
    lines.append(f"Ready for shadow read: `{report['ready_for_shadow_read']}`")
    lines.append(f"Ready for runtime postgres: `{report['ready_for_runtime_postgres']}`")
    lines.append(f"Blockers: `{len(report['blockers'])}`")
    lines.extend(["", "| Check | Status | Detail |", "| --- | --- | --- |"])
    for name, check in report["checks"].items():
        detail = ""
        if check.get("missing"):
            detail = "missing: " + ", ".join(check["missing"])
        elif check.get("reason"):
            detail = str(check["reason"])
        elif name == "alembic_revision":
            detail = f"actual={check.get('actual')} expected={check.get('expected')}"
        elif name == "reconciliation" and check.get("report"):
            detail = f"failed={check['report'].get('failed')}"
        elif name == "read_compare" and check.get("report"):
            detail = f"failed={check['report'].get('failed')}"
        elif name == "family_preflight" and check.get("report"):
            detail = f"issues={len(check['report'].get('issues', []))} warnings={len(check['report'].get('warnings', []))}"
        lines.append(f"| `{name}` | `{check.get('status')}` | {detail} |")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Check whether PostgreSQL shadow-read or cutover can be enabled.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--database-url", default=os.getenv("FINANCE_APP_DATABASE_URL", ""))
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--allow-postgres-backend", action="store_true")
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
        allow_postgres_backend=args.allow_postgres_backend,
        skip_data_checks=args.skip_data_checks,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["ready_for_shadow_read"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
