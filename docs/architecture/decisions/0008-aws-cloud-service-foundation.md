# ADR-0008: AWS Cloud Service Foundation

**Status:** Accepted for repository implementation; deployment still requires an
explicit release decision.

**Date:** 2026-08-03

## Context

DocWeave must be more than a desktop client with a configured model endpoint.
The hackathon rules require an agentic application that uses CockroachDB as
persistent memory and is deployed on AWS. The submission also needs to identify
which AWS services are used and what they do in the agent environment.

The product needs a cloud path that preserves original documents, queues
bounded analysis work, runs controlled compute, invokes Amazon Bedrock for real
intelligence, and writes durable memory to CockroachDB without inventing
success states.

## Decision

DocWeave will use a serverless AWS foundation for the first cloud slice:

- Amazon S3 stores uploaded PDF originals and cloud artifacts with private,
  encrypted, versioned storage.
- Amazon API Gateway exposes a small HTTP boundary for health checks,
  pre-signed PDF uploads, and queued analysis-job requests.
- AWS Lambda hosts the API handler and the asynchronous analysis worker.
- Amazon SQS buffers analysis jobs and isolates user requests from longer
  processing.
- Amazon CloudWatch Logs records Lambda runtime evidence with bounded
  retention.
- Amazon Bedrock remains the real model-inference service for document
  classification and relationship reasoning. The first deployed smoke-test
  model is `eu.amazon.nova-2-lite-v1:0`; Anthropic Claude access requires the
  account-level use-case form before it can be used in this environment.
- CockroachDB remains the authoritative memory layer; the cloud worker must use
  the existing runtime contracts rather than creating a separate database model.

Infrastructure is represented as CloudFormation in
`infrastructure/aws/docweave-cloud-foundation.template.json`. The template is
not auto-deployed by application startup or tests.

## Consequences

- The repository now has a concrete AWS multi-service implementation path that
  can satisfy the AWS side of the hackathon story once deployed and validated.
- S3 object keys are workspace scoped, and API requests validate PDF type,
  maximum size, and workspace-prefix boundaries before queueing work.
- The queue and worker provide a restartable asynchronous boundary, but the
  worker must still be connected to the shared extraction, Bedrock, and
  CockroachDB runtime before cloud analysis can be claimed as end-to-end.
- The template grants Bedrock invocation permission with `Resource: "*"` because
  model and inference-profile ARN scoping differs by provider and region. This
  must be tightened if AWS supports exact ARNs for the final selected model and
  profile.
- Deployment, secret creation, custom domain, authentication, and public demo
  exposure remain separate release decisions.

## Alternatives considered

### Bedrock-only cloud integration

Rejected for the judged architecture. Bedrock is necessary for intelligence,
but it does not by itself prove a complete AWS-deployed agent environment.

### Container-first Amazon ECS or Amazon EKS deployment

Deferred. Containers may become useful for long PDF processing or richer cloud
UI hosting, but the first cloud control plane is smaller and safer with Lambda,
SQS, and S3.

### Direct browser upload through API Gateway

Rejected. API Gateway has payload limits and would route document bytes through
the API handler. Pre-signed S3 uploads keep the API thin and preserve a clear
artifact boundary.
