# CockroachDB Migrations

This directory contains manually authored, reviewed Alembic migrations for
DocWeave.

Offline SQL rendering is safe and does not connect to CockroachDB:

```powershell
.\.venv\Scripts\python -m alembic upgrade head --sql
```

Online execution requires `DOCWEAVE_DATABASE_URL`. Do not set that variable or
run an online migration without explicit approval, a verified target, and a
cost and resource preflight.

No migration in this directory proves that a schema is deployed. Deployment
evidence must name the target, revision, command, result, and verification
queries without exposing credentials.
