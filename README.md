# DocWeave

DocWeave is a human-governed multi-agent document-management system for the
CockroachDB x AWS Hackathon — Build with Agentic Memory.

The product is designed to discover large PDF collections, classify documents,
propose meaningful names and destinations, identify related records, execute
approved copy or move operations, and safely restore prior states. CockroachDB
is the persistent operational, semantic, episodic, and preference memory. The
complete judged product will run on Amazon Web Services.

## Current status

DocWeave is in the approved requirements and architecture phase with an initial
local Python engineering scaffold, deterministic local filesystem discovery
contracts, local content fingerprinting, PDF signature inspection, and
deterministic intake records with duplicate grouping, and safe file-operation
planning, approval, single-operation execution, bounded local batch execution,
per-item results, in-memory idempotency, interrupted-operation reconciliation,
and append-only local audit event contracts. The first non-vector CockroachDB
migration is validated offline and against a clean, isolated live validation
database. The application does not yet connect to that schema, so the local
contracts are not durable persistence. No runtime database integration,
restore, AWS workload, user interface, or intelligent document analysis is
claimed yet.

The current approved product direction includes:

- a complete PySide6 desktop application for authorized Windows folders;
- a complete cloud application using the same production agentic core;
- discovery of up to 10,000 files;
- up to 5,000 actively managed documents per Minimum Viable Product project;
- resumable processing batches of up to 1,000 documents;
- a representative demonstration corpus of approximately 300 synthetic PDFs;
- confidence-driven human review and high-confidence quality sampling;
- safe copy, move, and restore operations with append-only history;
- complete attribution for operators, reviewers, agents, and project managers;
- a relational-first CockroachDB design with meaningful vector retrieval.

## Documentation

Start with the [requirements index](docs/requirements/README.md).

Mandatory governance:

- [Project operating rules](PROJECT_RULES.md)
- [Competition rules and compliance guide](docs/requirements/competition-rules.md)
- [Product requirements](docs/requirements/product-requirements.md)
- [Domain and relational data requirements](docs/requirements/domain-data-requirements.md)
- [Minimum Viable Product scope and acceptance](docs/requirements/mvp-scope-and-acceptance.md)
- [Quality and security charter](docs/requirements/quality-security-charter.md)
- [Requirements traceability matrix](docs/requirements/requirements-traceability-matrix.md)

Approved architecture:

- [Amazon Bedrock primary-model decision](docs/architecture/decisions/0001-amazon-bedrock-primary-model.md)
- [CockroachDB physical-data-model decision](docs/architecture/decisions/0002-cockroachdb-physical-data-model.md)
- [CockroachDB migration-tooling decision](docs/architecture/decisions/0003-cockroachdb-migration-tooling.md)
- [Document-processing pipeline](docs/architecture/document-processing-pipeline.md)
- [CockroachDB physical-schema specification](docs/architecture/cockroachdb-physical-schema.md)
- [CockroachDB Entity Relationship model](docs/architecture/cockroachdb-entity-relationship.md)
- [Verified AWS and CockroachDB environment baseline](docs/operations/environment-baseline.md)
- [CockroachDB live validation evidence](docs/operations/cockroachdb-live-validation.md)
- [Delivery plan](docs/operations/delivery-plan.md)

## Repository policy

- Repository artifacts and submission material are written in English.
- Architecture and implementation require explicit approval.
- Intelligent behavior must be genuine, observable, and evaluated.
- Private reference data, credentials, and real company documents must never be
  committed.
- Material changes are developed on branches and reviewed through pull
  requests.

## Local development

The Python scaffold contains no runtime cloud integration and does not connect
to a database by default. It includes an initial CockroachDB migration that is
rendered and tested offline and whose exact SQL has been accepted by a clean
live validation database. The validation schema is not a runtime or production
deployment. The scaffold establishes reproducible local quality gates before
durable or cloud-connected product behavior is implemented.

Create a virtual environment, install the pinned development tools, and run the
local checks:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\scripts\check.ps1
```

## License

A competition-compatible open-source license will be selected explicitly before
the repository is made public. No license is implied at this stage.
