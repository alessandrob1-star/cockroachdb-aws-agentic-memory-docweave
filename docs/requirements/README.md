# Requirements Documentation

**Project:** DocWeave
**Status:** Active governance
**Language:** English is authoritative for repository artifacts

## Reading order

1. [`competition-rules.md`](competition-rules.md) — external competition
   obligations and submission evidence.
2. [`product-requirements.md`](product-requirements.md) — users, problem,
   functional behavior, constraints, and product success measures.
3. [`domain-data-requirements.md`](domain-data-requirements.md) — relational
   domain data, synthetic source boundaries, and the initial document taxonomy.
4. [`user-workflows.md`](user-workflows.md) — the safe, understandable journeys
   presented by the desktop and cloud interfaces.
5. [`mvp-scope-and-acceptance.md`](mvp-scope-and-acceptance.md) — the exact
   Minimum Viable Product boundary and objective acceptance criteria.
6. [`quality-security-charter.md`](quality-security-charter.md) — mandatory
   engineering, evaluation, security, and release gates.
7. [`requirements-traceability-matrix.md`](requirements-traceability-matrix.md)
   — mapping from requirements to controls, tests, evidence, and status.

Approved architecture that realizes these requirements is indexed from the
repository [`README.md`](../../README.md). The CockroachDB data-model baseline
is defined by
[`ADR-0002`](../architecture/decisions/0002-cockroachdb-physical-data-model.md),
the
[`physical-schema specification`](../architecture/cockroachdb-physical-schema.md),
and the
[`Entity Relationship model`](../architecture/cockroachdb-entity-relationship.md).

## Authority

These documents are governed by [`../../PROJECT_RULES.md`](../../PROJECT_RULES.md).
An approved requirement may be changed only through an explicit, documented
decision. A technical implementation does not silently redefine product
behavior.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| Proposed | Documented for discussion but not approved |
| Approved | Explicitly accepted as part of the product baseline |
| Planned | Approved but not implemented |
| Implemented | Present in the code or deployed system but not fully verified |
| Verified | Acceptance evidence exists and current gates pass |
| Deferred | Intentionally postponed with a recorded reason |
| Rejected | Considered and explicitly excluded |
