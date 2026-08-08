# AWS Cloud Live Deployment Evidence

**Date:** 2026-08-08  
**Region:** `eu-central-1`  
**Environment:** `dev`  
**Status:** Live stack updated; worker code targets the simple DocWeave schema;
CockroachDB secret parameter is still missing in the deployed environment.

## Deployed Stacks

| Stack | Purpose | Last observed status |
| --- | --- | --- |
| `docweave-artifacts` | Private versioned S3 bucket for Lambda packages | `CREATE_COMPLETE` |
| `docweave-cloud-dev` | S3 documents, SQS queue, Lambda API and worker, HTTP API, logs, Bedrock permissions | `UPDATE_COMPLETE` |

The CloudFormation template validated and `docweave-cloud-dev` updated to
`UPDATE_COMPLETE` on 2026-08-08 with Lambda artifact:

```text
lambda/docweave-cloud-api-c83902aa0bf9.zip
```

## AWS Services

| Service | Purpose |
| --- | --- |
| Amazon S3 | Uploaded PDFs and bounded analysis-result artifacts. |
| Amazon SQS | Workspace-scoped analysis job queue. |
| AWS Lambda | HTTP API and queued worker. |
| Amazon API Gateway | Public HTTP entrypoint for health, upload pre-signing, analysis jobs, and result reads. |
| Amazon CloudWatch Logs | Runtime logs for API and worker functions. |
| Amazon Bedrock | Real PDF classification through the configured model. |
| AWS Secrets Manager | Optional dynamic reference for the CockroachDB `database_url` secret. |

## Current Cloud Persistence Path

The worker now persists successful Bedrock classifications into the same
CockroachDB schema used by the local dashboard:

```text
docweave.documents
docweave.agent_runs
docweave.proposals
```

Human decisions and file history remain dashboard actions because they require
explicit human approval before any file move or rename.

For Lambda CockroachDB persistence, the stack parameter
`CockroachDbSecretArn` must point to a Secrets Manager secret whose JSON value
contains:

```json
{
  "database_url": "cockroachdb+psycopg://..."
}
```

The template uses a CloudFormation dynamic reference to set
`DOCWEAVE_DATABASE_URL`; the secret value is not stored in the repository.

## Health Payload

Observed `GET /health` after the 2026-08-08 update:

```json
{
  "service": "docweave-cloud-api",
  "status": "ready",
  "aws_services": {
    "amazon_bedrock": "configured",
    "amazon_s3": "configured",
    "amazon_sqs": "configured",
    "aws_lambda": "running",
    "cockroachdb_secret": "missing"
  }
}
```

Because `cockroachdb_secret` is currently `missing`, cloud analysis can still
produce S3 result artifacts but Lambda CockroachDB persistence is not
configured. Do not claim live cloud-to-CockroachDB persistence until the secret
ARN is supplied and a live worker run produces rows in `docweave`.

## Deployment Verification

Validate the template:

```powershell
aws cloudformation validate-template --region eu-central-1 --template-body file://infrastructure/aws/docweave-cloud-foundation.template.json
```

Inspect live stacks:

```powershell
aws cloudformation list-stacks --region eu-central-1 --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
```

After packaging and deployment, verify:

1. `GET /health` reports configured AWS services.
2. `POST /uploads/presign` returns a workspace-scoped S3 upload URL.
3. `POST /analysis-jobs` queues an SQS job and returns a result URL.
4. The worker invokes Amazon Bedrock and writes an S3 result artifact.
5. If `CockroachDbSecretArn` is configured, CockroachDB receives document,
   agent-run, and proposal rows in `docweave`.

## Limitations

- The CockroachDB secret ARN still must be configured before claiming AWS cloud
  persistence in the demo.
- The cloud path does not approve file moves. Approval remains a dashboard
  workflow.
- Relationship inference is not the main cloud smoke test.
