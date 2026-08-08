# DocWeave

**Hackathon submission in one sentence:** DocWeave is an agentic document
cockpit that uses **CockroachDB Cloud as persistent memory**, proves
CockroachDB tool use with **`ccloud` Command-Line Interface (CLI)** and the
**CockroachDB Agent Skills repository**, and runs a real **Amazon Web Services
(AWS)** path with **Amazon Bedrock, AWS Lambda, Amazon Simple Storage Service
(Amazon S3), Amazon Simple Queue Service (Amazon SQS), Amazon API Gateway,
Amazon CloudWatch Logs, and AWS Secrets Manager dynamic references**.

DocWeave solves a concrete workflow: a user has a folder full of badly named
Portable Document Format (PDF) files like `scan_000184.pdf`. The dashboard lets
the user choose that folder, analyze the PDFs with a Large Language Model
(LLM), review safer names and folders, approve the move, and then prove exactly
where every renamed file originally came from.

```text
Choose folder -> Bedrock analysis -> CockroachDB memory -> human approval -> safe rename/move -> original path still visible
```

## Submission Fit

| Requirement | DocWeave evidence |
| --- | --- |
| Agentic application | Bedrock reads extracted PDF text and proposes class, metadata, evidence, destination folder, and filename. |
| CockroachDB as persistent memory | CockroachDB stores documents, Bedrock runs, proposals, human decisions, and before/after file history. |
| Deployed on AWS | CloudFormation deploys Lambda API/worker, S3 artifacts, SQS queue, API Gateway, CloudWatch Logs, Bedrock permissions, and Secrets Manager dynamic references. |
| AWS services identified | Amazon Bedrock; AWS Lambda; Amazon S3; Amazon SQS; Amazon API Gateway; Amazon CloudWatch Logs; AWS Secrets Manager dynamic references. |
| CockroachDB tools identified | `ccloud` CLI inspects the live `docweave-memory` CockroachDB Cloud cluster; CockroachDB Agent Skills review schema and transaction design. |
| Demo must show memory layer | The dashboard and SQL queries show original filename, current filename, proposal, human decision, and file history in CockroachDB. |

The distinctive product surface is the **glass-effect desktop cockpit**. It is
not a generic chat wrapper: the PySide6 dashboard shows folder scanning,
embedded PDF preview, Bedrock evidence, approval controls, CockroachDB memory
status, and original/current path history in one visual workflow. A judge can
understand the product from the screen before reading logs.

## AWS Services Used

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

## CockroachDB Tools Used

- **`ccloud` CLI** - verifies the live CockroachDB Cloud cluster
  `docweave-memory`, its AWS region, serverless plan, version, and SQL users
  without exposing the database password.
- **CockroachDB Agent Skills repository** - applied the `cockroachdb-sql` and
  `designing-application-transactions` skills to review the six-table schema,
  primary keys, idempotent writes, `FOR UPDATE` proposal locking, and bounded
  `40001` serialization retry handling.

Evidence is recorded in
[`docs/operations/hackathon-requirement-evidence.md`](docs/operations/hackathon-requirement-evidence.md).

## CockroachDB Memory

CockroachDB is intentionally simple. There is one schema, `docweave`, and six
judge-visible tables. No hidden judge schema. No demo-only table family.

| Table | What It Proves |
| --- | --- |
| `documents` | Original directory/name, current directory/name, digest, page count, status. |
| `agent_runs` | Bedrock provider, model, task, input hash, sanitized output, timing. |
| `proposals` | Proposed class, destination folder, destination filename, confidence, evidence. |
| `human_decisions` | Human approval or rejection of a model proposal. |
| `file_history` | Before/after path memory for an approved move or rename. |
| `document_relationships` | Optional lightweight links between related documents. |

In a four-minute demo:

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

On this workstation, `launch-docweave-dashboard.cmd` delegates to the approved
runtime launcher when present so runtime values stay outside the repository.

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

- The AWS stack needs a valid CockroachDB secret ARN with a `database_url`
  value before Lambda can persist to CockroachDB.
- Relationship inference exists as a lightweight table but is not the main demo
  path.
- Confidence is an uncalibrated review-ordering signal, not a production
  probability.
- Extraction quality still depends on PDF text quality and the selected
  Bedrock model.

## Governance

Mandatory project rules are in [PROJECT_RULES.md](PROJECT_RULES.md). Claims in
the README, demo, and submission must match live evidence. Intelligent behavior
must remain genuine: no canned classifications, hidden bypasses, or fabricated
success states.
