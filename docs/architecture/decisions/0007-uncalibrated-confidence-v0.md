# ADR-0007: Uncalibrated Confidence v0.1

**Status:** Accepted for pre-evaluation use
**Date:** 2026-07-26
**Decision owner:** Project owner

## Context

The classification runtime must persist the separate confidence fields required
by the approved physical schema. The `classification.v1` model contract emits
ordinal signals because a model-generated percentage is not a verified
probability. The runtime previously required an injected score provider and
correctly had no fabricated default, but that prevented a complete local
classification write path.

The full calibration method still requires reviewed corpus outcomes. No
calibrated probability or automated threshold can be selected before that
evidence exists.

## Decision

Adopt `confidence.raw.v0_1` as a deterministic, uncalibrated review-ordering
method. Its values are bounded from zero to one for storage compatibility but
must not be described as probabilities or displayed using High, Medium, or Low
thresholds.

The classification base is:

```text
0.50 * classification strength
+ 0.30 * evidence coverage
+ 0.20 * inverse ambiguity
```

Ordinal values are:

| Signal | Strength and coverage | Inverse ambiguity |
| --- | ---: | ---: |
| Strong | 0.85 | 0.35 |
| Moderate | 0.60 | 0.60 |
| Weak | 0.35 | 0.85 |

The following bounded deductions apply:

- `0.10` per contradiction, capped at `0.30`;
- `0.03` per missing expected-evidence item, capped at `0.15`; and
- `0.05` per alternative class, capped at `0.10`.

`raw_confidence` equals the resulting uncalibrated classification score.
`calibrated_confidence` remains `NULL`.

Extraction confidence is the bounded ratio of extracted page records to the
verified document page count, and becomes zero when completion or source
provenance is missing.

Metadata confidence is the fraction of candidate metadata entries whose cited
evidence identifiers exist in the validated proposal. It is zero when no
metadata was proposed.

All values use decimal arithmetic and five decimal places. Filenames,
directories, model-authored percentages, costs, and provider latency do not
affect the score.

## Alternatives considered

### Persist model-generated percentages

Rejected. They would present uncalibrated model self-assessment as measured
confidence.

### Use one fixed value for every proposal

Rejected. It would satisfy the database shape while hiding meaningful
differences in evidence and uncertainty.

### Block all proposal persistence until calibration

Rejected for the pre-evaluation phase. It would prevent durable collection of
the proposals and human outcomes needed for later evaluation.

### Select calibrated thresholds now

Rejected. No held-out reviewed dataset currently supports thresholds or
probability claims.

## Consequences and controls

- The score can order a review queue but cannot authorize file operations,
  suppress human review, or label a proposal High, Medium, or Low.
- Stronger signals increase the score; contradictions, missing evidence, and
  alternatives cannot increase it.
- The method is versioned in every persisted proposal.
- Calibration must use held-out reviewed outcomes and record method,
  parameters, dataset version, class coverage, sample size, and evaluation
  date.
- Corpus evaluation may replace the weights or the whole method through a new
  version and Architecture Decision Record. Historical scores remain
  attributable to `confidence.raw.v0_1`.
- Tests cover bounds, monotonic behavior, missing provenance, metadata
  evidence, exact decimal results, and explicit absence of calibration.

## Non-claims

This decision does not establish classification accuracy, calibration,
confidence bands, automatic-approval thresholds, corpus quality, or production
readiness.
