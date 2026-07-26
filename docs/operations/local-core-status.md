# Local Core Status

**Project:** DocWeave
**Status date:** 2026-07-26
**Scope:** Local deterministic core and database adapter contracts

## 1. Purpose

This note records what the local DocWeave core currently implements, what it
does not yet implement, and what must be true before the project starts the
next batch, audit, CockroachDB, AWS, or user-interface work.

It is an evidence index, not a release-readiness claim.

The initial CockroachDB operational migration is authored, validated offline,
and accepted by an isolated live validation database. A local CockroachDB
adapter now targets that shape, but no application code connects to the live
target.

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
- typed database-ready batch, intent, result, and audit command contracts;
- explicit domain-to-database identity, root-reference, batch, intent, result,
  and audit mappings;
- optional durable lifecycle recording around filesystem execution, with
  intent-before-mutation and result-after-mutation ordering;
- workspace-scoped loading of durable terminal results and execution claims
  through the repository boundary;
- restart-aware terminal replay, active-lease rejection, and expired-lease
  reconciliation without duplicate filesystem execution;
- fail-closed behavior that prevents mutation when intent persistence fails and
  preserves an in-progress state when result persistence fails;
- bounded serializable transaction execution with SQLSTATE `40001` retry,
  rollback, capped backoff, and sanitized failures;
- atomic CockroachDB statement contracts for batch creation, execution claim,
  terminal result, aggregate counts, and audit append;
- exact idempotent replay without silent overwrite;
- workspace-scoped queries and tamper-evident audit digest chaining;
- local and GitHub Actions quality gates for formatting, linting, strict type
  checking, tests, and coverage.

## 3. Current local quality evidence

The latest verified local quality gate on
`codex/durable-restart-state-loading` reported:

- 221 tests passed;
- 94 percent total package coverage;
- Ruff format check passed;
- Ruff lint check passed;
- MyPy strict check passed;
- offline migration upgrade and downgrade rendering passed;
- one ordered Alembic migration head was verified; and
- online migration execution was verified to fail closed when no database URL
  is explicitly supplied.

The 144-test migration baseline passed GitHub Actions on pull request 22 and
after its merge to `main`. The Node.js 24 workflow update passed on pull request
23 and after its merge to `main`. The 221-test restart-state increment is local
evidence until a separately authorized pull request passes GitHub Actions.

The check command is:

```powershell
.\scripts\check.ps1
```

## 4. Important limits and non-claims

DocWeave does not yet implement or claim:

- an application connection to CockroachDB or a production schema;
- persistent operational, semantic, episodic, preference, or audit memory;
- AWS infrastructure or deployed DocWeave workloads;
- Amazon Bedrock invocation inside the product;
- PySide6 desktop or cloud user interface;
- PDF text extraction;
- model-driven classification, naming, confidence, or relationship analysis;
- live durable idempotency in the running application;
- restore planning or restore execution;
- durable Activity History;
- release security scanning beyond the current Python quality gate.

The batch executor remains a local primitive, but its optional lifecycle
recorder and restart-aware ledger now connect execution ordering and state
loading to the durable adapter contract. No live runtime engine constructs
these components or loads a CockroachDB row. The project therefore does not
claim persistent application behavior.

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
| Runtime components are not constructed against a live engine | The tested restart path is not yet an application integration | Add approved engine, recorder, ledger, and bootstrap wiring |
| Audit adapter has no live runtime evidence | Activity History cannot yet survive restart | Run approved integration and restart tests against CockroachDB |
| Lease renewal and execution fencing are not implemented | A worker that outlives its lease is not yet safe for concurrent production execution | Add renewal or fencing before enabling multiple workers |
| No restore contract | Move and copy outcomes are not yet reversible through tested restore semantics | Add restore planning after batch result and audit semantics |
| No workspace/user authorization model | Approval uses user identifiers but no role policy yet | Add authorization contract before user interface or cloud execution |

## 6. Completed live validation boundary

The 2026-07-24 controlled validation:

- verified the Basic-plan usage and no-paid-usage boundary;
- created the isolated `docweave_validation` target;
- applied the exact offline-rendered initial revision;
- introspected the revision, six tables, critical constraints, and indexes;
- proved two invalid states were rejected without persisted rows; and
- preserved sanitized evidence without exposing a connection URL or secret.

It did not validate the online Alembic and Psycopg connection path, application
persistence, cross-workspace runtime authorization, live serialization
contention, or recovery.

## 7. Readiness for CockroachDB, AWS, and UI

The next CockroachDB application step is approved runtime engine construction
and a controlled restart integration test using the implemented
workspace-scoped loader. Live execution remains behind separate approval and a
current cost preflight.

The PySide6 desktop preview interface is no longer blocked by a missing batch
model. Its first implementation should still wait for an approved surface
contract so it does not invent persistence or authorization behavior.

AWS infrastructure should begin after the CockroachDB migration strategy and
first local vertical slice are ready, so cloud work deploys real product
behavior rather than scaffolding without evidence.
