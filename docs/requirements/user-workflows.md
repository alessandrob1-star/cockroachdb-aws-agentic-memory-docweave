# DocWeave User Workflows

**Status:** Focused demo workflows  
**Last updated:** 2026-08-10

## Workflow 1 - Local Dashboard Demo

1. The user opens DocWeave.
2. The user selects a local folder.
3. DocWeave lists PDFs and shows a read-only preview.
4. The user clicks Analyze.
5. DocWeave extracts text from each selected PDF.
6. Amazon Bedrock returns a structured classification proposal.
7. CockroachDB records the document, agent run, and proposal.
8. The user reviews proposed class, folder, filename, confidence, and evidence.
9. The user approves or rejects.
10. On approval, DocWeave moves/renames the file.
11. CockroachDB records the human decision and before/after file path.
12. The user can select the moved PDF and immediately see its original name and
    original directory.

## Workflow 2 - CockroachDB Console Demo

1. Open CockroachDB Console.
2. Show schema `docweave`.
3. Show the six tables.
4. Query `documents` for original/current paths.
5. Query `agent_runs` and `proposals` for the Bedrock analysis.
6. Query `human_decisions` and `file_history` after approval.

This is the database story judges must understand quickly.

## Workflow 3 - AWS Cloud Demo

1. Call `GET /health`.
2. Confirm S3, SQS, Lambda, API Gateway, CloudWatch, Bedrock, and the
   CockroachDB secret are configured.
3. Upload a PDF through a pre-signed S3 URL.
4. Queue an analysis job.
5. Let the Lambda worker invoke Bedrock.
6. Read the S3 analysis-result artifact.
7. Verify the worker returns
   `analysisStatus: bedrock_classified_cockroachdb_persisted`.
8. Read the CockroachDB memory rows written to `docweave.documents`,
   `docweave.agent_runs`, and `docweave.proposals`.

## Empty And Failure States

The dashboard must keep these states clear:

- no folder selected;
- no PDFs found;
- extraction failed;
- Bedrock unavailable;
- CockroachDB unavailable;
- proposal rejected;
- move failed;
- AWS CockroachDB secret unavailable.

No state may claim success unless the relevant file operation, model call, or
database write actually happened.
