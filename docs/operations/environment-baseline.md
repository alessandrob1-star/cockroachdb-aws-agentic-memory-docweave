# Environment Baseline

**Project:** DocWeave  
**Last updated:** 2026-08-08

## AWS

| Item | Current setting |
| --- | --- |
| Region | `eu-central-1` |
| Live stacks | `docweave-artifacts`, `docweave-cloud-dev` |
| Runtime services | S3, SQS, Lambda, API Gateway, CloudWatch Logs, Bedrock |
| Bedrock smoke model | `eu.amazon.nova-2-lite-v1:0` |
| Secret handling | Lambda can receive `DOCWEAVE_DATABASE_URL` through a Secrets Manager dynamic reference when `CockroachDbSecretArn` is supplied |

## CockroachDB

| Item | Current setting |
| --- | --- |
| Cluster | `docweave-memory` |
| Cloud provider | AWS |
| Region | `eu-central-1` |
| Current application schema | `docweave` |
| Current table count | 6 |
| Runtime URL storage | Outside the repository |

## Local Runtime

The approved local launcher under the user's DocWeave application-data folder
sets:

```text
DOCWEAVE_DATABASE_URL
DOCWEAVE_WORKSPACE_ID
DOCWEAVE_TAXONOMY_VERSION_ID
DOCWEAVE_APPROVED_BY_ACTOR_ID
```

The repository does not store those values.

## Verification

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-schema.exe --flat
aws cloudformation validate-template --region eu-central-1 --template-body file://infrastructure/aws/docweave-cloud-foundation.template.json
```
