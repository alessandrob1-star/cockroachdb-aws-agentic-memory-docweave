# Verified Environment Baseline

**Project:** DocWeave
**Last verified:** 2026-07-24
**Implementation status:** Validation schema available; product deployment not started

## 1. Purpose

This document records the verified development environment without claiming
that planned application integrations are already implemented. Exact account
identifiers, credentials, connection strings, promotional codes, and private
billing details are deliberately excluded.

The live provider state remains authoritative. Re-run the documented checks
before deployment and release.

## 2. AWS baseline

| Item | Verified state |
| --- | --- |
| Account plan | AWS Free plan is active |
| Project cost ceiling | 80 USD total unless the project owner explicitly approves a change |
| Promotional credits | Available credits do not increase the approved project cost ceiling |
| Budget | `DocWeave-Total-Cost`, cost budget, custom total period, 80 USD |
| Budget alerts | Actual spend at 50%, 80%, and 100%; forecasted spend at 100% |
| Cost anomaly detection | Default service monitor and confirmed daily email subscription |
| Primary Region | `eu-central-1` |
| Bedrock primary profile | `eu.anthropic.claude-sonnet-4-6`, active |
| Bedrock invocation | Not performed for DocWeave; no runtime integration is claimed |
| DocWeave infrastructure | No DocWeave CloudFormation stack or application workload deployed |

Existing resources created for unrelated exercises are outside DocWeave scope
and must not be reused, renamed, or deleted as part of this project.

The accepted Bedrock model decision is therefore currently feasible in the
selected European source Region. Invocation still requires the approved prompt
contract, bounded token limits, least-privilege runtime role, cost measurement,
and evaluation evidence.

## 3. CockroachDB Cloud baseline

| Item | Verified state |
| --- | --- |
| Organization | Project owner's authorized education organization |
| Cluster | `docweave-memory` |
| Cloud provider | AWS |
| Primary Region | `eu-central-1` |
| Plan | CockroachDB Cloud Basic, reported by `ccloud` as `SERVERLESS` |
| Cluster state | `CREATED` |
| CockroachDB version | `v26.2.1` at verification time |
| Request Unit limit | 50,000,000 per monthly cycle |
| Storage limit | 10 GiB |
| Network visibility | Public endpoint |
| SQL administration | Administrative SQL user exists; credentials are not stored in the repository |
| Validation database | `docweave_validation`, created on 2026-07-24 |
| Initial schema | Revision `0001_operational_foundation` accepted and introspected in the isolated validation database |
| Application connection | Not implemented; the validation schema is not a runtime or production deployment |

The current resource limits match the organization's documented monthly Basic
free-resource allowance. They are not permission to increase capacity or
enable unlimited usage.

The public endpoint is an explicit pre-implementation security item. The
project owner approved existing root and administrator access for
predevelopment control-plane validation without exposing credentials. Before
an application connects, the architecture must define approved network
controls, Transport Layer Security, certificate validation, application
authentication, separate runtime identities, Row-Level Security, secret
resolution, connection pooling, and workspace-context cleanup. Least-privilege
deployment and runtime identities remain separately approval-gated.

## 4. Tool evidence

- `ccloud` version 0.6.12 authenticated successfully and was used to list and
  inspect the real `docweave-memory` cluster and SQL-user names.
- The exact offline-rendered initial migration was accepted through the
  authenticated CockroachDB Cloud SQL Shell in a clean validation database.
  See [`cockroachdb-live-validation.md`](cockroachdb-live-validation.md).
- The AWS Model Context Protocol server was used for the verified read-only
  account, budget, Free plan, Cost Explorer, anomaly detection, resource, and
  Bedrock inventory.
- These checks are operational evidence only. They do not yet satisfy the
  competition's meaningful-product-integration requirement.

## 5. Open gates before implementation

The following decisions or artifacts remain mandatory:

1. seed and test the approved taxonomy baseline before classification
   contracts depend on it;
2. approve the embedding model, vector dimension, and distance metric;
3. implement the remaining reviewed CockroachDB migrations from ADR-0002;
4. complete transaction, workspace-isolation, and recovery tests;
5. create separately approved least-privilege migration, runtime, audit, and
   bounded Model Context Protocol identities before application deployment;
6. approve the local-versus-cloud extraction and privacy boundary;
7. approve the AWS compute, storage, queue, authentication, and network
   topology through Infrastructure as Code;
8. implement and evaluate the Bedrock structured-output contract; and
9. record cost, latency, quality, security, and recovery evidence.

Until these gates are closed, the correct compliant state is to preserve the
isolated validation schema without treating it as application persistence or
deploying DocWeave workloads.
