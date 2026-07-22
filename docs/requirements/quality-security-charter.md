# Quality and Security Charter

**Project:** DocWeave
**Effective date:** 2026-07-21
**Status:** Mandatory engineering baseline

## 1. Objective

DocWeave will be developed as a credible, production-minded agentic document
system, not as a fragile hackathon prototype. Quality means correct behavior,
genuine intelligence, secure boundaries, reproducibility, accessibility,
observability, and honest evidence.

Security and quality gates are release requirements. They are not postponed to
the final week.

## 2. Local benchmark

The minimum comparison project is
`D:\repo\ai-act-compliance-navigator-openai-build-week`.

Observed benchmark evidence on 2026-07-21:

| Area | Evidence |
| --- | --- |
| Automated tests | 14 test files, 134 discovered test functions, and a final report recording 133 passed tests |
| Documentation | 64 Markdown or reStructuredText files |
| Continuous Integration | Two GitHub Actions workflows covering quality, tests, security, Docker, and demo artifacts |
| Static quality | Ruff formatting and linting, MyPy type checking, Python compilation, and JavaScript syntax checks |
| Security | Gitleaks, private-key detection, dependency vulnerability audit, pinned tooling, security policy, and Dependabot |
| Runtime validation | Docker builds, Compose validation, package smoke tests, generated reports, and agent traces |
| Governance | Contributing guide, code owners, pull-request template, security reporting policy, architecture and agent documentation |
| Product evidence | Final validation report, multilingual and responsive checks, policy-agent evaluations, and documented limitations |

DocWeave must meet or exceed the depth of these controls. Test counts alone do
not establish parity; coverage must address DocWeave's own risks.

## 3. Standards baseline

Use the following current primary references, tailored to project scope:

