from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_snapshot_files(source_root: Path, auth_db: str, root_finance_db: Optional[str], users_dir: str) -> List[Path]:
    paths = [source_root / auth_db]
    if root_finance_db:
        paths.append(source_root / root_finance_db)
    user_root = source_root / users_dir
    if user_root.exists():
        paths.extend(sorted(user_root.glob("*/finance.db")))
    return [path for path in paths if path.exists() and path.is_file()]


def target_path_for(source_root: Path, target_root: Path, source_file: Path) -> Path:
    return target_root / source_file.resolve().relative_to(source_root.resolve())


def copy_snapshot(
    source_root: Path,
    target_root: Path,
    auth_db: str,
    root_finance_db: Optional[str],
    users_dir: str,
    overwrite: bool,
) -> Dict[str, Any]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    if source_root == target_root:
        raise ValueError("source_root and target_root must be different")
    if target_root.exists() and any(target_root.iterdir()) and not overwrite:
        raise ValueError("target_root is not empty; pass --overwrite to replace snapshot files")
    target_root.mkdir(parents=True, exist_ok=True)

    copied = []
    for source_file in discover_snapshot_files(source_root, auth_db, root_finance_db, users_dir):
        target_file = target_path_for(source_root, target_root, source_file)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        copied.append(
            {
                "source": str(source_file),
                "target": str(target_file),
                "size": target_file.stat().st_size,
                "sha256": sha256_file(target_file),
            }
        )
    return {"source_root": str(source_root), "target_root": str(target_root), "copied": copied}


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# SQLite Snapshot Copy",
        "",
        f"Source root: `{report['source_root']}`",
        f"Target root: `{report['target_root']}`",
        "",
        "| File | Size | SHA256 |",
        "| --- | ---: | --- |",
    ]
    for item in report["copied"]:
        lines.append(f"| `{item['target']}` | {item['size']} | `{item['sha256']}` |")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Copy SQLite auth/finance files into an explicit stage snapshot root.")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--auth-db", default="auth.db")
    parser.add_argument("--root-finance-db", default="finance.db")
    parser.add_argument("--users-dir", default="data/users")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown")
    args = parser.parse_args()

    root_finance_db = args.root_finance_db.strip() or None
    report = copy_snapshot(
        source_root=Path(args.source_root),
        target_root=Path(args.target_root),
        auth_db=args.auth_db,
        root_finance_db=root_finance_db,
        users_dir=args.users_dir,
        overwrite=args.overwrite,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
