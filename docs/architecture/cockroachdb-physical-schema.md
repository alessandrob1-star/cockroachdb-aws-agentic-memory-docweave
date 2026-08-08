# CockroachDB Physical Schema Specification

**Project:** DocWeave
**Version:** 0.1
**Decision status:** Approved by ADR-0002
**Implementation status:** In progress; initial operational migration authored offline

## 1. Purpose

This document defines the approved physical responsibilities, keys, major
columns, constraints, indexes, and transaction boundaries for the DocWeave
CockroachDB schema. It is a migration design, not executable Data Definition
Language.

No table or index described here exists until an approved migration implements
and verifies it.

## 2. Database conventions

### 2.1 Namespace and names

- Application objects use the `docweave` SQL schema.
- Tables and columns use lowercase `snake_case`.
- Primary keys use `UUID` with `gen_random_uuid()` unless an external immutable
  identifier is explicitly required.
- Tenant-owned rows include a non-null `workspace_id`.
- Operational timestamps use `TIMESTAMPTZ`.
- Dates extracted from documents use `DATE`.
- Monetary values use `DECIMAL(19,4)` and a three-character currency code.
- Confidence values use a fixed-precision value constrained to the interval
  from zero through one.
- Content fingerprints use the full SHA-256 digest in `BYTES`.
- Flexible technical payloads may use minimized `JSONB`, but never as the only
  authoritative representation of product state.

### 2.2 Mutable and historical records

Mutable rows hold current coordination state, such as a workflow lease or
current file-instance location. Historical rows hold proposals, decisions,
operations, checkpoints, and audit evidence.

Historical correction uses one of:

- a new row that references the record it supersedes;
- an explicit append-only transition;
- a new compensating operation.

Material history is not deleted or rewritten as a normal product workflow.

### 2.3 State values

Stable workflow states use `STRING` columns with database `CHECK` constraints.
User-configurable concepts, especially taxonomy classes and preference rules,
use versioned relational data rather than SQL enums.

## 3. Access and workspace tables

### 3.1 `workspaces`

One authorized product boundary.

| Column | Type | Rule |
| --- | --- | --- |
| `workspace_id` | `UUID` | Primary key |
| `workspace_key` | `STRING` | Stable, unique public-safe key |
| `display_name` | `STRING` | Non-empty |
| `status` | `STRING` | `active`, `suspended`, or `archived` |
| `created_at` | `TIMESTAMPTZ` | Required |
| `archived_at` | `TIMESTAMPTZ` | Nullable |

### 3.2 `actors`

Identifies human users, services, and bounded agents without treating them as
interchangeable.

| Column | Type | Rule |
| --- | --- | --- |
| `actor_id` | `UUID` | Primary key |
| `actor_type` | `STRING` | `human`, `service`, or `agent` |
| `external_subject` | `STRING` | Nullable external identity identifier |
| `display_name` | `STRING` | Required |
| `status` | `STRING` | `active` or `disabled` |
| `created_at` | `TIMESTAMPTZ` | Required |

`external_subject` is unique when present. Authentication secrets are not
stored in this table.

### 3.3 `workspace_members`

| Column | Type | Rule |
| --- | --- | --- |
| `workspace_id` | `UUID` | Foreign key to `workspaces` |
| `actor_id` | `UUID` | Foreign key to `actors` |
| `role_code` | `STRING` | Approved product role |
| `granted_by_actor_id` | `UUID` | Human authority provenance |
| `granted_at` | `TIMESTAMPTZ` | Required |
| `revoked_at` | `TIMESTAMPTZ` | Nullable |

The primary key is `(workspace_id, actor_id, role_code, granted_at)`. An index
supports active membership checks by workspace and actor.

## 4. Document-control tables

### 4.1 `documents`

Stable logical identity independent of filename, location, and content version.

| Column | Type | Rule |
| --- | --- | --- |
| `document_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required workspace boundary |
| `lifecycle_status` | `STRING` | Current document state |
| `current_version_id` | `UUID` | Nullable until first version is registered |
| `current_classification_id` | `UUID` | Nullable canonical classification |
| `created_at` | `TIMESTAMPTZ` | Required |
| `retired_at` | `TIMESTAMPTZ` | Nullable |

Circular current-state foreign keys are added after the referenced tables exist
or are validated in a later migration step.

### 4.2 `document_versions`

| Column | Type | Rule |
| --- | --- | --- |
| `document_version_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `document_id` | `UUID` | Foreign key to `documents` |
| `version_number` | `INT8` | Positive and unique per document |
| `sha256` | `BYTES` | Full content digest |
| `byte_size` | `INT8` | Non-negative |
| `media_type` | `STRING` | Verified content type |
| `page_count` | `INT4` | Nullable, positive when present |
| `extraction_status` | `STRING` | Explicit extraction outcome |
| `predecessor_version_id` | `UUID` | Nullable self-reference |
| `registered_at` | `TIMESTAMPTZ` | Required |

