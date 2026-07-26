# Document Processing Pipeline

**Status:** Approved architecture baseline
**Approved:** 2026-07-22
**Implementation status:** In progress

## 1. Purpose

This document defines the shared production pipeline used by the PySide6
desktop application and the complete cloud application. It translates the
approved product workflow into bounded agent responsibilities, deterministic
controls, CockroachDB checkpoints, and human decisions.

The architecture uses the versioned primary model through Amazon Bedrock as recorded in
[`ADR-0001`](decisions/0001-amazon-bedrock-primary-model.md). It does not define
the physical CockroachDB schema or create any Amazon Web Services resources.

## 2. Design principles

1. A document is identified before it is analyzed.
2. Document content is untrusted data, never agent instruction.
3. Every expensive or long-running stage is resumable from CockroachDB.
4. Model output is a proposal until deterministic validation succeeds.
5. Classification, naming, destination, and relationships are separate
   decisions with separate confidence signals.
6. No file mutation occurs before a visible plan and recorded human approval.
7. Every retry is idempotent: repeating a request cannot create a second
   unintended operation.
8. Partial failure is represented per document rather than hidden behind a
   successful batch status.

## 3. End-to-end flow

```text
User selects folders or files
        |
        v
Discovery and stable identity
        |
        v
Safety inspection and extraction
        |
        v
Structured Bedrock analysis
        |
        v
Deterministic validation and evidence checks
        |
        +---- invalid or insufficient ----> bounded retry or review queue
        |
        v
Classification proposal persisted in CockroachDB
        |
        +----> naming and destination proposal
        |
        +----> related-document proposal
        |
        v
Confidence scoring, calibration, and review priority
        |
        v
Human review and approval
        |
        v
Pre-execution state and collision checks
        |
        v
Copy or move execution with per-file results
        |
        v
Append-only history, reconciliation, and optional restore
```

## 4. Pipeline stages

### 4.1 Selection and discovery

The user selects one folder, multiple folders where supported, one file, or
multiple files. The Intake Agent enumerates candidates within authorized roots.
Deterministic code records file metadata, computes a content fingerprint, and
checks CockroachDB for prior processing state.

**Persistent checkpoint:** source selection, scan, logical document, physical
file instance, fingerprint, discovery status, and prior-work match.

**Result:** each candidate is classified as new, unchanged, changed, moved,
missing, completed, interrupted, duplicate, unsupported, or unreadable.

### 4.2 Safety inspection and extraction

A resource-limited extraction worker validates the Portable Document Format
(PDF) signature and configured limits before parsing. It extracts text,
page boundaries, selected metadata, and structural signals. Suspicious,
encrypted, malformed, or unsupported documents are quarantined or routed to
review rather than passed to the model as normal input.

**Persistent checkpoint:** extraction attempt, extractor version, page count,
content spans, limitations, artifact hashes, and extraction status.

**Result:** versioned extracted evidence or an explicit limited-processing
state. Optical Character Recognition (OCR) remains outside this baseline until
separately approved.

**Current implementation:** ADR-0004 implements local Qt PDF text extraction in
a disposable process with authorized-root, signature, size, page, character,
timeout, and source-digest controls. Page text and extractor provenance are
returned through path-free typed contracts. CockroachDB checkpointing,
quarantine storage, Optical Character Recognition, malware scanning, and
operating-system sandboxing remain pending.

### 4.3 Context assembly

The Memory Steward retrieves only workspace-authorized taxonomy definitions,
reviewed preferences, relevant prior decisions, and candidate relationships.
The gateway labels provenance and trust level and keeps system instructions
separate from document text and retrieved memory.

Deterministic token budgeting selects relevant evidence without silently
truncating required instructions or provenance.

**Persistent checkpoint:** context manifest containing references, versions,
trust labels, retrieval reason, and token estimate. Full prompts need not be
stored when references and reproducible configuration are sufficient.

### 4.4 Structured model analysis

The Classification Agent calls the central Bedrock gateway using the approved
European inference profile. The request uses a versioned JSON (JavaScript
Object Notation) Schema, a side-effect-free forced emission envelope, and an
explicit maximum output-token limit.

The requested proposal includes:

- taxonomy class and alternatives;
- evidence references;
- expected evidence that is missing;
- contradictions and extraction limitations;
- class-specific candidate metadata;
- abstention reason where appropriate; and
- model and analysis provenance.

The agent does not issue file commands or write canonical business facts.

**Persistent checkpoint:** agent run, model identifier, inference profile,
prompt-contract version, taxonomy version, request timing, token usage, raw
response reference, and completion status.

### 4.5 Deterministic validation

Application code validates the response schema, taxonomy membership, evidence
references, field types, filename policy, and declared contradictions. Values
not supported by extracted evidence remain proposals and are never promoted by
the validator.

A malformed response may receive a small, recorded number of retries. Exhausted
retries, insufficient evidence, or contradictory results enter the human
review queue. There is no canned classification fallback.

**Persistent checkpoint:** validation ruleset version, results, errors, retry
count, and final routing decision.

**Current implementation:** `classification.v1` provides the
Bedrock-compatible constrained-emission schema, bounded request fields, typed
proposal, and fail-closed local decoder. The pinned boto3 gateway now supplies
the approved profile, adaptive retry and timeout configuration, strict response
handling, observed token and latency provenance, and optional externally
configured cost estimation. Exact quotations are reconstructed locally from
selected evidence segments. One bounded live proposal passed validation;
corpus-quality evidence, application composition, and the CockroachDB
checkpoint remain pending.

