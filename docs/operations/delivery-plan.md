# Delivery Plan

**Project:** DocWeave
**Plan date:** 2026-07-24
**Submission deadline:** 2026-08-18 17:00 EDT / 2026-08-18 23:00 CEST
**Implementation status:** In progress

## 1. Purpose

This plan turns the approved requirements and architecture into an execution
sequence for the remaining submission window. It is an operating plan, not a
claim that any application behavior, database migration, cloud workload, or
competition evidence already exists.

The plan prioritizes a truthful working product over broad unfinished scope.
Every milestone must preserve the project rules: genuine model behavior,
CockroachDB as meaningful persistent memory, Amazon Web Services deployment,
human approval before material file actions, append-only evidence, cost
control, and no private or credential data in the repository.

## 2. Delivery strategy

DocWeave should be built in vertical slices that can be demonstrated and
tested end to end. Architecture-only work stops as soon as the next
implementation decision is sufficiently bounded.

The critical path is:

1. close remaining implementation-blocking decisions;
2. implement local quality, security, and project scaffolding gates;
3. implement CockroachDB migrations and memory contracts;
4. implement the shared agentic core with real Bedrock structured output;
5. implement the desktop workflow against authorized local folders;
6. implement the cloud workflow with Infrastructure as Code;
7. create the synthetic corpus and evaluation evidence;
8. harden, document, record the demo, and submit.

## 3. Workstreams

| Workstream | Outcome | Release risk if late |
| --- | --- | --- |
| Product core | Shared domain services, workflow state, proposals, review, and operations | Desktop and cloud drift or rely on shortcuts |
| CockroachDB memory | Migrations, transactions, vectors, provenance, and audit | Competition memory claim cannot be demonstrated |
| Bedrock intelligence | Structured analysis, evidence, confidence signals, and measured cost | Classification becomes unverified or too expensive |
| Desktop application | PySide6 review and file-operation workflow | Judged device footage is incomplete |
| Cloud application | Deployed full workflow on AWS with real storage and compute | Submission lacks functional demo URL |
| Data and evaluation | Synthetic corpus, labels, evaluations, and demo dossiers | Quality claims lack evidence |
| Quality and security | CI gates, secret scanning, tests, threat model, and release checklist | Release is blocked by governance |
| Submission package | Public repository, license, README, demo video, and Devpost text | Eligible product is not submit-ready |

## 4. Milestones

### M0 - Baseline complete

**Target date:** 2026-07-23

**Exit criteria:**

- PR #5, PR #7, and PR #8 are merged into `main`.
- Environment baseline, physical data model, Bedrock model decision, and MVP
  taxonomy baseline are documented.
- No DocWeave cloud workload or database schema is claimed as deployed.

### M1 - Implementation decisions and scaffolding

**Target window:** 2026-07-24 to 2026-07-26

**Objectives:**

- Decide repository package layout for the shared core, desktop app, cloud app,
  infrastructure, tests, and synthetic data tooling.
- Decide the Python packaging, formatting, linting, type checking, and test
  stack.
- Decide PDF extraction library and isolation boundary.
- Decide the initial Bedrock structured-output contract boundary.
- Decide whether the first cloud slice uses AWS Lambda, Amazon ECS, or another
  approved compute service.

**Exit criteria:**

- Architecture Decision Records or approved implementation notes exist for the
  above choices.
- Local quality commands run without cloud access.
- The repository contains no runtime secret values.

**Current progress on 2026-07-26:**

- Local Python package and quality gates are implemented.
- GitHub Actions runs the Python quality gate on pull requests.
- Local discovery, fingerprinting, PDF signature inspection, intake, duplicate
  grouping, operation planning, approval validation, and single-operation
  execution primitives are implemented and tested.
- Bounded local batch execution, per-item result records, in-memory
  idempotency, interrupted-operation reconciliation, and append-only local audit
  event contracts are implemented and tested.
- The CockroachDB migration toolchain is pinned and the initial non-vector
  operational migration is tested through offline SQL rendering and an
  isolated live clean-database validation.
- The application does not connect to the validation schema. CockroachDB
  runtime persistence, durable Activity History, restore, AWS infrastructure,
  Bedrock invocation, and user interfaces remain not implemented.
- Typed persistence commands, a bounded serializable retry runner, and an
  atomic CockroachDB operation repository are implemented and tested locally.
  Explicit domain identity and operation mappings are also implemented. They
  are connected to the local batch executor through an optional fail-closed
  lifecycle recorder, but not to a live engine.
- The preparatory notes
  [`local-core-status.md`](local-core-status.md) and
  [`local-batch-operation-design-note.md`](../architecture/local-batch-operation-design-note.md)
  define the recommended handoff into the next batch and audit implementation
  block.
