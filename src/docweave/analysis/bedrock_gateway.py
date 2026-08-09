"""Amazon Bedrock Runtime gateway for evidence-backed classification."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from time import monotonic
from typing import Any, Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    CredentialRetrievalError,
    EndpointConnectionError,
    LoginTokenLoadError,
    NoAuthTokenError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
    ReadTimeoutError,
    SSOError,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)

from docweave.analysis.contracts import (
    CLASSIFICATION_CONTRACT_VERSION,
    ClassificationProposal,
)
from docweave.analysis.request import classification_v1_converse_fields
from docweave.analysis.schema import CLASSIFICATION_TOOL_NAME
from docweave.analysis.taxonomy import TAXONOMY_VERSION
from docweave.analysis.validation import (
    ClassificationValidationCode,
    ClassificationValidationError,
    decode_classification_v1,
)
from docweave.extraction import ExtractedPage

APPROVED_BEDROCK_REGION = "eu-central-1"
APPROVED_BEDROCK_MODEL_ID = "eu.amazon.nova-2-lite-v1:0"
BEDROCK_CONNECT_TIMEOUT_SECONDS = 5
BEDROCK_READ_TIMEOUT_SECONDS = 90
BEDROCK_TOTAL_MAX_ATTEMPTS = 5
_MAXIMUM_REQUEST_ID_CHARACTERS = 128
_MAXIMUM_VALIDATION_RETRY_ATTEMPTS = 2
_VALIDATION_RETRY_CODES = {
    ClassificationValidationCode.ABSTENTION_INVALID,
    ClassificationValidationCode.ALTERNATIVE_INVALID,
    ClassificationValidationCode.EVIDENCE_REFERENCE_INVALID,
    ClassificationValidationCode.METADATA_INVALID,
    ClassificationValidationCode.SCHEMA_INVALID,
}


class ConverseClient(Protocol):
    """Narrow Bedrock client surface required by the gateway."""

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        """Invoke the Bedrock Runtime Converse operation."""


class SessionLike(Protocol):
    """Narrow boto3 session surface used for side-effect-free construction."""

    def client(self, service_name: str, **kwargs: Any) -> ConverseClient:
        """Create one service client."""


@dataclass(frozen=True, slots=True)
class BedrockGatewayConfig:
    """Approved immutable runtime settings for the primary classifier."""

    region_name: str = APPROVED_BEDROCK_REGION
    model_id: str = APPROVED_BEDROCK_MODEL_ID
    connect_timeout_seconds: int = BEDROCK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: int = BEDROCK_READ_TIMEOUT_SECONDS
    total_max_attempts: int = BEDROCK_TOTAL_MAX_ATTEMPTS

    def __post_init__(self) -> None:
        if self.region_name != APPROVED_BEDROCK_REGION:
            raise ValueError("Unapproved Bedrock region.")
        if self.model_id != APPROVED_BEDROCK_MODEL_ID:
            raise ValueError("Unapproved Bedrock model.")
        if (
            self.connect_timeout_seconds <= 0
            or self.read_timeout_seconds <= 0
            or self.total_max_attempts <= 0
        ):
            raise ValueError("Bedrock runtime limits must be positive.")


@dataclass(frozen=True, slots=True)
class BedrockUsage:
    """Token counts observed in the actual Converse response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_input_tokens: int = 0
    cache_write_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class BedrockTokenPricing:
    """Externally supplied on-demand prices in US dollars per million tokens."""

    input_per_million_usd: Decimal
    output_per_million_usd: Decimal

    def __post_init__(self) -> None:
        if self.input_per_million_usd < 0 or self.output_per_million_usd < 0:
            raise ValueError("Bedrock token prices cannot be negative.")

    def estimate_usd(self, usage: BedrockUsage) -> Decimal:
        """Estimate uncached token cost without claiming billing authority."""
        million = Decimal(1_000_000)
        return (
            Decimal(usage.input_tokens) * self.input_per_million_usd
            + Decimal(usage.output_tokens) * self.output_per_million_usd
        ) / million


