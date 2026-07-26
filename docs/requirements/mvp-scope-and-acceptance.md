# Minimum Viable Product Scope and Acceptance

**Version:** 0.1
**Baseline approved:** 2026-07-21
**Implementation status:** In progress; no complete MVP workflow claimed

## 1. Definition of Minimum Viable Product

For DocWeave, Minimum Viable Product does not mean a disposable prototype. It
means the smallest complete, secure, testable, and competition-ready product
that proves the real workflow with persistent agentic memory.

The MVP must be honest enough for judges to use, safe enough to operate on
controlled files, and structured so later scale and document types do not
require replacing the core design.

## 2. MVP outcome

A legal, procurement, or compliance team can submit a PDF collection, let real
agents analyze and organize it, focus human review on uncertainty, execute
approved copy or move operations, inspect a complete history, and safely restore
one document or a batch. The same core workflow runs through the desktop and
cloud product surfaces and persists memory in CockroachDB.

## 3. Required MVP capabilities

### 3.1 Product surfaces

- Complete PySide6 desktop application for authorized Windows folders.
- Complete cloud application for a real cloud-backed workspace.
- Shared production backend, agents, memory semantics, review controls, and
  audit history.
- Clear disclosure of storage-medium differences without reduced intelligence.

### 3.2 Supported input

- PDF is the required MVP document format.
- Recursive source discovery is required.
- Text-bearing PDFs are the primary evaluated path.
- Image-only, malformed, encrypted, or unsupported PDFs must be detected and
  routed to an explicit limited or manual-review state.
- Optical Character Recognition may be included only after architecture, cost,
  and evaluation approval; it is not silently assumed.

### 3.3 Intelligence and memory

- Real content extraction and agent-driven classification.
- Multiple bounded agent responsibilities with observable handoffs rather than
  one opaque prompt presented as a multi-agent system.
- Proposed filename and destination with explanation and evidence.
- Related-document proposals with typed relationship and confidence.
- Raw and calibrated confidence with reproducible provenance.
- Persistent operational, semantic, episodic, and preference memory in
  CockroachDB.
- Controlled use of corrections in future recommendations.
- Visible resume behavior backed by memory, not a local-only shortcut.
- A bounded memory and database stewardship agent that retrieves context,
  checks provenance and consistency, and reports anomalies without replacing
  deterministic database integrity or receiving unrestricted administration.
- Relational persistence for important extracted and approved project,
  supplier, tender, contract, purchase-order, invoice, and payment data.
- Separation between uncertain extracted candidates and reviewed canonical
  facts, with confidence, evidence, provenance, and supersession history.

### 3.4 Human review

- Sortable and filterable review table.
- PDF preview and side-by-side before-and-after proposal.
- Low-confidence queue and high-confidence quality sampling.
- Single and multi-select approve, reject, edit, and defer actions.
- Operator, Reviewer or Project Manager, and Administrator permissions.
- Optional separate-reviewer policy for high-impact batches.

### 3.5 File operations

- Copy mode preserving and tracking the original.
- Move mode preserving prior identity and location in history.
- Preview, collision checks, authorization, execution, and verification.
- Checkpointed batches of at most 1,000 documents.
- Safe resume without duplicate effects.
- Individual, selection, and batch restore.
- Recoverable trash behavior for reverting generated copies where supported.
- Append-only Activity History.

### 3.6 Capacity and evidence

- Approximately 300 representative PDFs in the principal demonstration and
  evaluation corpus.
- Up to 5,000 actively managed documents per MVP project.
- A 10,000-file discovery, indexing, restart, and resume test.
- Per-file and per-batch status, timing, failure, and cost evidence.

## 4. Required demonstration journey

The judged demonstration must show a continuous real flow:

1. Open a prepared workspace containing a representative PDF collection.
2. Show CockroachDB remembering prior work or resume an interrupted batch.
3. Scan and analyze new documents with real agents.
4. Sort the review queue by lowest calibrated confidence.
5. Open a low-confidence PDF and inspect explanation and evidence.
6. Correct or approve its classification and proposed name.
7. Show a high-confidence quality sample.
8. Preview and approve a bounded copy or move batch.
9. Execute and verify the operations.
10. Inspect Activity History and responsibility information.
11. Restore one selected document.
12. Show the appended restore event and persistent CockroachDB memory.
13. Navigate at least one meaningful related-document link.

The final video may use a smaller subset to remain below the competition time
limit, but every claimed capability must be available in the judged product.

## 5. Acceptance scenarios

### AC-001 — repeated scan does not repeat completed work

**Given** a source containing completed, interrupted, and new files,
**when** the user scans it again,
**then** completed unchanged files remain complete, interrupted work is
resumable, and only new or explicitly changed files enter new analysis.

### AC-002 — interruption resumes safely

**Given** a 1,000-document batch interrupted after a persisted checkpoint,
**when** the application restarts and the user resumes,
**then** verified completed operations are not repeated and every document ends
with one unambiguous status.

### AC-003 — confidence review is actionable

**Given** completed classification results,
**when** a reviewer sorts by calibrated confidence ascending,
**then** the lowest-confidence items appear first and each item exposes PDF
preview, explanation, evidence, proposal, and correction controls.

### AC-004 — high-confidence sampling detects risk

**Given** a batch with high-confidence results,
**when** a reviewer requests a quality sample,
**then** the sample is reproducible, its review outcome is recorded, and an
unacceptable observed error rate blocks or escalates approval.

