# Hackathon Requirement Evidence

**Last updated:** 2026-08-08

DocWeave must prove meaningful AWS and CockroachDB tool use, not just mention
services in documentation.

## CockroachDB Tools

### 1. `ccloud` CLI

Status: **used against the live CockroachDB Cloud organization**.

Evidence command:

```powershell
.\scripts\cockroachdb-tool-evidence.ps1
```

Observed evidence from the current workstation:

- `ccloud 0.6.12`
- authenticated organization: `student at Opit -Open Institute of Technology`
- cluster: `docweave-memory`
- cluster ID: `b5ed9ba5-5130-409c-b22b-6e5f8ba64e44`
- plan: `SERVERLESS`
- cloud provider: `AWS`
- region: `eu-central-1`
- state: `CREATED`
- CockroachDB version: `v26.2.5`
- SQL user visible through `ccloud cluster user list`: `docweave_admin`

How DocWeave uses it:

- verifies the live CockroachDB Cloud cluster that backs the dashboard memory;
- records the cluster ID and AWS region used in the submission evidence;
- gives the agent an auditable control-plane command for cluster and user
  inspection without reading database passwords.

### 2. CockroachDB Agent Skills repository

Status: **used during this repository review**.

Pinned source:

```text
https://github.com/cockroachlabs/cockroachdb-skills
HEAD: e14e86d23ce8ee2e7e40a34ce2944c2502b6eadd
```

Skills applied:

- `cockroachdb-query-and-schema-design/cockroachdb-sql`
- `cockroachdb-application-development/designing-application-transactions`

Findings applied to DocWeave:

- every current memory table has an explicit primary key;
- the schema uses UUID primary keys for distributed-write friendliness;
- the memory writer uses parameterized SQL through SQLAlchemy Core;
- analysis writes use `INSERT ... ON CONFLICT`/idempotent replay behavior;
- human decisions lock the reviewed proposal with `FOR UPDATE` before changing
  proposal and file-history state;
- the transaction runner retries CockroachDB serialization failures
  (`SQLSTATE 40001`) with bounded backoff and jitter;
- large PDF bytes stay outside CockroachDB and are handled by local files or
  Amazon S3 artifacts, keeping database rows small.

## AWS Services

Status: **deployed stack observed in AWS account `125579685441`, region
`eu-central-1`**.

Stack:

```text
docweave-cloud-dev
status: UPDATE_COMPLETE
lambda artifact: lambda/docweave-cloud-api-6866f23e2332.zip
```

Services used:

- Amazon Bedrock: document classification model, currently
  `eu.amazon.nova-2-lite-v1:0`;
- AWS Lambda: HTTP API function and asynchronous analysis worker;
- Amazon S3: document artifact bucket and analysis result artifacts;
- Amazon SQS: analysis queue connected to Lambda event source mapping;
- Amazon API Gateway: public HTTP API endpoint;
- Amazon CloudWatch Logs: Lambda operational logs;
- AWS Secrets Manager dynamic references: CloudFormation wiring for
  `DOCWEAVE_DATABASE_URL` when a secret ARN is supplied.

Observed endpoint:

```text
https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev
```

Observed `/health` capabilities after the 2026-08-08 deployment:

```text
health
presigned_pdf_upload
queued_analysis_request
worker_s3_artifact_verification
worker_bedrock_document_classification
analysis_result_artifacts
simple_cockroachdb_memory_persistence
```

Current live health limitation:

```text
cockroachdb_secret: missing
```

Meaning: AWS infrastructure and Bedrock worker path are active, but Lambda
cloud-to-CockroachDB persistence must not be claimed as complete until the
CockroachDB database URL secret ARN is connected and `/health` reports the
secret as configured.