@dataclass(frozen=True, slots=True)
class BedrockRunProvenance:
    """Observed runtime provenance, never copied from model-authored JSON."""

    region_name: str
    model_id: str
    contract_version: str
    taxonomy_version: str
    stop_reason: str
    usage: BedrockUsage
    service_latency_ms: int
    observed_duration_ms: int
    request_id: str | None
    retry_attempts: int
    estimated_cost_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class BedrockClassificationRun:
    """One validated proposal and its observed Bedrock provenance."""

    proposal: ClassificationProposal
    provenance: BedrockRunProvenance


class BedrockGatewayErrorCode(StrEnum):
    """Content-free terminal category for a failed gateway attempt."""

    ACCESS_DENIED = "access_denied"
    AUTHENTICATION_FAILED = "authentication_failed"
    CONTENT_FILTERED = "content_filtered"
    GUARDRAIL_INTERVENED = "guardrail_intervened"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    MODEL_TIMEOUT = "model_timeout"
    REQUEST_INVALID = "request_invalid"
    RESPONSE_INVALID = "response_invalid"
    RESPONSE_TRUNCATED = "response_truncated"
    SERVICE_UNAVAILABLE = "service_unavailable"
    THROTTLED = "throttled"
    TRANSPORT_FAILED = "transport_failed"
    UNEXPECTED_AWS_ERROR = "unexpected_aws_error"
    UNEXPECTED_STOP_REASON = "unexpected_stop_reason"


