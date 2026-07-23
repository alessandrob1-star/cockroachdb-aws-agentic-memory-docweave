# ADR-0002: CockroachDB Physical Data Model

**Status:** Accepted
**Decision date:** 2026-07-23
**Decision owner:** Project owner
**Implementation status:** Not started

## Context

DocWeave requires CockroachDB to be the durable memory for document identity,
workflow state, agent provenance, semantic retrieval, human decisions,
controlled preferences, domain facts, file operations, and audit history.

The approved requirements reject both a single oversized table and an opaque
object store disguised as a relational database. They also require uncertain
agent proposals to remain distinguishable from reviewed canonical state.

The physical model must support:

- stable logical document identity across copies, moves, and versions;
- genuine relational domain data for projects, procurement, invoices, and
  payments;
- versioned and attributable agent proposals;
- typed candidate facts and governed promotion to canonical entities;
- resumable and idempotent workflows;
- safe file-operation reconciliation;
- semantic retrieval within a workspace boundary;
- append-only material history; and
- complete attribution to human and agent actors.

## Decision

DocWeave will use a relational-first CockroachDB schema named `docweave`.
Tables are grouped into access, document, proposal, domain, workflow, operation,
preference, and audit responsibilities.

### Stable identity

`documents` represents a logical document. `document_versions` represents a
specific content revision. `file_instances` represents each local or cloud
copy. A move changes an instance location, a copy creates another instance,
and a content change creates another version.

### Proposal hierarchy

All intelligent outputs begin as rows in `proposals`. Type-specific tables
store classification, organization, relationship, or fact-candidate content.
`review_decisions` always references a proposal through a real foreign key.

A later result supersedes an earlier proposal instead of overwriting it.
Canonical classifications and relationships are stored separately from their
source proposals.

### Typed facts and relational domain entities

`fact_candidates` stores exactly one typed candidate value and retains
evidence, confidence, and model provenance. Approved facts are promoted through
an authorized transaction into typed canonical tables for projects, suppliers,
tenders, contracts, purchase orders, invoices, and payments.

`domain_entities` provides a common relational identity for those typed tables.
This allows document-to-entity and promotion records to use foreign keys
without reducing canonical business data to generic JSON.

### Semantic memory

Authorized extracted text and source coordinates are stored in
`document_chunks`. The active embedding is stored with its chunk, model
identifier, model version, and creation timestamp.

The vector dimension and final index definition require a separate embedding
model decision. No migration may invent or silently change the dimension.

### Workspace isolation

Every tenant-owned table carries `workspace_id`. Application authorization is
the primary control. CockroachDB privileges and Row-Level Security provide
defense in depth. Runtime, migration, audit-reader, and Managed Model Context
Protocol identities remain separate.

### Transaction model

Material state changes use CockroachDB's default serializable isolation and
bounded client-side retries for retryable serialization failures. File-system
or object-storage operations are not represented as atomically committed with
SQL. They use a persisted intent, external execution, verification, and
reconciliation protocol.

### Historical integrity

Agent runs, proposals, review decisions, operations, checkpoints, preferences,
and audit events are never silently rewritten to hide prior state. Corrections
create superseding records or explicit state transitions.

## Consequences

### Benefits

- CockroachDB remains central to every important product workflow.
- Foreign keys and constraints protect relationships that the application
  actually knows.
- Agent uncertainty cannot become canonical state without an attributable
  decision.
- Desktop and cloud surfaces can share the same persistence contracts.
- Semantic and relational retrieval remain in one database.
- File-operation failures remain visible and recoverable.
- The schema can demonstrate operational, semantic, episodic, preference, and
  audit memory without fabricated behavior.

### Costs and limitations

- The model contains more small tables than a document-only prototype.
- Promotion transactions and canonical subtype tables require explicit
  application services and tests.
- Serializable transactions require safe client retry handling.
- Row-Level Security policies require dedicated authorization tests and careful
  connection-pool context management.
- Vector migrations cannot be completed before the embedding model and
  dimension are approved.
- The filesystem and database cannot share a distributed transaction, so
  reconciliation remains a first-class workflow.

## Alternatives considered

### One document table with JSON metadata

Rejected because it would weaken constraints, provenance, joins, canonical
facts, and the demonstrated role of CockroachDB.

### One table per agent

Rejected because agent ownership is not a durable data boundary. Shared
proposal and provenance contracts are clearer and avoid duplicated review
logic.

### Generic entity-attribute-value canonical storage

Rejected as the authoritative domain representation because dates, money,
identifiers, and relationships would lose useful relational constraints.
Generic typed candidates remain appropriate before promotion.

### Separate vector database

Rejected for the Minimum Viable Product because it would duplicate
authorization and provenance concerns while weakening the qualifying
CockroachDB vector integration.

### Treat file operations as SQL-atomic

Rejected because SQL cannot atomically commit a Windows filesystem or Amazon
Simple Storage Service mutation. Claiming otherwise would create false success
states.

## Known prerequisite

The approved domain-data requirements and classification specification contain
different initial taxonomy lists. The physical schema deliberately stores
versioned taxonomy data and does not hardcode either list. The taxonomy baseline
must be reconciled and approved before seed data or classification contracts
are implemented.

## Verification required before implementation is accepted

1. Schema migrations create all approved tables, constraints, and indexes on a
   clean CockroachDB database.
2. Migration rollback or forward-recovery behavior is tested.
3. Cross-workspace reads and writes fail under application authorization and
   Row-Level Security tests.
4. Duplicate document registration is idempotent.
5. Candidate promotion preserves proposal, evidence, review, and canonical
   provenance.
6. Interrupted workflows resume without repeating completed effects.
7. Duplicate operation commands do not repeat a copy, move, or restore.
8. Serialization failures are retried only by idempotent transaction
   functions.
9. Vector retrieval is scoped to the authorized workspace and records the
   embedding configuration used.
10. Audit events reconcile with every material state transition.

## Out of scope

This decision does not create the database, approve an embedding model, resolve
the taxonomy discrepancy, define retention periods, authorize cloud resources,
or implement application code.

## Detailed design

- [CockroachDB physical schema specification](../cockroachdb-physical-schema.md)
- [Entity Relationship model](../cockroachdb-entity-relationship.md)