The pair `(workspace_id, sha256)` is indexed for duplicate discovery. The
application decides whether equal content maps to the same logical document or
to a duplicate relationship; the database does not silently merge identities.

### 4.3 `file_instances`

Represents every observed or DocWeave-created physical instance.

| Column | Type | Rule |
| --- | --- | --- |
| `file_instance_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `document_version_id` | `UUID` | Foreign key |
| `storage_kind` | `STRING` | `local` or `s3` initially |
| `root_reference` | `STRING` | Authorized root or bucket reference |
| `relative_path` | `STRING` | Normalized path within the root |
| `path_comparison_key` | `STRING` | Platform-normalized collision key |
| `instance_role` | `STRING` | `original`, `copy`, `organized`, or `restored` |
| `availability_status` | `STRING` | Current observed state |
| `observed_sha256` | `BYTES` | Last verified content |
| `observed_size` | `INT8` | Last verified size |
| `last_verified_at` | `TIMESTAMPTZ` | Nullable |
| `created_by_operation_id` | `UUID` | Nullable provenance |
| `created_at` | `TIMESTAMPTZ` | Required |
| `retired_at` | `TIMESTAMPTZ` | Nullable |

An active-path uniqueness rule covers
`(workspace_id, storage_kind, root_reference, path_comparison_key)` where
`retired_at IS NULL`.

### 4.4 `document_chunks`

| Column | Type | Rule |
| --- | --- | --- |
| `document_chunk_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required vector-index prefix |
| `document_version_id` | `UUID` | Foreign key |
| `chunk_ordinal` | `INT4` | Non-negative and unique per version |
| `page_start` | `INT4` | Nullable |
| `page_end` | `INT4` | Nullable |
| `character_start` | `INT8` | Nullable |
| `character_end` | `INT8` | Nullable |
| `content_text` | `STRING` | Authorized extracted content |
| `content_sha256` | `BYTES` | Chunk fingerprint |
| `extraction_method` | `STRING` | Provenance |
| `embedding` | `VECTOR(N)` | Nullable until an embedding is produced |
| `embedding_model` | `STRING` | Required when `embedding` is present |
| `embedding_version` | `STRING` | Required when `embedding` is present |
| `embedded_at` | `TIMESTAMPTZ` | Required when `embedding` is present |

`N` is deliberately unresolved until the embedding Architecture Decision
Record is approved.

## 5. Taxonomy and proposal tables

### 5.1 `taxonomy_versions`

| Column | Type | Rule |
| --- | --- | --- |
| `taxonomy_version_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `version_label` | `STRING` | Unique within workspace |
| `status` | `STRING` | `draft`, `active`, or `retired` |
| `approved_by_actor_id` | `UUID` | Required before activation |
| `approved_at` | `TIMESTAMPTZ` | Required before activation |
| `created_at` | `TIMESTAMPTZ` | Required |

Only one active taxonomy version is permitted per workspace.

### 5.2 `taxonomy_classes`

| Column | Type | Rule |
| --- | --- | --- |
| `taxonomy_class_id` | `UUID` | Primary key |
| `taxonomy_version_id` | `UUID` | Foreign key |
| `class_code` | `STRING` | Stable within the version |
| `display_name` | `STRING` | Required |
| `definition` | `STRING` | Required |
| `expected_evidence` | `STRING` | Human-readable criteria |
| `is_abstention` | `BOOL` | Distinguishes `unclassified` |
| `sort_order` | `INT4` | Deterministic presentation |

### 5.3 `proposals`

Common identity and provenance for every intelligent recommendation.

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `document_version_id` | `UUID` | Nullable for cross-document proposals |
| `proposal_type` | `STRING` | Classification, organization, relationship, or fact |
| `proposal_status` | `STRING` | Lifecycle state |
| `agent_run_id` | `UUID` | Required provenance |
| `supersedes_proposal_id` | `UUID` | Nullable self-reference |
| `raw_confidence` | `DECIMAL(6,5)` | Zero through one |
| `calibrated_confidence` | `DECIMAL(6,5)` | Nullable, zero through one |
| `confidence_method_version` | `STRING` | Required |
| `created_at` | `TIMESTAMPTZ` | Required |

The database validates that exactly one matching subtype exists through the
proposal-writing service and contract tests. A subtype cannot exist without its
base proposal.

### 5.4 `classification_proposals`

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_id` | `UUID` | Primary and foreign key |
| `taxonomy_version_id` | `UUID` | Required |
| `proposed_class_id` | `UUID` | Required |
| `alternative_class_id` | `UUID` | Nullable |
| `abstention_reason` | `STRING` | Required for abstention |
| `extraction_confidence` | `DECIMAL(6,5)` | Zero through one |
| `classification_confidence` | `DECIMAL(6,5)` | Zero through one |
| `metadata_confidence` | `DECIMAL(6,5)` | Zero through one |
| `contradiction_count` | `INT4` | Non-negative |

