# Devpost Submission Draft

Use this as copy-ready submission text. Replace `TODO_VIDEO_URL` only after the
public YouTube or Vimeo video is uploaded.

## Project Name

DocWeave

## Tagline

An agentic glass dashboard for massive PDF renaming and reorganization for
SMEs: Bedrock proposes, humans approve, and CockroachDB remembers every move.

## Project Description

DocWeave solves a concrete small and medium-sized enterprise (SME) problem:
massive Portable Document Format (PDF) renaming and reorganization.

A user opens the glass-effect desktop dashboard, chooses a chaotic folder full
of opaque PDF names like `scan_000184.pdf`, `attachment_081.pdf`, and
`document_final_02.pdf`, and asks the document agents to reorganize it. The app
extracts text from each PDF, sends evidence to Amazon Bedrock, classifies the
document, proposes a clearer filename, and suggests a destination folder.

The model cannot rename or move files by itself. The user can approve all
proposals, approve only selected rows, reject individual rows, or reopen the
PDF preview before deciding. CockroachDB is the system of record for the
persistent memory agent: it stores original paths, current paths, extracted
evidence, Bedrock runs, proposals, human decisions, and file-history records.

That restore memory is the practical point of the project. After a massive
cleanup, DocWeave can still answer: "What was this PDF called before, where did
it come from, why was it moved, and how do I restore it?"

## What It Does

- Scans a user-selected folder of synthetic or real PDFs.
- Extracts document text and previews the PDF in the dashboard.
- Uses Amazon Bedrock to classify each document and propose a safer filename
  and destination folder.
- Persists document state, model runs, proposals, human decisions, and restore
  history in CockroachDB.
- Lets the user approve/reject single rows, approve selected files, or approve
  the full batch.
- Moves approved PDFs into readable folders such as
  `DocWeave Organized/Invoices`.
- Restores renamed PDFs back to their original filename and directory using
  CockroachDB file-history memory.

## CockroachDB Tools Used

1. `ccloud` CLI

   DocWeave uses `ccloud` evidence scripts to verify the live CockroachDB Cloud
   serverless cluster `docweave-memory`, its AWS region, SQL users, status, and
   operational readiness. This is part of the judge-facing proof that the
   project is backed by a real CockroachDB Cloud memory layer, not a local demo
   table.

2. CockroachDB Agent Skills repository

   The project uses CockroachDB Agent Skills guidance for schema and
   transaction design. The memory layer follows CockroachDB-oriented patterns:
   stable primary keys, idempotent writes, append-only human decision records,
   proposal locking, restore-safe file history, and bounded retry handling for
   serializable transaction conflicts.

DocWeave does not claim CockroachDB Managed MCP Server or Distributed Vector
Indexing in the current submission.

## AWS Services Used

- Amazon Bedrock: classifies documents and produces structured rename/move
  proposals from extracted PDF evidence.
- AWS Lambda: runs the cloud API and asynchronous analysis worker.
- Amazon S3: stores uploaded PDF artifacts and JSON analysis results.
- Amazon SQS: queues analysis jobs between the API and worker.
- Amazon API Gateway: exposes the public cloud health, upload, job, and result
  endpoints.
- Amazon CloudWatch Logs: records Lambda execution and operational evidence.
- AWS Secrets Manager dynamic references: wires the CockroachDB runtime URL into
  AWS without committing database credentials.

## Built With

Python, PySide6, CockroachDB Cloud, `ccloud` CLI, CockroachDB Agent Skills,
Amazon Bedrock, AWS Lambda, Amazon S3, Amazon SQS, Amazon API Gateway, Amazon
CloudWatch Logs, AWS Secrets Manager, CloudFormation, pypdf, pytest.

## Repository

https://github.com/alessandrob1-star/cockroachdb-aws-agentic-memory-docweave

## Functional Demo App URL

DocWeave is desktop-first. The public AWS demo endpoint proves the deployed
cloud slice is live:

https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev/health

Live cloud proof result:

https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev/analysis-results/55555555-5555-4555-8555-555555555555?workspace_id=11111111-1111-4111-8111-111111111111

Judges can run the dashboard locally from the public repository using the
testing instructions below.

## Demo Video URL

TODO_VIDEO_URL

## Testing Instructions

Run the desktop dashboard:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\docweave-desktop.exe
```

Suggested test flow:

1. Choose `pdf_sintetici`.
2. Scan PDFs.
3. Analyze PDFs.
4. Open PDF preview and inspect the proposal evidence.
5. Click Approve to review the batch table.
6. Approve or reject individual proposals, or approve all.
7. Click Restore to see original filenames and original directories from
   CockroachDB memory.
8. Restore one row or restore all.

Additional test instructions:

https://github.com/alessandrob1-star/cockroachdb-aws-agentic-memory-docweave/blob/main/docs/submission/testing-instructions.md

## What Makes It Agentic

DocWeave has separate responsibilities that behave like a document operations
team: discovery, extraction, classification, proposal, human-governed decision,
file movement, and memory-based restore. CockroachDB gives those agents durable
shared memory, so every action can be audited, replayed, and reversed.

## Challenges

The hardest part was avoiding a flashy demo that silently loses user trust. A
file-management agent is dangerous if it renames and moves hundreds of PDFs
without memory, so the schema had to preserve original names, original
directories, current paths, proposal evidence, human decisions, and restore
records. The AWS worker also had to prove that Bedrock classification and
CockroachDB persistence work together from the deployed cloud environment.

## Accomplishments

- A working glass-effect dashboard for end-to-end folder cleanup.
- A CockroachDB memory schema that supports audit and restore, not just logging.
- A live AWS deployment using Bedrock, Lambda, S3, SQS, API Gateway, CloudWatch,
  and Secrets Manager dynamic references.
- 100 synthetic PDFs with deliberately poor filenames for repeatable judging.
- Local test suite: 552 tests passing with 87% coverage on the latest verified
  run.

## What's Next

- Add managed multi-user workspaces.
- Add optional semantic related-document retrieval once Distributed Vector
  Indexing is implemented deeply enough to claim it honestly.
- Add richer restore policies for partial folder rollbacks.
- Package the desktop dashboard as a signed Windows installer.
