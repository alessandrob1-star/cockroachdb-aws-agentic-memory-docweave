# Requirements Traceability Matrix

**Project:** DocWeave
**Last updated:** 2026-07-23
**Status vocabulary:** Not started, Planned, In progress, Verified, Blocked

## 1. Purpose

This matrix connects each material requirement to a control and evidence. A
feature is not complete because code exists; it is complete when its evidence
is reproducible.

## 2. Competition requirements

| ID | Requirement | Planned control | Required evidence | Status |
| --- | --- | --- | --- | --- |
| COMP-001 | New project created during the submission period | Preserve repository creation history and disclose reused work | Git history and disclosure section | Verified for repository origin; ongoing for incorporated work |
| COMP-002 | Agentic application | Explicit multi-agent responsibilities, tools, memory, and handoffs | Runtime traces and end-to-end demo | Planned |
| COMP-003 | CockroachDB is persistent memory | Transactional, semantic, episodic, preference, and audit memory in CockroachDB | Schema, queries, traces, and demo | Planned |
| COMP-004 | Deployed on AWS | Reproducible Infrastructure as Code deployment | Deployment output and public demo URL | Planned |
| COMP-005 | At least two CockroachDB tools | Managed Model Context Protocol Server and Distributed Vector Indexing; optional Agent Skills | Per-tool implementation and demo evidence | Planned |
| COMP-006 | At least one AWS service | Amazon Bedrock and Amazon Simple Storage Service, plus approved compute | Runtime traces and architecture evidence | Planned |
| COMP-007 | Components meaningfully integrated | Each service supports a real user or agent workflow | Integration tests and video steps | Planned |
| COMP-008 | Consistent installation and operation | Pinned dependencies, setup automation, smoke tests, health checks | Clean-machine test report | In progress |
| COMP-009 | Public open-source repository | Public GitHub repository with approved license and complete source | Public URL and license detection | Planned |
| COMP-010 | Functional demo | Public, free, stable deployment through judging | URL, uptime evidence, testing instructions | Planned |
| COMP-011 | Video under three minutes | Scripted demonstration of product and CockroachDB memory | Public YouTube or Vimeo URL | Planned |
| COMP-012 | English submission | English README, text, video narration or captions, and instructions | Submission review checklist | Planned |
| COMP-013 | Authorized third-party use | Dependency, data, media, trademark, and model license inventory | Software Bill of Materials and attribution file | Planned |
| COMP-014 | Truthful submission | Claims generated from verified release evidence | Final validation report and tagged release | Planned |

## 3. Judging criteria

| ID | Criterion | DocWeave evidence goal | Status |
| --- | --- | --- | --- |
| JUDGE-001 | Agentic Memory Design | Production-relevant CockroachDB state, vectors, provenance, relationships, decisions, and audit trail | Planned |
| JUDGE-002 | Technological Implementation | Safe integrations, tested agent contracts, query and retrieval quality, observability, and reproducibility | Planned |
| JUDGE-003 | Real-World Impact | Measured reduction in document triage effort and improved discoverability with human control | Planned |
| JUDGE-004 | Product Readiness | Security, resilience, access control, scalability, failure behavior, operations, and cost evidence | Planned |
| JUDGE-005 | Creativity and Originality | Multi-agent document memory and relationship reasoning beyond a chatbot or conventional file organizer | Planned |

## 4. Governance and integrity

| ID | Requirement | Control | Evidence | Status |
| --- | --- | --- | --- | --- |
| GOV-001 | Explain before new initiatives | Mandatory approval protocol in `PROJECT_RULES.md` and `AGENTS.md` | Recorded user approval | Verified |
| GOV-002 | English repository artifacts | Repository convention | Documentation and naming review | In progress |
| GOV-003 | Expand acronyms for learning | Documentation and communication convention | Review checklist | Verified as policy |
| GOV-004 | No fabricated intelligence or success | Integrity rules and evaluation evidence | Tests, traces, and limitation disclosures | Planned |
| GOV-005 | Architecture decisions are recorded | Architecture Decision Record process | `docs/architecture/decisions/0001-amazon-bedrock-primary-model.md` and `docs/architecture/decisions/0002-cockroachdb-physical-data-model.md` | In progress |
| GOV-006 | Claims require evidence | Release evidence matrix | Final validation report | Planned |

## 5. Quality controls