class BedrockGatewayError(RuntimeError):
    """Sanitized gateway failure that retains no document or AWS message."""

    def __init__(
        self,
        code: BedrockGatewayErrorCode,
        *,
        validation_code: ClassificationValidationCode | None = None,
        service_error_code: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.validation_code = validation_code
        self.service_error_code = service_error_code


def create_bedrock_runtime_client(
    *,
    config: BedrockGatewayConfig | None = None,
    session: SessionLike | None = None,
) -> ConverseClient:
    """Create the approved Bedrock Runtime client without making an API call."""
    active_config = config or BedrockGatewayConfig()
    active_session = session
    if active_session is None:
        active_session = cast(SessionLike, boto3.Session())
    client_config = Config(
        retries={
            "total_max_attempts": active_config.total_max_attempts,
            "mode": "adaptive",
        },
        connect_timeout=active_config.connect_timeout_seconds,
        read_timeout=active_config.read_timeout_seconds,
        max_pool_connections=10,
        user_agent_appid="docweave",
    )
    return active_session.client(
        "bedrock-runtime",
        region_name=active_config.region_name,
        config=client_config,
    )


class BedrockClassificationGateway:
    """Invoke Converse and validate one classification proposal."""

    def __init__(
        self,
        client: ConverseClient,
        *,
        config: BedrockGatewayConfig | None = None,
        pricing: BedrockTokenPricing | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._client = client
        self._config = config or BedrockGatewayConfig()
        self._pricing = pricing
        self._clock = clock

    def classify(
        self,
        pages: tuple[ExtractedPage, ...],
    ) -> BedrockClassificationRun:
        """Perform one bounded real model call through the injected client."""
        request = classification_v1_converse_fields(pages)
        responses: list[dict[str, Any]] = []
        validation_retry_attempts = 0
        started_at = self._clock()
        while True:
            response = self._converse(request)
            responses.append(response)

            stop_reason = _required_string(response, "stopReason")
            _validate_stop_reason(stop_reason)
            response_text = _response_text(response)
            try:
                proposal = decode_classification_v1(
                    response_text,
                    extracted_pages=pages,
                )
                break
            except ClassificationValidationError as error:
                if (
                    validation_retry_attempts < _MAXIMUM_VALIDATION_RETRY_ATTEMPTS
                    and error.code in _VALIDATION_RETRY_CODES
                ):
                    validation_retry_attempts += 1
                    request = _with_validation_retry_instruction(
                        request,
                        validation_code=error.code,
                    )
                    continue
                raise BedrockGatewayError(
                    BedrockGatewayErrorCode.INVALID_MODEL_OUTPUT,
                    validation_code=error.code,
                ) from error
        observed_duration_ms = max(
            0,
            round((self._clock() - started_at) * 1_000),
        )

        usage = _aggregate_usage(_decode_usage(item.get("usage")) for item in responses)
        service_latency_ms = sum(
            _service_latency(item.get("metrics")) for item in responses
        )
        request_id, retry_attempts = _response_metadata(
            response.get("ResponseMetadata")
        )
        retry_attempts += validation_retry_attempts + sum(
            _response_metadata(item.get("ResponseMetadata"))[1]
            for item in responses[:-1]
        )
        estimated_cost = (
            self._pricing.estimate_usd(usage) if self._pricing is not None else None
        )
        return BedrockClassificationRun(
            proposal=proposal,
            provenance=BedrockRunProvenance(
                region_name=self._config.region_name,
                model_id=self._config.model_id,
                contract_version=CLASSIFICATION_CONTRACT_VERSION,
                taxonomy_version=TAXONOMY_VERSION,
                stop_reason=stop_reason,
                usage=usage,
                service_latency_ms=service_latency_ms,
                observed_duration_ms=observed_duration_ms,
                request_id=request_id,
                retry_attempts=retry_attempts,
                estimated_cost_usd=estimated_cost,
            ),
        )

    def _converse(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._client.converse(
                modelId=self._config.model_id,
                **request,
            )
        except (
            ConnectTimeoutError,
            EndpointConnectionError,
            ReadTimeoutError,
        ) as error:
            raise BedrockGatewayError(
                BedrockGatewayErrorCode.TRANSPORT_FAILED
            ) from error
        except (
            CredentialRetrievalError,
            LoginTokenLoadError,
            NoAuthTokenError,
            NoCredentialsError,
            PartialCredentialsError,
            SSOError,
            SSOTokenLoadError,
            TokenRetrievalError,
            UnauthorizedSSOTokenError,
        ) as error:
            raise BedrockGatewayError(
                BedrockGatewayErrorCode.AUTHENTICATION_FAILED
            ) from error
        except ParamValidationError as error:
            raise BedrockGatewayError(
                BedrockGatewayErrorCode.REQUEST_INVALID
            ) from error
        except ClientError as error:
            raise _mapped_client_error(error) from error
        except BotoCoreError as error:
            raise BedrockGatewayError(
                BedrockGatewayErrorCode.TRANSPORT_FAILED
            ) from error


def _with_validation_retry_instruction(
    request: dict[str, Any],
    *,
    validation_code: ClassificationValidationCode,
) -> dict[str, Any]:
    retry_request = dict(request)
    retry_request["system"] = [
        *request["system"],
        {
            "text": (
                "The previous emit_classification tool input failed DocWeave "
                f"validation with code {validation_code.value}. Re-read the "
                "same untrusted document data and approved taxonomy, then emit "
                "a fresh classification.v1 tool input. Do not reuse invalid "
                "evidence references. Every evidence_id used in rationale, "
                "metadata, alternatives, or contradictions must exist in the "
                "evidence array you emit. Use a compact evidence array and "
                "prefer only ev_1 through ev_8 for rationale_evidence_ids. If "
                "proposed_class is not unclassified, abstention_reason must be "
                "null."
            )
        },
    ]
    return retry_request


def _aggregate_usage(usages: Any) -> BedrockUsage:
    items = tuple(usages)
    if not items:
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return BedrockUsage(
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
        cache_read_input_tokens=sum(item.cache_read_input_tokens for item in items),
        cache_write_input_tokens=sum(item.cache_write_input_tokens for item in items),
    )


def _validate_stop_reason(stop_reason: str) -> None:
    error_codes = {
        "max_tokens": BedrockGatewayErrorCode.RESPONSE_TRUNCATED,
        "guardrail_intervened": BedrockGatewayErrorCode.GUARDRAIL_INTERVENED,
        "content_filtered": BedrockGatewayErrorCode.CONTENT_FILTERED,
        "model_context_window_exceeded": BedrockGatewayErrorCode.RESPONSE_TRUNCATED,
        "malformed_model_output": BedrockGatewayErrorCode.INVALID_MODEL_OUTPUT,
    }
    if stop_reason == "tool_use":
        return
    raise BedrockGatewayError(
        error_codes.get(
            stop_reason,
            BedrockGatewayErrorCode.UNEXPECTED_STOP_REASON,
        )
    )


def _response_text(response: dict[str, Any]) -> str:
    try:
        output = response["output"]
        if not isinstance(output, dict):
            raise TypeError
        message = output["message"]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise TypeError
        content = message["content"]
        if not isinstance(content, list) or len(content) != 1:
            raise TypeError
        block = content[0]
        if not isinstance(block, dict) or set(block) != {"toolUse"}:
            raise TypeError
        tool_use = block["toolUse"]
        if not isinstance(tool_use, dict) or set(tool_use) != {
            "toolUseId",
            "name",
            "input",
        }:
            raise TypeError
        tool_use_id = tool_use["toolUseId"]
        name = tool_use["name"]
        tool_input = tool_use["input"]
        if (
            not isinstance(tool_use_id, str)
            or not tool_use_id
            or name != CLASSIFICATION_TOOL_NAME
            or not isinstance(tool_input, dict)
        ):
            raise TypeError
        return json.dumps(
            tool_input,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (KeyError, TypeError) as error:
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID) from error


def _decode_usage(value: Any) -> BedrockUsage:
    if not isinstance(value, dict):
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    usage = BedrockUsage(
        input_tokens=_nonnegative_int(value, "inputTokens"),
        output_tokens=_nonnegative_int(value, "outputTokens"),
        total_tokens=_nonnegative_int(value, "totalTokens"),
        cache_read_input_tokens=_optional_nonnegative_int(
            value,
            "cacheReadInputTokens",
        ),
        cache_write_input_tokens=_optional_nonnegative_int(
            value,
            "cacheWriteInputTokens",
        ),
    )
    if usage.total_tokens < usage.input_tokens + usage.output_tokens:
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return usage


def _service_latency(value: Any) -> int:
    if not isinstance(value, dict):
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return _nonnegative_int(value, "latencyMs")


def _response_metadata(value: Any) -> tuple[str | None, int]:
    if not isinstance(value, dict):
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    request_id = value.get("RequestId")
    if request_id is not None and (
        not isinstance(request_id, str)
        or len(request_id) > _MAXIMUM_REQUEST_ID_CHARACTERS
    ):
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    retry_attempts = _optional_nonnegative_int(value, "RetryAttempts")
    return request_id, retry_attempts


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return item


def _nonnegative_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 0:
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return item


def _optional_nonnegative_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key, 0)
    if type(item) is not int or item < 0:
        raise BedrockGatewayError(BedrockGatewayErrorCode.RESPONSE_INVALID)
    return item


def _mapped_client_error(error: ClientError) -> BedrockGatewayError:
    error_details = error.response.get("Error", {})
    error_code = error_details.get("Code") if isinstance(error_details, dict) else None
    mapped = {
        "AccessDeniedException": BedrockGatewayErrorCode.ACCESS_DENIED,
        "ExpiredTokenException": BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        "IncompleteSignature": BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        "InvalidClientTokenId": BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        "InvalidSignatureException": BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        "UnrecognizedClientException": BedrockGatewayErrorCode.AUTHENTICATION_FAILED,
        "ThrottlingException": BedrockGatewayErrorCode.THROTTLED,
        "ModelTimeoutException": BedrockGatewayErrorCode.MODEL_TIMEOUT,
        "ServiceUnavailableException": BedrockGatewayErrorCode.SERVICE_UNAVAILABLE,
        "InternalServerException": BedrockGatewayErrorCode.SERVICE_UNAVAILABLE,
        "ValidationException": BedrockGatewayErrorCode.REQUEST_INVALID,
        "ResourceNotFoundException": BedrockGatewayErrorCode.REQUEST_INVALID,
    }
    if not isinstance(error_code, str):
        return BedrockGatewayError(BedrockGatewayErrorCode.UNEXPECTED_AWS_ERROR)
    mapped_code = mapped.get(error_code)
    if mapped_code is None:
        return BedrockGatewayError(BedrockGatewayErrorCode.UNEXPECTED_AWS_ERROR)
    return BedrockGatewayError(
        mapped_code,
        service_error_code=error_code,
    )
