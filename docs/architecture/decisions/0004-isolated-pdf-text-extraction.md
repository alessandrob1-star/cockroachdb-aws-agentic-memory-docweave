# ADR-0004: Isolated PDF Text Extraction

**Status:** Accepted
**Decision date:** 2026-07-26
**Decision owner:** Project owner
**Implementation status:** Implemented locally; pull-request verification pending

## Context

DocWeave must analyze real PDF content while treating every selected document
as untrusted data. The approved processing pipeline requires page boundaries,
explicit limited-processing states, resource budgets, provenance, and a parser
failure boundary before text can be sent to Amazon Bedrock.

PySide6 `6.11.1` is already pinned for the desktop application and includes the
Qt PDF module. `QPdfDocument.getAllText()` returns text for one page, which
allows the shared Python core to retain page-level evidence without adding
another PDF parser dependency.

This decision does not approve Optical Character Recognition, malware
scanning, Amazon Bedrock invocation, CockroachDB writes, or cloud processing.

## Decision

DocWeave will use the pinned Qt PDF module for the initial local text-extraction
boundary. Each extraction runs in a disposable child process launched with the
same Python interpreter as the parent application.

The default limits are:

- 100 mebibytes of source data;
- 500 pages;
- 5,000,000 extracted characters; and
- 30 seconds per extraction attempt.

The parent validates that the source is a regular `.pdf` file inside the
authorized root, rejects symbolic links, verifies the PDF signature, applies
the file-size limit, and computes a SHA-256 digest. It passes the request to the
worker through standard input rather than exposing the private source path in
process arguments.

The worker repeats root and source validation, reads at most the approved file
budget into an immutable in-memory snapshot, and verifies its SHA-256 digest
before parsing. A changed source is rejected. The worker returns only
path-free, typed evidence through standard output.

Successful results retain:

- source SHA-256 digest and byte count;
- extractor and Qt version;
- document page count;
- zero-based page index and PDF page label; and
- extracted text for each page.

The boundary returns explicit terminal states for completed extraction, no
extractable text, encrypted content, unsupported security, malformed content,
file, page, or character limit violations, source rejection or change,
timeout, and worker failure.

## Security boundary

The child process contains normal parser crashes, hangs, and unhandled
exceptions so that the main application can continue and record a limited
state. File content and filenames remain data and are never evaluated as
commands or Structured Query Language.

This process boundary is not an operating-system security sandbox, malware
scanner, or antivirus. It does not claim to make arbitrary hostile PDFs safe.
Stronger platform-specific containment and malware controls remain a separate
decision requiring threat analysis, cross-platform design, and approval.

## Alternatives considered

### Parse in the desktop process

Rejected because a parser crash or hang could terminate or freeze the review
interface and lose process-local work.

### Add `pypdfium2`

Deferred because Qt PDF already provides the required initial page-level text
API. A second native PDF binding would increase the dependency and
software-supply-chain surface without current evidence of a necessary quality
gain.

### Add `pypdf`

Deferred because it would add a second parser dependency and would still
require process isolation. It may be evaluated later if corpus evidence shows
material extraction gaps in Qt PDF.

### Send whole PDF documents directly to Amazon Bedrock

Rejected for the initial pipeline because it would weaken deterministic size,
page, evidence, privacy, and cost controls. Bedrock analysis will consume
bounded extracted evidence under a separately approved contract.

## Consequences

### Benefits

- no new runtime dependency or cloud cost;
- the desktop preview and extraction path use the same pinned Qt distribution;
- private paths do not appear in worker arguments or public result contracts;
- failures and resource limits are explicit rather than hidden;
- page-level evidence is available for later model output validation; and
- all 30 initial synthetic PDFs can be extracted with real content.

### Costs and limitations

- the source is read once for the parent digest and once for the worker
  snapshot;
- the bounded snapshot can use up to the configured file budget in worker
  memory;
- image-only pages correctly produce no text and require separately approved
  Optical Character Recognition;
- encrypted PDFs are not opened with guessed or collected passwords; and
- strict operating-system sandboxing remains unimplemented.

## Verification

Acceptance requires:

- real child-process extraction of page-level text;
- successful extraction of all 30 initial synthetic PDFs;
- source-root, signature, size, page, character, timeout, and changed-source
  tests;
- explicit malformed, encrypted, unsupported-security, and no-text states;
- adversarial filename and document text remaining inert data;
- sanitized worker failures that do not disclose private paths; and
- the complete local quality gate and GitHub Actions result.

## References

- [Qt `QPdfDocument` documentation](https://doc.qt.io/qt-6/qpdfdocument.html)
- [Document processing pipeline](../document-processing-pipeline.md)
- [Quality and security charter](../../requirements/quality-security-charter.md)
