# DocWeave

DocWeave is a hackathon desktop cockpit that lets a human clean up messy PDF
folders with help from a real document-analysis agent.

The demo loop is intentionally simple:

```text
Choose folder -> analyze PDFs -> review proposed names -> approve moves -> inspect CockroachDB memory
```

DocWeave does not rename files because a model said so. Amazon Bedrock reads
the extracted PDF text and proposes a document class, destination folder, safer
filename, confidence signal, and evidence summary. CockroachDB stores what was
found, what the model proposed, what the human decided, and the before/after
path history. Files move only after explicit human approval in the dashboard.

## Why It Exists

Many real document folders contain files named `scan_000184.pdf`,
`attachment_final_02.pdf`, or `received_file_003.pdf`. The information inside
those PDFs may connect purchase orders, invoices, payments, contracts, and
receipts, but the folder structure hides that context.

DocWeave turns the folder into explainable agent memory:

1. The user opens the dashboard and selects an authorized folder.
2. The dashboard lists the PDFs and shows a read-only preview.
3. The user clicks Analyze.
4. DocWeave extracts text, invokes Amazon Bedrock, and writes a proposal to
   CockroachDB.
5. The user approves or rejects each proposal in the dashboard.
6. On approval, DocWeave renames and moves the PDF into an understandable
   folder, then records the original and new path.
7. Selecting a moved PDF shows the original filename and original directory
   immediately.

## Hackathon Architecture

The project uses one simple CockroachDB schema: `docweave`.

| Table | Purpose |
| --- | --- |
| `docweave.documents` | One row per PDF, including original and current directory/name. |
| `docweave.agent_runs` | One row per Amazon Bedrock analysis attempt. |
| `docweave.proposals` | The proposed class, folder, filename, confidence, and evidence summary. |
| `docweave.human_decisions` | Human approve, reject, or request-change decisions. |
| `docweave.file_history` | Before/after path memory for approved file operations. |
| `docweave.document_relationships` | Optional AI-suggested document links. |

There is no separate judge schema. The schema shown in CockroachDB Cloud is the
same schema used by the dashboard and by the AWS worker.

## AWS Services

DocWeave uses:

- Amazon Bedrock for PDF classification and evidence-backed proposals.
- Amazon S3 for cloud document artifacts and analysis-result artifacts.
- Amazon SQS for queued cloud analysis jobs.
- AWS Lambda for the cloud API and worker.
- Amazon API Gateway for the HTTP API.
- Amazon CloudWatch Logs for operational evidence.
- AWS Secrets Manager dynamic references for the CockroachDB runtime URL in the
  deployed Lambda environment when a secret ARN is supplied.

The cloud worker persists Bedrock classifications into the same `docweave`
CockroachDB tables used by the local dashboard.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
```

Start the dashboard:

```powershell
.\.venv\Scripts\docweave-desktop.exe
```

On this workstation, `launch-docweave-dashboard.cmd` delegates to the approved
runtime launcher when present so secrets stay outside the repository.

## Runtime Checks

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-evidence.exe
.\.venv\Scripts\docweave-memory-schema.exe --flat
```

Expected database readiness:

```text
runtime_config: ok (loaded)
bedrock_client: ok (eu-central-1:configured)
cockroachdb_connection: ok (reachable)
docweave_schema: ok (ready)
```

Expected schema report:

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

Show the six-table schema:

```sql
SHOW TABLES FROM docweave;
```

Show current document names and original paths:

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

Show the approval path history:

```sql
SELECT
    d.original_directory,
    d.original_filename,
    h.event_sequence,
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
ORDER BY d.original_filename, h.event_sequence;
```

## CLI Helpers

Single PDF analysis:

```powershell
.\.venv\Scripts\docweave-classify-pdf.exe pdf_sintetici\scan_000184.pdf --authorized-root pdf_sintetici
```

Batch analysis:

```powershell
.\.venv\Scripts\docweave-classify-batch.exe pdf_sintetici --authorized-root pdf_sintetici --limit 30
```

Schema migration rendering:

```powershell
.\.venv\Scripts\python -m alembic heads
.\.venv\Scripts\python -m alembic upgrade head --sql
```

The migration history now contains one revision:

```text
0001_simple_docweave_schema
```

## Repository Map

- `src/docweave/desktop/cockpit.py` - dashboard workflow.
- `src/docweave/classification_cli.py` - extraction, Bedrock, CockroachDB
  proposal persistence.
- `src/docweave/review_cli.py` - human decision and file-history persistence.
- `src/docweave/persistence/simple_memory_repository.py` - six-table
  CockroachDB writer.
- `services/api/docweave_cloud_api/` - AWS Lambda API and worker.
- `infrastructure/aws/` - CloudFormation templates.
- `migrations/versions/0001_simple_docweave_schema.py` - reproducible schema.

## Current Limitations

- Relationship inference is represented in the schema but is not yet the main
  demo path.
- Classification confidence is an uncalibrated review-ordering signal, not a
  production probability.
- The AWS stack needs a valid CockroachDB secret ARN with a `database_url` JSON
  key before Lambda can persist to CockroachDB.
- Real document quality still depends on the PDF text extraction quality and
  the selected Bedrock model.

## Governance

Mandatory project rules are in [PROJECT_RULES.md](PROJECT_RULES.md). Claims in
the README, demo, and submission must match live evidence. Intelligent behavior
must remain genuine: no canned classifications, hidden bypasses, or fabricated
success states.
