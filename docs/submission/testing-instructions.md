# Testing Instructions

DocWeave is a desktop-first hackathon project with an AWS cloud API slice.

For a clean-machine setup, CockroachDB Cloud database creation, Amazon Bedrock
access, and optional deployment of every AWS service, follow the
[`complete installation guide`](../complete-installation-guide.md).

## What To Test First

Use the public synthetic corpus in `pdf_sintetici`. It contains 100 fake PDFs
with deliberately poor filenames so the dashboard can demonstrate the core
product loop:

```text
Choose folder -> Scan PDFs -> Analyze -> Review proposals -> Approve moves -> Restore from CockroachDB memory
```

## Functional Demo URLs

Cloud API health endpoint:

```text
https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev/health
```

Public repository:

```text
https://github.com/alessandrob1-star/cockroachdb-aws-agentic-memory-docweave
```

## Local Dashboard Test

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\docweave-desktop.exe
```

To run live analysis, set the variables documented in [`.env.example`](../../.env.example)
in the current shell, authenticate to AWS, and initialize the schema:

```powershell
$env:DOCWEAVE_DATABASE_URL = "cockroachdb+psycopg://USER:PASSWORD@HOST:26257/docweave?sslmode=verify-full"
$env:DOCWEAVE_WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
$env:DOCWEAVE_TAXONOMY_VERSION_ID = "22222222-2222-4222-8222-222222222222"
$env:DOCWEAVE_APPROVED_BY_ACTOR_ID = "33333333-3333-4333-8333-333333333333"
$env:AWS_PROFILE = "YOUR_AWS_PROFILE"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\docweave-runtime-preflight.exe --database
```

The AWS identity needs Amazon Bedrock model invocation access in
`eu-central-1`. Do not commit real database credentials or AWS keys.

Demo flow:

1. Choose `pdf_sintetici`.
2. Scan the folder.
3. Analyze PDFs.
4. Open one document in review.
5. Approve a proposed rename/move.
6. Open the batch review table and approve or reject rows.
7. Select a moved PDF and inspect original/current path memory.
8. Click Restore to see the restore table driven by CockroachDB file history.

## CockroachDB Memory Evidence

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-schema.exe --flat
.\.venv\Scripts\docweave-memory-evidence.exe
```

Expected schema:

```text
docweave.documents
docweave.agent_runs
docweave.proposals
docweave.human_decisions
docweave.file_history
docweave.document_relationships
```

## CockroachDB Tool Evidence

```powershell
.\scripts\cockroachdb-tool-evidence.ps1
```

This verifies:

- `ccloud` CLI authentication and live cluster inspection;
- live cluster `docweave-memory`;
- AWS region `eu-central-1`;
- CockroachDB Agent Skills repository and skills used for schema/transaction
  review.

## AWS Evidence

```powershell
aws cloudformation describe-stacks --stack-name docweave-cloud-dev --region eu-central-1
aws lambda list-event-source-mappings --function-name docweave-cloud-dev-analysis-worker --region eu-central-1
```

Deployed AWS services:

- Amazon Bedrock;
- AWS Lambda;
- Amazon S3;
- Amazon SQS;
- Amazon API Gateway;
- Amazon CloudWatch Logs;
- AWS Secrets Manager dynamic references.

Expected `/health` evidence:

```text
aws_lambda: running
amazon_bedrock: configured
amazon_s3: configured
amazon_sqs: configured
cockroachdb_secret: configured
```

Live cloud proof from 2026-08-10:

```text
job_id: 55555555-5555-4555-8555-555555555555
analysisStatus: bedrock_classified_cockroachdb_persisted
persistedClassificationCount: 1
resultArtifactCount: 1
```

This proves the AWS Lambda worker can classify a PDF with Amazon Bedrock, write
the analysis artifact to Amazon S3, and persist the proposal memory in
CockroachDB.
