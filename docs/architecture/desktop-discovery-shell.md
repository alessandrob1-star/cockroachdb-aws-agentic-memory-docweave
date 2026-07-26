# Desktop Discovery Shell

**Project:** DocWeave
**Status:** Progressive read-only PySide6 surface implemented locally
**Date:** 2026-07-26

## 1. Purpose

The first desktop surface makes the existing deterministic discovery and intake
core visible without implying that CockroachDB persistence, Amazon Bedrock
analysis, review, or file operations are connected.

The shell lets a user:

1. authorize one existing local directory;
2. start recursive discovery without blocking the user-interface thread;
3. observe separate discovery and deterministic-intake progress;
4. cancel at cooperative file or fingerprint-chunk boundaries;
5. inspect discovered, ready, and attention-required counts;
6. view per-file relative path, deterministic intake state, byte size, and safe
   diagnostic category; and
7. select multiple completed rows for later review; and
8. explicitly preview one ready PDF in a read-only DocWeave window.

It never renames, copies, moves, uploads, extracts text from, or sends a document
to a model.

## 2. Authorized-root boundary

The selected folder is resolved as an existing directory before use. Discovery
receives only that root and the existing core prevents symbolic-link traversal.
The interface does not expose a free-form path editor. Selecting another root
is blocked while a scan is active.

This is a local authorization boundary, not the pending user, workspace, and
role authorization system.

## 3. Responsiveness and lifecycle

Discovery and deterministic intake execute through a worker object on a
dedicated Qt thread. The main thread receives typed, throttled progress and
then exactly one complete immutable result, cancellation signal, or minimized
exception category.

While scanning:

- a duplicate start request is ignored;
- root changes are rejected;
- the scan button and root field are disabled;
- a cancellation control requests a cooperative stop; and
- window closure is deferred to avoid destroying an active thread.

Cancellation is checked between discovered files, between intake records, and
between one-mebibyte fingerprint chunks. Partial results are discarded rather
than presented as complete. Directory enumeration can still take time before
the next cooperative boundary, so immediate hard cancellation is not claimed.
Progressive row delivery and durable checkpoints remain required before the
10,000-file user-interface acceptance scenario is claimed.

## 4. In-memory workspace state

The desktop session records one immutable snapshot with the authorized root,
lifecycle phase, latest progress, complete result, selected document keys, and
sanitized error category. Transition checks reject decreasing progress,
mismatched result roots, selection before completion, and unknown document
keys.

This state is deliberately process-local. It is not a CockroachDB workspace,
does not survive restart, and does not establish user or role authorization.

## 5. Embedded PDF preview boundary

A double click or the `Preview PDF` button can request previewing exactly one
completed `Ready` record. Immediately before the request, DocWeave verifies
that the observed path still exists, is a regular `.pdf` file, is not a
symbolic link, resolves inside the authorized root, and still has a valid PDF
signature. A failed check blocks the request with a safe category.

The preview uses Qt PDF's `QPdfDocument` and `QPdfView` from the already pinned
PySide6 distribution. It presents all pages in a continuously scrollable
multi-page view with bounded zoom-in, zoom-out, and fit-to-width controls.
The preview exposes no editing, annotation, printing, exporting, or shell
execution. Invalid, password-protected, or unsupported documents remain in an
explicit safe error state.

## 6. Presentation and accessibility baseline

The document table uses a read-only `QAbstractTableModel` rather than one widget
per cell. This is the correct base for later pagination or virtualization.
Controls, status messages, progress, selection count, metrics, and the table
have accessible names. Status and safety meaning are expressed in text rather
than color alone.

Windows rendering was inspected with an empty workspace and earlier with a
controlled result. The product owner accepted the embedded preview's speed,
scrolling, and basic behavior on 2026-07-26; visual polish, including larger
zoom controls, remains planned. Web Content Accessibility Guidelines 2.2 Level
AA conformance is not yet claimed; keyboard, screen-reader, contrast, high-DPI,
and reduced-motion evidence remain pending.

## 7. Dependency and launch

PySide6 6.11.1 and its exact transitive Qt packages are pinned. The selected
release supports the approved Python range and provides Windows wheels. Its
declared open-source license expression is recorded in
`docs/operations/dependency-baseline.md`.

After installing the locked environment and editable package, launch the shell
with:

```powershell
.\.venv\Scripts\docweave-desktop.exe
```

Packaged desktop delivery remains a separate architecture decision.

## 8. Verification and non-claims

Automated evidence covers:

- application bootstrap and metadata;
- virtualized table content and size formatting;
- authorized-root scanning and nested relative paths;
- worker progress, success, cancellation, and minimized failure output;
- background completion without freezing the event loop;
- cooperative cancellation with partial-result discard;
- validated in-memory workspace transitions and multiple row selection;
- current-state, root-containment, file-type, symlink, and signature checks
  before embedded PDF preview;
- real Qt PDF loading, multipage mode, zoom controls, and malformed-document
  states using controlled test files;
- root-change and close protection during an active scan;
- missing-root, invalid-result, and non-directory failure states; and
- folder-picker authorization.

This implementation does not claim progressive row delivery, repeated-scan
comparison, durable checkpoints, persistence across restart, extracted-text
review, annotation, classification, operation approval, restore, cloud parity,
packaging, or production readiness.
