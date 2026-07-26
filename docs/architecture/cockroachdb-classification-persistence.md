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
the runtime requires an injected score provider and has no fallback. The
desktop must not manufacture scores merely to write a proposal.

## Runtime sequence

The side-effect-free runtime builder composes one transaction runner, the
document and taxonomy repository, and the classification repository around
caller-supplied engine, Bedrock gateway, and score provider dependencies.
Construction opens no connection and invokes no model.

One explicit classification request then:

1. extracts the authorized PDF in the existing disposable worker;
2. rejects unusable text or incomplete extraction provenance before database
   or model input/output;
3. registers or exactly replays the logical document and verified version;
4. installs or verifies the complete approved taxonomy with human authority;
5. invokes Bedrock outside every database transaction;
6. obtains versioned scores from the mandatory injected provider; and
7. atomically persists the run, proposal subtype, and evidence.

Document registration is durable even if later model analysis fails. That
record is verified intake state, not a fabricated classification success.

## Current limitations

- No application runtime composes this repository with extraction and Bedrock.
- No file-instance registration is implemented.
- No review, canonical promotion, workflow checkpoint, or classification audit
  event is implemented in this revision.
- No vector column or index is created; embedding parameters remain unresolved.
- Local tests prove document and taxonomy replay behavior, statement
  parameterization, runtime ordering, fail-closed extraction gates, transaction
  grouping, conflict handling, side-effect-free composition, and offline
  migration rendering. Live validation evidence is recorded separately.