### AC-005 — move preserves identity and history

**Given** an approved move with no conflict,
**when** execution completes,
**then** the file exists at the verified destination, its stable logical
identity remains unchanged, and prior and resulting state are recorded.

### AC-006 — copy distinguishes physical instances

**Given** an approved copy,
**when** execution completes,
**then** the original remains unchanged, the created copy has a distinct file
instance identity, and both refer to the correct logical document.

### AC-007 — collision never overwrites silently

**Given** an unrelated destination file with the proposed name,
**when** a copy, move, or restore is prepared,
**then** execution does not overwrite the file and the conflict is presented
for an explicit decision.

### AC-008 — individual move restore

**Given** one moved document within a completed batch,
**when** an authorized reviewer restores its original state,
**then** only that file is returned, a missing authorized source directory is
recreated if necessary, and the restore is appended to history.

### AC-009 — copy restore is recoverable

**Given** a DocWeave-created copy and an intact original,
**when** an authorized reviewer reverts the copy operation,
**then** the original remains untouched and the copy is moved to recoverable
trash where the platform supports it.

### AC-010 — batch restore reports partial outcomes

**Given** a batch containing both safe and conflicted restore candidates,
**when** a reviewer executes the approved restore plan,
**then** every item reports its actual result and conflicted files are never
misreported as restored.

### AC-011 — project-manager accountability

**Given** work performed by multiple users and agents,
**when** a project manager filters Activity History,
**then** the manager can attribute proposals, approvals, executions,
corrections, failures, and restores without direct database access.

### AC-012 — persistent agentic memory is visible

**Given** a prior user correction or interrupted agent workflow,
**when** a later authorized workflow retrieves relevant memory,
**then** the product shows what memory was used, its provenance, and how it
affected the result or resume point.

### AC-013 — desktop and cloud use the real core

**Given** equivalent controlled inputs in desktop and cloud workspaces,
**when** the principal analysis and review flow runs,
**then** both surfaces invoke the same production logic and persistent memory
semantics, with no canned cloud result or local-only intelligent shortcut.

### AC-014 — scale discovery remains safe

**Given** a 10,000-file supported test source,
**when** discovery, restart, and resume are exercised,
**then** the interface remains responsive, counts reconcile, checkpoints
persist, and no file is lost, duplicated, or silently reprocessed.

## 6. Evaluation corpus requirements

The approximately 300-document corpus shall be authorized, synthetic, or safely
licensed and shall include:

- invoices;
- purchase proposals and quotations;
- contracts;
- tender and procurement documents;
- appendices and supporting evidence;
- duplicates and near-duplicates;
- multiple versions of a document;
- ambiguous documents;
- uninformative filenames;
- sparse-text PDFs;
- unsupported, malformed, or encrypted negative cases;
- deliberate naming and destination collisions;
- related-document groups with known expected links.

The corpus shall have a reviewed reference label set for classification,
relationships, naming attributes, and expected review conditions. Generated
scale fixtures may test throughput, but they do not replace the curated corpus
for intelligence evaluation.

## 7. Mandatory failure and recovery tests

- Application termination during scan, analysis, copy, move, and restore.
- Temporary loss of AWS or CockroachDB connectivity.
- Duplicate submission of the same execution request.
- External file change after analysis but before execution.
- Source or destination permission loss.
- Missing source folder during restore.
- Existing destination filename collision.
- Copy succeeds but later persistence or verification step fails.
- Partial batch failure and selective retry.
- Simultaneous actions on the same document.
- Expired user authorization during a long workflow.
- Cost or rate limit reached during analysis.

## 8. Explicitly outside the MVP

These capabilities are not required for the first release unless separately
approved:

- non-PDF office formats;
- native mobile applications;
- email, enterprise content-management, or shared-drive connectors;
- fully autonomous copy, move, delete, or external sharing;
- unrestricted user-authored agent tools;
- automatic schema administration by a language model;
- handwritten-document recognition;
- legal conclusions or compliance determinations;
- unlimited file counts or unbounded batches;
- silent destructive deletion;
- production processing of confidential third-party company archives during
  development or demonstration.

## 9. MVP release blockers

The MVP is not complete if any of the following is true:

- a core workflow uses mocked or canned intelligence in the judged product;
- CockroachDB memory is not meaningful, persistent, and visibly demonstrated;
- the cloud product omits a claimed core workflow;
- an operation can bypass authorization, preview, or current-state validation;
- duplicate execution can create duplicate effects;
- a restore can silently overwrite an unrelated file;
- confidence lacks provenance or evaluation;
- Activity History cannot attribute material actions;
- the required capacity and recovery tests lack evidence;
- critical quality, security, accessibility, cost, or competition gates fail.

## 10. Deferred decisions before implementation

Architecture work must resolve and obtain approval for:

1. confidence-calibration method;
2. embedding model, vector dimension, and distance metric;
3. local-versus-cloud extraction and privacy boundary;
4. cloud storage and compute topology;
5. desktop-to-cloud authentication and authorization;
6. web technology and cross-surface design approach;
7. exact performance reference environment;
8. cost model and protective limits; and
9. final role and approval-policy matrix.

The primary Large Language Model is resolved by
[`ADR-0001`](../architecture/decisions/0001-amazon-bedrock-primary-model.md).
The database schema, indexes, transaction strategy, and operation
reconciliation protocol are resolved by
[`ADR-0002`](../architecture/decisions/0002-cockroachdb-physical-data-model.md).
Their implementations remain not started.
