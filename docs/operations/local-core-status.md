# Local Core Status

**Project:** DocWeave
**Status date:** 2026-07-24
**Scope:** Local deterministic core only

## 1. Purpose

This note records what the local DocWeave core currently implements, what it
does not yet implement, and what must be true before the project starts the
next batch, audit, CockroachDB, AWS, or user-interface work.

It is an evidence index, not a release-readiness claim.

The initial CockroachDB operational migration is now authored and validated
offline. It is not part of the implemented local runtime core and has not been
applied to a database.

## 2. Current implemented local core

The repository currently contains a tested Python package with:

- deterministic local filesystem discovery for authorized roots;
- recursive PDF candidate discovery with bounded file count;
- unsupported, unreadable, blocked, and candidate discovery states;
- symlink blocking and cross-platform unreadable-path hardening;
- streaming SHA-256 content fingerprinting;
- PDF signature inspection based on the `%PDF-` header;
- deterministic intake records;
- duplicate grouping for ready intake records with identical fingerprints;
- safe copy and move operation planning;
- human approval contracts bound to exact operation plan fingerprints;
- single-operation local copy and move execution for already-ready and
  already-approved plans;
- bounded local operation batches with a maximum of 1,000 items;
- per-item source fingerprint and byte-size approval preconditions;
- independent per-item outcomes and truthful partial-batch summaries;
- append-only in-memory audit event contracts with minimized diagnostics;
- an in-memory execution-intent and result ledger for local idempotency tests;
- duplicate-request replay without repeated successful filesystem effects;
- explicit interrupted-operation reconciliation before retry;
- local and GitHub Actions quality gates for formatting, linting, strict type
  checking, tests, and coverage.

## 3. Current local quality evidence

The latest verified local quality gate on
`codex/cockroachdb-migration-foundation` reported:

- 144 tests passed;
- 99 percent total package coverage;
- Ruff format check passed;
- Ruff lint check passed;
- MyPy strict check passed;
- offline migration upgrade and downgrade rendering passed;
- one ordered Alembic migration head was verified; and
- online migration execution was verified to fail closed when no database URL
  is explicitly supplied.

The previous 132-test local-core baseline also passed GitHub Actions on pull
request 21 and on its merge to `main`. GitHub Actions evidence for the current
migration branch remains pending until an explicitly authorized pull request
is published.

The check command is:

```powershell
.\scripts\check.ps1
```

## 4. Important limits and non-claims

DocWeave does not yet implement or claim:

- deployed CockroachDB application tables or a successful live migration;
- persistent operational, semantic, episodic, preference, or audit memory;
- AWS infrastructure or deployed DocWeave workloads;
- Amazon Bedrock invocation inside the product;
- PySide6 desktop or cloud user interface;
- PDF text extraction;
- model-driven classification, naming, confidence, or relationship analysis;
- persistent idempotency;
- restore planning or restore execution;
- durable Activity History;
- release security scanning beyond the current Python quality gate.

The batch executor is a local primitive. It records intent before mutation in
an in-memory ledger and emits append-only local events, but a process loss also
loses those records. It is not yet a complete product workflow because it does
not use CockroachDB to make intent, audit, idempotency, or workspace
authorization durable and transactional.

## 5. Contract review findings

The current operations layer is intentionally split into three deterministic
steps:

1. `planning.py` previews copy or move feasibility without mutation.
2. `approval.py` binds a human approval to the exact visible plan.
3. `execution.py` executes one approved operation and verifies the result.

This separation is sound for the next batch design, but the following gaps
must be closed before production-grade batch execution:

| Gap | Impact | Required next control |
| --- | --- | --- |
| No persistent idempotency key registry | Process loss removes the local replay registry | Enforce workspace-scoped unique keys in CockroachDB |
| Audit events are local and in-memory | Activity History cannot survive restart or prove database ordering | Persist append-only audit events with transaction and integrity evidence |
| Pre-mutation intent is not durable | A process or machine failure can still leave an ambiguous external outcome | Persist intent before mutation and claim it with a bounded lease |
| No restore contract | Move and copy outcomes are not yet reversible through tested restore semantics | Add restore planning after batch result and audit semantics |
| No workspace/user authorization model | Approval uses user identifiers but no role policy yet | Add authorization contract before user interface or cloud execution |

## 6. Recommended next implementation block

The next smallest safe database block is controlled live validation of the
offline operational migration. It should:

- verify current Basic-plan usage and the no-paid-usage boundary;
- use a controlled clean target and least-privilege migration identity;
- apply and introspect the exact approved revision;
- test invalid states and workspace-scoped constraints; and
- preserve sanitized evidence without exposing the connection URL.

Live validation requires a new cost and target preflight plus explicit user
approval.

## 7. Readiness for CockroachDB, AWS, and UI

CockroachDB implementation can now begin after separate approval because the
local batch and audit contracts define the persistent transaction and audit
shape.

The PySide6 desktop preview interface is no longer blocked by a missing batch
model. Its first implementation should still wait for an approved surface
contract so it does not invent persistence or authorization behavior.

AWS infrastructure should begin after the CockroachDB migration strategy and
first local vertical slice are ready, so cloud work deploys real product
behavior rather than scaffolding without evidence.
