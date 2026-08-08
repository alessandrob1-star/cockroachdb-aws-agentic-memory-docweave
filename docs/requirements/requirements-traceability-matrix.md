# Requirements Traceability Matrix

**Project:** DocWeave  
**Last updated:** 2026-08-08

## Hackathon Evidence Matrix

| Requirement | Evidence | Status |
| --- | --- | --- |
| User can choose a PDF folder from the dashboard | `src/docweave/desktop/cockpit.py` folder selection and discovery flow | Implemented |
| User can analyze PDFs from the dashboard | Dashboard dispatches bounded classification work through the configured runtime | Implemented |
| Analysis uses real document text and a real model path | `src/docweave/classification_cli.py`, extraction module, Bedrock gateway | Implemented; quality depends on PDF extraction and model output |
| CockroachDB stores visible agent memory | Six-table `docweave` schema and `src/docweave/persistence/simple_memory_repository.py` | Implemented |
| Human approves before file mutation | Dashboard approve/reject controls and review CLI | Implemented |
| Approved files keep original path memory | `docweave.documents` stores original/current path; `docweave.file_history` stores before/after events | Implemented |
| At least two CockroachDB tools are meaningfully used | `ccloud` CLI inspects the live `docweave-memory` cluster; CockroachDB Agent Skills repository reviewed schema and transaction design | Implemented; evidence in `docs/operations/hackathon-requirement-evidence.md` |
| AWS powers the cloud path | CloudFormation template, Lambda API/worker, S3, SQS, API Gateway, CloudWatch, Bedrock | Implemented and deployed; live stack is `UPDATE_COMPLETE` |
| AWS worker can persist to CockroachDB | Worker writes cloud classifications to `docweave.documents`, `agent_runs`, and `proposals` when `DOCWEAVE_DATABASE_URL` is configured | Implemented and deployed; live health shows CockroachDB secret missing, so cloud persistence remains blocked until the secret ARN is configured |
| Repository includes open-source license | `LICENSE` contains the MIT license | Implemented |
| Repository includes testing instructions | `docs/submission/testing-instructions.md` | Implemented |
| No fake intelligence | Tests and code keep Bedrock/model path separate from deterministic validation; no canned success is used | Implemented |
| Schema is simple enough for judging | One `docweave` schema with six tables and one migration | Implemented |

## Current Verification

```text
ruff: passed on full `src`, `services`, and `tests` tree
pytest: 463 passed
ccloud evidence: passed against live `docweave-memory` cluster
cloudformation stack: `docweave-cloud-dev` is `UPDATE_COMPLETE`
```

## Remaining Release Gates

| Gate | Needed before final submission |
| --- | --- |
| Cloud CockroachDB proof | Configure `CockroachDbSecretArn`, run a live cloud analysis, and show rows in `docweave`. |
| Public repository visibility | Make the GitHub repository public before Devpost submission if it is still private. |
| Functional demo URL | Use the AWS health/demo endpoint for cloud access and the local desktop build for dashboard evaluation. |
| Demo recording | Record the dashboard folder -> Analyze -> Approve -> CockroachDB path-history loop. |
| Submission text | Lead with one focused workflow and the six-table memory evidence. |

## Explicit Non-Claims

- DocWeave does not claim production-grade classification accuracy.
- Relationship inference is schema-ready but not the core demo path.
- Confidence is an uncalibrated review-ordering signal, not a probability.
- The cloud path does not approve or move files; approval remains in the
  dashboard.
