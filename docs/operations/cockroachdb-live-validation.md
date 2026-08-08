# CockroachDB Live Validation Evidence

**Project:** DocWeave  
**Last updated:** 2026-08-08  
**Current target schema:** `docweave`

## Current Live State

The active DocWeave database is expected to expose exactly the simple
hackathon memory schema:

```text
docweave.documents
docweave.agent_runs
docweave.proposals
docweave.human_decisions
docweave.file_history
docweave.document_relationships
```

The live runtime preflight verifies:

```text
runtime_config: ok (loaded)
bedrock_client: ok (eu-central-1:configured)
cockroachdb_connection: ok (reachable)
docweave_schema: ok (ready)
```

## Read-Only Evidence Commands

```powershell
.\.venv\Scripts\docweave-runtime-preflight.exe --database
.\.venv\Scripts\docweave-memory-evidence.exe --json
.\.venv\Scripts\docweave-memory-schema.exe --flat
```

These commands do not print the database URL and do not mutate schema or data.

## Demo Evidence

The primary CockroachDB demo evidence is:

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

and, after approvals:

```sql
SELECT
    d.original_directory,
    d.original_filename,
    h.previous_directory,
    h.previous_filename,
    h.next_directory,
    h.next_filename,
    h.status
FROM docweave.file_history AS h
JOIN docweave.documents AS d
    ON d.document_id = h.document_id
ORDER BY d.original_filename, h.event_sequence;
```

## Non-Claims

- This document does not claim production readiness.
- It does not claim vector search.
- It does not claim relationship quality beyond rows that are actually
  produced and inspected.
