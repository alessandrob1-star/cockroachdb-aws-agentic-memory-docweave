# CockroachDB Live Validation Evidence

**Project:** DocWeave
**Validation date:** 2026-07-24
**Revision:** `0001_operational_foundation`
**Result:** Passed within the stated boundary

## 1. Scope

This record preserves sanitized evidence for the first live acceptance of a
DocWeave migration. It contains no cluster identifier, account identifier,
endpoint, connection URL, password, payment detail, or private identity value.

The validation used:

- the existing CockroachDB Cloud Basic cluster on AWS `eu-central-1`;
- an isolated clean database named `docweave_validation`;
- the authenticated CockroachDB Cloud SQL Shell;
- the project-owner-approved root or administrator predevelopment mode; and
- the exact SQL rendered by Alembic from the repository migration head.

The project owner deferred least-privilege migration and runtime profiles to a
later separately approved phase. No root or administrator credential is
approved for application runtime use.

## 2. Cost preflight

Before mutation, the console reported:

| Metric | Observed value |
| --- | --- |
| Request Units used | 80.59 thousand of 50 million |
| Storage used | 3.31 MiB of 10 GiB |
| Gross current-period amount | 0.02 USD |
| Credits applied | 0.02 USD |
| Accumulated payable total | 0.00 USD |
| Other organization clusters | None |

The organization has a payment method, so the configured limits remain a
required control. The user approved the small live consumption only within the
existing limits and did not authorize paid CockroachDB usage.

## 3. Executed artifact

The offline render reported the CockroachDB dialect and non-transactional Data
Definition Language semantics. The rendered SQL:

- contained 14,886 characters;
- had SHA-256
  `3b686fb99a3451ee481e00b1d4bb819bb6af0ff489180ab6c0ad1659f6f8444a`;
- contained no `BEGIN` or `COMMIT`;
- contained no connection URL; and
- contained no password field.

The first submission included a `USE` statement for target selection. The
Cloud SQL Shell rejected that first statement as a disallowed statement type,
so no migration Data Definition Language statement ran. Catalog inspection
then confirmed that the selected validation database still contained zero
DocWeave tables and no Alembic version table.

The database was selected through the Cloud SQL Shell database control. The
unchanged rendered migration SQL was then accepted successfully.

## 4. Catalog evidence

Post-migration catalog inspection reported:

| Evidence | Result |
| --- | --- |
| Current database | `docweave_validation` |
| Alembic revision | `0001_operational_foundation` |
| DocWeave tables | 6 |
| Required tables present | 6 of 6 |
| Table constraints exposed by the catalog | 130 |
| Indexes exposed by the catalog | 23 |
| Selected critical constraints present | 12 of 12 |
| Explicit migration indexes present | 6 of 6 |

The required tables are:

- `workspaces`;
- `actors`;
- `workspace_members`;
- `operation_batches`;
- `file_operations`; and
- `audit_events`.

This proves live acceptance of the initial schema shape. It does not prove
revisions `0002_classification_memory` or `0003_review_decision_memory`, vector
indexing, Row-Level Security, runtime roles, or application integration.

## 5. Invalid-state evidence

Two deliberately invalid single-statement inserts were attempted:

1. an unsupported workspace status; and
2. an unsupported actor type.

Both were rejected with SQLSTATE `23514` check-constraint failures. A final
row-count query confirmed zero rows in all six DocWeave tables. No test data,
document content, or private data was persisted.

## 6. Observed resource result

After validation, the console reported:

| Metric | Observed value |
| --- | --- |
| Request Units used | 85.94 thousand of 50 million |
| Storage used | 3.88 MiB of 10 GiB |
| Gross current-period amount | 0.02 USD |
| Accumulated payable total | 0.00 USD |

The observed differences were 5.35 thousand Request Units and 0.57 MiB.
Background and monitoring activity can also affect these provider metrics, so
the differences are not claimed as exact per-migration attribution.

## 7. Remaining non-claims and gates

This validation does not prove:

- online Alembic execution through Psycopg;
- secret delivery or certificate handling;
- application reads or writes;
- serializable retry behavior;
- workspace isolation or Row-Level Security;
- foreign-key and cross-workspace failure behavior beyond catalog inspection;
- persistent batch reconciliation;
- Distributed Vector Indexing; or
- competition-qualifying meaningful memory integration.

Each future live migration still requires a target, cost, identity, recovery,
and explicit approval gate.

## 8. Current head status as of 2026-07-30

The current repository migration head is `0003_review_decision_memory`. Offline
rendering from an empty database to `head` was verified locally, including all
three ordered revisions. Live acceptance of revisions `0002` and `0003` remains
pending.

The runtime preflight command fails closed when `DOCWEAVE_DATABASE_URL` is not
present. That is the expected safe behavior and proves no live database
operation occurred from an unconfigured process.
