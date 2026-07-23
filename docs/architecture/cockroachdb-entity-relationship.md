# CockroachDB Entity Relationship Model

**Project:** DocWeave
**Version:** 0.1
**Decision status:** Approved by ADR-0002
**Implementation status:** Not started

## Purpose

This diagram shows the principal relational boundaries approved for DocWeave.
It intentionally omits some descriptive columns so that identity, provenance,
review, workflow, and canonical-state relationships remain readable.

## Core document and proposal model

```mermaid
erDiagram
    WORKSPACES ||--o{ WORKSPACE_MEMBERS : authorizes
    ACTORS ||--o{ WORKSPACE_MEMBERS : receives_role
    WORKSPACES ||--o{ DOCUMENTS : owns
    DOCUMENTS ||--o{ DOCUMENT_VERSIONS : has
    DOCUMENT_VERSIONS ||--o{ FILE_INSTANCES : materializes_as
    DOCUMENT_VERSIONS ||--o{ DOCUMENT_CHUNKS : contains

    WORKSPACES ||--o{ TAXONOMY_VERSIONS : owns
    TAXONOMY_VERSIONS ||--o{ TAXONOMY_CLASSES : defines

    DOCUMENT_VERSIONS ||--o{ PROPOSALS : analyzed_as
    AGENT_RUNS ||--o{ PROPOSALS : produces
    PROPOSALS ||--o| CLASSIFICATION_PROPOSALS : specializes
    PROPOSALS ||--o| ORGANIZATION_PROPOSALS : specializes
    PROPOSALS ||--o| RELATIONSHIP_PROPOSALS : specializes
    PROPOSALS ||--o| FACT_CANDIDATES : specializes
    PROPOSALS ||--o{ PROPOSAL_EVIDENCE : supported_by
    DOCUMENT_CHUNKS ||--o{ PROPOSAL_EVIDENCE : supplies

    PROPOSALS ||--o{ REVIEW_DECISIONS : reviewed_by
    ACTORS ||--o{ REVIEW_DECISIONS : makes
    CLASSIFICATION_PROPOSALS ||--o| DOCUMENT_CLASSIFICATIONS : accepted_as
    RELATIONSHIP_PROPOSALS ||--o| DOCUMENT_RELATIONSHIPS : accepted_as
    TAXONOMY_CLASSES ||--o{ DOCUMENT_CLASSIFICATIONS : classifies
```

## Canonical domain model

```mermaid
erDiagram
    WORKSPACES ||--o{ DOMAIN_ENTITIES : owns
    DOMAIN_ENTITIES ||--o| PROJECTS : specializes
    DOMAIN_ENTITIES ||--o| SUPPLIERS : specializes
    DOMAIN_ENTITIES ||--o| TENDERS : specializes
    DOMAIN_ENTITIES ||--o| CONTRACTS : specializes
    DOMAIN_ENTITIES ||--o| PURCHASE_ORDERS : specializes
    DOMAIN_ENTITIES ||--o| INVOICES : specializes
    DOMAIN_ENTITIES ||--o| PAYMENTS : specializes

    PROJECTS ||--o{ TENDERS : contains
    TENDERS ||--o{ CONTRACTS : governs
    SUPPLIERS ||--o{ CONTRACTS : signs
    CONTRACTS ||--o{ PURCHASE_ORDERS : authorizes
    SUPPLIERS ||--o{ PURCHASE_ORDERS : receives
    PURCHASE_ORDERS ||--o{ INVOICES : billed_by
    SUPPLIERS ||--o{ INVOICES : issues
    INVOICES ||--o{ PAYMENTS : settled_by

    DOCUMENTS ||--o{ DOCUMENT_ENTITY_LINKS : evidences
    DOMAIN_ENTITIES ||--o{ DOCUMENT_ENTITY_LINKS : linked_from
    FACT_CANDIDATES ||--o| FACT_PROMOTIONS : promoted_through
    DOMAIN_ENTITIES ||--o{ FACT_PROMOTIONS : receives
    REVIEW_DECISIONS ||--o{ FACT_PROMOTIONS : authorizes
```

## Workflow, operation, and memory model

```mermaid
erDiagram
    WORKSPACES ||--o{ PROCESSING_BATCHES : owns
    PROCESSING_BATCHES ||--o{ BATCH_ITEMS : contains
    DOCUMENT_VERSIONS ||--o{ BATCH_ITEMS : processes

    BATCH_ITEMS ||--o{ WORKFLOW_RUNS : executes
    WORKFLOW_RUNS ||--o{ WORKFLOW_CHECKPOINTS : checkpoints
    WORKFLOW_RUNS ||--o{ AGENT_RUNS : orchestrates
    AGENT_RUNS ||--o{ AGENT_RUNS : delegates_to

    REVIEW_DECISIONS ||--o{ OPERATION_BATCHES : authorizes
    OPERATION_BATCHES ||--o{ FILE_OPERATIONS : contains
    DOCUMENTS ||--o{ FILE_OPERATIONS : affects
    FILE_INSTANCES ||--o{ FILE_OPERATIONS : starts_from
    FILE_OPERATIONS ||--o{ FILE_OPERATIONS : compensates

    REVIEW_DECISIONS ||--o{ PREFERENCE_RULES : grounds
    WORKSPACES ||--o{ PREFERENCE_RULES : learns

    WORKSPACES ||--o{ AUDIT_EVENTS : records
    ACTORS ||--o{ AUDIT_EVENTS : causes
    WORKFLOW_RUNS ||--o{ AUDIT_EVENTS : correlates
```

## Invariants represented by the model

- A physical file instance belongs to one exact document version.
- A document version may have multiple local or cloud instances.
- Every intelligent subtype has one proposal identity and one producing agent
  run.
- Every canonical classification, relationship, or promoted fact retains its
  source proposal and human decision.
- Every canonical business entity has one typed subtype.
- A file operation is authorized before execution and may be compensated by a
  later operation without deleting history.
- Workflow checkpoints and agent runs remain connected to the same durable
  document and workspace identities.
- Preference memory is grounded in attributable decisions and can be revoked or
  superseded.

## Deliberate omissions

The diagram does not imply:

- that every table is writable by every application role;
- that a model may promote facts without review;
- that file operations are atomic with SQL;
- that vector dimensions are already approved;
- that the current taxonomy discrepancy has been resolved; or
- that implementation or database creation has started.