- [OWASP Application Security Verification Standard 5.0.0](https://owasp.org/www-project-application-security-verification-standard/), targeting Level 2 where applicable;
- [OWASP Top 10 for Large Language Model Applications 2025](https://genai.owasp.org/llm-top-10/);
- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/);
- [NIST Secure Software Development Framework 1.1](https://csrc.nist.gov/pubs/sp/800/218/final);
- [NIST AI Risk Management Framework and Generative AI Profile](https://www.nist.gov/itl/ai-risk-management-framework);
- [AWS Well-Architected Framework Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html);
- [SLSA specification 1.2](https://slsa.dev/spec/v1.2/), targeting Build Level 2 where feasible;
- [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/), targeting Level AA.

These are risk-based references, not unsupported certification claims. Any
conformance claim requires a mapped assessment and evidence.

## 4. Mandatory quality gates

Every pull request and release candidate must pass applicable gates:

1. deterministic formatting check;
2. linting with bug-risk and security rules;
3. strict static type checking for application code;
4. schema and configuration validation;
5. unit tests;
6. integration and contract tests;
7. end-to-end tests for critical user journeys;
8. agent and retrieval evaluations;
9. secret scanning across the full Git history;
10. Software Composition Analysis for vulnerable dependencies;
11. Static Application Security Testing;
12. Infrastructure as Code security scanning;
13. container image scanning when containers are introduced;
14. Software Bill of Materials generation for releases;
15. license-policy validation;
16. accessibility and responsive-layout checks;
17. deployment smoke test and rollback verification;
18. documentation and competition-evidence validation.

Gates fail closed. A scanner crash or skipped mandatory job is a failure, not a
pass.

## 5. Test strategy

Tests must cover behavior and failure, not only happy paths.

| Layer | Required coverage |
| --- | --- |
| Unit | Parsers, validators, policies, state transitions, scoring, permissions, and naming rules |
| Contract | Agent inputs and outputs, database schemas, events, application programming interfaces, and model structured output |
| Integration | CockroachDB transactions and vectors, Amazon storage, Bedrock invocation, queues, and authentication boundaries |
| End-to-end | Upload, analysis, proposal, human review, approval, organization, relationship navigation, and audit replay |
| Evaluation | Classification, name quality, relationship precision, citation grounding, refusal behavior, prompt injection, and memory poisoning |
| Resilience | Retries, duplicate events, partial failures, timeouts, unavailable models, database contention, and recovery |
| Security | Authorization bypass, path traversal, malicious files, unsafe content, injection, data leakage, and tool abuse |

Initial coverage targets:

- at least 85 percent line coverage for application code;
- at least 95 percent branch coverage for authorization, policy, audit,
  irreversible-action, and workflow state-transition modules;
- 100 percent coverage of documented critical acceptance scenarios;
- zero accepted flaky tests.

Threshold changes require an approved Architecture Decision Record.

## 6. Agent quality and evaluation

- Maintain a versioned, legally usable evaluation corpus.
- Separate training examples, development fixtures, and final evaluation cases.
- Record model identifier, prompt version, tool version, input hash, output,
  latency, tokens, estimated cost, confidence, and evaluator result.
- Evaluate both quality and calibration. Confidence must not be fabricated.
- Use deterministic validators for schemas, permissions, citations, and policy
  constraints, not as replacements for model reasoning.
- Run regression evaluations when models, prompts, tools, chunking, embeddings,
  or schemas change.
- Define minimum thresholds before tuning against the final evaluation set.
- Preserve unsuccessful cases and disclose known limitations.
- Never present cached or fixture output as a live model result.

Provisional metrics to refine before implementation:

- document classification macro F1 score at least 0.90 on the approved corpus;
- relationship precision at least 0.90 for surfaced high-confidence links;
- valid structured-output rate at least 99 percent after bounded retry;
- grounded material-claim rate at least 95 percent where source evidence exists;
- unauthorized action execution rate exactly zero;
- critical prompt-injection and memory-poisoning attack success rate exactly zero
  in the release red-team suite.

## 7. Document ingestion hardening

- Accept only explicitly supported formats.
- Validate extension, declared content type, and file signature independently.
- Enforce size, page, object, recursion, and decompression limits.
- Detect encrypted, malformed, polyglot, active-content, macro-enabled, and
  archive-bomb cases.
- Quarantine before parsing when a file is suspicious.
- Parse in an isolated, resource-limited worker without ambient cloud authority.
- Store the immutable original before derived processing.
- Hash originals and derived artifacts and preserve provenance.
- Normalize filenames without trusting user paths.
- Prevent path traversal, symbolic-link escape, overwrite, and reserved-name
  attacks.
- Treat embedded instructions, links, metadata, and extracted text as untrusted
  data.

## 8. Agentic hardening

Controls must address the OWASP agentic risk classes, including:

- agent goal hijacking;
- tool misuse and exploitation;
- identity and privilege abuse;
- agentic supply-chain compromise;
- unexpected code execution;
- memory and context poisoning;
- insecure inter-agent communication;
- cascading failures;
- human trust exploitation;
- rogue or misaligned agent behavior.

Required design measures:

- explicit agent identities and narrowly scoped capabilities;
- allowlisted tools and validated structured arguments;
- separation of instructions, retrieved evidence, user data, and tool output;
- provenance and trust labels on every memory item;
- no direct execution of instructions found in documents;
- bounded loops, timeouts, budgets, retries, and concurrency;
- idempotency keys for retried work;
- circuit breakers and dead-letter handling;
- schema validation on every inter-agent message;
- human approval for rename, move, delete, overwrite, and external share;
- immediate authorization re-check before executing approved actions;
- immutable audit events for proposals, approvals, rejections, and executions.

## 9. Data and CockroachDB hardening

- CockroachDB is the authoritative application memory and system of record.
- Transactional state, embeddings, relationships, agent runs, review decisions,
  and audit events share explicit ownership and lifecycle rules.
- Every query is parameterized.
- Workspace and user scope is enforced server-side.
- Sensitive values are minimized and encrypted where required.
- Vector retrieval cannot bypass document authorization.
- Derived memory records reference source document versions and extraction
  provenance.
- Untrusted or disputed memories can be quarantined, superseded, or revoked
  without rewriting history.
- Destructive migrations require backups, tested rollback, and user approval.
- Schema migrations are versioned, reviewed, reproducible, and tested against a
  realistic CockroachDB environment.

## 10. AWS hardening

- Local AWS administration and development use the project owner's AWS root
  profile, as explicitly directed by the project owner. Deployed application
  workloads use dedicated AWS service roles and never receive human login
  credentials.
- Apply least privilege and separate deployment, runtime, and human identities.
- Use short-lived credentials and runtime secret resolution.
- Use Infrastructure as Code for reproducible resources and reviewed changes.
- Encrypt storage and network traffic.
- Block unintended public access by default.
- Log material control-plane and application events without leaking document
  contents or secrets.
- Define alarms for errors, latency, throttling, security events, and cost.
- Establish AWS Budget alerts before paid workloads.
- Define backup, recovery, retention, and deletion behavior.
- Test degraded dependencies and rollback before the public demo.

## 11. Software supply chain

- Pin direct dependencies and commit deterministic lock files.
- Use automated dependency update pull requests with review and test gates.
- Scan dependencies, containers, Infrastructure as Code, licenses, and secrets.
- Generate a CycloneDX Software Bill of Materials for release artifacts.
- Prefer maintained primary packages and record rejected alternatives.
- Pin third-party automation actions to immutable commit identifiers before
  release.
- Produce build provenance and target SLSA Build Level 2 where feasible.
- Never download and execute unverified scripts in a release workflow.

## 12. Observability and auditability

- Use structured logs with correlation identifiers across agents and services.
- Record workflow state changes, tool calls, approval decisions, model usage,
  errors, latency, retries, and cost.
- Redact secrets and minimize personal or document content in telemetry.
- Distinguish live, cached, fixture, and degraded-mode data visibly.
- Provide a replayable evidence trail without storing hidden model reasoning.
- Define service-level indicators for availability, latency, error rate, queue
  age, evaluation regressions, and cost per document.

## 13. User experience and accessibility

- Target Web Content Accessibility Guidelines 2.2 Level AA.
- Support keyboard navigation, visible focus, semantic labels, status messages,
  adequate contrast, reduced motion, and non-color-only meaning.
- Human review screens must clearly separate facts, model proposals, confidence,
  evidence, and consequences.
- Destructive or high-impact actions require explicit confirmation and provide
  recovery where practical.
- Empty, loading, error, retry, degraded, and partial-success states are designed
  intentionally.
- Responsive layout and core journeys receive automated and manual checks.

## 14. Documentation and evidence

Required living documents include:

- project charter and scope;
- architecture and data-flow diagrams;
- Architecture Decision Records;
- threat model and abuse cases;
- data classification and retention policy;
- agent contracts and authority matrix;
- evaluation plan and results;
- security policy and vulnerability reporting process;
- operations, rollback, backup, and incident runbooks;
- cost model and observed cost report;
- final validation report;
- competition evidence matrix and demo script.

## 15. Release gate

A release candidate is blocked when:

- a mandatory test or security gate fails or is skipped;
- a critical or high vulnerability is unresolved without an approved exception;
- competition evidence is missing;
- a claimed integration cannot be reproduced;
- the public demo differs materially from the tagged source;
- a destructive agent action can bypass human approval;
- secrets or unauthorized data are present;
- cost controls, rollback, or audit evidence are absent;
- documentation materially misrepresents behavior.
