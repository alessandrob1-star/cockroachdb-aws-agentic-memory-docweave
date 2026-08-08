# Delivery Plan

**Project:** DocWeave  
**Last updated:** 2026-08-08  
**Submission priority:** A focused, explainable hackathon demo.

## Product Loop

The only release-critical loop is:

```text
Dashboard folder selection
-> PDF discovery and preview
-> real text extraction
-> Amazon Bedrock classification
-> CockroachDB proposal memory
-> human approval
-> file move/rename
-> CockroachDB original/current path evidence
```

## Done Before Submission

| Item | Required evidence |
| --- | --- |
| Dashboard Analyze works | User can select a folder and create proposal rows. |
| Dashboard Approve works | File is renamed/moved only after approval. |
| Original path remains visible | Dashboard and SQL show original directory/name. |
| CockroachDB is simple | Only the six-table `docweave` schema is shown. |
| AWS is meaningful | Deployed Lambda worker uses Bedrock and, when configured, persists to CockroachDB. |
| Submission is focused | README, video, and Devpost lead with the same loop. |

## Remaining Work

1. Redeploy the updated AWS worker/template.
2. Configure the CockroachDB secret ARN for Lambda persistence.
3. Run a live AWS analysis and show rows in CockroachDB.
4. Record the dashboard demo with CockroachDB Console visible.
5. Prepare Devpost text and screenshots around the six-table memory story.

## Scope Cuts

The following are not release-critical:

- broad workspace administration;
- vector retrieval;
- large relationship graphs;
- multi-tenant role management;
- restore workflows beyond visible path history;
- a 300-PDF corpus.

These may be discussed as future work only if the working demo is already
clear.