### 4.6 Proposal enrichment

After a valid classification proposal exists:

- the Organization Agent proposes a filename and destination;
- the Relationship Agent proposes typed links to related documents; and
- the Review Agent checks proposal consistency against deterministic policy and
  authorized evidence.

These responsibilities use separate typed messages and cannot approve their
own output. A later second-model review is optional and not part of this
baseline.

**Persistent checkpoint:** independently versioned classification,
organization, and relationship proposals with evidence and provenance.

### 4.7 Confidence and review priority

The Confidence Service combines reproducible signals such as extraction
coverage, evidence strength, missing fields, contradictions, class margin, and
agent disagreement. A model-stated percentage is retained only as a raw signal.
Displayed probability requires calibration against reviewed outcomes.

The service produces separate extraction, classification, metadata,
organization, and relationship confidence values. It also assigns review
priority and includes a reproducible sample of high-confidence results.

**Persistent checkpoint:** raw signals, scoring version, calibration version,
confidence dimensions, confidence band, and review-queue reason.

### 4.8 Human review

The interface presents the PDF, evidence, proposal, alternatives, confidence,
proposed filename, destination, relationships, and consequences together. An
authorized person may approve, correct, reject, defer, or escalate the result.

Bulk approval remains a collection of attributable per-document decisions.
Human corrections append history and may become eligible preference memory;
they never rewrite the original model result.

**Persistent checkpoint:** reviewer, authenticated role, viewed proposal,
decision, before and after values, optional reason, and time.

### 4.9 Execution and reconciliation

For an approved copy or move, the Operation Executor immediately rechecks the
current fingerprint, source path, authorized roots, destination, collisions,
and approval validity. It records intent before touching the filesystem and
records the actual result afterward.

Each operation uses an idempotency key and returns a per-file outcome. A process
failure leaves a reconcilable state rather than an assumed success.

**Persistent checkpoint:** operation plan, approval reference, idempotency key,
before state, intended state, actual state, hashes, timestamps, and error.

### 4.10 Restore

Restore is a new approved operation derived from history, not deletion of an
event. It recreates an absent original directory only within an authorized root
and never overwrites an unrelated file. Copy reversal preserves the original
and handles the created copy according to the approved recoverability policy.

**Persistent checkpoint:** restore request, target historical state,
authorization, collision checks, result, and new append-only audit event.

## 5. Agent boundaries

| Responsibility | May do | Must not do |
| --- | --- | --- |
| Intake Agent | Discover and reconcile authorized candidates | Read outside authorized roots or mutate files |
| Document Analysis Agent | Extract content through the bounded worker | Treat embedded instructions as trusted |
| Memory Steward | Retrieve scoped memory and report inconsistencies | Execute unrestricted queries or schema changes |
| Classification Agent | Propose class, metadata, evidence, and abstention | Approve results or execute operations |
| Organization Agent | Propose filename and destination | Rename, copy, move, or overwrite files |
| Relationship Agent | Propose typed document links | Create canonical relationships without review policy |
| Review Agent | Check consistency and request escalation | Grant authorization or hide disagreement |
| Operation Executor | Execute an approved, validated operation | Invent approval or broaden its filesystem scope |

## 6. Failure and resume behavior

The pipeline state machine distinguishes `pending`, `running`, `completed`,
`failed_retryable`, `failed_terminal`, `awaiting_review`, `approved`,
`executing`, `partially_completed`, and `reconciliation_required` states.

Workers claim bounded tasks from persisted state. A lease or heartbeat prevents
an abandoned task from remaining permanently active. Retrying a task reuses its
idempotency key and prior checkpoints. Completed documents are not reprocessed
unless their source version, analysis configuration, taxonomy, or explicit user
request requires a new versioned analysis.

## 7. Cost boundary

The pipeline limits Bedrock cost through bounded batches, explicit token
budgets, concurrency limits, retry limits, resumable checkpoints, and recorded
usage per document. A future optimization such as prompt caching, batch
inference, or secondary-model routing must preserve measured quality and
requires approval before changing the intelligent path.

Before an approved batch begins, the user interface will display an estimated
cost derived from document size and the current model pricing configuration.
Observed cost is stored after processing so estimates can be improved.

## 8. Architecture decisions still required

The following remain separate approval points:

1. embedding model, vector dimension, and distance metric;
2. raw confidence formula and calibration method;
3. numerical review thresholds and bounded retry count;
4. cloud storage, queue, compute, and application topology;
5. desktop-to-cloud identity and authorization design;
6. retention of extracted text and raw model responses; and
7. whether and when a secondary model is evaluated.

The physical CockroachDB schema, indexes, and transaction boundaries are
approved by
[`ADR-0002`](decisions/0002-cockroachdb-physical-data-model.md). The initial
non-vector operational migration has been validated separately; document,
extraction, analysis, and vector migrations remain pending.

## 9. Acceptance evidence

Implementation of this baseline will require automated evidence that:

- interrupted work resumes without duplicate model or file effects;
- invalid model output cannot enter authoritative relational state;
- document instructions cannot invoke tools or alter agent policy;
- completed files are not reprocessed by an unchanged rescan;
- review decisions and file operations remain attributable and reversible;
- partial failure is visible per document;
- every Bedrock result records model, profile, contract, token, latency, and
  cost provenance; and
- desktop and cloud surfaces execute the same production pipeline contracts.
