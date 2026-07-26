# CockroachDB Operation Persistence Boundary

**Project:** DocWeave
**Status:** Local adapter and contract tests implemented; live runtime pending
**Date:** 2026-07-26

## 1. Purpose

This document records the application-facing boundary for durable operation
batches, execution intent, terminal results, and append-only audit evidence.
It implements the approved non-vector schema contract without changing that
schema or connecting to a live database.

The implementation is in:

- `src/docweave/persistence/contracts.py`;
- `src/docweave/persistence/mappers.py`;
- `src/docweave/persistence/orchestration.py`;
- `src/docweave/persistence/transactions.py`; and
- `src/docweave/persistence/operation_repository.py`.

## 2. Transaction policy

Each repository command executes through a fresh SQLAlchemy connection at
`SERIALIZABLE` isolation. Only SQLSTATE `40001` serialization failures are
retried. Retry attempts are bounded, use capped exponential backoff with full
jitter, and create a new transaction for every attempt.

Non-retryable database failures are returned as sanitized
`TransactionExecutionError` values without SQL text, parameters, connection
details, or driver messages. Application validation errors are not retried or
rewritten.

## 3. Atomic commands

### Create batch

The command inserts:

1. one `operation_batches` row;
2. all initial `file_operations` rows; and
3. the initial audit events.

The workspace-scoped batch idempotency key uses `ON CONFLICT DO NOTHING`.
An exact batch identity and preview digest returns an idempotent replay.
Different content under the same key fails closed and is never overwritten.

### Record execution intent

The command locks the workspace-scoped operation row, verifies that it is
approved, records the execution identity and bounded lease, increments the
attempt count, marks the batch as executing, and appends the matching audit
event in one transaction.

An exact repeated claim is an idempotent replay. A competing execution identity
or invalid lifecycle state fails closed.

### Record terminal result

The command locks the same operation, verifies its execution identity, records
the actual before-and-after relative paths and result evidence, clears the
lease, updates aggregate batch counts and completion state, and appends the
matching audit event in one transaction.

An exact terminal result is replay-safe and cannot increment aggregate counts
twice. A different result for an already terminal operation is a conflict that
requires explicit reconciliation.

## 4. Audit integrity

Audit append operations lock the owning workspace row before reading the prior
event. Each event digest is SHA-256 over:

- the prior event digest, when one exists; and
- a canonical JSON representation of the current minimized event.

The caller cannot provide predecessor identifiers or event digests. The
repository derives both. This is tamper-evident chaining, not an assertion that
the current database identity, privileges, retention, backup, or external
verification make the history tamper-proof.

## 5. Filesystem execution ordering

The local batch executor accepts an optional durable lifecycle recorder. When
configured, the order is:

1. create and persist the execution-intent event;
2. update the local in-progress ledger;
3. perform the approved filesystem mutation;
4. observe the destination evidence;
5. persist the terminal result and matching audit event;
6. update the local terminal ledger and audit trail.

If intent persistence fails, filesystem mutation does not start. If filesystem
mutation succeeds but result persistence fails, the in-progress intent remains
available for reconciliation and no terminal success is emitted locally.
Successful results require an observed destination byte size in addition to
the verified digest.

Replay, no-effect reconciliation, and aggregate batch-completion events also
pass through the durable recorder. The default recorder remains optional so
existing local-only tests and development do not silently imply database
persistence.

## 6. Workspace isolation

Every batch, operation, and audit lookup or mutation includes `workspace_id`.
Operation identity queries also include the owning batch and operation
identifiers. Audit events in one command must share the same workspace, and
batch events may reference only operations contained in that batch.

These query contracts provide defense in depth but do not replace the pending
runtime role and Row-Level Security design.

## 7. Current verification

Local tests cover:

- serializable isolation and rollback between retry attempts;
- bounded retry only for SQLSTATE `40001`;
- sanitized retry exhaustion and immediate non-retryable failure;
- atomic statement sequencing through the transaction port;
- exact batch, intent, and result replay;
- conflict behavior without overwrite;
- workspace-scoped lookups;
- missing identity and missing workspace failure;
- result-count updates without duplicate increments;
- reconciliation-required verification failures; and
- deterministic append-only digest chaining.
- intent-persistence failure prevents filesystem mutation;
- result-persistence failure preserves an in-progress reconciliation state;
- successful mutation follows the exact intent, filesystem, result order; and
- missing post-mutation destination evidence fails closed.

The tests use controlled local doubles and SQLite only for transaction rollback
semantics. They do not claim that the application adapter has executed against
CockroachDB.

## 8. Remaining work and non-claims

The following remain pending:

- runtime engine construction and approved secret delivery;
- runtime construction of the lifecycle recorder around the application
  workflow;
- loading durable terminal and in-progress execution state after restart;
- live Psycopg execution and contention tests against an approved target;
- runtime identities, authorization, and Row-Level Security;
- restart and lease-expiry reconciliation against CockroachDB;
- restore persistence and execution;
- production telemetry and Activity History queries; and
- any claim of persistent application memory or competition integration.

No cloud resource, database object, credential, migration, or paid operation
was created by this implementation.
