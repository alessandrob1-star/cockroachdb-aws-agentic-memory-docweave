from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ParamValidationError,
)

from docweave.analysis import (
    APPROVED_BEDROCK_MODEL_ID,
    APPROVED_BEDROCK_REGION,
    BEDROCK_CONNECT_TIMEOUT_SECONDS,
    BEDROCK_READ_TIMEOUT_SECONDS,
    BEDROCK_TOTAL_MAX_ATTEMPTS,
    BedrockClassificationGateway,
    BedrockGatewayConfig,
    BedrockGatewayError,
    BedrockGatewayErrorCode,
    BedrockTokenPricing,
    BedrockUsage,
    ClassificationValidationCode,
    TaxonomyClass,
    create_bedrock_runtime_client,
)
from docweave.extraction import ExtractedPage

PAGES = (
    ExtractedPage(
        page_index=0,
        page_label="1",
        text="INVOICE INV-17 Total EUR 42.00",
    ),
)


def _proposal_json(*, segment_id: str = "p0_s1") -> str:
    return json.dumps(
        {
            "contract_version": "classification.v1",
            "taxonomy_version": "docweave_mvp_v0_1",
            "proposed_class": "invoice",
            "document_language": "en",
            "rationale": "The document identifies itself as an invoice.",
            "rationale_evidence_ids": ["ev_1"],
            "evidence": [
                {
                    "evidence_id": "ev_1",
                    "segment_id": segment_id,
                    "supports": ["classification"],
                }
            ],
            "candidate_metadata": [],
            "alternative_classes": [],
            "contradictions": [],
            "missing_expected_evidence": ["supplier"],
            "raw_signals": {
                "classification_strength": "strong",
                "evidence_coverage": "moderate",
                "ambiguity": "weak",
            },
            "abstention_reason": None,
        }
    )


def _response(
    *,
    text: str | None = None,
    stop_reason: str = "tool_use",
) -> dict[str, Any]:
    tool_input = json.loads(text or _proposal_json())
    return {
        "stopReason": stop_reason,
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-123",
                            "name": "emit_classification",
                            "input": tool_input,
                        }
                    }
                ],
            }
        },
        "usage": {
            "inputTokens": 500,
            "outputTokens": 200,
            "totalTokens": 700,
        },
        "metrics": {"latencyMs": 321},
        "ResponseMetadata": {
            "RequestId": "request-123",
            "RetryAttempts": 2,
        },
    }


class FakeConverseClient:
    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = _response() if response is None else response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeSession:
    def __init__(self, client: FakeConverseClient) -> None:
        self.returned_client = client
        self.service_name: str | None = None
        self.kwargs: dict[str, Any] = {}

    def client(self, service_name: str, **kwargs: Any) -> FakeConverseClient:
        self.service_name = service_name
        self.kwargs = kwargs
        return self.returned_client


def test_client_factory_uses_approved_region_retries_and_timeouts() -> None:
    expected_client = FakeConverseClient()
    session = FakeSession(expected_client)

    client = create_bedrock_runtime_client(session=session)

    assert client is expected_client
    assert session.service_name == "bedrock-runtime"
    assert session.kwargs["region_name"] == APPROVED_BEDROCK_REGION
    config = session.kwargs["config"]
    assert isinstance(config, Config)
    assert config.retries == {
        "total_max_attempts": BEDROCK_TOTAL_MAX_ATTEMPTS,
        "mode": "adaptive",
    }
    assert config.connect_timeout == BEDROCK_CONNECT_TIMEOUT_SECONDS
    assert config.read_timeout == BEDROCK_READ_TIMEOUT_SECONDS
    assert config.max_pool_connections == 10
    assert config.user_agent_appid == "docweave"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"region_name": "us-east-1"},
        {"model_id": "eu.anthropic.claude-sonnet-4-6"},
        {"model_id": "global.anthropic.claude-opus-4-6-v1"},
        {"model_id": "global.amazon.nova-2-lite-v1:0"},
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": 0},
        {"total_max_attempts": 0},
    ],
)
def test_config_rejects_unapproved_or_unbounded_settings(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="Unapproved|must be positive"):
        BedrockGatewayConfig(**kwargs)


def test_gateway_returns_validated_proposal_and_observed_provenance() -> None:
    client = FakeConverseClient()
    clock = iter([10.0, 10.123]).__next__
    pricing = BedrockTokenPricing(
        input_per_million_usd=Decimal("3"),
        output_per_million_usd=Decimal("15"),
    )
    gateway = BedrockClassificationGateway(
        client,
        pricing=pricing,
        clock=clock,
    )

    result = gateway.classify(PAGES)

    assert result.proposal.proposed_class is TaxonomyClass.INVOICE
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["modelId"] == APPROVED_BEDROCK_MODEL_ID
    assert request["inferenceConfig"]["maxTokens"] == 4_096
    assert "outputConfig" not in request
    assert request["toolConfig"]["toolChoice"] == {
        "tool": {"name": "emit_classification"}
    }
    assert result.provenance.region_name == APPROVED_BEDROCK_REGION
    assert result.provenance.model_id == APPROVED_BEDROCK_MODEL_ID
    assert result.provenance.stop_reason == "tool_use"
    assert result.provenance.usage == BedrockUsage(500, 200, 700)
    assert result.provenance.service_latency_ms == 321
    assert result.provenance.observed_duration_ms == 123
    assert result.provenance.request_id == "request-123"
    assert result.provenance.retry_attempts == 2
    assert result.provenance.estimated_cost_usd == Decimal("0.0045")
    assert not hasattr(result, "raw_response")
    assert not hasattr(result.provenance, "prompt")


