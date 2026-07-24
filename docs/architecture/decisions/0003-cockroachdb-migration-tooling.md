# ADR-0003: CockroachDB Migration Tooling

**Status:** Accepted
**Decision date:** 2026-07-24
**Decision owner:** Project owner
**Implementation status:** In progress

## Context

DocWeave needs reproducible CockroachDB schema evolution before operational,
semantic, episodic, preference, and audit memory can become durable. The
approved physical model requires versioned migrations, clean-database tests,
forward recovery, serializable application transactions, and explicit
workspace isolation.

CockroachDB recommends using a schema migration tool or its SQL client instead
of using an Object-Relational Mapper to create or change schemas implicitly.
CockroachDB also does not provide full transactional guarantees for arbitrary
groups of Data Definition Language statements. The migration workflow must
therefore expose each change, avoid hidden auto-generation, and make partial
schema-change failure observable.

## Decision

DocWeave will use:

- Alembic `1.18.5` as the migration versioning and execution tool;
- SQLAlchemy `2.0.51` Core as the typed schema expression layer;
- `sqlalchemy-cockroachdb` `2.0.4` as the CockroachDB dialect;
- Psycopg `3.3.4` with its pinned binary distribution as the PostgreSQL wire
  protocol driver; and
- manually authored and reviewed migrations rather than unreviewed
  auto-generated schema changes.

Migration configuration will read the database URL only from the
`DOCWEAVE_DATABASE_URL` environment variable during online execution. The
repository will contain no real endpoint, username, password, certificate,
account identifier, or connection string.

Offline SQL rendering will use a non-routable local placeholder URL only to
select the CockroachDB dialect. Offline rendering never opens a connection.
Online migration execution fails closed when `DOCWEAVE_DATABASE_URL` is
absent.

Alembic will be configured with non-transactional Data Definition Language
semantics. A migration may group initial `CREATE TABLE` statements where
CockroachDB supports them, but later destructive or backfill-heavy changes must
be split into independently observable revisions.

## Migration safety rules

1. Migrations never run automatically when the desktop or cloud application
   starts.
2. Continuous Integration renders and validates migrations offline by default.
3. A live migration requires explicit user approval, a preflight cost and
   resource check, a named target, and a recorded command.
4. Production downgrades are not an automatic rollback mechanism. Forward
   recovery is preferred after data-bearing changes.
5. Destructive changes require a backup and tested recovery plan.
6. No migration may invent the unresolved vector dimension, retention policy,
   confidence thresholds, or Row-Level Security session mechanism.
7. Runtime application identities never receive schema-owner or migration
   privileges.
8. Migration logs and errors must not expose connection URLs or credentials.

## Initial migration boundary

The first migration is limited to the non-vector operational foundation:

- `workspaces`;
- `actors`;
- `workspace_members`;
- `operation_batches`;
- `file_operations`; and
- `audit_events`.

It establishes workspace-scoped keys, source-state preconditions, operation
intent and result fields, reconciliation state, and append-only audit storage
shape. Database privileges, Row-Level Security policies, document tables,
agent memory, taxonomy, vectors, and seed data require later approved
migrations.

The initial operation rows contain nullable document, document-version, and
file-instance identifiers, but their foreign keys are deferred until those
tables exist. The batch approval identifier is preserved now; its foreign key
to the future append-only review decision is also deferred. These columns do
not authorize canonical document or review claims before the referenced schema
is implemented.

## Alternatives considered

### Direct SQL files with a custom runner

Rejected for the initial implementation because DocWeave would have to build
and maintain version ordering, checksum, state tracking, offline rendering,
and failure reporting that Alembic already provides.

### Implicit schema creation from Object-Relational Mapper models

Rejected because it hides reviewed migration intent, weakens forward-recovery
evidence, and conflicts with CockroachDB guidance for schema changes.

### Flyway or Liquibase

Both are supported migration tools, but they add a separate Java runtime and
toolchain to a Python-first repository. Alembic keeps migration contracts close
to the shared Python core while still emitting reviewable SQL.

### Apply raw commands directly with `ccloud` or the SQL shell

Rejected as the normal product workflow because manual commands are difficult
to reproduce and audit. The SQL shell remains useful for controlled diagnostics
and independently approved verification.

## Consequences

### Benefits

- migration history is reproducible and reviewable;
- the dialect renders CockroachDB-specific SQL semantics;
- application and migration dependencies are explicitly pinned;
- offline checks cannot consume Request Units or storage; and
- later integration tests can exercise the same revisions on a controlled
  CockroachDB target.

### Costs and limitations

- four maintained Python packages enter the dependency surface;
- online migration tests are still required before the schema is claimed as
  deployed;
- non-transactional schema changes require forward-recovery discipline; and
- the first migration does not yet prove Row-Level Security, runtime roles,
  persistent document memory, or vector retrieval.

## Competition alignment

Alembic, SQLAlchemy, the CockroachDB dialect, and Psycopg are supporting
frameworks permitted by the competition rules. They do not count as one of the
minimum two eligible CockroachDB tools. Offline migration rendering is also
not evidence of meaningful CockroachDB integration.

The judged product must still demonstrate live CockroachDB persistent memory,
meaningful use of at least two eligible CockroachDB tools, deployment on AWS,
and visible memory behavior in the public demonstration. Those requirements
remain future work and are not claimed by this decision.

## Verification

Acceptance requires:

- successful offline upgrade and downgrade SQL rendering;
- exactly one ordered migration head;
- tests for required tables, workspace-scoped uniqueness, state constraints,
  foreign keys, digest fields, and reconciliation fields;
- a test proving online execution fails without an explicit database URL;
- the complete local quality gate; and
- a separately approved clean-database test against CockroachDB.

The clean-database acceptance test completed on 2026-07-24 using the exact
offline-rendered SQL for revision `0001_operational_foundation`. Online Alembic
execution through Psycopg remains pending. See
[`../../operations/cockroachdb-live-validation.md`](../../operations/cockroachdb-live-validation.md).

## References

- [CockroachDB schema design overview](https://www.cockroachlabs.com/docs/stable/schema-design-overview)
- [CockroachDB Alembic guide](https://www.cockroachlabs.com/docs/stable/alembic)
- [CockroachDB online schema changes](https://www.cockroachlabs.com/docs/stable/online-schema-changes)
- [ADR-0002: CockroachDB Physical Data Model](0002-cockroachdb-physical-data-model.md)
