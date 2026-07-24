# Local Batch Operation Design Note

**Project:** DocWeave
**Status:** Preparatory design note
**Date:** 2026-07-24
**Scope:** Local batch, audit, and operation result contracts

## 1. Purpose

This note prepares the next implementation block: safe local operation batches
with per-file outcomes, idempotency semantics, and append-only audit events.

It does not approve or implement CockroachDB migrations, AWS resources,
Bedrock calls, restore execution, or user-interface behavior.

## 2. Design goals

The batch layer must:

- preserve human approval before material file actions;
- execute only plans that are still ready immediately before mutation;
- isolate per-file failures instead of making a whole batch ambiguous;
- prevent duplicate effects when a request is retried;
- record enough evidence for CockroachDB persistence and Activity History;
- make crash recovery and partial success explicit;
- avoid silent overwrite, path traversal, symlink escape, or approval bypass;
- keep deterministic controls separate from future model-driven intelligence.

## 3. Proposed local concepts

### 3.1 Operation batch request

An operation batch request should describe:

- `batch_id`;
- workspace identifier placeholder;
- requested operation mode: copy or move;
- requested item list;
- creating user identifier;
- creation timestamp;
- idempotency key;
- policy version placeholder;
- maximum item count.

The initial local maximum should follow the approved MVP limit of 1,000 items.

### 3.2 Batch item

Each batch item should bind:

- item identifier;
- source root and relative path;
- destination root and relative path;
- expected operation type;
- observed source fingerprint and byte size at preview time;
- current plan;
- approval reference when approved;
- latest result when attempted;
- item state.

The observed source fingerprint is required so a source content change after
approval can block execution rather than silently organizing a different file.

### 3.3 Batch item states

Proposed item states:

| State | Meaning |
| --- | --- |
| `planned` | The item has a deterministic preview but no approval yet |
| `blocked` | The item cannot be approved or executed without user correction |
| `approved` | A human approval is bound to the exact plan and source identity |
| `executing` | Execution intent has been recorded before filesystem mutation |
| `succeeded` | Execution completed and verification passed |
| `failed` | Execution attempted and failed without verified success |
| `verification_failed` | Filesystem mutation may have occurred but verification failed |
| `skipped` | The item was explicitly removed or deferred from the batch |

Terminal states are `blocked`, `succeeded`, `failed`, `verification_failed`,
and `skipped`.

### 3.4 Batch aggregate states

Proposed batch states:

| State | Meaning |
| --- | --- |
| `draft` | Batch preview exists and may still be edited |
| `ready_for_approval` | All included executable items have stable plans |
| `approved` | Required human approval policy has been satisfied |
| `executing` | At least one item is executing or pending execution |
| `completed` | All included items reached terminal states |
| `completed_with_failures` | At least one included item failed or verification failed |
| `cancelled` | The batch was explicitly cancelled before execution |

Batch state is derived from item states where possible. It must not hide
partial outcomes.

## 4. Audit event contract

Local audit events should be append-only value objects before CockroachDB
persistence exists. They should include:

- event identifier;
- workspace identifier placeholder;
- batch identifier;
- optional batch item identifier;
- event type;
- actor type: user, system, or future agent;
- actor identifier;
- timestamp in UTC;
- correlation identifier;
- idempotency key where applicable;
- previous state;
- new state;
- reason;
- plan fingerprint;
- approval identifier where applicable;
- source and destination relative paths where applicable;
- minimized error class and message category.

Audit events must not contain document text, secrets, account identifiers, or
private data.

## 5. Proposed audit event types

Initial event types:

- `batch_created`;
- `item_planned`;
- `item_blocked`;
- `batch_submitted_for_approval`;
- `item_approved`;
- `batch_approved`;
- `item_execution_intent_recorded`;
- `item_execution_succeeded`;
- `item_execution_failed`;
- `item_verification_failed`;
- `item_skipped`;
- `batch_completed`;
- `batch_completed_with_failures`;
- `batch_cancelled`.

Restore events should be added in a separate restore design.

## 6. Idempotency semantics

The batch layer should define idempotency before CockroachDB implementation:

1. A client provides or receives one idempotency key per batch request.
2. Each batch item receives a deterministic execution key derived from the
   batch id, item id, operation, and approved plan fingerprint.
3. If an item is already `succeeded`, retry returns the prior result without
   re-executing the filesystem operation.
4. If an item is `executing` after process restart, reconciliation checks the
   filesystem state before retrying.
5. If the destination exists with the expected digest and the source state
   matches the expected post-condition, reconciliation may mark success only
   with an audit event explaining the recovery.
6. If state is ambiguous, the item becomes `verification_failed` or `failed`
   rather than successful.

The CockroachDB implementation should enforce idempotency with unique keys and
serializable transactions.

## 7. Pre-execution checks

Immediately before an item executes, the batch layer must re-check:

- the plan is still ready;
- the approval is valid and not expired;
- the source path exists and is not a symlink;
- the source fingerprint still matches the approved preview;
- the destination does not collide;
- missing destination directories are still within authorized roots;
- the item has not already reached a terminal successful state;
- the execution key has not already been consumed.

Failure of any check blocks only that item unless policy says to stop the
entire batch.

## 8. Failure policy

Default local policy should be:

- continue independent items after one item fails;
- never report batch success while any item is failed, verification-failed, or
  blocked;
- record item outcomes separately;
- stop only if a systemic safety failure is detected, such as policy mismatch,
  authorization failure, or batch-level approval invalidation.

## 9. Test plan for the next block

The next implementation should include tests for:

- empty batch rejection;
- maximum item count enforcement;
- mixed ready and blocked item preview;
- batch approval bound to exact item plans;
- expired approval blocks execution;
- source digest changed after approval blocks execution;
- destination collision isolates one item;
- one item success and one item failure produce partial batch outcome;
- duplicate execution request does not repeat a successful copy;
- interrupted `executing` item reconciles explicitly;
- audit event order is append-only;
- audit events do not include document bytes or private content;
- batch summary counts match item terminal states.

## 10. Handoff to GPT-5.6 Sol

Implementation of these contracts should be done with GPT-5.6 Sol because the
state machine, idempotency, and audit semantics will shape the CockroachDB
schema implementation and future user interface.

The first Sol task should start by reviewing this document, the local core
status note, `src/docweave/operations`, and the approved physical CockroachDB
schema before writing code.