def test_gateway_omits_cost_when_no_current_pricing_is_supplied() -> None:
    gateway = BedrockClassificationGateway(FakeConverseClient())

    result = gateway.classify(PAGES)

    assert result.provenance.estimated_cost_usd is None


def test_pricing_rejects_negative_values_and_estimates_uncached_usage() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        BedrockTokenPricing(Decimal("-1"), Decimal("2"))

    pricing = BedrockTokenPricing(Decimal("2.5"), Decimal("10"))
    estimate = pricing.estimate_usd(BedrockUsage(1_000, 250, 1_250))

    assert estimate == Decimal("0.005")


@pytest.mark.parametrize(
    ("stop_reason", "expected"),
    [
        ("max_tokens", BedrockGatewayErrorCode.RESPONSE_TRUNCATED),
        (
            "model_context_window_exceeded",
            BedrockGatewayErrorCode.RESPONSE_TRUNCATED,
        ),
        ("guardrail_intervened", BedrockGatewayErrorCode.GUARDRAIL_INTERVENED),
        ("content_filtered", BedrockGatewayErrorCode.CONTENT_FILTERED),
        ("malformed_model_output", BedrockGatewayErrorCode.INVALID_MODEL_OUTPUT),
        ("end_turn", BedrockGatewayErrorCode.UNEXPECTED_STOP_REASON),
    ],
)
def test_gateway_rejects_nonterminal_or_filtered_stop_reasons(
    stop_reason: str,
    expected: BedrockGatewayErrorCode,
) -> None:
    gateway = BedrockClassificationGateway(
        FakeConverseClient(response=_response(stop_reason=stop_reason))
    )

    with pytest.raises(BedrockGatewayError) as captured:
        gateway.classify(PAGES)

    assert captured.value.code is expected


@pytest.mark.parametrize(
    "response",
    [
        {},
        {
            **_response(),
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "{}"}, {"text": "{}"}],
                }
            },
        },
        {
            **_response(),
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"toolUse": {"name": "move_file"}}],
                }
            },
        },
        {**_response(), "usage": {"inputTokens": 1}},
        {**_response(), "metrics": {"latencyMs": -1}},
        {**_response(), "ResponseMetadata": {"RetryAttempts": -1}},
    ],
)
def test_gateway_rejects_malformed_response_shapes(
    response: dict[str, Any],
) -> None:
    gateway = BedrockClassificationGateway(FakeConverseClient(response=response))

    with pytest.raises(BedrockGatewayError) as captured:
        gateway.classify(PAGES)

    assert captured.value.code is BedrockGatewayErrorCode.RESPONSE_INVALID


def test_gateway_rejects_model_output_with_fabricated_evidence() -> None:
    response = _response(text=_proposal_json(segment_id="p0_s999"))
    gateway = BedrockClassificationGateway(FakeConverseClient(response=response))

    with pytest.raises(BedrockGatewayError) as captured:
        gateway.classify(PAGES)

    assert captured.value.code is BedrockGatewayErrorCode.INVALID_MODEL_OUTPUT
    assert (
        captured.value.validation_code is ClassificationValidationCode.EVIDENCE_INVALID
    )
    assert captured.value.service_error_code is None
    assert "Fabricated" not in str(captured.value)


@pytest.mark.parametrize(
    ("aws_code", "expected"),
    [
        ("AccessDeniedException", BedrockGatewayErrorCode.ACCESS_DENIED),
        (
            "ExpiredTokenException",
            BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        ),
        (
            "InvalidSignatureException",
            BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        ),
        (
            "UnrecognizedClientException",
            BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        ),
        ("ThrottlingException", BedrockGatewayErrorCode.THROTTLED),
        ("ModelTimeoutException", BedrockGatewayErrorCode.MODEL_TIMEOUT),
        (
            "ServiceUnavailableException",
            BedrockGatewayErrorCode.SERVICE_UNAVAILABLE,
        ),
        ("InternalServerException", BedrockGatewayErrorCode.SERVICE_UNAVAILABLE),
        ("ValidationException", BedrockGatewayErrorCode.REQUEST_INVALID),
        ("ResourceNotFoundException", BedrockGatewayErrorCode.REQUEST_INVALID),
        ("UnknownException", BedrockGatewayErrorCode.UNEXPECTED_AWS_ERROR),
    ],
)
def test_gateway_maps_aws_errors_without_exposing_messages(
    aws_code: str,
    expected: BedrockGatewayErrorCode,
) -> None:
    error = ClientError(
        {
            "Error": {
                "Code": aws_code,
                "Message": "private document or account detail",
            }
        },
        "Converse",
    )
    gateway = BedrockClassificationGateway(FakeConverseClient(error=error))

    with pytest.raises(BedrockGatewayError) as captured:
        gateway.classify(PAGES)

    assert captured.value.code is expected
    if aws_code == "UnknownException":
        assert captured.value.service_error_code is None
    else:
        assert captured.value.service_error_code == aws_code
    assert captured.value.validation_code is None
    assert "private" not in str(captured.value)
    assert len(captured.value.args) == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            NoCredentialsError(),
            BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        ),
        (
            EndpointConnectionError(endpoint_url="https://example.invalid"),
            BedrockGatewayErrorCode.TRANSPORT_FAILED,
        ),
        (
            ParamValidationError(report="private invalid field"),
            BedrockGatewayErrorCode.REQUEST_INVALID,
        ),
    ],
)
def test_gateway_maps_sdk_errors_without_exposing_details(
    error: Exception,
    expected: BedrockGatewayErrorCode,
) -> None:
    gateway = BedrockClassificationGateway(FakeConverseClient(error=error))

    with pytest.raises(BedrockGatewayError) as captured:
        gateway.classify(PAGES)

    assert captured.value.code is expected
    assert "private" not in str(captured.value)
