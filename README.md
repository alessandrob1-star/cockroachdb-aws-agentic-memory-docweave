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
planning contracts. No file mutation, database migration, deployed schema,
cloud integration, or intelligent document analysis is claimed yet.

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
- [Document-processing pipeline](docs/architecture/document-processing-pipeline.md)
- [CockroachDB physical-schema specification](docs/architecture/cockroachdb-physical-schema.md)
- [CockroachDB Entity Relationship model](docs/architecture/cockroachdb-entity-relationship.md)
- [Verified AWS and CockroachDB environment baseline](docs/operations/environment-baseline.md)
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

The initial Python scaffold contains no runtime cloud integration and no
database migration. It exists to establish reproducible local quality gates
before product behavior is implemented.

Create a virtual environment, install the pinned development tools, and run the
local checks:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pip install -e .
.\scripts\check.ps1
```

## License

A competition-compatible open-source license will be selected explicitly before
the repository is made public. No license is implied at this stage.
