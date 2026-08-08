# ADR-0003: CockroachDB Migration Tooling

**Status:** Accepted for the hackathon submission
**Decision date:** 2026-08-08
**Decision owner:** Project owner

## Context

The database must be reproducible without requiring readers to understand old
prototype schemas. The migration history should show the current product, not a
sequence of abandoned detours.

## Decision

DocWeave uses:

- Alembic for versioned migrations;
- SQLAlchemy Core with the CockroachDB dialect for reviewed schema rendering;
- Psycopg for the PostgreSQL wire protocol; and
- one current revision, `0001_simple_docweave_schema`.

Online migration execution reads `DOCWEAVE_DATABASE_URL` from the environment
and fails closed when it is absent. Offline rendering uses only a placeholder
URL and never connects to a database.

## Migration Safety Rules

1. The application never auto-runs migrations at startup.
2. Online migrations require explicit operator intent and a configured target.
3. Connection strings and credentials are never committed to the repository.
4. Destructive schema changes require a separate backup and recovery plan.
5. The current submission has one schema, `docweave`, and six tables.

## Verification

Acceptance requires:

1. exactly one Alembic head;
2. successful offline upgrade and downgrade rendering;
3. tests proving the six-table schema and the absence of extra views;
4. a fail-closed test when `DOCWEAVE_DATABASE_URL` is missing; and
5. live runtime preflight against CockroachDB before claiming the demo is ready.
