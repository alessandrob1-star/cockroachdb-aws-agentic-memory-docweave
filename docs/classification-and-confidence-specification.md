# Classification, Confidence, and Trusted Learning Specification

**Project:** DocWeave

**Version:** 0.1

**Baseline approved:** 2026-07-22

**Implementation status:** In progress

**Document status:** Approved product design; physical schema approved separately; implementation pending

## 1. Purpose

This document specifies how DocWeave classifies documents, represents
uncertainty, supports human review, and uses trusted human decisions to improve
later recommendations without silently changing historical facts or weakening
human control.

The design applies to the shared production workflow used by the PySide6
desktop application and the complete cloud application. Amazon Bedrock provides
Large Language Model (LLM) inference. CockroachDB provides persistent,
relational-first memory for evidence, results, decisions, calibration,
preferences, and governed rules.

This document does not approve a physical database schema, model training, or
cloud resource creation. The current temporary primary Bedrock model is
recorded under
[`ADR-0001`](architecture/decisions/0001-amazon-bedrock-primary-model.md).

## 2. Objectives

The classification system shall:

1. classify supported Portable Document Format (PDF) files using real document
   content rather than filenames alone;
2. explain each proposal with evidence that can be inspected by a person;
3. distinguish extraction quality, classification confidence, metadata
   confidence, organization confidence, and relationship confidence;
4. abstain when evidence is insufficient;
5. prioritize useful human review rather than hiding uncertainty;
6. calibrate confidence against reviewed outcomes rather than trusting a
   model-generated percentage;
7. preserve every proposal, correction, rule, and supersession event;
8. learn only from attributable, authorized, reviewable decisions;
9. prevent one mistaken or malicious correction from silently changing global
   behavior; and
10. provide measurable evidence of quality for the hackathon demonstration.

## 3. Governing principles

### 3.1 Evidence before confidence

A model statement such as `confidence: 0.95` is a raw signal, not a verified
probability. DocWeave shall calculate confidence from reproducible signals and
calibrate it using reviewed ground truth.

### 3.2 Uncertainty is a valid result

`Unclassified` is an intentional outcome. DocWeave shall not force a document
into the nearest category when the evidence is inadequate or contradictory.

### 3.3 Proposals are not canonical facts

An agent proposal, a human decision, and an approved canonical value are
distinct records. A correction supersedes a result; it does not rewrite it.

### 3.4 Human authority is scoped

A user's authority is determined by authenticated role and workspace policy,
not by a self-declared expertise score. Higher authority permits governed
review and rule management; it does not make every decision automatically
correct.

### 3.5 Learning is controlled and reversible

Human feedback may improve later recommendations only with provenance, scope,
versioning, conflict handling, evaluation, and revocation. Automatic online
model-weight updates are not part of the Minimum Viable Product (MVP).

## 4. Initial document taxonomy

The approved initial taxonomy baseline is `docweave_mvp_v0_1`. It is deliberately
useful but small enough to evaluate reliably, and it matches the domain
requirements:

| Code | Display name | Typical evidence |
| --- | --- | --- |
| `invoice` | Invoice | Invoice number, taxable amount, tax, total, due date |
| `contract` | Contract | Parties, obligations, signatures, effective dates |
| `purchase_order` | Purchase Order | Order number, buyer, supplier, ordered items |
| `tender_document` | Tender Document | Tender identifier, proposal, quotation, deadline, eligibility, scope |
| `payment_notice` | Payment Notice | Invoice reference, payment workflow status, due or scheduled date |
| `bank_certification` | Bank Certification | Bank issuer, certified payment reference, amount, account or transaction evidence |
| `supplier_receipt` | Supplier Receipt | Supplier acknowledgement, received amount, invoice or payment reference |
| `bank_statement` | Bank Statement | Statement period, transaction rows, payment references, account evidence |
| `acceptance_document` | Acceptance Document | Acceptance statement, goods or services received, approver, date |
| `technical_attachment` | Technical Attachment | Technical specification, asset, material, measurement, delivery detail |
| `other` | Other | Sufficient evidence that no configured class applies |
| `unclassified` | Unclassified | Insufficient, conflicting, unreadable, or unsupported evidence |

