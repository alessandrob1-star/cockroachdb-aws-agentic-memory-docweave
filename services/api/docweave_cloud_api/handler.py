"""AWS Lambda handlers for the DocWeave cloud service foundation."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

try:  # pragma: no cover - exercised in Lambda, replaced by fakes in tests.
    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - keeps local static checks import-safe.
    boto3 = None
    Config = None


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_PRESIGN_SECONDS = 900
MAX_FILENAME_LENGTH = 255
MAX_BATCH_ITEMS = 1000
PDF_CONTENT_TYPE = "application/pdf"
KNOWN_ROUTES = ("/health", "/uploads/presign", "/analysis-jobs")

_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._ -]+")


class S3Client(Protocol):
    """Narrow S3 client surface used by the API handler."""

    def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
        """Return a pre-signed S3 URL."""


class SqsClient(Protocol):
    """Narrow SQS client surface used by the API handler."""

    def send_message(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        """Send one job message to SQS."""


@dataclass(frozen=True)
class CloudConfig:
    """Runtime configuration sourced from Lambda environment variables."""

    document_bucket: str
    analysis_queue_url: str
    bedrock_model_id: str
    cockroachdb_secret_arn: str
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    presign_seconds: int = DEFAULT_PRESIGN_SECONDS

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> CloudConfig:
        values = os.environ if environ is None else environ
        return cls(
            document_bucket=values.get("DOCWEAVE_DOCUMENT_BUCKET", "").strip(),
            analysis_queue_url=values.get("DOCWEAVE_ANALYSIS_QUEUE_URL", "").strip(),
            bedrock_model_id=values.get("DOCWEAVE_BEDROCK_MODEL_ID", "").strip(),
            cockroachdb_secret_arn=values.get(
                "DOCWEAVE_COCKROACHDB_SECRET_ARN", ""
            ).strip(),
            max_upload_bytes=_positive_int(
                values.get("DOCWEAVE_MAX_UPLOAD_BYTES"),
                DEFAULT_MAX_UPLOAD_BYTES,
            ),
            presign_seconds=_positive_int(
                values.get("DOCWEAVE_PRESIGN_SECONDS"),
                DEFAULT_PRESIGN_SECONDS,
            ),
        )


def api_handler(event: Mapping[str, Any], context: object) -> dict[str, Any]:
    """Handle API Gateway HTTP API events."""

    del context
    config = CloudConfig.from_environment()
    method = _event_method(event)
    path = _event_path(event)

    try:
        if method == "GET" and path == "/health":
            return _json_response(200, _health_payload(config))
        if method == "POST" and path == "/uploads/presign":
            return _handle_presign_upload(config, _json_body(event))
        if method == "POST" and path == "/analysis-jobs":
            return _handle_analysis_job(config, _json_body(event))
    except ValueError as error:
        return _json_response(400, {"error": str(error)})
    return _json_response(404, {"error": "route_not_found"})


def worker_handler(event: Mapping[str, Any], context: object) -> dict[str, Any]:
    """Accept queued analysis jobs without inventing analysis results."""

    del context
    accepted = 0
    failed_items: list[dict[str, str]] = []
    for record in cast(Sequence[Mapping[str, Any]], event.get("Records", [])):
        message_id = str(record.get("messageId", "unknown"))
        try:
            body = json.loads(str(record.get("body", "{}")))
            if not isinstance(body, dict):
                raise ValueError("json_object_required")
            _validate_analysis_job_payload(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            failed_items.append({"itemIdentifier": message_id})
            continue
        accepted += 1
    return {
        "accepted": accepted,
        "batchItemFailures": failed_items,
        "analysisStatus": "queued_for_real_runtime",
    }


def _handle_presign_upload(
    config: CloudConfig, body: Mapping[str, Any]
) -> dict[str, Any]:
    if not config.document_bucket:
        return _json_response(503, {"error": "document_bucket_not_configured"})

    workspace_id = _required_uuid_text(body, "workspace_id")
    filename = _safe_pdf_filename(str(body.get("filename", "")))
    content_type = str(body.get("content_type", PDF_CONTENT_TYPE)).strip().lower()
    byte_size = _bounded_size(body.get("byte_size"), config.max_upload_bytes)
    if content_type != PDF_CONTENT_TYPE:
        raise ValueError("content_type_must_be_application_pdf")

    object_key = f"workspaces/{workspace_id}/originals/{uuid.uuid4()}/{filename}"
    url = _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": config.document_bucket,
            "Key": object_key,
            "ContentType": PDF_CONTENT_TYPE,
        },
        ExpiresIn=config.presign_seconds,
    )
    return _json_response(
        200,
        {
            "bucket": config.document_bucket,
            "key": object_key,
            "content_type": PDF_CONTENT_TYPE,
            "max_bytes": config.max_upload_bytes,
            "declared_bytes": byte_size,
            "expires_in_seconds": config.presign_seconds,
            "upload_url": url,
        },
    )


def _handle_analysis_job(
    config: CloudConfig, body: Mapping[str, Any]
) -> dict[str, Any]:
    if not config.analysis_queue_url:
        return _json_response(503, {"error": "analysis_queue_not_configured"})
    payload = _validate_analysis_job_payload(body)
    job_id = str(uuid.uuid4())
    message = {
        "job_id": job_id,
        "workspace_id": payload["workspace_id"],
        "object_keys": payload["object_keys"],
        "requested_action": "classification",
    }
    _sqs_client().send_message(
        QueueUrl=config.analysis_queue_url,
        MessageBody=json.dumps(message, sort_keys=True, separators=(",", ":")),
    )
    return _json_response(
        202,
        {
            "job_id": job_id,
            "status": "queued",
            "item_count": len(payload["object_keys"]),
        },
    )


def _validate_analysis_job_payload(body: Mapping[str, Any]) -> dict[str, Any]:
    workspace_id = _required_uuid_text(body, "workspace_id")
    raw_keys = body.get("object_keys")
    if not isinstance(raw_keys, list):
        raise ValueError("object_keys_required")
    if not 1 <= len(raw_keys) <= MAX_BATCH_ITEMS:
        raise ValueError("object_keys_count_out_of_range")

    allowed_prefix = f"workspaces/{workspace_id}/"
    object_keys: list[str] = []
    for raw_key in raw_keys:
        key = str(raw_key)
        if not key.startswith(allowed_prefix):
            raise ValueError("object_key_outside_workspace")
        if not key.casefold().endswith(".pdf"):
            raise ValueError("object_key_must_be_pdf")
        if "\x00" in key or ".." in key.split("/"):
            raise ValueError("object_key_invalid")
        object_keys.append(key)
    return {"workspace_id": workspace_id, "object_keys": object_keys}


def _health_payload(config: CloudConfig) -> dict[str, Any]:
    return {
        "service": "docweave-cloud-api",
        "status": "ready",
        "aws_services": {
            "amazon_s3": "configured" if config.document_bucket else "missing",
            "amazon_sqs": "configured" if config.analysis_queue_url else "missing",
            "aws_lambda": "running",
            "amazon_bedrock": "configured" if config.bedrock_model_id else "missing",
            "cockroachdb_secret": (
                "configured" if config.cockroachdb_secret_arn else "missing"
            ),
        },
        "capabilities": [
            "health",
            "presigned_pdf_upload",
            "queued_analysis_request",
        ],
    }


def _event_method(event: Mapping[str, Any]) -> str:
    request_context = cast(Mapping[str, Any], event.get("requestContext", {}))
    http = cast(Mapping[str, Any], request_context.get("http", {}))
    return str(http.get("method", event.get("httpMethod", ""))).upper()


def _event_path(event: Mapping[str, Any]) -> str:
    path = str(event.get("rawPath", event.get("path", "/"))).rstrip("/") or "/"
    for route in KNOWN_ROUTES:
        if path == route or path.endswith(route):
            return route
    return path


def _json_body(event: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_body = event.get("body")
    if raw_body in (None, ""):
        return {}
    parsed = json.loads(str(raw_body))
    if not isinstance(parsed, dict):
        raise ValueError("json_object_required")
    return cast(Mapping[str, Any], parsed)


def _json_response(status_code: int, body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, sort_keys=True, separators=(",", ":")),
    }


def _required_uuid_text(body: Mapping[str, Any], field_name: str) -> str:
    raw_value = str(body.get(field_name, "")).strip()
    try:
        return str(uuid.UUID(raw_value))
    except ValueError as error:
        raise ValueError(f"{field_name}_must_be_uuid") from error


def _safe_pdf_filename(raw_filename: str) -> str:
    candidate = raw_filename.replace("\\", "/").split("/")[-1].strip()
    candidate = _SAFE_FILENAME_PATTERN.sub("_", candidate)
    candidate = candidate.strip(" .")
    if not candidate.casefold().endswith(".pdf"):
        raise ValueError("filename_must_end_with_pdf")
    if not candidate or len(candidate) > MAX_FILENAME_LENGTH:
        raise ValueError("filename_invalid")
    return candidate


def _bounded_size(raw_size: object, max_upload_bytes: int) -> int:
    if isinstance(raw_size, int):
        size = raw_size
    elif isinstance(raw_size, str):
        try:
            size = int(raw_size)
        except ValueError as error:
            raise ValueError("byte_size_required") from error
    else:
        raise ValueError("byte_size_required")
    if not 1 <= size <= max_upload_bytes:
        raise ValueError("byte_size_out_of_range")
    return size


def _positive_int(raw_value: str | None, default: int) -> int:
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def _s3_client() -> S3Client:
    if boto3 is None or Config is None:
        raise RuntimeError("boto3_unavailable")
    region_name = os.environ.get("AWS_REGION", "").strip()
    if region_name:
        return cast(
            S3Client,
            boto3.client(
                "s3",
                region_name=region_name,
                endpoint_url=f"https://s3.{region_name}.amazonaws.com",
                config=Config(signature_version="s3v4"),
            ),
        )
    return cast(S3Client, boto3.client("s3", config=Config(signature_version="s3v4")))


def _sqs_client() -> SqsClient:
    if boto3 is None:
        raise RuntimeError("boto3_unavailable")
    return cast(SqsClient, boto3.client("sqs"))
