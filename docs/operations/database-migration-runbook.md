# Database Migration Runbook

**Project:** DocWeave
**Status:** Initial revision validated live; online Alembic runner pending
**Last updated:** 2026-07-24

## 1. Purpose

This runbook defines the controlled CockroachDB migration workflow. It does not
authorize future live migrations. Revision `0001_operational_foundation` was
separately authorized and accepted in the isolated `docweave_validation`
database on 2026-07-24. That evidence does not mean the application connects to
CockroachDB or that a production schema is deployed.

The current migration head is:

```text
0001_operational_foundation
```

It creates only the approved non-vector operational foundation:

- workspace and actor identity;
- workspace membership history;
- operation batches;
- per-file operation intent, result, lease, and reconciliation state; and
- append-only audit event storage shape.

## 2. Cost boundary

Offline Alembic commands do not open a database connection and consume no
CockroachDB Request Units or storage.

A live migration can consume Request Units and storage, including background
work for indexes and schema changes. Before any live command:

1. obtain explicit user approval for the exact target and revision;
2. verify the cluster plan, current monthly Request Unit usage, storage usage,
   and billing controls;
3. estimate whether the migration remains inside the approved free allowance;
4. stop if paid usage is possible unless the user separately authorizes it;
5. confirm the target contains no unrelated schema that could be affected; and
6. record a recovery or forward-fix plan.

The current user authorization does not permit paid CockroachDB usage.

## 3. Offline verification

Show the ordered migration head:

```powershell
.\.venv\Scripts\python -m alembic heads
```

Render the upgrade without connecting:

```powershell
.\.venv\Scripts\python -m alembic upgrade head --sql
```

Render the disposable-environment downgrade:

```powershell
.\.venv\Scripts\python -m alembic downgrade 0001_operational_foundation:base --sql
```

Run the complete repository quality gate:

```powershell
.\scripts\check.ps1
```

Offline rendering validates migration ordering and SQL generation. It does not
prove that CockroachDB accepted the migration.

## 4. Online execution gate

Online Alembic execution fails when `DOCWEAVE_DATABASE_URL` is absent. The
connection value must be supplied at runtime through an approved secret
delivery mechanism and must never be written to the repository, command logs,
screenshots, issue text, or pull-request output.

The migration must not run automatically during desktop startup, cloud startup,
tests, or deployment. A separately authorized operator runs it as an explicit
release step.

Before a future live migration, add or verify:

- a controlled clean test target;
- the identity mode explicitly approved for that phase;
- Transport Layer Security certificate validation;
- current cluster usage and cost evidence;
- a clean-database migration test;
- schema introspection evidence;
- invalid-state and cross-workspace constraint tests;
- forward-recovery behavior; and
- the exact revision recorded by Alembic.

For the 2026-07-24 predevelopment validation, the project owner explicitly
approved the existing authenticated root or administrator path and deferred
least-privilege profiles to a later separately approved phase. No credential
was exported, logged, or committed. Root or administrator access is not
approved for application runtime use.

## 5. Failure handling

CockroachDB does not provide full transactional rollback for arbitrary groups
of Data Definition Language changes. If a schema change fails:

1. stop subsequent revisions;
2. preserve the complete sanitized error and schema-job identifier;
3. inspect actual schema state before retrying;
4. do not assume the downgrade is safe on a data-bearing database;
5. prefer a reviewed forward-fix migration; and
6. obtain approval before destructive cleanup.

An unavailable check or ambiguous schema state is a failure, never a pass.

## 6. Current non-claims

The repository does not yet prove:

- online Alembic execution through the Psycopg driver;
- a production or runtime-connected DocWeave schema;
- persistent application memory;
- runtime database roles or Row-Level Security;
- serializable transaction retries;
- live operation reconciliation;
- Distributed Vector Indexing; or
- competition-qualifying CockroachDB integration.

The repository does prove that the exact offline-rendered SQL for revision
`0001_operational_foundation` was accepted and introspected in a clean,
isolated CockroachDB Cloud validation database. See
[`cockroachdb-live-validation.md`](cockroachdb-live-validation.md).