- The PDF extraction library and process boundary are decided in ADR-0004.
  Real page-level Qt PDF extraction now runs in a bounded disposable process
  without a new dependency or cloud access.

### M2 - CockroachDB memory foundation

**Target window:** 2026-07-27 to 2026-07-30

**Objectives:**

- Implement reviewed migrations for the approved non-vector schema subset.
- Seed the approved taxonomy baseline in a reproducible way.
- Add migration tests for clean database creation and idempotent setup.
- Add transaction helper patterns for serializable retries.
- Add initial authorization and workspace-isolation test scaffolding.

**Current progress on 2026-07-26:**

- ADR-0003 records the approved Alembic, SQLAlchemy, CockroachDB dialect, and
  Psycopg migration toolchain.
- Direct and transitive dependency versions are pinned.
- Revision `0001_operational_foundation` renders offline for workspace, actor,
  operation, and audit tables.
- Offline contract tests are implemented.
- The exact rendered revision was accepted and introspected in the isolated
  live `docweave_validation` database.
- Online Alembic driver execution, runtime roles, Row-Level Security,
  persistent application orchestration, and live contention tests remain
  pending.
- Serializable transaction retries, workspace-scoped repository statements,
  idempotent batch and operation writes, aggregate result updates, and
  hash-chained audit appends have local contract evidence.
- Intent-before-mutation, result-after-mutation, replay event, and
  reconciliation-state ordering have local orchestration evidence.
- Workspace-scoped terminal and execution-claim loading, active-lease
  rejection, terminal replay, and expired-lease reconciliation have local
  restart evidence. Live engine wiring, lease renewal, and fencing remain
  pending.

**Exit criteria:**

- Migrations are reproducible against a controlled CockroachDB target.
- No vector dimension is invented before the embedding decision.
- No application role receives unrestricted schema administration.

### M3 - Real document analysis slice

**Accelerated target window:** 2026-07-29 to 2026-08-01

**Objectives:**

- Implement PDF discovery, fingerprinting, extraction, and checkpointing.
- Implement the Bedrock gateway using the approved primary model and bounded
  token settings.
- Persist classification proposals, evidence, confidence signals, and agent
  provenance in CockroachDB.
- Route malformed, encrypted, suspicious, or unsupported files to explicit
  limited states.

**Current progress on 2026-07-26:**

- Real page-level extraction succeeds across the initial 30-PDF synthetic
  corpus through a disposable Qt PDF worker.
- Authorized-root, signature, source-digest, file, page, character, and timeout
  controls are implemented with explicit limited-processing states.
- Bedrock invocation, structured classification, CockroachDB extraction
  checkpoints, and model provenance remain pending.

**Exit criteria:**

- A small synthetic dossier runs through real extraction and model analysis.
- Invalid model output cannot become canonical state.
- Token, latency, retry, and estimated cost are recorded per agent run.

### M4 - Human review and safe operations

**Accelerated target window:** 2026-08-02 to 2026-08-05

**Objectives:**

- Implement review decisions, correction history, and controlled preference
  candidates.
- Implement filename and destination proposals.
- Implement copy, move, collision, resume, and restore planning.
- Implement execution only after recorded human approval and current-state
  revalidation.

**Exit criteria:**

- Duplicate execution requests are idempotent.
- Restore appends history and does not silently overwrite unrelated files.
- Activity History can attribute proposals, approvals, executions, errors, and
  restores.

### M5 - Desktop and cloud product surfaces

**Accelerated target window:** 2026-08-04 to 2026-08-08

**Objectives:**

- Build the PySide6 desktop workflow for workspace selection, scan, review,
  approval, operations, history, and restore.
- Build the cloud application using the same production core.
- Define and deploy AWS infrastructure through Infrastructure as Code after
  explicit approval.
- Keep cost alarms and shutdown instructions current.

**Exit criteria:**

- Desktop and cloud run the same core contracts.
- Cloud deployment is reproducible and within the approved cost ceiling.
- The judged workflow does not use canned or simulated intelligence.

### M6 - Evaluation, security, and scale evidence

**Accelerated target window:** 2026-08-09 to 2026-08-14

**Objectives:**

- Generate or finalize the approximately 300-PDF synthetic corpus.
- Run classification, relationship, confidence, prompt-injection, and recovery
  evaluations.
- Run the 10,000-file discovery and resume test.
- Complete threat model, security checks, dependency review, and release
  evidence.

**Exit criteria:**

- Critical quality, security, cost, accessibility, and competition gates are
  either green or have an approved exception.
- Known limitations are documented honestly.
- Claims in README, demo, and Devpost draft match observed behavior.

### M7 - Submission readiness

