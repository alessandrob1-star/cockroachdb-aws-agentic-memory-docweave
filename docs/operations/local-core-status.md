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
- isolated Qt PDF text extraction with page boundaries and extractor
  provenance;
- authorized-root, source-digest, file, page, character, and timeout controls
  around each disposable extraction worker;
- explicit malformed, encrypted, unsupported-security, changed-source,
  text-free, and worker-failure extraction states;
- bounded `classification.v1` Converse request fields with document text
  explicitly separated as untrusted data;
- a closed forced-emission schema tied to the approved taxonomy baseline;
- typed non-authoritative classification proposals with exact page-evidence
  validation, abstention, alternatives, contradictions, and ordinal raw
  signals;
- a pinned boto3 Bedrock Runtime gateway with an injected Converse client,
  approved European profile, adaptive retries, explicit timeouts, strict stop
  reasons, sanitized errors, and observed token and latency provenance;
- optional token-cost estimation that requires externally supplied current
  prices rather than hardcoded rates;
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
- side-effect-free composition of one coherent transaction runner, repository,
  restart ledger, lifecycle recorder, and execution hook set;
- a read-only PySide6 desktop shell for authorized-folder selection,
  non-blocking phase progress, cooperative cancellation, deterministic intake
  metrics, validated in-memory workspace state, multiple selection, status, and
  document table presentation;
- guarded user-initiated preview of one ready PDF inside DocWeave after current
  path, root, symlink, file-type, and signature checks;
- read-only multipage PDF scrolling with bounded zoom and fit-to-width controls
  through the already pinned Qt PDF modules;
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
`codex/bedrock-live-evaluation` reported:

- 401 tests passed;
- 93 percent total package coverage;
- Ruff format check passed;
- Ruff lint check passed;
- MyPy strict check passed;
- offline migration upgrade and downgrade rendering passed;
- one ordered Alembic migration head was verified; and
- online migration execution was verified to fail closed when no database URL
  is explicitly supplied.

Native Qt desktop tests can abort on some local and hosted headless runners
when the real Qt PDF widget is exercised directly. The cockpit tests therefore
verify scan, table, metric, and selected-document preview wiring while avoiding
the native PDF load path in Continuous Integration. The most recent complete
local gate passed with all 431 tests, formatting, linting, and strict type
checking. GitHub Actions uses the supported Python 3.12 test target.

The check command is:

```powershell
.\scripts\check.ps1
```

## 4. Important limits and non-claims

DocWeave does not yet implement or claim:

- a live application transaction against CockroachDB or a production schema;
- persistent operational, semantic, episodic, preference, or audit memory;
- AWS infrastructure or deployed DocWeave workloads;
- Amazon Bedrock invocation inside the product bootstrap;
- a complete PySide6 desktop workflow or any cloud user interface;
- corpus-level model quality, naming, calibrated confidence, or relationship
  analysis;
- live durable idempotency in the running application;
- restore planning or restore execution;
- durable Activity History;
- release security scanning beyond the current Python quality gate.

The batch executor remains a local primitive, but its optional lifecycle
recorder and restart-aware ledger now connect execution ordering and state
loading to the durable adapter contract. The application runtime boundary can
now compose a CockroachDB SQLAlchemy engine and approved Bedrock gateway from
explicit runtime configuration without opening either service. A runtime
preflight command can now validate configuration without external I/O, or open
the configured CockroachDB target on request and verify the required
classification schema tables. No live application invocation has loaded or
written a CockroachDB row through this boundary, so the project does not yet
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
| No live application bootstrap execution | The composed restart path is not yet a live application integration | Run the configured runtime against the approved validation target |
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

The next CockroachDB application step is a controlled live integration test
using the configured classification runtime boundary. Live execution remains
behind explicit runtime environment values and a current validation target.

To preserve time for manual testing and personalization, the first desktop
surface is now scheduled in parallel with the remaining live-integration work
instead of waiting for the whole CockroachDB milestone to finish.

The desktop cockpit now presents phase progress, cooperative cancellation,
process-local workspace state, discovered PDF preview, guarded external-link
delegation, sanitized fail-closed CockroachDB/Bedrock runtime preflight
readiness, and a background Analyze dispatch for the selected ready PDF. The
startup preflight does not open CockroachDB or invoke Bedrock; it only exposes
configuration and client-construction readiness. Accepted proposals update the
visible document row to `REVIEW`, show the proposed class, and report Bedrock
token and persistence dispositions as non-authoritative review evidence. Its
next increment must run that workflow against the approved live validation
target without inventing CockroachDB persistence or user authorization.

AWS infrastructure should begin after the CockroachDB migration strategy and
first local vertical slice are ready, so cloud work deploys real product
behavior rather than scaffolding without evidence.
