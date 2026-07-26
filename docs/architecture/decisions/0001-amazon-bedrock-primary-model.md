# ADR-0001: Amazon Bedrock Primary Model

**Status:** Accepted
**Decision date:** 2026-07-22
**Decision owner:** Project owner
**Implementation status:** In progress; gateway implemented, live invocation pending

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

DocWeave will use **Anthropic Claude Sonnet 4.6** as its primary MVP model
through Amazon Bedrock.

| Setting | Approved value |
| --- | --- |
| Provider | Anthropic |
| Model | Claude Sonnet 4.6 |
| Base model identifier | `anthropic.claude-sonnet-4-6` |
| Geographic inference profile | `eu.anthropic.claude-sonnet-4-6` |
| AWS source region | `eu-central-1` |
| Runtime interface | Amazon Bedrock Runtime Converse API |
| Output contract | Bedrock structured output constrained by a versioned JSON Schema |
| Commercial mode | On-demand inference |

The European geographic inference profile is selected so Bedrock may route
requests across supported European Regions for capacity while retaining the
European geographic boundary. The application will not silently replace it
with a global inference profile.

Every request will set an explicit maximum output-token value. Limits will be
defined per agent contract rather than allowing a model maximum to become the
application default.

## Why this model

Claude Sonnet 4.6 provides the balance required for the MVP:

- strong document reasoning and agent planning;
- text and image input support;
- a large context window for substantial documents and grounded context;
- response streaming for interactive user experiences;
- prompt caching support for reusable taxonomy and policy context; and
- native structured outputs through Bedrock Runtime, reducing malformed
  classification records and avoidable retries.

Structured output is especially important because DocWeave must persist typed
classification, evidence, confidence signals, alternatives, and provenance.
Free-form text is not an acceptable authoritative interface between an LLM and
CockroachDB.

## Alternatives considered

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

Nova 2 Lite is a cost-efficient multimodal document-processing model. It was
not selected as the primary because the approved design prioritizes reasoning
quality and a reliable structured classification contract. It remains an
evaluation candidate rather than a hidden fallback.

## Consequences

### Benefits

- One model baseline makes evaluation and regression results comparable.
- The Converse API provides a consistent Bedrock integration boundary.
- European geographic routing improves capacity without choosing global data
  routing.
- Structured output supports deterministic validation before persistence.

### Costs and limitations

- Usage is billed by input and output tokens.
- Anthropic may require completion of its one-time model-use questionnaire
  before the first invocation.
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

Items 1 through 3 now have local evidence: the European inference profile was
reported active on 2026-07-26 without invocation, `classification.v1` is
implemented, and ADR-0006 provides the pinned gateway and provenance boundary.
Items 4 through 7 still require a separately approved live synthetic
evaluation and durable persistence evidence.

## Out of scope

This decision does not approve prompt text, confidence thresholds, a secondary
model, optical character recognition, database schema, AWS infrastructure, or
production invocation.
