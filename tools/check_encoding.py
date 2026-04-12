from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".html",
    ".md",
    ".json",
    ".yml",
    ".yaml",
}

SKIP_DIRS = {
    ".git",
    ".archive",
    "node_modules",
    "dist",
    "__pycache__",
    ".venv",
    "backups",
}

KNOWN_LEGACY_NON_UTF8 = {
    "docs/sessions/2026-04-11.md",
}

UTF8_BOM = b"\xef\xbb\xbf"

MOJIBAKE_PATTERNS = {
    "utf8-decoded-as-latin1": re.compile(r"(?:Ð.|Ñ.){3,}"),
    "utf8-decoded-as-cp1251": re.compile(r"(?:[??][^\s]){4,}"),
}


def should_scan(path: Path, extensions: set[str]) -> bool:
    if path.suffix.lower() not in extensions:
        return False
    parts = {p.lower() for p in path.parts}
    return not any(skip.lower() in parts for skip in SKIP_DIRS)


def is_legacy_excluded(path: Path, root: Path) -> bool:
    rel = path.resolve().relative_to(root).as_posix().lower()
    return rel in {p.lower() for p in KNOWN_LEGACY_NON_UTF8}


def detect_mojibake(content: str) -> list[str]:
    issues: list[str] = []
    if "\ufffd" in content:
        issues.append("replacement-character")
    for name, pattern in MOJIBAKE_PATTERNS.items():
        if pattern.search(content):
            issues.append(name)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository text files for encoding issues.")
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    bad_utf8: list[str] = []
    bom_files: list[str] = []
    suspicious: list[tuple[str, list[str]]] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not should_scan(path, DEFAULT_EXTENSIONS):
            continue
        if is_legacy_excluded(path, root):
            continue

        raw = path.read_bytes()
        if raw.startswith(UTF8_BOM):
            bom_files.append(str(path))

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad_utf8.append(str(path))
            continue

        mojibake_issues = detect_mojibake(content)
        if mojibake_issues:
            suspicious.append((str(path), mojibake_issues))

    if bad_utf8 or bom_files or suspicious:
        print("Encoding check failed.")
        if bad_utf8:
            print("\nFiles not decodable as UTF-8:")
            for file_path in bad_utf8:
                print(f"- {file_path}")
        if bom_files:
            print("\nFiles with UTF-8 BOM (must be UTF-8 without BOM):")
            for file_path in bom_files:
                print(f"- {file_path}")
        if suspicious:
            print("\nFiles with suspicious mojibake markers:")
            for file_path, reasons in suspicious:
                reasons_str = ", ".join(reasons)
                print(f"- {file_path} ({reasons_str})")
        print("\nFix encoding and rerun: python tools/check_encoding.py")
        return 1

    print("Encoding check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