### 5.5 `organization_proposals`

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_id` | `UUID` | Primary and foreign key |
| `proposed_filename` | `STRING` | Sanitized but still untrusted |
| `proposed_relative_directory` | `STRING` | Sanitized but still untrusted |
| `organization_confidence` | `DECIMAL(6,5)` | Zero through one |
| `naming_rule_version` | `STRING` | Required |
| `collision_status` | `STRING` | Current preview result |

### 5.6 `relationship_proposals`

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_id` | `UUID` | Primary and foreign key |
| `source_document_id` | `UUID` | Required |
| `target_document_id` | `UUID` | Required and different from source |
| `relationship_type` | `STRING` | Versioned application vocabulary |
| `is_directional` | `BOOL` | Required |
| `relationship_confidence` | `DECIMAL(6,5)` | Zero through one |

### 5.7 `proposal_evidence`

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_evidence_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `proposal_id` | `UUID` | Foreign key |
| `document_chunk_id` | `UUID` | Nullable chunk evidence |
| `evidence_kind` | `STRING` | Span, validator, memory, or contradiction |
| `quoted_text` | `STRING` | Minimized inspectable excerpt |
| `page_number` | `INT4` | Nullable |
| `character_start` | `INT8` | Nullable |
| `character_end` | `INT8` | Nullable |
| `strength` | `DECIMAL(6,5)` | Nullable |
| `created_at` | `TIMESTAMPTZ` | Required |

Evidence cannot consist solely of an opaque raw provider response.

### 5.8 `document_classifications`

Canonical reviewed classification.

