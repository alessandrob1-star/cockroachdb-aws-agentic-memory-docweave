# DocWeave

**DocWeave is a program for massive Portable Document Format (PDF) renaming and
reorganization for small and medium-sized enterprises (SMEs).** It solves the
very ordinary mess of folders full of files called `scan_000184.pdf`,
`attachment_081.pdf`, or `document_final_02.pdf`: the app reads the text inside
each PDF, proposes clear filenames and destination folders, and lets the human
approve all proposals or only selected files.

The model never mutates files by itself. The advanced PySide6 glass-effect
dashboard shows PDF previews, model evidence, batch review controls, and
per-row approve/reject actions. CockroachDB is the system of record for the
persistent memory agent:
it remembers the original filename, original directory, model proposal, human
decision, executed path change, and restore path, so renamed PDFs can be moved
back to their original name and position.

```text
messy SME folder -> PDF text extraction -> Bedrock rename/folder proposal -> human selects some or all -> CockroachDB memory -> safe move -> restore original name/path
```

**[Watch the complete DocWeave demo on YouTube (under three minutes)](https://youtu.be/p1QFV6ahOJo)**

The visible product is the dashboard, not a chat box. The left screen shows the
selected folder, the center screen previews the PDF and model evidence, and the
right screen shows live memory/runtime status. After analysis, the center
screen becomes a review table: original PDF name, proposed filename, suggested
directory, approve/reject controls, and preview buttons. The restore view is
the point of the project: CockroachDB `file_history` lets the agent answer the
practical question a real user asks after cleanup: **"What was this file called
before, and where did it come from?"**

![DocWeave dashboard showing a Bedrock proposal, CockroachDB memory trace, PDF preview, and batch classification status](docs/assets/docweave-dashboard-memory-trace.png)

## Screenshot Sequence

![After choosing a folder and running Scan, DocWeave mirrors the PDFs from the local directory inside the cockpit with live preview.](docs/assets/docweave-screenshot-01-folder-scan.png)

After choosing a folder and running Scan, DocWeave mirrors the PDFs from the
local directory inside the cockpit with live preview.

![DocWeave analyzes 9 PDFs with Bedrock, proposes classes and safer filenames, and persists memory traces in CockroachDB for human review.](docs/assets/docweave-screenshot-02-batch-analysis-memory.png)

DocWeave analyzes 9 PDFs with Bedrock, proposes classes and safer filenames,
and persists memory traces in CockroachDB for human review.

![DocWeave presents 9 proposed renames and folders for human review, requiring explicit approval before changing files.](docs/assets/docweave-screenshot-03-human-review.png)

DocWeave presents 9 proposed renames and folders for human review, requiring
explicit approval before changing files.

![After human approval, DocWeave creates category folders, moves the renamed PDFs into them, and keeps a restore review ready for rollback.](docs/assets/docweave-screenshot-04-approved-organization.png)

After human approval, DocWeave creates category folders, moves the renamed PDFs
into them, and keeps a restore review ready for rollback.

![DocWeave's restore review maps moved PDFs back to original names and locations, letting the user approve or reject rollback before restore.](docs/assets/docweave-screenshot-05-restore-review.png)

DocWeave's restore review maps moved PDFs back to original names and locations,
letting the user approve or reject rollback before restore.

![After restore approval, DocWeave restores all 9 PDFs to their original folder and filenames using persistent file history.](docs/assets/docweave-screenshot-06-restore-complete.png)

After restore approval, DocWeave restores all 9 PDFs to their original folder
and filenames using persistent file history.

![DocWeave combines CockroachDB memory with AWS runtime to analyze folders, require approval, move files safely, and restore from history.](docs/assets/docweave-screenshot-07-architecture-summary.png)

DocWeave combines CockroachDB memory with AWS runtime to analyze folders,
require approval, move files safely, and restore from history.

## Hackathon Proof In One Screen

| Requirement | DocWeave evidence |
| --- | --- |
| Agentic application | PDF extraction plus Amazon Bedrock produces class, evidence, metadata, destination folder, and filename proposals. |
| Human-governed actions | The model cannot mutate files. The dashboard records approval/rejection before any rename or move. |
| CockroachDB persistent memory | Six judge-visible tables store the full document lifecycle: what the agent saw, what it proposed, what the human decided, what moved, and how to restore it. |
| CockroachDB Tool #1 | `ccloud` Command-Line Interface (CLI) verifies the live CockroachDB Cloud serverless cluster `docweave-memory` on AWS `eu-central-1`. |
| CockroachDB Tool #2 | CockroachDB Agent Skills repository guided schema and transaction design: primary keys, idempotent writes, proposal locking, and bounded `40001` retry handling. |
| AWS deployment | CloudFormation deploys Amazon Bedrock permissions, AWS Lambda API/worker, Amazon S3 artifacts, Amazon SQS jobs, Amazon API Gateway, Amazon CloudWatch Logs, and AWS Secrets Manager dynamic references. |
| Live cloud memory proof | AWS Lambda classified `scan_000184.pdf` with Amazon Bedrock and persisted the result to CockroachDB on 2026-08-10. |
| Sample data | `pdf_sintetici` contains 100 synthetic PDFs with deliberately unhelpful filenames for realistic folder cleanup. |

![DocWeave architecture connecting the document agents, CockroachDB persistent memory, and AWS services](docs/assets/docweave-architecture-diagram.png)

## Agent Memory Model

CockroachDB is the durable memory layer, not a side log. The memory agent writes
and reads this chain:

```text
documents -> agent_runs -> proposals -> human_decisions -> file_history
```

- `documents` keeps original and current path state.
- `agent_runs` records the Bedrock model, task, input hash, output, and timing.
- `proposals` stores the agent's class, evidence, destination, and filename.
- `human_decisions` records whether the user accepted or rejected the proposal.
- `file_history` is the restore memory: previous path, next path, operation,
  status, and decision link.
- `document_relationships` is available for lightweight related-document links.

That is the core loop: **large language model understanding, human authority,
and persistent path memory**. DocWeave remains useful after the files move
because CockroachDB can still explain why a PDF has its current name and how to
restore it.

## AWS Services

- **Amazon Bedrock** - model reasoning for document class, evidence, metadata,
  rationale, confidence signal, destination folder, and filename proposal.
- **AWS Lambda** - serverless HTTP API and asynchronous analysis worker.
- **Amazon S3** - uploaded PDF artifacts and JSON analysis-result artifacts.
- **Amazon SQS** - queued analysis jobs between upload/API and worker.
- **Amazon API Gateway** - public HTTP boundary for health, upload requests,
  analysis requests, and result lookup.
- **Amazon CloudWatch Logs** - operational evidence for Lambda execution.
- **AWS Secrets Manager dynamic references** - CloudFormation wiring for the
  CockroachDB runtime URL when a secret ARN is supplied.

## CockroachDB Tools

- **`ccloud` CLI** - verifies the live CockroachDB Cloud cluster
  `docweave-memory`, its AWS region, serverless plan, version, and SQL users
  without exposing the database password.
- **CockroachDB Agent Skills repository** - applied the `cockroachdb-sql` and
  `designing-application-transactions` skills to review the six-table schema,
  primary keys, idempotent writes, `FOR UPDATE` proposal locking, and bounded
  `40001` serialization retry handling.

Tool verification is reproducible with:

```powershell
.\scripts\cockroachdb-tool-evidence.ps1
```

## Live Cloud Proof

Current AWS stack:

```text
docweave-cloud-dev
region: eu-central-1
status: UPDATE_COMPLETE
lambda artifact: lambda/docweave-cloud-api-3eee97039dbc.zip
```

The public `/health` endpoint reports Amazon S3, Amazon SQS, AWS Lambda,
Amazon Bedrock, and the CockroachDB secret as configured. A live worker proof
on 2026-08-10 classified `scan_000184.pdf` with Bedrock and returned:

```text
analysisStatus: bedrock_classified_cockroachdb_persisted
persistedClassificationCount: 1
resultArtifactCount: 1
```

In the demo video:

1. Start the cockpit and choose a messy PDF folder.
2. Click Analyze. Bedrock produces a structured proposal and CockroachDB records
   the run.
3. Open a PDF row. The cockpit shows the PDF, model evidence, proposed class,
   proposed destination, and memory status.
4. Approve. The file moves only after the human decision.
5. Select the moved PDF. DocWeave still shows the original filename and
   original directory because CockroachDB retained the path history.

## Why This Is Not Just Another AI Wrapper

DocWeave treats the model as a proposal engine, not an authority. A Bedrock
response cannot silently mutate files. The human approves the operation, the
dashboard executes the move, and CockroachDB records both the model suggestion
and the human decision.

That gives the project a clean interview/hackathon explanation:

```text
LLM understanding + human control + durable path memory
```

The output is useful even after the demo window closes: CockroachDB can answer
"what was this file originally called?" and "why did it move here?"

## Run The Dashboard

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\docweave-desktop.exe
```

Before analysis, configure your own CockroachDB Cloud connection and AWS
credentials. The
[`complete installation guide`](docs/complete-installation-guide.md)
covers a clean Windows installation, CockroachDB cluster and schema creation,
Amazon Bedrock access, the desktop test, and optional deployment of the full
AWS cloud slice. For an existing environment, copy the variable names from
[`.env.example`](.env.example), set them in the current shell, and create the
six-table schema:

```powershell
$env:DOCWEAVE_DATABASE_URL = "cockroachdb+psycopg://USER:PASSWORD@HOST:26257/docweave?sslmode=verify-full"
$env:DOCWEAVE_WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
$env:DOCWEAVE_TAXONOMY_VERSION_ID = "22222222-2222-4222-8222-222222222222"
$env:DOCWEAVE_APPROVED_BY_ACTOR_ID = "33333333-3333-4333-8333-333333333333"
$env:AWS_PROFILE = "YOUR_AWS_PROFILE"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\docweave-runtime-preflight.exe --database
```

The AWS identity must be able to invoke the configured Amazon Nova model in
Amazon Bedrock in `eu-central-1`. `launch-docweave-dashboard.cmd` is only a
Windows convenience launcher; it does not contain credentials.

## Functional Demo Endpoint

```text
https://76824l7ub1.execute-api.eu-central-1.amazonaws.com/dev/health
```

Demo video: [https://youtu.be/p1QFV6ahOJo](https://youtu.be/p1QFV6ahOJo)

Testing instructions for judges are in
[`docs/submission/testing-instructions.md`](docs/submission/testing-instructions.md).

## Validate The Memory Path

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-schema.exe --flat
.\.venv\Scripts\docweave-memory-evidence.exe
```

Expected readiness:

```text
runtime_config: ok (loaded)
bedrock_client: ok (eu-central-1:configured)
cockroachdb_connection: ok (reachable)
docweave_schema: ok (ready)
```

Expected schema:

```text
memory_schema_revision: simple_docweave_schema
memory_schema_tables: 6
memory_schema_views: 0
table docweave.documents
table docweave.agent_runs
table docweave.proposals
table docweave.human_decisions
table docweave.file_history
table docweave.document_relationships
```

## CockroachDB Demo Queries

Show the schema a judge should see:

```sql
SHOW TABLES FROM docweave;
```

Show original and current file names:

```sql
SELECT
    original_directory,
    original_filename,
    current_directory,
    current_filename,
    status
FROM docweave.documents
ORDER BY discovered_at DESC;
```

Show the approved move history:

```sql
SELECT
    d.original_directory,
    d.original_filename,
    h.operation,
    h.previous_directory,
    h.previous_filename,
    h.next_directory,
    h.next_filename,
    h.status,
    h.occurred_at
FROM docweave.file_history AS h
JOIN docweave.documents AS d
    ON d.document_id = h.document_id
ORDER BY h.occurred_at DESC;
```

## Command-Line Proofs

Analyze one PDF:

```powershell
.\.venv\Scripts\docweave-classify-pdf.exe pdf_sintetici\scan_000184.pdf --authorized-root pdf_sintetici
```

Analyze a bounded batch:

```powershell
.\.venv\Scripts\docweave-classify-batch.exe pdf_sintetici --authorized-root pdf_sintetici --limit 30
```

Render the schema migration:

```powershell
.\.venv\Scripts\python -m alembic heads
.\.venv\Scripts\python -m alembic upgrade head --sql
```

Current migration head:

```text
0001_simple_docweave_schema
```

## Repository Map

- `src/docweave/desktop/cockpit.py` - glass-effect dashboard and approval flow.
- `src/docweave/classification_cli.py` - PDF extraction, Bedrock call,
  proposal creation, CockroachDB write.
- `src/docweave/review_cli.py` - human decision and file-history persistence.
- `src/docweave/persistence/simple_memory_repository.py` - six-table
  CockroachDB writer.
- `services/api/docweave_cloud_api/` - AWS Lambda API and analysis worker.
- `infrastructure/aws/` - CloudFormation for S3, SQS, Lambda, API Gateway,
  CloudWatch Logs, Bedrock permissions, and secret dynamic references.
- `migrations/versions/0001_simple_docweave_schema.py` - reproducible schema.

## Current Limitations

- Relationship inference exists as a lightweight table but is not the main demo
  path.
- Confidence is an uncalibrated review-ordering signal, not a production
  probability.
- Extraction quality still depends on PDF text quality and the selected
  Bedrock model.
- The cloud worker classifies and persists proposals; local dashboard approval
  remains the path that renames or restores files.