Taxonomy definitions shall be stored as versioned CockroachDB data rather than
scattered constants or prompt-only text. A classification result shall retain
the taxonomy version used to produce it.

`Other` and `Unclassified` are different: `Other` is an informed conclusion,
while `Unclassified` is an abstention.

## 5. Classification pipeline

### 5.1 Intake and extraction

The Intake Agent verifies document identity, supported type, prior processing
state, and authorization. The Document Analysis Agent extracts text and
document structure and records extraction limitations.

Image-only, encrypted, malformed, suspicious, or unreadable files enter an
explicit limited or manual-review state. Optical Character Recognition (OCR)
requires separate architecture, cost, privacy, and evaluation approval.

### 5.2 Structured analysis

The Classification Agent shall request a structured result through the central
Bedrock model gateway. At minimum, a proposal contains:

- taxonomy version and proposed class;
- candidate metadata relevant to that class;
- document-language assessment;
- page or content-span evidence;
- alternative classes considered;
- contradictions and missing expected evidence;
- raw model signals;
- model, prompt, and analysis-configuration provenance; and
- an explicit abstention reason where applicable.

Free-form model text shall not become authoritative application state without
schema validation.

**Current implementation:** ADR-0005 defines `classification.v1`, constructs
bounded side-effect-free Converse request fields, and decodes the closed
structured response into a non-authoritative typed proposal. Deterministic
validation confirms taxonomy and contract versions, page existence, exact
evidence quotations, cross-references, alternatives, abstention, and
application-side budgets. No Bedrock invocation, model-quality result,
confidence calculation, or persistence is claimed.

### 5.3 Independent review

The Review Agent checks the proposal against extracted content, taxonomy
constraints, deterministic validators, and authorized retrieved memory. A
second model analysis may be requested for uncertain or high-impact cases, but
shall not be described as independent if it reuses the same context and
reasoning trace.

Disagreement is a confidence signal and a reason for review, not an instruction
to hide one result.

### 5.4 Organization and relationships

The Organization Agent proposes a filename and destination only after a
classification proposal exists. The Relationship Agent proposes typed links
between documents using content and relational evidence. These proposals have
their own confidence dimensions and review states.

### 5.5 Persistence

Every stage is checkpointed. Reanalysis creates a new result linked to its
predecessor. No previous result, human decision, or evidence record is deleted
because a later result is preferred.

## 6. Confidence model

### 6.1 Confidence dimensions

DocWeave shall expose separate scores rather than one misleading universal
number:

| Dimension | Meaning |
| --- | --- |
| `extraction_confidence` | Reliability and completeness of extracted content |
| `classification_confidence` | Reliability of the proposed document class |
| `metadata_confidence` | Reliability of extracted class-specific fields |
| `organization_confidence` | Reliability of proposed filename and destination |
| `relationship_confidence` | Reliability of a proposed document relationship |

An optional overall review priority may combine these dimensions, but it shall
not replace them or be presented as a probability unless it is calibrated.

### 6.2 Candidate signals

Confidence may use:

- extraction coverage and quality;
- presence and strength of class-specific evidence;
- evidence location and uniqueness;
- required-field completeness;
- consistency between extracted values and document totals or dates;
- contradictions within the document;
- agreement between bounded agents or repeated analyses;
- distance between the leading and alternative classes;
- similarity to authorized, reviewed examples;
- taxonomy coverage and ambiguity;
- prior calibration performance for the class, language, and difficulty; and
- conflict with an active policy or grounding rule.

Filename and source directory may be weak contextual signals. They shall not be
the sole evidence when usable document content exists.

### 6.3 Raw and calibrated confidence

The system shall store both:

- **raw confidence**, produced by the approved scoring method from current
  signals; and
- **calibrated confidence**, adjusted using a held-out set of reviewed outcomes
  so that displayed probabilities correspond to observed correctness.

The calibration method, parameters, dataset version, sample size, class
coverage, and evaluation date shall be recorded. The exact mathematical method
requires evaluation before selection; candidate methods include isotonic
regression and logistic calibration.

No numerical confidence threshold is approved yet. Thresholds shall be selected
from evaluation evidence and may vary by class or risk policy.

### 6.4 Confidence bands

The user interface shall support these semantic states:

| Band | Meaning | Default behavior |
| --- | --- | --- |
| High | Strong calibrated evidence | Eligible for quality sampling and review |
| Medium | Useful proposal with meaningful uncertainty | Review recommended |
| Low | Weak or conflicting evidence | Priority review required |
| Unclassified | No defensible class | Human classification required |

For the MVP, even a High result remains a proposal until the applicable human
approval policy is satisfied.

### 6.5 High-confidence sampling

DocWeave shall sample some High results for human review. The sample must be
reproducible from a recorded policy and seed. An unacceptable observed error
rate shall block or escalate the affected batch according to policy.

This control detects systematic overconfidence that a low-confidence queue
alone would miss.

## 7. Review decisions and trusted learning

### 7.1 Decision types

A reviewer may:

- approve the proposal unchanged;
- correct the class or metadata;
- reject the proposal without supplying a replacement;
- defer the decision;
- mark the document unreadable or unsupported; or
- escalate it to a higher-authority reviewer.

Each decision records the proposal, final value, user, authenticated role,
workspace, time, optional reason, and evidence viewed.

### 7.2 Eligibility for learning

Feedback shall not become a trusted learning signal merely because it exists.
An eligible signal requires:

- an authenticated user;
- an authorized Reviewer, Project Manager, or Administrator role according to
  workspace policy;
- a completed, non-deferred decision;
- an unchanged source document version;
- complete provenance; and
- no unresolved conflict, revocation, or security quarantine.

Operator corrections remain valuable feedback but may require confirmation by
a reviewer before they influence other documents.

### 7.3 Controlled preference memory

Eligible decisions may create scoped preference-memory candidates in
CockroachDB. A preference may apply to a user, team, workspace, supplier,
project, document family, language, or taxonomy version. Global scope requires
the strongest approval policy.

Preference memory influences a later proposal as retrieved evidence. It does
not silently overwrite taxonomy definitions, deterministic controls, or model
weights. Each use shall be visible in the agent trace and explainable in the
review interface.

A single correction shall not automatically create a global rule. Promotion
may require repeated support, reviewer confirmation, conflict analysis, and a
measured improvement on a held-out evaluation set.

### 7.4 Active learning

DocWeave shall use active learning to prioritize documents whose review is
expected to improve the system most. Candidate signals include uncertainty,
agent disagreement, novel document patterns, underrepresented classes, and
possible calibration drift.

The reviewed outcomes become versioned evaluation and preference data. They do
not enter the production model prompt or retrieval memory without authorization
and provenance checks.

### 7.5 No silent self-training

Automatic online fine-tuning or model-weight updates are deferred. Such a
capability would require a separate proposal covering dataset governance,
privacy, poisoning resistance, evaluation, rollback, cost, and Bedrock model
support.

## 8. Governed grounding rules

### 8.1 Purpose

A future **Grounding Rule Studio** in the user interface may allow authorized
users to define explicit organizational knowledge and constraints without
editing prompts, source code, or Structured Query Language (SQL).

Examples include:

- a reviewed supplier-specific naming convention;
- a workspace-specific destination rule;
- required evidence before assigning a sensitive class;
- a mapping between an approved identifier pattern and a project; or
- a rule that certain ambiguous documents always require manual review.

### 8.2 Rule categories

Rules shall distinguish:

- **deterministic policy rules**, which enforce validation, authorization,
  naming, routing, or mandatory review;
- **grounding facts**, which provide approved domain context to agents; and
- **preferences**, which influence ranking but do not enforce an outcome.

The interface shall state which category is being created and its effect.

### 8.3 Required rule controls

Every rule requires:

- stable identity and version;
- author and authenticated role;
- workspace and scope;
- rule type and plain-language description;
- typed conditions and effects;
- source evidence or justification;
- creation, activation, expiration, and supersession times;
- review and approval state;
- precedence and conflict behavior;
- simulation results before activation;
- usage and outcome metrics; and
- immediate disable, revocation, and rollback capability.

Free-form user text shall not become an executable tool instruction. Rule input
shall be constrained, validated, and treated as untrusted until approved.

### 8.4 Safe activation workflow