| ID | Requirement | Automated control | Evidence | Status |
| --- | --- | --- | --- | --- |
| QUAL-001 | Formatting and linting | Language-specific formatter and linter | Continuous Integration logs | In progress |
| QUAL-002 | Static type safety | Strict type checker | Continuous Integration logs | In progress |
| QUAL-003 | Unit tests | Test runner with coverage | Test and coverage reports | In progress |
| QUAL-004 | Integration and contract tests | Real CockroachDB and mocked or sandboxed AWS boundaries as appropriate | Integration report | Planned |
| QUAL-005 | End-to-end critical journeys | Browser and service end-to-end suite | Video and machine-readable report | Planned |
| QUAL-006 | Agent regression evaluation | Versioned corpus and evaluation runner | Evaluation report | Planned |
| QUAL-007 | Resilience testing | Failure injection, retries, idempotency, and recovery tests | Resilience report | Planned |
| QUAL-008 | Accessibility | Automated scanner plus manual keyboard and screen review | Web Content Accessibility Guidelines checklist | Planned |
| QUAL-009 | Reproducible setup | Pinned dependencies, containers, and clean-machine smoke test | Setup validation artifact | Planned |
| QUAL-010 | Benchmark parity | Compare gates and evidence with AI Act benchmark | Benchmark comparison report | In progress |

## 6. Security controls

| ID | Requirement | Automated or design control | Evidence | Status |
| --- | --- | --- | --- | --- |
| SEC-001 | Threat model before sensitive implementation | Data-flow and threat analysis | Approved threat model | Planned |
| SEC-002 | No committed secrets | Pre-commit and full-history secret scanning | Scanner report | Planned |
| SEC-003 | Dependency security | Software Composition Analysis and pinned lock files | Vulnerability report | Planned |
| SEC-004 | Static application security | Static Application Security Testing | Scanner report | Planned |
| SEC-005 | Supply-chain inventory | CycloneDX Software Bill of Materials | Release artifact | Planned |
| SEC-006 | Infrastructure security | Infrastructure as Code scanning | Scanner report | Planned |
| SEC-007 | Container security | Image scanning and non-root runtime | Image report | Planned |
| SEC-008 | Least privilege | Dedicated human, deployment, and runtime identities | Identity and Access Management policy review | Planned |
| SEC-009 | Secure secrets | Runtime secret resolution and no plaintext storage | Configuration test and audit evidence | Planned |
| SEC-010 | Secure uploads | Type, signature, size, structure, malware, and quarantine controls | Malicious-file test suite | Planned |
| SEC-011 | Prompt injection resistance | Instruction-data separation and adversarial evaluations | Red-team report | Planned |
| SEC-012 | Memory poisoning resistance | Provenance, trust labels, quarantine, revocation, and retrieval authorization | Memory attack evaluation | Planned |
| SEC-013 | Tool misuse prevention | Allowlisted tools, typed arguments, scoped identities, and approval gates | Authorization tests and audit traces | Planned |
| SEC-014 | Human approval for material actions | Review decision and execution state machine | End-to-end tests | Planned |
| SEC-015 | Immutable originals and audit | Content hashes, versioned objects, append-only events | Integrity tests and demo | Planned |
| SEC-016 | Data protection | Encryption, minimization, retention, and deletion controls | Policy and configuration evidence | Planned |
| SEC-017 | Incident and recovery readiness | Alarm, rollback, backup, and incident runbooks | Recovery exercise report | Planned |

## 7. Initial environment readiness

| ID | Item | Current evidence | Status |
| --- | --- | --- | --- |
| ENV-001 | Local repository | `D:\repo\cockroachdb-aws-agentic-memory-docweave` | Verified |
| ENV-002 | CockroachDB Cloud cluster | `docweave-memory`, CockroachDB Cloud Basic on AWS Frankfurt with free-resource limits | Verified environment only; application schema not created |
| ENV-003 | CockroachDB Managed Model Context Protocol connection | OAuth connection configured and previously queried | Verified environment only; product integration pending |
| ENV-004 | AWS authentication | AWS Command-Line Interface login verified | Verified environment only |
| ENV-005 | AWS Model Context Protocol | Proxy handshake and read-only region query succeeded | Verified environment only; product integration pending |
| ENV-006 | AWS budget ceiling | AWS Free plan and `DocWeave-Total-Cost` custom total budget at 80 USD with actual and forecast alerts | Verified control; credits do not increase authorization |
| ENV-007 | Amazon Bedrock primary profile | European Claude Sonnet 4.6 inference profile active in `eu-central-1` | Verified availability only; invocation and product integration pending |
| ENV-008 | Environment baseline | `docs/operations/environment-baseline.md` | Verified on 2026-07-23; re-verification required before deployment |

