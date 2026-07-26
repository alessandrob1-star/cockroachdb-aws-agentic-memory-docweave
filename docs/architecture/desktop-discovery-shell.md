# Desktop Discovery Shell

**Project:** DocWeave
**Status:** Initial read-only PySide6 surface implemented locally
**Date:** 2026-07-26

## 1. Purpose

The first desktop surface makes the existing deterministic discovery and intake
core visible without implying that CockroachDB persistence, Amazon Bedrock
analysis, review, or file operations are connected.

The shell lets a user:

1. authorize one existing local directory;
2. start recursive discovery without blocking the user-interface thread;
3. inspect discovered, ready, and attention-required counts; and
4. view per-file relative path, deterministic intake state, byte size, and safe
   diagnostic category.

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
dedicated Qt thread. The main thread receives either one immutable result
snapshot or a minimized exception category.

While scanning:

- a duplicate start request is ignored;
- root changes are rejected;
- the scan button and root field are disabled; and
- window closure is deferred to avoid destroying an active thread.

The initial shell has no cancellation control because the current synchronous
discovery core has no safe cooperative-cancellation contract. Cancellation,
progressive row delivery, and durable checkpoints remain required before the
10,000-file user-interface acceptance scenario is claimed.

## 4. Presentation and accessibility baseline

The document table uses a read-only `QAbstractTableModel` rather than one widget
per cell. This is the correct base for later pagination or virtualization.
Controls, status messages, metrics, and the table have accessible names. Status
and safety meaning are expressed in text rather than color alone.

Windows rendering was inspected with both an empty workspace and a controlled
three-file result. Web Content Accessibility Guidelines 2.2 Level AA
conformance is not yet claimed; keyboard, screen-reader, contrast, high-DPI,
and reduced-motion evidence remain pending.

## 5. Dependency and launch

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

## 6. Verification and non-claims

Automated evidence covers:

- application bootstrap and metadata;
- virtualized table content and size formatting;
- authorized-root scanning and nested relative paths;
- worker success and minimized failure output;
- background completion without freezing the event loop;
- root-change and close protection during an active scan;
- missing-root, invalid-result, and non-directory failure states; and
- folder-picker authorization.

This implementation does not claim progressive results, repeated-scan
comparison, persistence across restart, PDF preview, content extraction,
classification, review, operation approval, restore, cloud parity, packaging,
or production readiness.
