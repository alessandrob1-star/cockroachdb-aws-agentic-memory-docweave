# Project Governance

- Read `PROJECT_RULES.md` before proposing or performing project work.
- Treat `docs/requirements/competition-rules.md`,
  `docs/requirements/quality-security-charter.md`, and
  `docs/requirements/requirements-traceability-matrix.md` as mandatory project
  governance documents.
- Explain the objective, reason, alternatives, cost, risks, and exact scope to
  the user before starting a new initiative. Obtain explicit approval before
  implementation, architecture changes, cloud mutations, database schema
  changes, new dependencies, model changes, spending, external publication,
  or destructive actions.
- Keep source code, resource names, repository artifacts, and submission
  materials in English. Explain work to the user in Italian and expand an
  acronym the first time it appears.
- The minimum quality floor is the local benchmark project
  `D:\repo\ai-act-compliance-navigator-openai-build-week`. DocWeave must meet
  or exceed its engineering, testing, security, documentation, user experience,
  and demonstration quality.
- Never claim competition compliance, security, test success, production
  readiness, or meaningful service integration without current evidence.
- Never replace model-driven or retrieval-driven behavior with hardcoded
  answers, fabricated success, hidden demo bypasses, or test-specific shortcuts.

# AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
