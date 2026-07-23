# Domain and Relational Data Requirements

**Version:** 0.1
**Decision approved:** 2026-07-21
**Implementation status:** Not started

## 1. Purpose

This document defines the approved data direction for DocWeave. The product is
a document organizer with durable agentic memory, not a reconstruction of a
legacy accounting master workbook. Nevertheless, its demonstration corpus and
relational model shall reflect credible legal, procurement, compliance, and
project-document workflows.

Important information extracted from PDFs shall be represented in CockroachDB
as queryable relational data. JSON objects shall not replace the primary domain
model, canonical state, operation history, or evidence required to demonstrate
meaningful database use.

## 2. Domain reference policy

The initial domain categories were informed by the project owner's prior work
consolidating tabular project, invoice, order, contract, payment, supplier, and
regional data for operational reporting.

The local reference workbook contains obsolete but real company data. It is a
private structural reference and is explicitly excluded from Git. DocWeave
shall not copy its company names, tax identifiers, project identifiers, payment
references, exact amounts, filenames, or row-level records.

The synthetic corpus may reproduce only general field categories, plausible
relationships, document shapes, naming problems, and workflow complexity.

## 3. MVP document taxonomy

The approved initial taxonomy baseline is `docweave_mvp_v0_1`. It contains ten
primary business classes and two controlled outcomes used for coverage and
abstention:

| Code | Document type | Purpose |
| --- | --- | --- |
| `invoice` | Invoice | Supplier charge linked to an order, contract, or project |
| `contract` | Contract | Agreement governing commercial terms and obligations |
| `purchase_order` | Purchase Order | Authorized order linked to a supplier and contract |
| `tender_document` | Tender Document | Procurement, bid, proposal, quotation, or tender material linked to a project |
| `payment_notice` | Payment Notice | Evidence that an invoice entered a payment workflow |
| `bank_certification` | Bank Certification | Bank-originated evidence supporting payment |
| `supplier_receipt` | Supplier Receipt | Supplier acknowledgement or payment receipt |
| `bank_statement` | Bank Statement | Statement containing one or more payment references |
| `acceptance_document` | Acceptance Document | Evidence that goods, work, or services were accepted |
| `technical_attachment` | Technical Attachment | Material, asset, plant, measurement, or delivery detail |
| `other` | Other | Supported document with enough evidence to determine that no configured primary class applies |
| `unclassified` | Unclassified | Insufficient, conflicting, unreadable, suspicious, or unsupported evidence |

The taxonomy is deliberately small enough for a high-quality demonstration and
large enough to prove classification, naming, organization, uncertainty, and
cross-document relationships.

`Other` and `Unclassified` are intentionally different. `Other` is an informed
classification result inside the supported workflow. `Unclassified` is an
abstention or limited-processing outcome that requires human attention before
the product treats the document as classified.

## 4. Relational-first requirements

- **DATA-001:** Stable document identity, file instances, versions,
  classifications, relationships, batches, operations, reviews, agent runs,
  and audit events shall be stored in typed relational tables.
- **DATA-002:** Important approved business entities and facts shall be stored
  in relational tables with constraints and foreign keys where the relationship
  is known.
- **DATA-003:** A JSON field shall not be the sole or authoritative storage for
  a document's classification, confidence, canonical domain facts, operation
  state, relationship, user decision, or audit history.
- **DATA-004:** Raw provider responses may be retained separately for forensic
  or evaluation purposes, subject to minimization and retention policy, but
  application behavior shall not depend on an opaque response blob.
- **DATA-005:** Proposed model facts shall remain distinguishable from
  human-approved canonical facts.
- **DATA-006:** Every proposed fact shall preserve value type, confidence,
  evidence location, model provenance, review state, and supersession history.
- **DATA-007:** Promotion of a proposed fact into canonical state shall be an
  authorized and auditable operation; it shall not erase the original proposal.
- **DATA-008:** Relational constraints and deterministic transactions shall
  protect integrity rather than relying on language-model judgment.
- **DATA-009:** The model shall remain intentionally narrower than the private
  reference workbook; columns are added only when required by an approved user
  workflow, evaluation, relationship, or naming rule.
- **DATA-010:** CockroachDB features shall be demonstrated through meaningful
  transactions, joins, indexed filters, resumable state, authorization,
  provenance queries, and distributed vector retrieval.

## 5. Conceptual relational groups

This is a logical grouping, not an approved physical schema.

### 5.1 Document control

| Conceptual table | Responsibility |
| --- | --- |
| `workspaces` | Tenant and authorization boundary |
| `documents` | Stable logical document identity |
| `document_versions` | Content revisions and fingerprints |
| `file_instances` | Original, moved, copied, local, or cloud file locations |
| `classifications` | Versioned class proposals, confidence, evidence, and review |
| `document_relationships` | Typed and explainable links between documents |

### 5.2 Business entities

