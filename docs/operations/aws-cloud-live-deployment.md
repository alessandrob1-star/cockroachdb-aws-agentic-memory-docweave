# AWS Cloud Live Deployment Evidence

**Date:** 2026-08-03  
**Region:** `eu-central-1`  
**Environment:** `dev`  
**Status:** Live infrastructure deployed for the first DocWeave cloud
foundation slice.

## Scope

This evidence records the first live AWS deployment for DocWeave. It does not
claim the complete cloud product, public demo readiness, CockroachDB secret
configuration, or end-to-end cloud document analysis.

## Deployed stacks

| Stack | Purpose | Status |
| --- | --- | --- |
| `docweave-artifacts` | Private versioned S3 bucket for Lambda deployment artifacts | `CREATE_COMPLETE` |
| `docweave-cloud-dev` | S3 document artifacts, SQS queue, Lambda API and worker, HTTP API, log groups, and Bedrock runtime configuration | `UPDATE_COMPLETE` |

## AWS services verified

| Service | Live evidence | Result |
| --- | --- | --- |
| Amazon S3 | Deployment artifact uploaded to the artifact bucket; one synthetic PDF uploaded through the cloud API pre-signed URL to the document artifact bucket | Verified |
| Amazon API Gateway | `GET /health`, `POST /uploads/presign`, and `POST /analysis-jobs` reached the Lambda API | Verified |
| AWS Lambda | API Lambda returned live health; worker Lambda direct invocation accepted an SQS-shaped analysis job | Verified |
| Amazon SQS | Analysis job was queued and consumed; queue returned to zero visible and zero in-flight messages | Verified |
| Amazon CloudWatch Logs | API Lambda log stream exists for the live requests | Verified |
| Amazon Bedrock | `bedrock-runtime converse` smoke test succeeded with `eu.amazon.nova-2-lite-v1:0`, `stopReason=end_turn`, 62 total tokens, output `OK` | Verified |
| CockroachDB runtime secret | Not configured in the AWS stack yet | Pending |

## Live health payload

The cloud API reported:

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
  },
  "capabilities": [
    "health",
    "presigned_pdf_upload",
    "queued_analysis_request"
  ]
}
```

## Important limitations

- The worker currently acknowledges queued jobs but does not yet run the shared
  extraction, Bedrock classification, CockroachDB persistence, review-decision,
  or file-lineage runtime.
- The stack does not yet configure the CockroachDB runtime secret.
- Anthropic Claude was not available for live smoke testing because the AWS
  account still requires the Anthropic use-case details form. The working live
  smoke model is `eu.amazon.nova-2-lite-v1:0`.
- No guestbook resources were modified.

