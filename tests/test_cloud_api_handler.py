from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

SERVICES_API = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(SERVICES_API))

from docweave_cloud_api import handler  # noqa: E402

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"


class FakeBody:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.closed = False

    def read(self) -> bytes:
        return self.value

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.head_responses: dict[str, dict[str, Any]] = {}
        self.object_bodies: dict[str, FakeBody] = {}
        self.put_objects: dict[str, dict[str, Any]] = {}

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

    def get_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args
        self.calls.append(kwargs)
        key = str(kwargs["Key"])
        if key not in self.object_bodies:
            raise RuntimeError("object_body_not_found")
        return {"Body": self.object_bodies[key]}

    def put_object(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        del args
        self.calls.append(kwargs)
        self.put_objects[str(kwargs["Key"])] = kwargs
        return {"ETag": "etag"}


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, *args: Any, **kwargs: str) -> dict[str, str]:
        del args
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


class FakeBedrockRuntimeClient:
    def __init__(self, proposal: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.proposal = proposal or {
            "contract_version": "classification.v1",
            "taxonomy_version": "docweave_mvp_v0_1",
            "proposed_class": "invoice",
            "document_language": "en",
            "rationale": "The PDF contains invoice evidence.",
            "confidence_signal": "strong",
            "candidate_metadata": [{"name": "invoice_number", "value": "INV-001"}],
        }

    def converse(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {
                    "content": [{"text": json.dumps(self.proposal, sort_keys=True)}]
                }
            },
            "usage": {"inputTokens": 101, "outputTokens": 44, "totalTokens": 145},
        }


class FakeCloudMemoryWriter:
    def __init__(self, *, persisted_count: int) -> None:
        self.persisted_count = persisted_count
        self.calls: list[dict[str, Any]] = []

    def persist_classifications(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"persisted_count": self.persisted_count}


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
                "byte_size": len(b"%PDF-1.7\ninvoice"),
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
    assert _body(response)["result_url"].startswith("/analysis-results/")


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
    fake_bedrock = FakeBedrockRuntimeClient()
    valid_key = f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf"
    fake_s3.head_responses[valid_key] = {
        "ContentLength": 1234,
        "ContentType": "application/pdf",
    }
    fake_s3.object_bodies[valid_key] = FakeBody(b"%PDF-1.7\ninvoice")
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setenv("DOCWEAVE_BEDROCK_MODEL_ID", "eu.amazon.nova-2-lite-v1:0")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)
    monkeypatch.setattr(handler, "_bedrock_runtime_client", lambda: fake_bedrock)

    response = handler.worker_handler(
        {
            "Records": [
                {
                    "messageId": "good",
                    "body": json.dumps(
                        {
                            "job_id": "44444444-4444-4444-8444-444444444444",
                            "workspace_id": WORKSPACE_ID,
                            "object_keys": [valid_key],
                        }
                    ),
                },
                {"messageId": "bad", "body": "{}"},
            ]
        },
        object(),
    )

    assert response == {
        "accepted": 1,
        "analysisStatus": "bedrock_classified_pending_persistence",
        "batchItemFailures": [{"itemIdentifier": "bad"}],
        "classifiedObjectCount": 1,
        "classifications": [
            {
                "object_key": valid_key,
                "byte_size": len(b"%PDF-1.7\ninvoice"),
                "content_sha256": sha256(b"%PDF-1.7\ninvoice").hexdigest(),
                "model_id": "eu.amazon.nova-2-lite-v1:0",
                "proposal": {
                    "candidate_metadata": [
                        {"name": "invoice_number", "value": "INV-001"}
                    ],
                    "confidence_signal": "strong",
                    "contract_version": "classification.v1",
                    "document_language": "en",
                    "proposed_class": "invoice",
                    "rationale": "The PDF contains invoice evidence.",
                    "taxonomy_version": "docweave_mvp_v0_1",
                },
                "usage": {
                    "inputTokens": 101,
                    "outputTokens": 44,
                    "totalTokens": 145,
                },
            }
        ],
        "persistedClassificationCount": 0,
        "resultArtifactCount": 1,
        "verifiedBytes": 1234,
        "verifiedObjectCount": 1,
    }
    assert fake_s3.calls[0] == {"Bucket": "docweave-bucket", "Key": valid_key}
    assert fake_s3.object_bodies[valid_key].closed is True
    bedrock_call = fake_bedrock.calls[0]
    assert bedrock_call["modelId"] == "eu.amazon.nova-2-lite-v1:0"
    assert bedrock_call["inferenceConfig"]["maxTokens"] == 900
    assert bedrock_call["inferenceConfig"]["temperature"] == 0
    assert bedrock_call["messages"][0]["content"][1]["document"]["format"] == "pdf"
    result_key = (
        f"workspaces/{WORKSPACE_ID}/analysis-results/"
        "44444444-4444-4444-8444-444444444444.json"
    )
    result_object = fake_s3.put_objects[result_key]
    assert result_object["ContentType"] == "application/json"
    result_payload = json.loads(result_object["Body"].decode("utf-8"))
    assert (
        result_payload["status"] == "bedrock_classified_pending_cockroachdb_persistence"
    )
    assert result_payload["persistence"] == {
        "configured": False,
        "persisted_count": 0,
        "status": "bedrock_classified_pending_cockroachdb_persistence",
    }
    assert result_payload["classifiedObjectCount"] == 1


