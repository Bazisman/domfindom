# Session Addendum 2026-04-11 (Security Hardening Phase 1)

## Implemented
- Added CSRF protection for authenticated state-changing API methods (`POST/PUT/PATCH/DELETE`).
- Added CSRF cookie issuing on auth/session flow and automatic CSRF header in frontend API client.
- Added secure response headers in backend middleware:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - `Strict-Transport-Security` for HTTPS in production.
- Strengthened production session-secret policy:
  - strict check controlled by `FINANCE_APP_ENFORCE_STRICT_SESSION_SECRET`
  - emergency bypass with `FINANCE_APP_ALLOW_INSECURE_SESSION_SECRET`
- Tightened default login rate limit from 10 to 5 attempts per 15 minutes.
- Updated environment template with new security variables.

## Validation
- Backend tests: `python -m unittest tests.test_web_api -v` -> `OK` (29 tests).
- Frontend build: `npm run build` -> `OK`.
- Added CSRF test:
  - missing `X-CSRF-Token` => `403`
  - valid token => success.

## Required production action before backend deploy
Set a strong session secret in production environment:
- `FINANCE_APP_SESSION_SECRET=<strong-random-value>`

Recommended:
- keep `FINANCE_APP_ENFORCE_STRICT_SESSION_SECRET=true`
- keep `FINANCE_APP_ALLOW_INSECURE_SESSION_SECRET=false`

