# ADR-0002: CockroachDB Physical Data Model

**Status:** Accepted for the hackathon submission
**Decision date:** 2026-08-08
**Decision owner:** Project owner

## Context

Judges and interviewers must understand DocWeave in a few minutes:

1. choose a folder in the dashboard;
2. analyze PDFs with Amazon Bedrock;
3. store the original file identity and model proposal in CockroachDB;
4. approve a safe rename or move;
5. inspect where the approved file came from.

Earlier designs had too many tables for the current product story. They made
the repository harder to explain and weakened the demo narrative.

## Decision

DocWeave uses one CockroachDB schema named `docweave` with six tables:

| Table | Purpose |
| --- | --- |
| `documents` | Original path, current path, digest, page count, and file status. |
| `agent_runs` | Bedrock model provenance and sanitized output for one analysis. |
| `proposals` | Proposed class, destination folder, destination filename, confidence, and evidence summary. |
| `human_decisions` | Human approve or reject decision for a proposal. |
| `file_history` | Before and after path memory for approved file changes. |
| `document_relationships` | Optional lightweight links between documents. |

There is no separate judged schema, hidden demo schema, compatibility view, or
secondary table family for the current submission.

## Consequences

- The cockpit, command-line checks, CockroachDB console, and AWS cloud worker
  all point at the same memory model.
- Original and current paths are first-class fields, so a renamed PDF can still
  be traced back to its source directory and filename.
- Model output stays non-authoritative until a human decision is recorded.
- Advanced retrieval, canonical business entities, and long-running operation
  ledgers are out of scope for this submission unless a future approved product
  iteration reintroduces them with a clear user-facing reason.

## Verification

Acceptance requires:

1. Alembic has one head: `0001_simple_docweave_schema`.
2. Offline migration SQL creates exactly the six current tables.
3. Runtime preflight reports the same six-table schema.
4. A real analysis writes `documents`, `agent_runs`, and `proposals`.
5. A real approval writes `human_decisions` and `file_history`.