def test_worker_marks_result_persisted_when_cloud_memory_writer_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    fake_bedrock = FakeBedrockRuntimeClient()
    fake_writer = FakeCloudMemoryWriter(persisted_count=1)
    valid_key = f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf"
    fake_s3.head_responses[valid_key] = {
        "ContentLength": 1234,
        "ContentType": "application/pdf",
    }
    fake_s3.object_bodies[valid_key] = FakeBody(b"%PDF-1.7\ninvoice")
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setenv("DOCWEAVE_BEDROCK_MODEL_ID", "eu.amazon.nova-2-lite-v1:0")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)
    monkeypatch.setattr(handler, "_bedrock_runtime_client", lambda: fake_bedrock)
    monkeypatch.setattr(handler, "_cloud_memory_writer", lambda: fake_writer)

    response = handler.worker_handler(
        {
            "Records": [
                {
                    "messageId": "good",
                    "body": json.dumps(
                        {
                            "job_id": "44444444-4444-4444-8444-444444444444",
                            "workspace_id": WORKSPACE_ID,
                            "object_keys": [valid_key],
                        }
                    ),
                }
            ]
        },
        object(),
    )

    assert response["analysisStatus"] == "bedrock_classified_cockroachdb_persisted"
    assert response["persistedClassificationCount"] == 1
    assert fake_writer.calls[0]["workspace_id"] == WORKSPACE_ID
    assert fake_writer.calls[0]["job_id"] == "44444444-4444-4444-8444-444444444444"
    assert fake_writer.calls[0]["verified_objects"] == [
        {"key": valid_key, "content_length": 1234}
    ]
    assert (
        fake_writer.calls[0]["classifications"][0]["content_sha256"]
        == sha256(b"%PDF-1.7\ninvoice").hexdigest()
    )
    result_key = (
        f"workspaces/{WORKSPACE_ID}/analysis-results/"
        "44444444-4444-4444-8444-444444444444.json"
    )
    result_payload = json.loads(fake_s3.put_objects[result_key]["Body"].decode("utf-8"))
    assert result_payload["status"] == "bedrock_classified_cockroachdb_persisted"
    assert result_payload["persistence"] == {
        "configured": True,
        "persisted_count": 1,
        "status": "bedrock_classified_cockroachdb_persisted",
    }


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
        "analysisStatus": "bedrock_classified_pending_persistence",
        "batchItemFailures": [{"itemIdentifier": "missing"}],
        "classifiedObjectCount": 0,
        "classifications": [],
        "persistedClassificationCount": 0,
        "resultArtifactCount": 0,
        "verifiedBytes": 0,
        "verifiedObjectCount": 0,
    }


def test_worker_rejects_invalid_bedrock_classification_without_acknowledging_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    fake_bedrock = FakeBedrockRuntimeClient(
        proposal={
            "contract_version": "classification.v1",
            "taxonomy_version": "docweave_mvp_v0_1",
            "proposed_class": "wire_transfer_everything",
            "document_language": "en",
            "rationale": "Bad class.",
            "confidence_signal": "strong",
            "candidate_metadata": [],
        }
    )
    key = f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf"
    fake_s3.head_responses[key] = {
        "ContentLength": 1234,
        "ContentType": "application/pdf",
    }
    fake_s3.object_bodies[key] = FakeBody(b"%PDF-1.7\ninvoice")
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setenv("DOCWEAVE_BEDROCK_MODEL_ID", "eu.amazon.nova-2-lite-v1:0")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)
    monkeypatch.setattr(handler, "_bedrock_runtime_client", lambda: fake_bedrock)

    response = handler.worker_handler(
        {
            "Records": [
                {
                    "messageId": "invalid-model-output",
                    "body": json.dumps(
                        {"workspace_id": WORKSPACE_ID, "object_keys": [key]}
                    ),
                }
            ]
        },
        object(),
    )

    assert response == {
        "accepted": 0,
        "analysisStatus": "bedrock_classified_pending_persistence",
        "batchItemFailures": [{"itemIdentifier": "invalid-model-output"}],
        "classifiedObjectCount": 0,
        "classifications": [],
        "persistedClassificationCount": 0,
        "resultArtifactCount": 0,
        "verifiedBytes": 0,
        "verifiedObjectCount": 0,
    }


def test_api_returns_analysis_result_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    job_id = "44444444-4444-4444-8444-444444444444"
    result_key = f"workspaces/{WORKSPACE_ID}/analysis-results/{job_id}.json"
    fake_s3.object_bodies[result_key] = FakeBody(
        json.dumps(
            {
                "contract_version": "cloud_analysis_result.v1",
                "job_id": job_id,
                "workspace_id": WORKSPACE_ID,
                "status": "bedrock_classified_pending_cockroachdb_persistence",
            }
        ).encode("utf-8")
    )
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)

    response = handler.api_handler(
        {
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": f"/dev/analysis-results/{job_id}",
            "queryStringParameters": {"workspace_id": WORKSPACE_ID},
            "body": None,
        },
        object(),
    )

    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["contract_version"] == "cloud_analysis_result.v1"
    assert payload["job_id"] == job_id


def test_api_reports_missing_analysis_result_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    job_id = "44444444-4444-4444-8444-444444444444"
    monkeypatch.setenv("DOCWEAVE_DOCUMENT_BUCKET", "docweave-bucket")
    monkeypatch.setattr(handler, "_s3_client", lambda: fake_s3)

    response = handler.api_handler(
        {
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": f"/analysis-results/{job_id}",
            "queryStringParameters": {"workspace_id": WORKSPACE_ID},
            "body": None,
        },
        object(),
    )

    assert response["statusCode"] == 404
    assert _body(response)["error"] == "analysis_result_not_found"
