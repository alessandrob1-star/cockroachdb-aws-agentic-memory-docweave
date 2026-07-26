# Amazon Bedrock Live Classification Validation

**Validation date:** 2026-07-26

**Source region:** `eu-central-1`

**Synthetic target:** `pdf_sintetici/scan_000184.pdf`

## Purpose

This record provides bounded evidence that real PDF extraction, an Amazon
Bedrock model invocation, constrained proposal emission, deterministic evidence
reconstruction, and fail-closed validation can complete as one slice. It is not
a corpus-quality or production-readiness claim.

## Accepted run

The temporary European Amazon Nova 2 Lite profile returned one proposal that
passed the complete `classification.v1` decoder:

| Observation | Value |
| --- | --- |
| Proposed class | `purchase_order` |
| Stop reason | `tool_use` |
| Input tokens | 4,582 |
| Output tokens | 2,342 |
| Total tokens | 6,924 |
| Service latency | 6,928 ms |
| SDK retries | 0 |
| Estimated cost | 0.0072296 USD |

The model selected only supplied evidence-segment identifiers. DocWeave
reconstructed exact page indexes and quotations locally. No model-authored
quotation, filename, path, database statement, tool action, or AWS provenance
field was trusted.

## Fail-closed observations

Earlier bounded calls were rejected rather than converted into fabricated
success:

- the initial Sonnet slice produced no accepted proposal;
- Opus emitted an evidence-invalid proposal and later became unavailable
  because its commercial agreement was not active under the approved account
  plan;
- Nova rejected the unsupported Bedrock `outputConfig`;
- the first forced emission used invalid cross-reference identifiers and was
  rejected with `schema_invalid`.

The final accepted run followed deterministic evidence segmentation and a
forced, side-effect-free `emit_classification` envelope.

## Limitation

The selected synthetic PDF includes controlled-testing notes and an expected
category on its second page. The accepted class is correct, but this document
cannot measure blind classification quality. A later curated evaluation must
remove answer-bearing control metadata from model-visible content and evaluate
multiple categories, ambiguity, prompt injection, and abstention.