## 8. Product behavior

| ID | Requirement group | Primary specification | Required evidence | Status |
| --- | --- | --- | --- | --- |
| PROD-001 | Safe workspace discovery and differential rescan | `product-requirements.md` FR-001–FR-006 | Discovery, restart, and differential-scan tests | Planned |
| PROD-002 | Stable logical document and physical-instance identity | `product-requirements.md` FR-007–FR-010 | Identity, copy, move, and version tests | Planned |
| PROD-003 | Explainable analysis, classification, naming, and relationships | `product-requirements.md` FR-011–FR-017, `domain-data-requirements.md` taxonomy baseline, and `classification-and-confidence-specification.md` | Curated-corpus evaluation and trace evidence | Planned |
| PROD-004 | Confidence-driven and sampled human review | `product-requirements.md` FR-018–FR-024 | User-flow tests and calibration report | Planned |
| PROD-005 | Safe copy, move, resume, and restore | `product-requirements.md` FR-025–FR-034 | Failure-injection and end-to-end tests | Planned |
| PROD-006 | Team roles and append-only Activity History | `product-requirements.md` FR-035–FR-040 | Authorization and audit tests | Planned |
| PROD-007 | Four persistent memory classes in CockroachDB | `product-requirements.md` FR-041–FR-046 | Schema, retrieval, authorization, and demo evidence | Planned |
| PROD-008 | Complete desktop and cloud product parity | `product-requirements.md` FR-047–FR-050 | Cross-surface contract and end-to-end tests | Planned |
| PROD-009 | Bounded memory and database stewardship agent | `product-requirements.md` FR-051–FR-054 | Tool-authorization, provenance, anomaly, and audit tests | Planned |
| PROD-010 | Relational-first domain data and safe synthetic provenance | `product-requirements.md` FR-055–FR-060 and `domain-data-requirements.md` | Schema, constraints, provenance checks, and corpus audit | Planned |
| PROD-011 | Approved physical CockroachDB data model | `docs/architecture/decisions/0002-cockroachdb-physical-data-model.md`, physical-schema specification, and Entity Relationship model | Migration, constraint, transaction, authorization, vector, and provenance tests | Planned; design approved |

## 9. Capacity baseline

| ID | Requirement | Target | Required evidence | Status |
| --- | --- | ---: | --- | --- |
| CAP-001 | Source-folder discovery | 10,000 files | Responsive discovery, restart, and reconciliation test | Planned |
| CAP-002 | Active documents per MVP project | 5,000 files | Sorting, filtering, review, and persistence test | Planned |
| CAP-003 | Maximum processing batch | 1,000 files | Checkpoint, interruption, resume, and duplicate-request test | Planned |
| CAP-004 | Primary demonstration and evaluation corpus | Approximately 300 PDFs | Curated corpus, reference labels, license manifest, and evaluation report | Planned |

## 10. MVP acceptance baseline

| ID | Acceptance area | Specification | Required evidence | Status |
| --- | --- | --- | --- | --- |
| MVP-001 | Repeated scan and safe resume | AC-001, AC-002 | Automated end-to-end and fault-injection evidence | Planned |
| MVP-002 | Confidence review and quality sampling | AC-003, AC-004 | User-flow tests and calibration evidence | Planned |
| MVP-003 | Identity-safe move and copy | AC-005, AC-006 | Filesystem and persistence integrity tests | Planned |
| MVP-004 | Collision and individual restore | AC-007–AC-009 | Cross-platform operation tests | Planned |
| MVP-005 | Batch restore and accountability | AC-010, AC-011 | Role, audit, and partial-failure tests | Planned |
| MVP-006 | Visible persistent agentic memory | AC-012 | Trace, database, restart, and demo evidence | Planned |
| MVP-007 | Real desktop and cloud core | AC-013 | Deployment and parity evidence | Planned |
| MVP-008 | 10,000-file scale discovery | AC-014 | Performance and reconciliation report | Planned |

## 11. Update rule

Update this matrix in the same change that implements, verifies, rejects, or
re-scopes a requirement. `Verified` requires a link or path to current evidence.
