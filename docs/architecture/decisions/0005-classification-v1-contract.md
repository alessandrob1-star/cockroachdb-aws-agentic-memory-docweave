# ADR-0005: Classification v1 Structured Contract

**Status:** Accepted
**Decision date:** 2026-07-26
**Decision owner:** Project owner
**Implementation status:** Implemented locally; pull-request verification pending

## Context

DocWeave needs a versioned boundary between extracted page evidence and genuine
Amazon Bedrock classification. Free-form model text cannot become an
application proposal merely because it is valid prose or JSON. The boundary
must distinguish untrusted document content, untrusted model output,
deterministic validation, and runtime provenance observed from the Bedrock API.

The contract supports model-specific constrained emission through Amazon
Bedrock Runtime Converse. The current Nova 2 Lite integration forces a
side-effect-free `emit_classification` tool whose input uses the versioned JSON
Schema. The application still validates business invariants and evidence
independently and never executes the emission tool.

This decision does not approve a model invocation, Python Software Development
Kit dependency, CockroachDB migration or write, prompt logging, cloud resource,
or paid operation.

## Decision

The first analysis response contract is `classification.v1`, tied to taxonomy
version `docweave_mvp_v0_1`.

The side-effect-free Converse request builder supplies:

- a system instruction that treats document text as untrusted evidence;
- page index, page label, and extracted text without a filename or source path;
- an explicit maximum of 4,096 output tokens;
- temperature `0.0`;
- the Bedrock `outputConfig.textFormat` JSON Schema; and
- contract and taxonomy labels as request metadata.

The builder refuses empty input, duplicate page indexes, more than 100 pages,
or more than 100,000 extracted characters. It never truncates evidence
silently. Context selection for documents beyond this initial bound requires a
separate, recorded strategy.

The response schema requires:

- contract and taxonomy versions;
- one proposed class from the approved taxonomy;
- document language;
- an evidence-backed rationale;
- exact page-level evidence quotations;
- candidate class-specific metadata with evidence references;
- distinct alternative classes considered;
- contradictions and missing expected evidence;
- ordinal raw signals for classification strength, evidence coverage, and
  ambiguity; and
- an abstention reason for `unclassified`.

Every object rejects additional properties. The schema uses only the supported
Bedrock JSON Schema subset. Application-side limits remain necessary because
the Bedrock subset does not support string-length or general numerical
constraints.

## Deterministic validation

The local decoder fails closed when:

- JSON is invalid, oversized, contains duplicate keys, or uses non-finite
  numbers;
- contract or taxonomy versions do not match;
- a class, language tag, evidence identifier, metadata name, or signal is
  invalid;
- unknown fields appear at any checked object boundary;
- evidence cites a missing page or a quotation not present verbatim on that
  page;
- evidence references are missing, duplicated, or unresolved;
- alternatives repeat the proposed class or one another;
- `unclassified` has no meaningful abstention reason; or
- any application-side count or text budget is exceeded.

The decoder creates a typed proposal, not a canonical classification. Human
review, confidence calculation, persistence, and promotion remain separate.

## Provenance boundary

Model identity, inference profile, request time, stop reason, token use,
latency, retry count, and cost are deliberately absent from the model-authored
JSON. Those values cannot be trusted when self-reported by a model.

The future Bedrock gateway will record them from its configured request and the
actual Converse response. The unresolved raw-response retention policy remains
an approval gate before persistence.

The approved taxonomy is centralized in the contract module for this fixed
version. CockroachDB remains the required authoritative versioned taxonomy
store once the corresponding reviewed schema and seed migration are
implemented.

## Alternatives considered

### Prompt for JSON without structured outputs

Rejected because prompt-only formatting produces avoidable malformed responses
and retries. It also weakens the service-level contract available in Bedrock.

### Trust Bedrock schema validation without local validation

Rejected because JSON Schema cannot prove that a quotation exists on the cited
page, that references resolve, or that an abstention follows DocWeave policy.
Model output remains untrusted data.

### Add Pydantic or `jsonschema`

Deferred because the current closed contract can be validated without a new
runtime dependency. A library may be reconsidered if contract breadth or
maintenance evidence justifies the added supply-chain surface.

### Include numeric model confidence

Rejected for `classification.v1`. A model-stated percentage is not calibrated
probability. The contract retains bounded ordinal raw signals; a separately
approved deterministic confidence service will calculate and calibrate
displayed values.

### Add the Bedrock gateway in the same increment

Deferred to keep model access, credentials, retry behavior, runtime provenance,
cost estimation, and the first paid invocation behind a separate approval and
verification boundary.

## Consequences

### Benefits

- the real intelligent path has a precise, versioned input and output shape;
- document prompt injection remains labelled data and cannot add tool calls;
- fabricated page evidence is rejected deterministically;
- no new dependency or cloud cost is introduced;
- the future gateway can use the current Converse structured-output API; and
- invalid model output cannot silently become an authoritative fact.

### Costs and limitations

- the fixed schema must be versioned when fields or taxonomy semantics change;
- the initial input bound requires later context selection for large
  documents;
- no live model quality is demonstrated until an approved Bedrock invocation;
- schema-constrained output can still contain semantically poor proposals; and
- confidence calibration, naming, relationships, and persistence remain
  unimplemented.

## Verification

Acceptance requires:

- deterministic construction of Converse fields with explicit output tokens;
- a closed Bedrock-compatible JSON Schema;
- successful decoding of evidence-backed and abstaining proposals;
- rejection of fabricated quotations, wrong pages, missing references, unknown
  fields, duplicate keys, wrong versions, and oversized responses;
- adversarial instruction and Structured Query Language strings remaining
  inert document evidence;
- strict type, lint, formatting, and test gates; and
- GitHub Actions success before merge.

## References

- [Amazon Nova structured output](https://docs.aws.amazon.com/nova/latest/userguide/concept-chapter-servicename.html)
- [Amazon Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [ADR-0001: Amazon Bedrock Primary Model](0001-amazon-bedrock-primary-model.md)
- [Classification and confidence specification](../../classification-and-confidence-specification.md)
