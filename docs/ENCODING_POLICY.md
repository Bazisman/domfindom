# Encoding Policy

## Standard
- All text files in the repository must be `UTF-8` and `LF`.
- This is enforced by:
  - `.editorconfig`
  - `.gitattributes`

## Required Check Before Build/Deploy
- Run:
  - `python tools/check_encoding.py`
- If the check fails, deployment is blocked until files are fixed.

## Safe Editing Rules (PowerShell)
- For writing files from shell, always specify UTF-8 explicitly:
  - `Set-Content -Encoding utf8 ...`
  - `Out-File -Encoding utf8 ...`
- Avoid ad-hoc recoding between `cp1251` and `utf8`.
- If text is damaged, restore from Git/history and re-apply intended changes.

## Incident Protocol
When mojibake is found:
1. Freeze deployment for the affected files.
2. Identify the exact broken files.
3. Restore or rewrite text in UTF-8.
4. Run `python tools/check_encoding.py`.
5. Rebuild frontend/backend.
6. Deploy and verify user-visible pages.
7. Log incident in `docs/sessions/`.