```text
Draft
-> Validate
-> Simulate against reviewed documents
-> Show affected documents and conflicts
-> Obtain required approval
-> Activate a versioned rule
-> Monitor outcomes
-> Retain, revise, disable, or roll back
```

Simulation shall never mutate documents. Activating, changing, or disabling a
rule is an audited material action.

### 8.5 MVP boundary

The full Grounding Rule Studio is deferred unless separately approved. The MVP
shall preserve the data and workflow boundaries needed to add it later without
rewriting classification history. Controlled learning from approved human
corrections remains an MVP requirement.

## 9. Relational persistence requirements

The physical schema is approved separately by
[`ADR-0002`](architecture/decisions/0002-cockroachdb-physical-data-model.md).
Its implementation must preserve typed relational responsibilities for:

- taxonomy and taxonomy versions;
- classification results and alternatives;
- confidence dimensions and calibration versions;
- evidence references;
- human review decisions;
- learning eligibility and revocation;
- scoped preferences;
- grounding-rule definitions and versions;
- rule approvals, simulations, conflicts, and activations;
- agent and model provenance; and
- append-only audit events.

JavaScript Object Notation (JSON) may retain minimized raw technical evidence,
but it shall not be the only authoritative representation of classifications,
decisions, active rules, confidence, or audit history.

## 10. Evaluation and quality measures

The curated synthetic corpus shall provide reviewed ground truth and include
clear, ambiguous, incomplete, conflicting, duplicated, revised, sparse-text,
and unsupported examples.

At minimum, evaluation shall report:

- per-class precision, recall, and F1 score;
- confusion matrix;
- abstention rate and correctness of abstention;
- coverage at each confidence band;
- calibration error and reliability diagrams;
- accuracy of reviewed High-confidence samples;
- correction rate by class and document difficulty;
- evidence-reference validity;
- effect of preference memory compared with a versioned baseline;
- rule simulation false-positive and false-negative results; and
- latency and Bedrock cost per document and batch.

F1 is the harmonic mean of precision and recall. Metrics shall be expanded and
explained in user-facing learning documentation when the evaluation system is
created.

## 11. Security and integrity controls

- Document content is untrusted data and cannot issue agent instructions.
- Retrieved corrections and grounding facts require authorization, provenance,
  trust state, and workspace isolation.
- Prompt injection, cross-workspace leakage, rule escalation, and memory
  poisoning require dedicated adversarial tests.
- Agents cannot activate rules, elevate a user's role, or promote their own
  outputs to canonical facts.
- Role checks are deterministic and enforced outside the model.
- A missing authorization, validation, or audit dependency fails closed.
- Logs minimize document content and personally identifiable information.
- Historical results remain distinguishable from current active guidance.

## 12. Acceptance criteria

This specification is satisfied only when evidence demonstrates that:

1. every classification exposes evidence and full model provenance;
2. raw and calibrated confidence are distinguishable;
3. the interface supports sorting and filtering by calibrated confidence;
4. uncertain documents can be explicitly classified as `Unclassified`;
5. high-confidence sampling detects and escalates unacceptable error rates;
6. reviewer corrections preserve before-and-after values and provenance;
7. only eligible, authorized decisions influence later recommendations;
8. preference-memory use is visible, scoped, revocable, and evaluated;
9. reanalysis and correction never erase historical results;
10. desktop and cloud surfaces use the same production classification logic;
11. no model-reported percentage is presented as calibrated without evidence;
12. rule drafts can never mutate files during validation or simulation; and
13. security tests cover prompt injection, memory poisoning, privilege
    escalation, and cross-workspace retrieval.

## 13. Deferred decisions requiring approval

The following decisions remain open:

1. Optical Character Recognition boundary;
2. raw confidence scoring formula;
3. calibration algorithm and minimum sample requirements;
4. numerical confidence-band thresholds;
5. second-analysis triggers and cost limits;
6. preference-promotion thresholds and approval matrix;
7. Grounding Rule Studio MVP inclusion or post-MVP scheduling;
8. rule expression format and precedence engine; and
9. retention policy for raw model responses and learning evidence.

Each decision requires an explained proposal and explicit user approval before
implementation.

Physical CockroachDB tables, indexes, proposal boundaries, promotion
transactions, and file-operation reconciliation are resolved by ADR-0002.
