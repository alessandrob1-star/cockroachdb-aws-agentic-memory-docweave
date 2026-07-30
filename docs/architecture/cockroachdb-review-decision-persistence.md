# CockroachDB Review Decision Persistence Boundary

**Status:** Implemented adapter, migration, and command-line runtime wiring;
desktop button wiring pending
**Revision:** `0003_review_decision_memory`

## Purpose

This boundary persists one final human approve or reject decision for a
non-authoritative proposal without executing any filesystem operation.

One serializable transaction:

1. locks the workspace-scoped proposal row;
2. inserts one immutable `review_decisions` row;
3. binds the row to the exact proposal SHA-256 fingerprint and optional
   operation-plan SHA-256 fingerprint reviewed by the human; and
4. updates the owning proposal status to `approved` or `rejected`.

An exact replay returns `idempotent_replay`. A reused proposal decision with
different reviewer, action, fingerprint, reason, timestamp, or operation-plan
binding fails closed.

The `docweave-review-proposal` command is the first runtime boundary for this
capability. It accepts the retained proposal fingerprint, reviewer identity from
runtime configuration, and an explicit approve or reject action. It creates a
durable command with bound SQL parameters through the repository instead of
embedding document names, PDF content, or fingerprints into SQL text.

## Integrity boundaries

- Every proposal lookup is workspace scoped and locked before mutation.
- Every model-derived or document-derived value is passed as a bound SQL
  parameter.
- Fingerprints are validated as lowercase SHA-256 hexadecimal digests and stored
  as 32-byte values.
- Reject decisions require a reason.
- Only `approve` and `reject` are accepted by the current durable repository.
  `request_changes` and `escalate` remain schema-reserved future actions until
  their product workflow is implemented.
- A review decision never performs copy, move, rename, delete, restore, or
  external sharing.

## Current limitations

- The cockpit still records review decisions locally and is not wired to this
  durable repository.
- The migration is validated offline by the local quality gate; isolated live
  validation remains pending.
- Canonical document classification promotion remains pending.
- No audit-event bridge for review decisions is implemented yet.