| Column | Type | Rule |
| --- | --- | --- |
| `document_classification_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `document_id` | `UUID` | Foreign key |
| `document_version_id` | `UUID` | Foreign key |
| `taxonomy_class_id` | `UUID` | Foreign key |
| `source_proposal_id` | `UUID` | Foreign key |
| `review_decision_id` | `UUID` | Foreign key |
| `supersedes_classification_id` | `UUID` | Nullable self-reference |
| `effective_at` | `TIMESTAMPTZ` | Required |
| `superseded_at` | `TIMESTAMPTZ` | Nullable |

At most one non-superseded classification exists per logical document.

### 5.9 `document_relationships`

Canonical reviewed relationship with source proposal and decision provenance.
Symmetric relations store a deterministic ordered document pair. Directional
relations preserve source and target.

## 6. Candidate and canonical domain tables

### 6.1 `fact_definitions`

Versioned registry of supported candidate fields and their required value type.

### 6.2 `fact_candidates`

| Column | Type | Rule |
| --- | --- | --- |
| `proposal_id` | `UUID` | Primary and foreign key |
| `fact_definition_id` | `UUID` | Required |
| `subject_document_id` | `UUID` | Required |
| `subject_entity_id` | `UUID` | Nullable proposed or existing entity |
| `text_value` | `STRING` | Nullable typed value |
| `numeric_value` | `DECIMAL` | Nullable typed value |
| `date_value` | `DATE` | Nullable typed value |
| `boolean_value` | `BOOL` | Nullable typed value |
| `money_value` | `DECIMAL(19,4)` | Nullable typed value |
| `currency_code` | `STRING(3)` | Required with money |

A `CHECK` constraint requires exactly one value family. The promotion service
and contract tests verify that the chosen family matches the referenced fact
definition.

### 6.3 `domain_entities`

| Column | Type | Rule |
| --- | --- | --- |
| `domain_entity_id` | `UUID` | Primary key |
| `workspace_id` | `UUID` | Required |
| `entity_type` | `STRING` | Approved domain subtype |
| `created_from_proposal_id` | `UUID` | Nullable provenance |
| `created_at` | `TIMESTAMPTZ` | Required |
| `retired_at` | `TIMESTAMPTZ` | Nullable |

Each canonical subtype uses `domain_entity_id` as both primary key and foreign
key. A domain entity has exactly one subtype.

### 6.4 Canonical subtype tables

| Table | Required typed fields |
| --- | --- |
| `projects` | Project code, name, stream, region |
| `suppliers` | Supplier code, display name, synthetic tax identifier |
| `tenders` | Tender identifier, project, issue date |
| `contracts` | Contract number, tender, supplier, dates, value, currency |
| `purchase_orders` | Order number, contract, supplier, date, value, currency |
| `invoices` | Invoice number, supplier, order, dates, taxable amount, tax, total, currency |
| `payments` | Payment reference, invoice, date, amount, currency, method, beneficiary |

Subtype-specific identifiers are unique within a workspace and their relevant
business scope. Monetary consistency uses deterministic validation before
promotion and database checks where the rule is unambiguous.

### 6.5 `document_entity_links`

Links a document to a canonical entity as `represents`, `mentions`,
`supports`, or another approved relation. It retains the source proposal,
review decision, evidence summary, and effective interval.

### 6.6 `fact_promotions`

Append-only provenance connecting an accepted fact candidate to:

- the canonical `domain_entity_id`;
- the canonical field code;
- the authorizing review decision;
- the previous canonical value when superseded; and
- the promotion timestamp.

Canonical typed values remain in subtype tables. `fact_promotions` is
provenance, not an Entity-Attribute-Value replacement.

## 7. Workflow and agent memory

### 7.1 `processing_batches`

Defines bounded scan or analysis work with status, source scope, requested
limits, estimated cost, observed cost, creator, and timestamps.

### 7.2 `batch_items`

One row per document-version task. The unique key
`(processing_batch_id, document_version_id, task_kind)` prevents duplicate work.
State, attempt count, lease owner, lease expiry, and last checkpoint are
indexed for worker claiming.

### 7.3 `workflow_runs`

Stores the durable state-machine execution, configuration versions,
idempotency key, current state, terminal outcome, and correlation identifier.

### 7.4 `workflow_checkpoints`

Append-only checkpoints record workflow state, completed stage, attempt,
minimal typed resume data, and creation time. A checkpoint never claims an
external side effect that has not been verified.

### 7.5 `agent_runs`

Records:

- agent responsibility and contract version;
- parent workflow and optional parent agent run;
- model provider, model, inference profile, and prompt version;
- input and output token counts;
- latency, retry count, and observed cost;
- tool calls and bounded outcome;
- start, completion, and error state; and
- minimized raw technical payload only when retention is approved.

This table supplies episodic memory and evaluation provenance. It is not a log
of hidden model reasoning.

## 8. Review, operations, preferences, and audit

### 8.0 Judged hackathon memory schema

The judge-facing schema is `docweave_judged`. It is intentionally smaller than
the internal technical schema so the CockroachDB memory story can be understood
quickly during judging:

| Table | Purpose |
| --- | --- |
| `documents` | Discovered PDF identity with original and current directory and filename. |
| `agent_runs` | Amazon Bedrock analysis attempt, model, task, status, output JSON, and summary. |
| `proposals` | AI-proposed category, destination folder, filename, confidence, and evidence summary. |
| `human_decisions` | Human approve, reject, or request-change decision. |
| `file_history` | Before-and-after path memory for scan, proposal, approval, rename, move, restore, or blocked events. |
| `document_relationships` | AI-suggested links such as purchase order to invoice or invoice to payment. |

This schema is the primary hackathon demonstration surface. The broader
`docweave` schema remains available as internal implementation scaffolding, but
the judged workflow should first prove the simple loop from document discovery
to agent proposal, human decision, and file history.

### 8.1 `review_decisions`

An append-only decision references one proposal and one authorized human actor.
Decision types include approve, reject, correct, defer, and escalate. A
correction creates a corrected proposal or canonical value; it does not mutate
the original proposal.

### 8.2 `operation_batches`

Groups approved file operations. It records the approving decision, preview
version, scope, status, and aggregate result without hiding per-file outcomes.

### 8.3 `file_operations`

| Column family | Required content |
| --- | --- |
| Identity | Operation ID, workspace, batch, type, idempotency key |
| Subject | Document, version, source instance |
| Intent | Expected source state and intended destination |
| Authorization | Proposal and review-decision references |
| Execution | State, attempts, executor, lease, timestamps |
| Verification | Actual path, size, hash, and observed result |
| Recovery | Compensates-operation reference and reconciliation state |
| Failure | Structured error category and safe diagnostic summary |

The idempotency key is unique per workspace. A restore is a new operation that
references the operation it compensates.

### 8.4 `file_lineage_events`

Append-only file lineage memory records the visible path history required for
safe rename, move, copy, and restore workflows. Each row stores:

- workspace, logical document key, and a positive per-document lineage sequence;
- idempotency key for replay-safe writes;
- action: copy, move, rename, rename and move, or blocked;
- optional proposal, operation batch, file operation, and batch-item references;
- original directory and filename;
- previous directory and filename;
- next directory and filename;
- original, previous, and next relative paths;
- terminal operation status and occurrence time; and
- plan, source-before, and destination-after SHA-256 evidence when available.

The table does not overwrite the active file instance. It is a chronological
memory trail that lets the application explain how a document moved from its
original location to every later approved or blocked state.

### 8.5 `file_path_history`

`file_path_history` is a read-only CockroachDB view over
`file_lineage_events`. It exists to make the path-memory requirement directly
inspectable in CockroachDB Cloud without requiring a reviewer to decode every
technical audit column.

The view exposes the columns a human expects first:

- logical document key and lineage sequence;
- action, status, and occurrence time;
- original directory and filename;
- previous directory and filename;
- next directory and filename;
- original, previous, and next relative paths; and
- optional operation, file-operation, proposal, and lineage event identifiers.

The view is not a second source of truth and is not writable by DocWeave. The
append-only table remains authoritative so every rename, move, copy, blocked
attempt, and restore transition can be replayed without overwriting history.

### 8.6 `cloud_analysis_jobs` and `cloud_analysis_objects`

Cloud analysis memory records the AWS worker observation layer before final
canonical promotion. `cloud_analysis_jobs` stores one workspace-scoped worker
job identity, status, source service, and result-artifact key.
`cloud_analysis_objects` stores the per-S3-object observation:

- deterministic object identity within the workspace and job;
- S3 object key as data, not as executable path authority;
- content SHA-256, byte size, model identifier, proposed class, and confidence
  signal;
- validated proposal JSON and usage JSON; and
- replay-safe uniqueness by job sequence and object key.

This layer is intentionally separate from canonical classifications. It lets
the cloud worker prove that Bedrock analysis happened and that CockroachDB
remembered the observation, while later review and promotion workflows can
decide what becomes authoritative.

### 8.7 `preference_rules`

Controlled preference memory includes scope, version, rule type, structured
condition, structured outcome, provenance decisions, confidence, status,
activation authority, evaluation result, revocation, and supersession.

Preference conditions and outcomes may use validated `JSONB` because their
shape is versioned and rule-specific. Their authority, scope, status, and
provenance remain typed relational columns.

### 8.8 `audit_events`

Append-only material events contain:

- workspace and monotonic event identity;
- actor and correlation identifiers;
- event type and occurred time;
- typed subject kind and identifier;
- prior-event or causation reference;
- minimized structured details;
- integrity-chain predecessor and event digest.

The audit chain is tamper-evident evidence, not a substitute for CockroachDB
authorization or backups.

## 9. Initial indexes

Only indexes required by approved workflows enter the first migration:

| Table | Index purpose |
| --- | --- |
| `workspace_members` | Active membership by workspace and actor |
| `documents` | Workspace, lifecycle status, and recent activity |
| `document_versions` | Workspace hash lookup and version history |
| `file_instances` | Active normalized path and document instances |
| `document_chunks` | Document chunk order and workspace vector retrieval |
| `proposals` | Pending review by type and calibrated confidence |
| `document_classifications` | Current canonical class and class filters |
| `document_relationships` | Both directions of document traversal |
| Domain subtype tables | Approved business identifiers and dates |
| `batch_items` | Claimable pending or retryable tasks |
| `workflow_runs` | Workspace state and idempotency lookup |
| `agent_runs` | Workflow trace, document trace, and cost reporting |
| `file_operations` | Idempotency, executable state, and reconciliation queue |
| `file_lineage_events` | Per-document path history and current-path lookup |
| `file_path_history` | Human-readable path-history inspection view |
| `cloud_analysis_jobs` | Cloud worker status and result-artifact lookup |
| `cloud_analysis_objects` | Per-object cloud analysis observation and class lookup |
| `preference_rules` | Active rules by workspace and scope |
| `audit_events` | Workspace chronological activity and subject history |

Partial indexes cover active rows such as `needs_review`, `pending`,
`failed_retryable`, and `reconciliation_required`.

The vector index will use `workspace_id` as a prefix and cosine distance unless
the approved embedding model requires another metric. It is created on an empty
table during initial migration when possible.

## 10. Transaction boundaries

### 10.1 Register document

Atomically:

1. resolve authorized workspace and source;
2. create or reuse the content version;
3. create or reconcile the file instance;
4. attach the item to the processing batch;
5. append the audit event.

The operation is idempotent for the same discovery key and observed file state.

### 10.2 Persist proposal

Atomically persist the agent run outcome, proposal base row, one subtype,
evidence, checkpoint, and audit event. Invalid structured output creates a
failed run and never a partially authoritative proposal.

### 10.3 Review and promote

Lock the current proposal and relevant canonical subject, verify authorization
and non-supersession, append the review decision, create the canonical result or
fact promotion, supersede prior canonical state where applicable, and append
the audit event.

### 10.4 Prepare file operation

Persist the approved intent, expected source hash and location, destination,
collision result, authorization, and idempotency key before external execution.

### 10.5 Execute and reconcile

Claim one prepared operation with a bounded lease. Revalidate current external
state, execute the approved effect, verify the outcome, and then persist the
actual result. An ambiguous external outcome becomes
`reconciliation_required`, never `completed`.

### 10.6 Restore

Create a compensating operation from verified history. Re-run authorization,
current-state, path, hash, and collision checks. Preserve both the original and
compensating operations.

### 10.7 Serializable retry rule

Transaction functions may retry CockroachDB serialization failures only when:

- all external effects remain outside the retried closure;
- the function has a stable idempotency key;
- generated identifiers are stable across retries where required; and
- every retry rechecks authorization and current state.

## 11. Authorization model

- The API checks product roles before every material command.
- Runtime SQL roles receive only required table and statement privileges.
- Workspace-scoped tables use Row-Level Security as defense in depth.
- Connection checkout sets verified workspace context and connection return
  clears it.
- Table owners and migration roles are not application runtime roles.
- The Managed Model Context Protocol identity is separate, observable, and
  read-only unless a later bounded write workflow is explicitly approved.
- Agents cannot create schemas, alter tables, grant roles, or bypass review.

## 12. Migration sequence

1. Create database namespace, migration role, and application roles.
2. Create access and workspace tables.
3. Create document identity and file-instance tables.
4. Create taxonomy, proposal, evidence, and canonical-result tables.
5. Create domain entities and subtype tables.
6. Create workflow, operation, preference, and audit tables.
7. Add deferred circular foreign keys.
8. Add required secondary and partial indexes.
9. Enable and test Row-Level Security policies.
10. After the embedding decision, add the fixed-dimension vector column and
    vector index if they were not created in the initial empty-table migration.
11. Seed only the reconciled, approved taxonomy and synthetic test workspace.

Each migration requires a clean-database test and a forward-recovery test.

## 13. Deferred implementation parameters

The approved structure does not decide:

- embedding provider, model, dimension, and distance metric;
- initial taxonomy seed rows and version labels beyond the approved baseline;
- retention duration for extracted text and raw provider payloads;
- exact confidence formula and thresholds;
- exact Row-Level Security session-context mechanism;
- partitioning or regional topology;
- physical locality configuration;
- query-specific covering columns before measured plans exist.

These values require evidence and separate approval. They must not be guessed
inside a migration.

## 14. Required schema evidence

Implementation is accepted only with:

- migration tests on an empty database;
- constraint tests for invalid cross-workspace and invalid-state writes;
- transaction retry and contention tests;
- idempotent registration and operation tests;
- proposal-to-canonical provenance queries;
- resume and reconciliation tests;
- Row-Level Security isolation tests;
- vector recall, latency, and workspace-scope measurements;
- query plans for the primary review and activity-history screens; and
- an updated requirements traceability matrix.