| Conceptual table | Representative typed data |
| --- | --- |
| `projects` | Project code, name, stream, and region |
| `suppliers` | Synthetic supplier code, display name, and synthetic tax identifier |
| `tenders` | Tender identifier and project relationship |
| `contracts` | Contract number, dates, supplier, tender, and value |
| `purchase_orders` | Order number, date, supplier, contract, and value |
| `invoices` | Invoice number, date, supplier, order, taxable amount, tax, total, and currency |
| `payments` | Payment reference, date, invoice, amount, method, and beneficiary |
| `document_entity_links` | Evidence that a document represents or mentions an entity |

### 5.3 Agent and operational memory

| Conceptual table | Responsibility |
| --- | --- |
| `operation_batches` | Bounded processing and execution groups |
| `file_operations` | Planned and actual copy, move, rename, and restore actions |
| `review_decisions` | Human approval, rejection, correction, and escalation |
| `agent_runs` | Model, tool, handoff, timing, cost, and outcome provenance |
| `workflow_checkpoints` | Durable resume positions and idempotency state |
| `audit_events` | Append-only material state changes |
| `user_preferences` | Controlled, attributable, and revocable learned preferences |

### 5.4 Semantic memory

| Conceptual table | Responsibility |
| --- | --- |
| `document_chunks` | Authorized text segments with source coordinates |
| `chunk_embeddings` | Vector representations used for semantic retrieval |
| `relationship_evidence` | Chunk or fact evidence supporting a proposed link |

Physical consolidation or separation of these concepts requires architecture
approval and must preserve their responsibilities.

## 6. Proposed facts and canonical facts

An agent observation is not automatically accepted business truth. The
relational model shall support a lifecycle such as:

```text
Extracted candidate
→ Validated candidate
→ Human reviewed
→ Canonical fact
→ Corrected or superseded
```

A proposed fact requires, at minimum:

- document and version identity;
- field definition;
- typed candidate value;
- confidence and confidence method;
- page or content evidence;
- responsible agent run and model version;
- extraction and review timestamps;
- review state and reviewer where applicable;
- reference to the fact it supersedes.

The physical schema may use typed candidate columns or type-specific proposal
tables. It shall not coerce dates, money, identifiers, and free text into an
undifferentiated authoritative string.

## 7. Core synthetic field set

The corpus may contain more visible content, but the first canonical field set
should remain focused:

### 7.1 Identifiers

- synthetic project identifier;
- synthetic tender identifier;
- contract number;
- purchase-order number;
- invoice number;
- payment reference;
- document reference.

### 7.2 Parties

- synthetic supplier identifier and name;
- beneficiary name when different;
- approving or issuing organization.

### 7.3 Dates and money

- issue, contract, order, invoice, due, and payment dates where applicable;
- taxable amount;
- tax amount;
- total amount;
- payment amount;
- currency.

### 7.4 Project and technical context

- project name and stream;
- region;
- expense category;
- material or service description;
- asset or technical reference when applicable.

Fields that do not support classification, naming, linking, verification, or a
judged workflow are deferred rather than added for superficial completeness.

## 8. Relationship requirements

The corpus and database shall support real dossier graphs, for example:

```text
Project
└── Tender
    └── Contract
        └── Purchase Order
            ├── Invoice
            │   └── Payment Notice
            │       ├── Bank Certification
            │       ├── Supplier Receipt
            │       └── Bank Statement
            ├── Acceptance Document
            └── Technical Attachment
```

Relations shall not be inferred from filename alone when document evidence is
available. Each proposed relation records type, direction, evidence,
confidence, provenance, and review status.

## 9. Synthetic corpus direction

The approximately 300-PDF corpus shall be organized into multiple internally
consistent synthetic dossiers rather than 300 unrelated files. It shall use:

- fictional organizations and people;
- generated identifiers that cannot be mistaken for the reference records;
- mathematically consistent tax and total values in ordinary cases;
- chronologically plausible tender, contract, order, invoice, and payment
  sequences;
- repeated entities across related documents;
- deliberately ambiguous, incomplete, duplicated, conflicting, or revised
  cases for uncertainty and recovery testing.

A dataset manifest shall contain the expected type, fields, relationships,
difficulty, and review outcome for every generated document. The manifest is
evaluation ground truth; it is not exposed to the production agents during
analysis.

## 10. Privacy and provenance boundary

- The private workbook remains local and ignored by Git.
- No source row or exact filename is copied into the demonstration corpus.
- No real supplier, tax identifier, payment reference, project identifier, or
  confidential amount is used as generated content.
- Generated examples shall carry an explicit synthetic-data notice.
- The dataset generator shall use reviewed templates and seeds, not private
  records presented to a model as hidden source material.
- Provenance and licenses for any non-generated assets shall be recorded.

## 11. Deferred architecture decisions

The following require a separate proposal and approval:

- vector dimensions and index configuration;
- retention of raw model responses;
- synthetic corpus distribution and generation pipeline.

Physical tables and indexes, the typed proposal strategy, canonical-fact
promotion, workspace isolation, and file-operation reconciliation are approved
by
[`ADR-0002`](../architecture/decisions/0002-cockroachdb-physical-data-model.md).
Implementation and verification remain not started.
