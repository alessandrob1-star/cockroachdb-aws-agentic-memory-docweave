# DocWeave

**DocWeave turns a messy Portable Document Format (PDF) folder into a
human-approved, CockroachDB-backed memory trail.**

Most document automation demos stop at "the model classified this PDF."
DocWeave goes one step further: it lets a user pick a real folder, ask a Large
Language Model (LLM) to understand the documents, approve safer names and
folders, and then prove where every moved file originally came from.

The product is built around one judge-friendly loop:

```text
Open dashboard -> choose folder -> analyze PDFs -> approve rename/move -> inspect CockroachDB memory
```

The distinctive part is not a chat box. It is the **glass-effect desktop
cockpit**: a PySide6 dashboard with an embedded PDF preview, scan state,
model evidence, approval controls, and a memory panel in one surface. The user
interface (UI) is designed so a judge can see the workflow without reading
logs: original file, Artificial Intelligence (AI) proposal, human decision,
final path, and database memory are all visible from the dashboard.

DocWeave uses real Amazon Web Services (AWS) infrastructure:

- **Amazon Bedrock** reads extracted PDF text and returns structured document
  proposals with class, evidence, metadata, confidence signal, and rationale.
- **Amazon S3** stores cloud PDF artifacts and analysis result artifacts.
- **Amazon SQS** queues cloud analysis work so uploads and model calls are not
  the same blocking request.
- **AWS Lambda** runs the HTTP API and asynchronous analysis worker.
- **Amazon API Gateway** exposes the cloud API.
- **Amazon CloudWatch Logs** keeps operational evidence for the Lambda path.
- **AWS Secrets Manager dynamic references** are wired in CloudFormation for
  the CockroachDB runtime URL when a secret ARN is supplied.
- **CockroachDB Cloud** is the durable memory layer shared by local dashboard,
  command-line validation, and the AWS worker.

CockroachDB is intentionally simple. There is one schema, `docweave`, and six
tables. No hidden judge schema. No demo-only table family. The same tables a
judge sees in CockroachDB are the tables the dashboard writes:

| Table | What It Proves |
| --- | --- |
| `documents` | Original directory/name, current directory/name, digest, page count, status. |
| `agent_runs` | Bedrock provider, model, task, input hash, sanitized output, timing. |
| `proposals` | Proposed class, destination folder, destination filename, confidence, evidence. |
| `human_decisions` | Human approval or rejection of a model proposal. |
| `file_history` | Before/after path memory for an approved move or rename. |
| `document_relationships` | Optional lightweight links between related documents. |

In a four-minute demo, the story is:

1. Start the cockpit and choose a folder full of badly named PDFs.
2. Click Analyze. DocWeave extracts text, calls Bedrock, and writes proposals to
   CockroachDB.
3. Open a PDF row. The dashboard shows the document, proposed class, proposed
   destination, evidence, and memory status.
4. Approve. The file is renamed and moved only after the human decision.
5. Select the moved PDF. DocWeave still shows the original filename and original
   directory because that path history is stored in CockroachDB.

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
