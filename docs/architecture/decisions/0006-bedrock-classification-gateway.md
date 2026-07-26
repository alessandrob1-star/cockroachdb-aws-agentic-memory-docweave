# ADR-0006: Bedrock Classification Gateway

**Status:** Accepted
**Decision date:** 2026-07-26
**Decision owner:** Project owner
**Implementation status:** Implemented locally; live invocation pending approval

## Context

The approved `classification.v1` contract needs a production-shaped Amazon
Bedrock Runtime boundary. The boundary must call the European Claude Sonnet 4.6
inference profile, preserve observed service provenance, use bounded retries
and timeouts, reject incomplete responses, and avoid turning volatile pricing
or credentials into source-code constants.

This implementation step is approved for offline construction and tests. It
does not authorize a Bedrock inference request, cloud resource, secret,
CockroachDB write, user-interface action, or paid operation.

## Decision

DocWeave will use the AWS Software Development Kit for Python, boto3
`1.43.56`, and its pinned botocore dependency to call the Bedrock Runtime
Converse API.

The gateway is fixed to:

| Setting | Value |
| --- | --- |
| Source region | `eu-central-1` |
| Inference profile | `eu.anthropic.claude-sonnet-4-6` |
| Connection timeout | 5 seconds |
| Read timeout | 90 seconds |
| Retry mode | Adaptive |
| Total attempts | 5, including the initial attempt |
| Connection pool | 10 |

The gateway reuses the explicit 4,096 output-token maximum and structured
output configuration from `classification.v1`. It supplies no tools and
performs no file or database action.

The boto3 session uses the standard credential provider chain. No access key,
secret key, session token, account identifier, endpoint, or credential value
is accepted by the gateway constructor or committed to the repository.
Creating the module performs no client creation. The client factory is invoked
explicitly by future runtime composition.

## Response and provenance

Only `end_turn` is accepted as a successful completion reason. Truncation,
guardrail intervention, content filtering, malformed output, tool use, and
unknown stop reasons fail closed.

The response must contain exactly one assistant text block plus valid token,
latency, request, and retry metadata. The text is decoded through the existing
`classification.v1` evidence validator.

The gateway records:

- configured region and inference profile;
- contract and taxonomy versions;
- stop reason;
- input, output, total, cache-read, and cache-write token counts;
- Bedrock-reported latency;
- locally observed duration;
- request identifier;
- Software Development Kit retry count; and
- an estimated cost only when current pricing is supplied explicitly.

The model-authored JSON cannot set or override this provenance.

## Cost boundary

Token prices are not hardcoded because Bedrock pricing is externally managed
and may change. A caller may supply current input and output prices in US
dollars per million tokens. The estimate is labelled as an estimate and does
not replace AWS billing evidence.

Prompt caching is not enabled in `classification.v1`. Cache token counts are
recorded for forward compatibility, but the current estimator covers uncached
input and output only.

The first real request requires a separately approved current-price estimate,
a small named synthetic target, and confirmation that no private document is
being sent.

## Error policy

The gateway maps authentication, access denial, throttling, model timeout,
service unavailability, request validation, transport, filtering, truncation,
and response-validation failures to stable content-free codes.

It does not expose AWS error messages, document content, model text, account
details, or request payloads in the public exception. botocore performs the
bounded retry policy; DocWeave does not add a second hidden retry loop.

There is no canned classification, alternate model, fabricated success, or
silent fallback when Bedrock is unavailable.

## Alternatives considered

### Invoke the AWS Command Line Interface from Python

Rejected because subprocess serialization and error parsing are less typed,
less reusable, and harder to integrate with desktop and cloud runtimes.

### Use `InvokeModel`

Rejected because Converse provides the approved model-independent request
shape and native structured-output field.

### Add a manual application retry loop

Rejected for this boundary because botocore adaptive retries already handle
retryable transport and service failures. A second loop could multiply calls
and cost. A future bounded retry for invalid model semantics is a distinct
recorded agent attempt, not an invisible network retry.

### Hardcode current token prices

Rejected because stale prices would produce misleading estimates. Pricing must
be supplied from a reviewed, dated configuration before a paid batch.

## Consequences

### Benefits

- desktop and cloud code can share one tested Bedrock boundary;
- credentials follow the AWS provider chain and never enter repository code;
- model, token, latency, retry, and request provenance comes from the real API;
- failures remain sanitized and machine-actionable;
- no hidden fallback can impersonate model intelligence; and
- the first live test can remain small and explicitly cost-controlled.

### Costs and limitations

- boto3 and six transitive packages enter the pinned dependency inventory;
- no live classification or quality evidence exists until an approved call;
- raw response retention remains unresolved and no raw response is retained;
- the initial estimator does not price prompt-cache reads or writes; and
- application bootstrap, CockroachDB checkpointing, and user-interface wiring
  remain pending.

## Verification

Acceptance requires:

- a current AWS Command Line Interface and valid local authentication;
- the approved inference profile reported active without invoking it;
- pinned direct and transitive dependency versions;
- client construction tests for region, retry, timeout, and pool settings;
- request tests proving the approved model and explicit output-token limit;
- success tests for validated proposals and observed provenance;
- failure tests for stop reasons, malformed responses, fabricated evidence,
  Software Development Kit errors, and AWS service errors;
- no network call in the automated test suite;
- the complete local quality gate; and
- GitHub Actions success before merge.

## References

- [ADR-0001: Amazon Bedrock Primary Model](0001-amazon-bedrock-primary-model.md)
- [ADR-0005: Classification v1 Structured Contract](0005-classification-v1-contract.md)
- [AWS SDK for Python documentation](https://docs.aws.amazon.com/boto3/latest/guide/quickstart.html)
- [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
