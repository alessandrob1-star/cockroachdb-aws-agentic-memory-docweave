from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

SERVICES_API = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(SERVICES_API))

from docweave_cloud_api import handler  # noqa: E402

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.head_responses: dict[str, dict[str, Any]] = {}

    def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
        del args
        self.calls.append(kwargs)
        return "https://example.test/presigned"

    def head_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args
        self.calls.append(kwargs)
        key = str(kwargs["Key"])
        if key not in self.head_responses:
            raise RuntimeError("object_not_found")
        return self.head_responses[key]


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, *args: Any, **kwargs: str) -> dict[str, str]:
        del args
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


def _event(
    method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "body": None if body is None else json.dumps(body),
    }


def _body(response: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response["body"]))


def test_health_reports_configured_aws_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setenv("DOCWEAVE_ANALYSIS_QUEUE_URL", "https://sqs.example/queue")
    monkeypatch.setenv("DOCWEAVE_BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
    monkeypatch.setenv("DOCWEAVE_COCKROACHDB_SECRET_ARN", "arn:secret")

    response = handler.api_handler(_event("GET", "/health"), object())

    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["aws_services"] == {
        "amazon_bedrock": "configured",
        "amazon_s3": "configured",
        "amazon_sqs": "configured",
        "aws_lambda": "running",
        "cockroachdb_secret": "configured",
    }


def test_health_accepts_api_gateway_stage_prefixed_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")

    response = handler.api_handler(_event("GET", "/dev/health"), object())

    assert response["statusCode"] == 200
    assert _body(response)["service"] == "docweave-cloud-api"


def test_presign_upload_restricts_pdf_to_workspace_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)

    response = handler.api_handler(
        _event(
            "POST",
            "/uploads/presign",
            {
                "workspace_id": WORKSPACE_ID,
                "filename": "../Invoice 001.pdf",
                "content_type": "application/pdf",
                "byte_size": 1234,
            },
        ),
        object(),
    )

    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["key"].startswith(f"workspaces/{WORKSPACE_ID}/originals/")
    assert payload["key"].endswith("/Invoice 001.pdf")
    assert fake_s3.calls[0]["Params"]["ContentType"] == "application/pdf"
    assert "ServerSideEncryption" not in fake_s3.calls[0]["Params"]


def test_analysis_job_sends_sqs_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sqs = FakeSqsClient()
    key = f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf"
    monkeypatch.setenv("DOCWEAVE_ANALYSIS_QUEUE_URL", "https://sqs.example/queue")
    monkeypatch.setattr(handler, "_sqs_client", lambda: fake_sqs)

    response = handler.api_handler(
        _event(
            "POST",
            "/analysis-jobs",
            {"workspace_id": WORKSPACE_ID, "object_keys": [key]},
        ),
        object(),
    )

    assert response["statusCode"] == 202
    message = json.loads(fake_sqs.messages[0]["MessageBody"])
    assert message["workspace_id"] == WORKSPACE_ID
    assert message["object_keys"] == [key]
    assert message["requested_action"] == "classification"


def test_analysis_job_rejects_cross_workspace_s3_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCWEAVE_ANALYSIS_QUEUE_URL", "https://sqs.example/queue")

    response = handler.api_handler(
        _event(
            "POST",
            "/analysis-jobs",
            {
                "workspace_id": WORKSPACE_ID,
                "object_keys": ["workspaces/other/originals/document.pdf"],
            },
        ),
        object(),
    )

    assert response["statusCode"] == 400
    assert _body(response)["error"] == "object_key_outside_workspace"


def test_worker_verifies_s3_artifacts_before_accepting_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    valid_key = f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf"
    fake_s3.head_responses[valid_key] = {
        "ContentLength": 1234,
        "ContentType": "application/pdf",
    }
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)

    response = handler.worker_handler(
        {
            "Records": [
                {
                    "messageId": "good",
                    "body": json.dumps(
                        {"workspace_id": WORKSPACE_ID, "object_keys": [valid_key]}
                    ),
                },
                {"messageId": "bad", "body": "{}"},
            ]
        },
        object(),
    )

    assert response == {
        "accepted": 1,
        "analysisStatus": "artifact_verified_pending_runtime",
        "batchItemFailures": [{"itemIdentifier": "bad"}],
        "verifiedBytes": 1234,
        "verifiedObjectCount": 1,
    }
    assert fake_s3.calls[0] == {"Bucket": "docweave-bucket", "Key": valid_key}


def test_worker_reports_partial_failure_when_s3_artifact_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    missing_key = f"workspaces/{WORKSPACE_ID}/originals/job/missing.pdf"
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)

    response = handler.worker_handler(
        {
            "Records": [
                {
                    "messageId": "missing",
                    "body": json.dumps(
                        {"workspace_id": WORKSPACE_ID, "object_keys": [missing_key]}
                    ),
                }
            ]
        },
        object(),
    )

    assert response == {
        "accepted": 0,
        "analysisStatus": "artifact_verified_pending_runtime",
        "batchItemFailures": [{"itemIdentifier": "missing"}],
        "verifiedBytes": 0,
        "verifiedObjectCount": 0,
    }
