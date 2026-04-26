from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.sqlite_to_postgres_etl import normalize_psycopg_url


class StageCheckError(RuntimeError):
    pass


def is_local_database_url(database_url: str) -> bool:
    parsed = urlparse(normalize_psycopg_url(database_url))
    return (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def run_step(command: Sequence[str], cwd: Path, env: Dict[str, str]) -> Dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
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


def require_ok(step: Dict[str, Any], name: str) -> None:
    if int(step["returncode"]) != 0:
        raise StageCheckError(f"{name} failed with exit code {step['returncode']}")


def parse_json_stdout(step: Dict[str, Any], name: str) -> Dict[str, Any]:
    try:
        return json.loads(str(step["stdout"] or "{}"))
    except json.JSONDecodeError as exc:
        raise StageCheckError(f"{name} did not return JSON") from exc


def compact_step(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "command": step["command"],
        "returncode": step["returncode"],
        "stderr_tail": str(step["stderr"] or "")[-2000:],
    }


def run_stage_check(
    source_root: Path,
    database_url: str,
    auth_db: str,
    root_finance_db: str,
    users_dir: str,
    reset_target: bool,
    allow_nonlocal_target: bool,
) -> Dict[str, Any]:
    source_root = source_root.resolve()
    if not allow_nonlocal_target and not is_local_database_url(database_url):
        raise StageCheckError("Refusing non-local database URL without --allow-nonlocal-target")
    if not reset_target:
        raise StageCheckError("--reset-target is required so the stage target state is explicit")

    env = os.environ.copy()
    env["FINANCE_APP_DATABASE_URL"] = database_url
    steps: List[Dict[str, Any]] = []

    preflight = run_step(
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
        PROJECT_ROOT,
        env,
    )
    steps.append({"name": "preflight", **compact_step(preflight)})
    require_ok(preflight, "preflight")
    preflight_report = parse_json_stdout(preflight, "preflight")

    for name, alembic_args in (
        ("alembic_downgrade_base", ["downgrade", "base"]),
        ("alembic_upgrade_head", ["upgrade", "head"]),
    ):
        step = run_step([sys.executable, "-m", "alembic", *alembic_args], PROJECT_ROOT, env)
        steps.append({"name": name, **compact_step(step)})
        require_ok(step, name)

    etl = run_step(
        [
            sys.executable,
            "-B",
            "tools/sqlite_to_postgres_etl.py",
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
            "--write-target",
            "--wipe-target",
            "--format",
            "json",
        ],
        PROJECT_ROOT,
        env,
    )
    steps.append({"name": "etl", **compact_step(etl)})
    require_ok(etl, "etl")
    etl_report = parse_json_stdout(etl, "etl")

    reconciliation = run_step(
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
        PROJECT_ROOT,
        env,
    )
    steps.append({"name": "reconciliation", **compact_step(reconciliation)})
    require_ok(reconciliation, "reconciliation")
    reconciliation_report = parse_json_stdout(reconciliation, "reconciliation")

    return {
        "source_root": str(source_root),
        "preflight": {
            "issues": len(preflight_report.get("issues", [])),
            "warnings": len(preflight_report.get("warnings", [])),
            "counts": preflight_report.get("counts", {}),
        },
        "etl_loaded": etl_report.get("loaded", {}),
        "reconciliation_failed": reconciliation_report.get("failed"),
        "steps": steps,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# PostgreSQL Stage Check", "", f"Source root: `{report['source_root']}`", ""]
    preflight = report["preflight"]
    lines.append(f"Preflight issues: `{preflight['issues']}`")
    lines.append(f"Preflight warnings: `{preflight['warnings']}`")
    lines.append(f"Reconciliation failed checks: `{report['reconciliation_failed']}`")
    lines.extend(["", "Loaded finance databases:", ""])
    for item in report.get("etl_loaded", {}).get("finance", []):
        lines.append(f"- `{item['path']}`: {sum(int(v) for v in item.get('tables', {}).values())} rows across finance tables")
    family = report.get("etl_loaded", {}).get("family", {})
    if family:
        lines.extend(["", "Loaded family rows:", ""])
        for table, count in family.items():
            lines.append(f"- `{table}`: {count}")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run guarded PostgreSQL migration stage check.")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--reset-target", action="store_true")
    parser.add_argument("--allow-nonlocal-target", action="store_true")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    report = run_stage_check(
        source_root=Path(args.source_root),
        database_url=args.database_url,
        auth_db=args.auth_db,
        root_finance_db=args.root_finance_db,
        users_dir=args.users_dir,
        reset_target=args.reset_target,
        allow_nonlocal_target=args.allow_nonlocal_target,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["reconciliation_failed"] == 0 and report["preflight"]["issues"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
