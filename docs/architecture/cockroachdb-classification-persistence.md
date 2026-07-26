# CockroachDB Classification Persistence Boundary

**Status:** Implemented adapter and migration; runtime wiring pending  
**Revision:** `0002_classification_memory`

## Purpose

This boundary persists one validated Amazon Bedrock classification run as
CockroachDB episodic and proposal memory without turning model output into an
authoritative document classification.

One serializable transaction writes:

1. the `agent_runs` provenance and minimized validated outcome;
2. one `proposals` row with status `needs_review`;
3. one `classification_proposals` subtype row; and
4. the proposal's inspectable `proposal_evidence` excerpts.

The migration deliberately does not create `document_classifications` or
`review_decisions`. Those canonical tables belong to the separately approved
human-review and promotion workflow.

## Integrity boundaries

- Every document, run, proposal, and evidence foreign key is workspace scoped.
- The caller supplies a stable idempotency key and request SHA-256 digest.
- An exact replay returns `idempotent_replay`; reuse with a different run
  identity or request digest fails closed.
- SQL statements use bound parameters for every model-derived or
  document-derived value.
- Evidence quotes are required, minimized, and limited to 2,000 characters.
- The structured outcome is validated application data, not a raw provider
  payload and not hidden model reasoning.
- No filename, absolute path, credential, or source PDF bytes are stored.
- The current invocation target is recorded as an inference profile. The
  underlying foundation-model identifier remains null until Bedrock exposes or
  the runtime independently verifies it.

## Confidence boundary

The Bedrock classification contract intentionally emits ordinal signals rather
than fabricated probabilities. Persistence therefore requires a caller-supplied
`ClassificationScores` value and explicit `method_version`. The adapter never
converts ordinal model words into numeric confidence on its own.

The confidence method and calibration process remain pending. Until approved,
the adapter is ready but the desktop runtime must not manufacture scores merely
to write a proposal.

## Current limitations

- No application runtime composes this repository with extraction and Bedrock.
- Document registration and taxonomy seeding are not implemented.
- No review, canonical promotion, workflow checkpoint, or classification audit
  event is implemented in this revision.
- No vector column or index is created; embedding parameters remain unresolved.
- Local tests prove statement shape, transaction grouping, parameter binding,
  exact replay behavior, conflict handling, and offline migration rendering.
  Live validation evidence is recorded separately.
