# ADR-0001: Amazon Bedrock Primary Model

**Status:** Accepted
**Decision date:** 2026-07-22; revised 2026-07-26; reviewed 2026-07-29
**Decision owner:** Project owner
**Implementation status:** In progress; temporary model validated on one
bounded integration target

## Context

DocWeave requires a managed Large Language Model (LLM) for document analysis,
classification, naming proposals, relationship reasoning, and bounded agent
decisions. The model must support high-quality reasoning, multimodal document
inputs, predictable machine-readable results, and deployment through Amazon
Bedrock in the European geography.

The Minimum Viable Product (MVP) needs one stable primary model before prompt
contracts, evaluation fixtures, cost measurements, and runtime integration can
be designed. Selecting a model does not authorize cloud resource creation or
model invocation.

## Decision

DocWeave will temporarily use **Amazon Nova 2 Lite** as its primary MVP model
through Amazon Bedrock. This is a reversible pre-development selection, not a
claim that Nova 2 Lite is the final production model.

| Setting | Approved value |
| --- | --- |
| Provider | Amazon |
| Model | Nova 2 Lite |
| Base model identifier | `amazon.nova-2-lite-v1:0` |
| Geographic inference profile | `eu.amazon.nova-2-lite-v1:0` |
| AWS source region | `eu-central-1` |
| Runtime interface | Amazon Bedrock Runtime Converse API |
| Output contract | Forced side-effect-free tool input constrained by a versioned JSON Schema |
| Commercial mode | On-demand inference |

The European geographic inference profile is selected so Bedrock may route
requests across supported European Regions for capacity while retaining the
European geographic boundary. The application will not silently replace it
with a global inference profile.

Every request will set an explicit maximum output-token value. Limits will be
defined per agent contract rather than allowing a model maximum to become the
application default.

## Why this temporary model

Nova 2 Lite provides the strongest currently usable AWS-native baseline found
for the approved account state:

- reasoning support for document processing and business automation;
- text and image input support;
- response streaming for interactive user experiences;
- prompt caching support for reusable taxonomy and policy context; and
- constrained tool input through Bedrock Runtime, reducing malformed
  classification records without exposing an action-capable tool.

The project owner first revised the initial Sonnet 4.6 selection to Opus 4.6
after a bounded Sonnet slice produced no accepted classification. A bounded
Opus request reached the model, but later requests could not proceed because
the required commercial agreement was not active under the current account
plan. The owner explicitly prohibited upgrading the account plan at this
stage. Nova 2 Lite was therefore selected as a disclosed temporary model after
AWS reported its agreement, authorization, entitlement, European profile, and
regional availability as active. It is not a silent fallback.

Structured model output is especially important because DocWeave must persist typed
classification, evidence, confidence signals, alternatives, and provenance.
Free-form text is not an acceptable authoritative interface between an LLM and
CockroachDB.

## Alternatives considered

### Claude Sonnet 4.6

Sonnet 4.6 remains a quality candidate. On 2026-07-29, the European inference
profile was listed as active, but a live Converse request failed because
Anthropic use-case details had not been submitted for the account. It is not
currently usable by the runtime until that account-side requirement is
completed and revalidated.

### Claude Opus 4.6

Opus 4.6 remains the preferred quality candidate for a later controlled
benchmark. It is not currently usable because its commercial model agreement
is unavailable under the approved account plan. DocWeave will not activate a
paid account plan or silently route to a global profile to obtain access.

### Claude Sonnet 5

Sonnet 5 is newer and may provide higher reasoning quality. It was not selected
as the MVP primary because its current Bedrock Runtime feature set does not
provide the same structured-output support needed by the classification
contract. It may later be evaluated as a bounded reviewer for difficult cases.
That use requires a separate benchmark, cost analysis, and approval.

### Claude Haiku 4.5

Haiku 4.5 offers lower latency and cost. It remains a candidate for simple,
high-volume stages only if evaluation demonstrates that it preserves the
required quality. Cost alone is not sufficient reason to weaken the primary
classification path.

### Amazon Nova 2 Lite

Nova 2 Lite remains the temporary selected model. A 2026-07-29 live
desktop-runtime attempt returned invalid evidence references on one synthetic
PDF and was rejected fail-closed by DocWeave. It remains selected only because
the Anthropic profile is not yet usable under the current account state.

## Consequences

### Benefits

- One model baseline makes evaluation and regression results comparable.
- The Converse API provides a consistent Bedrock integration boundary.
- European geographic routing improves capacity without choosing global data
  routing.
- Constrained tool input supports deterministic validation before persistence.

### Costs and limitations

- Usage is billed by input and output tokens.
- The temporary model may not match Claude Opus quality on DocWeave tasks.
- Large document contexts can increase cost and latency, so extraction,
  chunking, caching, and token budgets still require explicit design.
- Model output remains untrusted until schema, evidence, policy, and
  authorization checks pass.
- A model version change requires a new Architecture Decision Record,
  regression evaluation, cost comparison, and project-owner approval.

## Verification required before implementation is accepted

1. Confirm the inference profile remains active in `eu-central-1`.
2. Confirm account access without running an unbounded request.
3. Define and validate the versioned structured-output schema.
4. Evaluate classification quality on the approved synthetic corpus.
5. Measure token use, latency, retry rate, and cost per document.
6. Demonstrate that invalid or incomplete model output cannot become canonical
   CockroachDB state.
7. Record the exact model and inference-profile identifiers with every result.

Items 1 through 3 now have local evidence: the Nova 2 Lite European inference
profile and account access were reported available on 2026-07-26 without
invocation, `classification.v1` is implemented, and ADR-0006 provides the
pinned gateway and provenance boundary. Items 4 through 7 still require a
separately approved live synthetic evaluation and durable persistence
evidence.

## Out of scope

This decision does not approve prompt text, confidence thresholds, a secondary
model, optical character recognition, database schema, AWS infrastructure, or
production invocation.
