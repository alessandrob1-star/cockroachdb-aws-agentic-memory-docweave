# DocWeave Product Requirements

**Status:** Focused hackathon product  
**Last updated:** 2026-08-08

## Product Goal

DocWeave helps a user turn a messy folder of PDFs into an understandable folder
structure without giving autonomous control to the model.

The product must be explainable in one sentence:

> Select a folder, let Amazon Bedrock read the PDFs, review the proposed names,
> approve the move, and inspect the memory in CockroachDB.

## Primary User

A non-technical operator who has a local folder full of poorly named PDFs and
needs to understand what each file is before renaming or moving it.

## Required Workflow

1. Open the dashboard.
2. Select an authorized folder.
3. See discovered PDFs.
4. Preview a PDF without changing it.
5. Click Analyze.
6. DocWeave extracts text and invokes Amazon Bedrock.
7. CockroachDB records the document, model run, and proposal.
8. The dashboard shows the proposed class, destination folder, filename,
   confidence, and evidence summary.
9. The user approves or rejects.
10. On approval, DocWeave moves/renames the file and records path history.
11. Selecting the moved PDF shows the original filename and original directory.

## CockroachDB Requirement

The demo uses one schema: `docweave`.

| Table | Requirement |
| --- | --- |
| `documents` | Preserve original and current directory/name. |
| `agent_runs` | Preserve Bedrock model run evidence. |
| `proposals` | Preserve the proposed class, folder, filename, confidence, and evidence. |
| `human_decisions` | Preserve the human approve/reject decision. |
| `file_history` | Preserve before/after path movement. |
| `document_relationships` | Preserve optional document links when produced. |

No other schema is required for the hackathon demo.

## AWS Requirement

AWS must be meaningful, not decorative:

- Amazon Bedrock performs document analysis.
- AWS Lambda runs the cloud API and worker.
- Amazon S3 stores uploaded PDFs and result artifacts.
- Amazon SQS queues analysis jobs.
- Amazon API Gateway exposes the cloud HTTP boundary.
- Amazon CloudWatch Logs provides runtime observability.

The AWS worker may persist to CockroachDB only when the CockroachDB secret ARN
is configured.

## Non-Goals For The Hackathon Demo

- Enterprise workspace administration.
- Multi-role team governance.
- Vector search.
- Ten-thousand-file scale proof.
- A 300-PDF evaluation corpus.
- Full restore workflows.
- Broad accounting or procurement data modeling.

These are future-product ideas, not requirements for the focused submission.

## Success Criteria

The project is demo-ready when a judge can understand within 3-4 minutes:

1. what problem DocWeave solves;
2. how the dashboard workflow works;
3. where Amazon Bedrock is used;
4. what CockroachDB remembers;
5. why human approval is required before file movement;
6. how the original filename and original directory remain visible after move.
