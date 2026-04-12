# Encoding Policy

## Standard
- All text files in the repository must be `UTF-8` and `LF`.
- UTF-8 must be **without BOM**.
- This is enforced by:
  - `.editorconfig`
  - `.gitattributes`
  - `.vscode/settings.json`
  - `.githooks/pre-commit`
  - `tools/check_encoding.py`

## Required Check Before Build/Deploy
- Run:
  - `python tools/check_encoding.py`
- If the check fails, deployment is blocked until files are fixed.
- Frontend build also runs this check automatically via `npm run build`.

## Safe Editing Rules (PowerShell)
- For writing files from shell, always specify UTF-8 explicitly:
  - `Set-Content -Encoding utf8NoBOM ...`
  - `Out-File -Encoding utf8NoBOM ...`
- Avoid ad-hoc recoding between `cp1251` and `utf8`.
- If text is damaged, restore from Git/history and re-apply intended changes.

## Local Setup (One Time)
1. Configure Git hooks:
   - `powershell -ExecutionPolicy Bypass -File tools/install_git_hooks.ps1`
2. Verify:
   - `git config --get core.hooksPath` should return `.githooks`
3. Run a manual check:
   - `python tools/check_encoding.py --root .`

## What the checker blocks
- Files that are not decodable as UTF-8.
- Files with UTF-8 BOM.
- Files with common mojibake signatures (`utf8->cp1251`, `utf8->latin1`).
- Files that already contain replacement markers (U+FFFD replacement character).

## Incident Protocol
When mojibake is found:
1. Freeze deployment for the affected files.
2. Identify the exact broken files.
3. Restore or rewrite text in UTF-8.
4. Run `python tools/check_encoding.py`.
5. Rebuild frontend/backend.
6. Deploy and verify user-visible pages.
7. Log incident in `docs/sessions/`.