**Accelerated target window:** 2026-08-15 to 2026-08-18

**Objectives:**

- Freeze a release candidate.
- Make the repository public only after secrets, licenses, and private-data
  checks pass.
- Record a public video under three minutes showing the working application and
  CockroachDB memory layer.
- Submit the Devpost entry with exact CockroachDB and AWS service descriptions.

**Exit criteria:**

- Public repository, license, demo URL, video URL, setup instructions, and
  evidence matrix are complete.
- The deployed demo remains available through the judging period.
- The submission does not claim unimplemented features.

## 5. Status measurement

**Measurement date:** 2026-07-26

The current evidence-weighted Schedule Performance Indicator is **42%**. This
is a planning estimate, not a product-completion or production-readiness claim.
It is calculated from fixed milestone weights and conservative completion
estimates based only on merged or locally verified evidence:

| Milestone | Project weight | Evidence-complete estimate | Weighted contribution |
| --- | ---: | ---: | ---: |
| M0 - Baseline complete | 8% | 100% | 8.0% |
| M1 - Decisions and scaffolding | 14% | 95% | 13.3% |
| M2 - CockroachDB foundation | 18% | 70% | 12.6% |
| M3 - Real analysis slice | 18% | 15% | 2.7% |
| M4 - Review and safe operations | 15% | 10% | 1.5% |
| M5 - Product surfaces | 12% | 30% | 3.6% |
| M6 - Evaluation and hardening | 9% | 5% | 0.45% |
| M7 - Submission readiness | 6% | 0% | 0.0% |
| **Total** | **100%** |  | **42.15%, rounded to 42%** |

The project is **on plan overall and ahead on the database foundation**. M1 is
nearly complete now that the extraction decision is closed, with the Bedrock
contract and cloud-compute decisions still open.
The clean live migration validation and local transaction and repository
contracts from M2 were completed before the M2 window opens, while runtime
application persistence is not complete.
No schedule credit is taken for the unimplemented Bedrock analysis, complete
PySide6 workflow, cloud product, AWS deployment, evaluation corpus, or
submission package. Limited credit is taken for the locally verified read-only
desktop discovery, cancellation, session-state, selection, and guarded
embedded PDF preview workflow.

The principal schedule risk is now the vertical integration path: application
transactions and persistence, genuine Bedrock analysis, human review, safe
operations, and both product surfaces must be connected before the evaluation
and submission windows. The plan retains the original 2026-08-18 deadline and
does not assume additional time.

The accelerated sequence intentionally overlaps the first desktop surface with
the final CockroachDB and analysis work. The target is a manually testable
PySide6 shell by 2026-08-02, a representative desktop vertical slice by
2026-08-05, and at least ten days for owner testing, personalization, and
regression correction before submission. Parallel work does not relax quality,
security, cost, or truthful-integration gates.

## 6. Remaining implementation decisions

The repository package layout, local toolchain, and initial migration tooling
are decided. The next vertical slices still require the following approved
decisions before their respective implementation begins:

1. embedding model, vector dimension, and distance metric;
2. Bedrock structured-output schema version `classification.v1`;
3. cloud compute, storage, queue, authentication, and network topology;
4. desktop-to-cloud identity and role matrix;
5. confidence scoring formula and review thresholds;
6. raw model-response and extracted-text retention policy;
7. runtime CockroachDB identities and least-privilege authorization model.

## 7. Next implementation slice

The approved local CockroachDB persistence boundary currently has:

1. implemented application-facing repository and transaction contracts;
2. implemented serializable retry behavior with bounded, observable failures;
3. implemented atomic batch, operation-result, and append-only audit statement
   contracts without connecting the user interface or invoking Bedrock;
4. verified rollback, idempotency, workspace scoping, and fail-closed conflict
   behavior using controlled local tests;
5. keep runtime identity creation, production data, cloud resources, and paid
   operations behind separate explicit approval.

Durable state loading, restart reconciliation, and side-effect-free runtime
composition are implemented and locally verified at the adapter boundary. The
desktop now has a read-only progressive discovery workflow and validated
process-local session state. The next product increment is a reviewed local
project workflow leading toward the real analysis slice, while live engine
configuration and controlled restart integration proceed as a separately
approved track. Live CockroachDB execution, runtime identities, dependencies,
and paid operations remain explicit approval gates.

## 8. Operating rules during delivery

- Every feature PR must state what is implemented and what remains planned.
- Cloud, database, dependency, and model-invocation changes require explicit
  approval before implementation.
- Every material claim must be backed by a reproducible command, test, trace,
  deployment output, screenshot, or demo step.
- If time compresses, cut scope by reducing document varieties or optional
  polish, not by faking memory, model intelligence, human approval, or audit
  behavior.
