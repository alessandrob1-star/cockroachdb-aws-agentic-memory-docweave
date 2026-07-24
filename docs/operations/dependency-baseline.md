# Dependency Baseline

**Project:** DocWeave
**Last updated:** 2026-07-24
**Status:** Initial pinned inventory; release review pending

## 1. Purpose

This inventory records direct dependencies introduced for the CockroachDB
migration foundation. It supports reproducible installation and third-party
license review. It is not yet the release Software Bill of Materials or final
license-policy approval.

## 2. Direct migration and persistence dependencies

| Package | Version | Role | Declared license |
| --- | --- | --- | --- |
| Alembic | 1.18.5 | Versioned schema migrations and offline SQL rendering | MIT |
| SQLAlchemy | 2.0.51 | Typed SQL and connection foundation | MIT |
| sqlalchemy-cockroachdb | 2.0.4 | CockroachDB SQLAlchemy dialect | Apache-2.0 |
| psycopg | 3.3.4 | PostgreSQL wire-protocol driver | LGPL-3.0-only |
| psycopg-binary | 3.3.4 | Pinned binary driver distribution | LGPL-3.0-only |

License values were read from installed package metadata after installation.
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

No dependency receives credentials automatically. Alembic requires an explicit
runtime database URL for online work, and migrations do not run during normal
application import or startup.
