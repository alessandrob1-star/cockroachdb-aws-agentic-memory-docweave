# Testing Instructions

DocWeave is a desktop-first hackathon project with an AWS cloud API slice.

## Functional Demo URLs

Cloud API health endpoint:

```text
https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev/health
```

Repository pull request with the current submission branch:

```text
https://github.com/alessandrob1-star/cockroachdb-aws-agentic-memory-docweave/pull/118
```

## Local Dashboard Test

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\docweave-desktop.exe
```

Demo flow:

1. Choose `pdf_sintetici`.
2. Scan the folder.
3. Analyze PDFs.
4. Open one document in review.
5. Approve a proposed rename/move.
6. Select the moved PDF and inspect original/current path memory.

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

Known submission gate:

```text
The cloud API currently reports cockroachdb_secret: missing.
```

Do not claim Lambda cloud-to-CockroachDB persistence as complete until the
CockroachDB database URL secret ARN is connected and `/health` reports the
secret as configured.
