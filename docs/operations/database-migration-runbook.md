# Database Migration Runbook

**Project:** DocWeave  
**Status:** Simple hackathon schema only  
**Last updated:** 2026-08-08

## Purpose

This runbook defines the controlled CockroachDB migration workflow for the
current DocWeave demo. The repository now has one schema and one migration.

Current head:

```text
0001_simple_docweave_schema
```

Current schema:

```text
docweave.documents
docweave.agent_runs
docweave.proposals
docweave.human_decisions
docweave.file_history
docweave.document_relationships
```

There is no separate judge schema and no legacy operational schema in the
current demo path.

## Offline Verification

```powershell
.\.venv\Scripts\python -m alembic heads
.\.venv\Scripts\python -m alembic upgrade head --sql
.\.venv\Scripts\python -m alembic downgrade head:base --sql
```

Offline rendering must not print credentials or open a database connection.

## Live Readiness

Before a live schema operation, confirm that the target is the intended
CockroachDB database and that the user has authorized the change.

Minimum read-only check:

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
```

Expected:

```text
runtime_config: ok (loaded)
bedrock_client: ok (eu-central-1:configured)
cockroachdb_connection: ok (reachable)
docweave_schema: ok (ready)
```

Read-only evidence:

```powershell
.\.venv\Scripts\docweave-memory-evidence.exe --json
.\.venv\Scripts\docweave-memory-schema.exe --flat
```

## Online Migration

Online migration must be an explicit operator action:

```powershell
.\.venv\Scripts\docweave-live-memory-validation.exe --online-upgrade --inspect-live
```

The command must run only from a shell that does not log environment variables
or connection strings. `DOCWEAVE_DATABASE_URL` must come from the approved
runtime launcher or another approved secret-delivery mechanism.

## Failure Handling

If a live schema operation fails:

1. Stop immediately.
2. Preserve the sanitized error.
3. Inspect the actual schema state before retrying.
4. Prefer a reviewed forward fix.
5. Do not run destructive cleanup without explicit approval.

Unavailable or ambiguous schema evidence is a failure, not a pass.
