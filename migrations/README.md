# Database migrations

This directory is reserved for the future PostgreSQL migration track.

Current production runtime still uses SQLite:
- `auth.db`
- `data/users/*/finance.db`

Do not wire Alembic into Passenger startup. PostgreSQL migrations must be an explicit release step after dry-run, reconciliation and stage verification.
