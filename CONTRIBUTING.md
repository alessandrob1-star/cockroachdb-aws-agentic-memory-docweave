# Contributing to DocWeave

## Governance first

Read [`PROJECT_RULES.md`](PROJECT_RULES.md) and the documents under
[`docs/requirements`](docs/requirements/README.md) before proposing a change.
An implementation must not silently redefine an approved requirement.

## Branch and pull-request workflow

1. Start from the current protected default branch.
2. Create a focused branch using a descriptive prefix such as `codex/`,
   `feature/`, `fix/`, `docs/`, or `security/`.
3. Keep the change limited to one reviewable objective.
4. Add or update tests, evidence, documentation, and traceability together.
5. Open a draft pull request early for substantial work.
6. Resolve required checks and review findings before marking it ready.
7. Merge only when the approved acceptance criteria and release gates pass.

## Pull-request content

Every pull request shall explain:

- what changed and why;
- which approved requirement or decision authorizes the change;
- user, security, privacy, reliability, and cost effects;
- the tests and evidence used for verification;
- limitations, deferred work, and rollback considerations.

## Data and secret safety

- Never commit real company documents or private reference workbooks.
- Never commit credentials, tokens, passwords, private keys, or production
  configuration.
- Use synthetic, authorized, or safely licensed demonstration data.
- Treat PDF contents, filenames, paths, and model output as untrusted input.

## Integrity

Do not replace model-driven or retrieval-driven behavior with canned outputs,
hidden demo bypasses, fabricated success, or test-specific shortcuts. A known
limitation must be disclosed and addressed through an approved decision.
