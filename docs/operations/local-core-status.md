# Local Core Status

**Project:** DocWeave
**Status date:** 2026-07-24
**Scope:** Local deterministic core only

## 1. Purpose

This note records what the local DocWeave core currently implements, what it
does not yet implement, and what must be true before the project starts the
next batch, audit, CockroachDB, AWS, or user-interface work.

It is an evidence index, not a release-readiness claim.

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
- local and GitHub Actions quality gates for formatting, linting, strict type
  checking, tests, and coverage.

## 3. Current local quality evidence

The latest verified local quality gate on `main` after PR #19 reported:

- 77 tests passed;
- 100 percent package coverage;
- Ruff format check passed;
- Ruff lint check passed;
- MyPy strict check passed;
- GitHub Actions `Python quality (3.12)` passed on PR #19.

The check command is:

```powershell
.\scripts\check.ps1
```

## 4. Important limits and non-claims

DocWeave does not yet implement or claim:

- CockroachDB migrations or application tables;
- persistent operational, semantic, episodic, preference, or audit memory;
- AWS infrastructure or deployed DocWeave workloads;
- Amazon Bedrock invocation inside the product;
- PySide6 desktop or cloud user interface;
- PDF text extraction;
- model-driven classification, naming, confidence, or relationship analysis;
- operation batch execution;
- persistent idempotency;
- restore planning or restore execution;
- Activity History;
- release security scanning beyond the current Python quality gate.

The single-operation executor is a local primitive. It is not yet a complete
product workflow because it does not persist intent before mutation, does not
record append-only audit events, and does not yet use CockroachDB to enforce
idempotency or workspace authorization.

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
| No persistent idempotency key registry | Repeating the same request across process restarts could execute again | Batch item state and execution idempotency must be persisted in CockroachDB |
| No append-only audit event | The system cannot yet prove who approved, executed, or observed a result | Add local audit event contracts before CockroachDB persistence |
| No durable pre-mutation intent record | A crash after filesystem mutation but before state recording would be ambiguous | Persist intent before mutation in the batch workflow |
| Approval is bound to plan paths and status, not persisted source identity | A source content change after approval must be detected by the future batch contract | Include observed source fingerprint and metadata in batch item preconditions |
| No restore contract | Move and copy outcomes are not yet reversible through tested restore semantics | Add restore planning after batch result and audit semantics |
| No workspace/user authorization model | Approval uses user identifiers but no role policy yet | Add authorization contract before user interface or cloud execution |

## 6. Recommended next implementation block

The next implementation block should define the local batch, audit, and result
contracts before adding CockroachDB persistence. It should produce:

- batch request and batch plan contracts;
- batch item states;
- per-item result records;
- append-only audit event contracts;
- idempotency key semantics;
- explicit crash and retry behavior;
- tests for partial success, duplicate execution request, stale source state,
  collision isolation, and failed verification.

This block is architecture-sensitive and should be performed with GPT-5.6 Sol
before implementation.

## 7. Readiness for CockroachDB, AWS, and UI

CockroachDB should begin after the local batch and audit contracts are
approved, because those contracts define the persistent transaction and audit
shape.

The PySide6 desktop interface can begin after the batch preview model exists,
because the first useful UI needs to display batch rows, per-file statuses,
approval state, and explanations of blocked operations.

AWS infrastructure should begin after the CockroachDB migration strategy and
first local vertical slice are ready, so cloud work deploys real product
behavior rather than scaffolding without evidence.
