# CockroachDB Operation Persistence Boundary

**Project:** DocWeave
**Status:** Local adapter, restart loading, file-lineage memory, and contract
tests implemented; live runtime pending
**Date:** 2026-08-02

## 1. Purpose

This document records the application-facing boundary for durable operation
batches, execution intent, terminal results, and append-only audit evidence.
It implements the approved non-vector schema contract without changing that
schema or connecting to a live database.

The implementation is in:

- `src/docweave/persistence/contracts.py`;
- `src/docweave/persistence/mappers.py`;
- `src/docweave/persistence/orchestration.py`;
- `src/docweave/persistence/runtime.py`;
- `src/docweave/persistence/transactions.py`; and
- `src/docweave/persistence/operation_repository.py`; and
- `src/docweave/persistence/lineage_repository.py`.

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

### Record file lineage event

The command inserts one append-only `file_lineage_events` row after a planned
or observed operation state has been projected into original, previous, and
next directory and filename fields. The row uses a workspace-scoped
idempotency key, optional proposal and operation references, and SHA-256
evidence for the reviewed plan and observed file digests when available.

An exact repeated command is an idempotent replay. A different row under the
same idempotency key is rejected and never rewrites prior lineage history.

The `docweave-file-lineage` command exposes this boundary for controlled
runtime smoke tests. `record` writes one explicit lineage event, and `list`
loads bounded workspace-scoped history. The command does not run migrations,
invoke Amazon Bedrock, inspect documents, or mutate files.

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

## 6. Restart state loading

The restart-aware execution ledger loads at most one operation row for each
derived execution key. The read includes `workspace_id`, `operation_batch_id`,
and `file_operation_id`; an unknown key cannot trigger an arbitrary database
lookup. Loaded claim identity, approval identity, source digest, state, and
result evidence are validated before use.

The executor treats loaded state as follows:

1. a validated terminal result is returned as an idempotent replay without
   invoking the filesystem executor;
2. an executing claim whose lease is still active raises a bounded
   `ActiveExecutionLeaseError` before filesystem inspection or mutation;
3. an executing claim whose lease has expired enters the existing filesystem
   reconciliation path; and
4. absent or non-executing state continues through current-source validation
   and normal durable intent recording.

The first result and in-progress checks share the same scoped read. Invalid,
incomplete, or mismatched persisted content fails closed instead of being
coerced into a successful result.

Lease expiry permits reconciliation but is not a claim that long-running
execution fencing or lease renewal is implemented. Those controls remain
required before concurrent production workers are enabled.

The runtime composer binds one transaction runner and repository to both the
restart ledger and lifecycle recorder. It accepts an already constructed
SQLAlchemy engine and performs no connection, credential lookup, schema
mutation, or data access during composition. Engine configuration and runtime
secret delivery remain separate approved responsibilities.

## 7. Workspace isolation

Every batch, operation, and audit lookup or mutation includes `workspace_id`.
Operation identity queries also include the owning batch and operation
identifiers. Audit events in one command must share the same workspace, and
batch events may reference only operations contained in that batch.

These query contracts provide defense in depth but do not replace the pending
runtime role and Row-Level Security design.

## 8. Current verification

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
- missing post-mutation destination evidence fails closed;
- terminal durable results replay without invoking filesystem execution;
- active durable leases block a second process before mutation;
- expired durable leases reconcile verified postconditions;
- persisted identity or evidence mismatches fail closed;
- result and in-progress checks reuse one workspace-scoped read; and
- runtime composition performs no database input/output and rejects mismatched
  batch identities before use.

The tests use controlled local doubles and SQLite only for transaction rollback
semantics. They do not claim that the application adapter has executed against
CockroachDB.

## 9. Remaining work and non-claims

The following remain pending:

- approved engine configuration and runtime secret delivery;
- application bootstrap invocation of the composed runtime;
- live Psycopg execution and contention tests against an approved target;
- runtime identities, authorization, and Row-Level Security;
- restart, lease expiry, renewal, and fencing evidence against CockroachDB;
- cockpit wiring that persists visible rename and move lineage rows during
  approval and execution;
- restore persistence and execution;
- production telemetry and Activity History queries; and
- any claim of persistent application memory or competition integration.

No cloud resource, database object, credential, migration, or paid operation
was created by this implementation.
