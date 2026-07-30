# Runtime Configuration Runbook

**Project:** DocWeave  
**Status:** Pre-development runtime setup guidance  
**Scope:** Local operator configuration for controlled classification runtime checks

## 1. Purpose

This runbook explains how to configure a local shell for the controlled
DocWeave runtime path:

1. extract one authorized PDF locally;
2. invoke the approved Amazon Bedrock classification gateway;
3. persist the accepted proposal through the configured CockroachDB boundary.

It does not approve new cloud infrastructure, database migrations, secrets, or
schema changes. It also does not require storing secrets in the repository.

## 2. Required runtime values

The runtime expects these environment variables to be present in the shell that
starts DocWeave:

| Variable | Purpose | Secret handling |
| --- | --- | --- |
| `DOCWEAVE_DATABASE_URL` | CockroachDB SQLAlchemy connection URL | Secret-like; never commit or paste into logs |
| `DOCWEAVE_WORKSPACE_ID` | Existing DocWeave workspace UUID | Non-secret identifier, but avoid publishing real project values |
| `DOCWEAVE_TAXONOMY_VERSION_ID` | Existing taxonomy version UUID | Non-secret identifier, but avoid publishing real project values |
| `DOCWEAVE_APPROVED_BY_ACTOR_ID` | Existing actor UUID used for controlled runtime approval metadata | Non-secret identifier, but avoid publishing real project values |
| `DOCWEAVE_CLASSIFICATION_PROMPT_VERSION` | Optional classification prompt version override | Defaults to the current contract version |

AWS credentials must also be available to the same process through the approved
local AWS authentication path. The current approved Bedrock region and model
are defined in code and validated by the Bedrock gateway configuration.

## 3. Safe PowerShell session setup

Set values only in the current PowerShell session while validating the runtime:

```powershell
$env:DOCWEAVE_DATABASE_URL = "<cockroachdb-sqlalchemy-url>"
$env:DOCWEAVE_WORKSPACE_ID = "<workspace-uuid>"
$env:DOCWEAVE_TAXONOMY_VERSION_ID = "<taxonomy-version-uuid>"
$env:DOCWEAVE_APPROVED_BY_ACTOR_ID = "<actor-uuid>"
```

Do not place real values in committed files, issue bodies, pull requests,
screenshots, terminal transcripts, or demo recordings.

## 4. Preflight sequence

Run the configuration-only preflight first:

```powershell
docweave-runtime-preflight
```

Expected successful shape:

```text
runtime_config: ok (...)
bedrock_client: ok (...)
cockroachdb_connection: skip (not_requested)
```

Then run the explicit database check:

```powershell
docweave-runtime-preflight --database
```

Expected successful shape:

```text
runtime_config: ok (...)
bedrock_client: ok (...)
cockroachdb_connection: ok (...)
docweave_schema: ok (...)
```

If the schema check reports missing tables, stop. That means the target is not
ready for the current application runtime. Do not fabricate rows or bypass the
repository contract.

## 5. Controlled single-document runtime check

After preflight passes, run one synthetic PDF through the controlled command:

```powershell
docweave-classify-pdf .\pdf_sintetici\<file-name>.pdf --authorized-root .\pdf_sintetici
```

This command performs real extraction, a real Bedrock model invocation, and
real CockroachDB writes. It should be used only against an approved validation
target until the production workflow is explicitly approved.

## 6. Controlled batch runtime check

After the single-document path has passed, run a bounded recursive batch over
an authorized validation folder:

```powershell
docweave-classify-batch .\pdf_sintetici --authorized-root .\pdf_sintetici --limit 30
```

This command uses the same extraction, Bedrock, and CockroachDB runtime path as
the single-document command. It caps each invocation at 1,000 discovered PDFs,
derives stable per-file idempotency keys for retry, continues after
per-document failures by default, and prints only sanitized status fields. It
does not rename, move, copy, delete, upload, or overwrite source files.

For reproducible validation evidence, write a sanitized JSON report:

```powershell
docweave-classify-batch .\pdf_sintetici --authorized-root .\pdf_sintetici --limit 30 --json-report .\artifacts\classification-batch-report.json
```

The report includes counts, relative paths, non-authoritative proposed classes,
token observations, dispositions, confidence fields, and sanitized error
categories. It excludes extracted document text, prompts, database URLs,
credentials, and absolute local paths. Existing report files are not
overwritten.

Use `--stop-on-failure` only when investigating a specific document failure and
wanting the first failure to terminate the batch.

## 7. Desktop startup

Launch the cockpit from the configured shell:

```powershell
docweave-desktop
```

The connection panel should show runtime readiness. If the runtime preflight is
blocked, the Analyze control remains unavailable and no Bedrock or CockroachDB
operation is attempted from the desktop.

## 8. Failure policy

- Missing runtime configuration blocks classification before external calls.
- Database schema mismatch blocks the database preflight.
- Bedrock or CockroachDB failures must be reported as sanitized categories.
- Batch failures remain item-level observations unless `--stop-on-failure` is
  used; failed items are not reported as successful and are safe to retry.
- The application must not replace failed intelligence or persistence with
  hardcoded, simulated, or fabricated results.
- Originals must not be moved, copied, renamed, or overwritten by this runtime
  validation path.
