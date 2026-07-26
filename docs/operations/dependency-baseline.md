# Dependency Baseline

**Project:** DocWeave
**Last updated:** 2026-07-26
**Status:** Pinned persistence, desktop, and Bedrock inventory; release review pending

## 1. Purpose

This inventory records direct dependencies introduced for the CockroachDB
persistence foundation, PySide6 desktop surface, and Amazon Bedrock gateway. It
supports reproducible installation and third-party license review. It is not
yet the release Software Bill of Materials or final license-policy approval.

## 2. Direct migration and persistence dependencies

| Package | Version | Role | Declared license |
| --- | --- | --- | --- |
| Alembic | 1.18.5 | Versioned schema migrations and offline SQL rendering | MIT |
| SQLAlchemy | 2.0.51 | Typed SQL and connection foundation | MIT |
| sqlalchemy-cockroachdb | 2.0.4 | CockroachDB SQLAlchemy dialect | Apache-2.0 |
| psycopg | 3.3.4 | PostgreSQL wire-protocol driver | LGPL-3.0-only |
| psycopg-binary | 3.3.4 | Pinned binary driver distribution | LGPL-3.0-only |
| PySide6 | 6.11.1 | Official Qt 6 Python bindings for the desktop application | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6-Addons | 6.11.1 | Qt modules required transitively by PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6-Essentials | 6.11.1 | Core Qt modules required transitively by PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.11.1 | Python binding support required transitively by PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| boto3 | 1.43.56 | AWS Software Development Kit for Python and Bedrock client | Apache-2.0 |
| botocore | 1.43.56 | AWS request, retry, credential, and service-model runtime | Apache-2.0 |
| jmespath | 1.1.0 | boto3 response-query dependency | MIT |
| s3transfer | 0.19.2 | boto3 transitive transfer dependency | Apache-2.0 |
| python-dateutil | 2.9.0.post0 | botocore date and time dependency | Apache-2.0 OR BSD-3-Clause |
| six | 1.17.0 | python-dateutil compatibility dependency | MIT |
| urllib3 | 2.7.0 | botocore HTTP transport dependency | MIT |

License values were read from installed package metadata after installation.
The PySide6 license expression and Python compatibility were also checked
against the current official package metadata before adoption.
The release process must independently verify source distributions, notices,
transitive dependencies, compatibility with the selected DocWeave license, and
the generated Software Bill of Materials.

## 3. Reproducibility files

- `requirements.txt` records direct runtime dependencies.
- `requirements-dev.txt` records direct development and migration tooling.
- `requirements-lock.txt` pins the resolved local and Continuous Integration
  environment, including transitive packages.
- `pyproject.toml` records installable package metadata.

The lock file currently pins versions but not artifact hashes. Hash locking,
vulnerability scanning, license scanning, and automated update policy remain
release-gate work.

## 4. Security boundary

Alembic requires an explicit runtime database URL for online work, and
migrations do not run during normal application import or startup. The
Bedrock module creates no client during import. Its explicit client factory
uses the standard AWS credential provider chain and accepts no credential
values. Automated tests inject a fake Converse transport and make no AWS call.
