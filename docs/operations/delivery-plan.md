# Delivery Plan

**Project:** DocWeave
**Plan date:** 2026-07-23
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

**Current progress on 2026-07-24:**

- Local Python package and quality gates are implemented.
- GitHub Actions runs the Python quality gate on pull requests.
- Local discovery, fingerprinting, PDF signature inspection, intake, duplicate
  grouping, operation planning, approval validation, and single-operation
  execution primitives are implemented and tested.
- Bounded local batch execution, per-item result records, in-memory
  idempotency, interrupted-operation reconciliation, and append-only local audit
  event contracts are implemented and tested.
- CockroachDB persistence, durable Activity History, restore, AWS
  infrastructure, Bedrock invocation, and user interfaces remain not
  implemented.
- The preparatory notes
  [`local-core-status.md`](local-core-status.md) and
  [`local-batch-operation-design-note.md`](../architecture/local-batch-operation-design-note.md)
  define the recommended handoff into the next batch and audit implementation
  block.

### M2 - CockroachDB memory foundation

**Target window:** 2026-07-27 to 2026-07-30

**Objectives:**

- Implement reviewed migrations for the approved non-vector schema subset.
- Seed the approved taxonomy baseline in a reproducible way.
- Add migration tests for clean database creation and idempotent setup.
- Add transaction helper patterns for serializable retries.
- Add initial authorization and workspace-isolation test scaffolding.

**Exit criteria:**

- Migrations are reproducible against a controlled CockroachDB target.
- No vector dimension is invented before the embedding decision.
- No application role receives unrestricted schema administration.

### M3 - Real document analysis slice

**Target window:** 2026-07-31 to 2026-08-03

**Objectives:**

- Implement PDF discovery, fingerprinting, extraction, and checkpointing.
- Implement the Bedrock gateway using the approved primary model and bounded
  token settings.
- Persist classification proposals, evidence, confidence signals, and agent
  provenance in CockroachDB.
- Route malformed, encrypted, suspicious, or unsupported files to explicit
  limited states.

**Exit criteria:**

- A small synthetic dossier runs through real extraction and model analysis.
- Invalid model output cannot become canonical state.
- Token, latency, retry, and estimated cost are recorded per agent run.

### M4 - Human review and safe operations

**Target window:** 2026-08-04 to 2026-08-07

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

**Target window:** 2026-08-08 to 2026-08-11

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

**Target window:** 2026-08-12 to 2026-08-15

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

**Target window:** 2026-08-16 to 2026-08-18

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

## 5. Immediate next decisions

The next implementation work is blocked until these decisions are made:

1. repository package layout and local toolchain;
2. PDF extraction library and process isolation boundary;
3. embedding model, vector dimension, and distance metric;
4. Bedrock structured-output schema version `classification.v1`;
5. cloud compute, storage, queue, authentication, and network topology;
6. desktop-to-cloud identity and role matrix;
7. confidence scoring formula and review thresholds;
8. raw model-response and extracted-text retention policy.

## 6. Day-one implementation slice

The smallest useful implementation slice after this plan is:

1. add the repository scaffolding for the shared Python core and tests;
2. add deterministic formatting, linting, type checking, and unit-test commands;
3. add no cloud resources and no database schema yet;
4. verify that a clean local run can execute the empty quality gates.

This creates the quality runway required before the first application behavior
or migration is introduced.

## 7. Operating rules during delivery

- Every feature PR must state what is implemented and what remains planned.
- Cloud, database, dependency, and model-invocation changes require explicit
  approval before implementation.
- Every material claim must be backed by a reproducible command, test, trace,
  deployment output, screenshot, or demo step.
- If time compresses, cut scope by reducing document varieties or optional
  polish, not by faking memory, model intelligence, human approval, or audit
  behavior.
