# MVP Scope and Acceptance

**Status:** Hackathon rescue scope  
**Last updated:** 2026-08-08

## MVP Definition

The Minimum Viable Product is the smallest honest workflow that proves
DocWeave's idea:

```text
Folder -> Bedrock analysis -> CockroachDB memory -> human approval -> moved PDF
```

## In Scope

- PySide6 dashboard.
- Local authorized folder selection.
- PDF discovery and preview.
- Real text extraction.
- Real Amazon Bedrock classification.
- Proposed category, folder, and filename.
- Human approve or reject.
- File move/rename only after approval.
- CockroachDB memory in the six-table `docweave` schema.
- AWS cloud API and worker using S3, SQS, Lambda, API Gateway, CloudWatch, and
  Bedrock.

## Acceptance Tests

### AC-001 - Folder Is Understandable

Given a messy PDF folder, when the user opens the dashboard, then the user sees
the folder contents and can select a PDF for preview.

### AC-002 - Analyze Uses Real Intelligence

Given a selected PDF, when the user runs Analyze, then DocWeave extracts text,
invokes Amazon Bedrock, and stores a proposal in CockroachDB.

### AC-003 - Human Approval Gates File Movement

Given a proposal, when the user approves it, then DocWeave validates and moves
or renames the file. Without approval, no file movement occurs.

### AC-004 - Original Path Remains Visible

Given an approved moved PDF, when the user selects it later, then the dashboard
and CockroachDB can show the original directory, original filename, current
directory, and current filename.

### AC-005 - CockroachDB Is Explainable

Given the live database, when a judge opens CockroachDB Console, then the
schema contains the six expected `docweave` tables and no extra demo schema is
needed to understand the product.

### AC-006 - AWS Is Honest

Given the deployed cloud stack, when `/health` is called, then AWS service
readiness is reported honestly. If CockroachDB secret configuration is missing,
the product must say so instead of claiming cloud persistence.

## Out Of Scope

- Vector retrieval.
- Enterprise team roles.
- Bulk restore.
- Large corpus evaluation.
- Autonomous file changes.
- Any canned or fake classification result.

## Release Blockers

- Bedrock classification is unavailable and hidden behind a fake result.
- CockroachDB rows are not created for Analyze.
- File movement can happen without approval.
- Original path memory is not visible.
- README or submission text describes features not present in the demo.
