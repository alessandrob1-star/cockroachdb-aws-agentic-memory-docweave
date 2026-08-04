from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

import pytest

SERVICES_API = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(SERVICES_API))

from docweave_cloud_api.memory import (  # noqa: E402
    CloudCockroachMemoryWriter,
    build_cloud_memory_writer_from_environment,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
JOB_ID = "44444444-4444-4444-8444-444444444444"


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement: object, parameters: object | None = None) -> object:
        self.calls.append((str(statement), parameters))
        return object()


class _FakeBegin:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, *args: object) -> None:
        return None


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self.connection)


def _classification() -> dict[str, object]:
    pdf_bytes = b"%PDF-1.7\ninvoice"
    return {
        "object_key": f"workspaces/{WORKSPACE_ID}/originals/job/document.pdf",
        "byte_size": len(pdf_bytes),
        "content_sha256": sha256(pdf_bytes).hexdigest(),
        "model_id": "eu.amazon.nova-2-lite-v1:0",
        "proposal": {
            "contract_version": "classification.v1",
            "taxonomy_version": "docweave_mvp_v0_1",
            "proposed_class": "invoice",
            "document_language": "en",
            "rationale": "The PDF contains invoice evidence.",
            "confidence_signal": "strong",
            "candidate_metadata": [{"name": "invoice_number", "value": "INV-001"}],
        },
        "usage": {"inputTokens": 101, "outputTokens": 44, "totalTokens": 145},
    }


def test_cloud_memory_writer_persists_job_and_objects_with_bound_parameters() -> None:
    engine = _FakeEngine()
    writer = CloudCockroachMemoryWriter(engine)

    result = writer.persist_classifications(
        workspace_id=WORKSPACE_ID,
        job_id=JOB_ID,
        verified_objects=[{"key": "ignored", "content_length": 16}],
        classifications=[_classification()],
    )

    assert result == {
        "configured": True,
        "memory_table": "docweave.cloud_analysis_objects",
        "persisted_count": 1,
    }
    job_sql, job_parameters = engine.connection.calls[0]
    object_sql, object_parameters = engine.connection.calls[1]
    assert "INSERT INTO docweave.cloud_analysis_jobs" in job_sql
    assert "ON CONFLICT (workspace_id, job_id) DO UPDATE" in job_sql
    assert isinstance(job_parameters, dict)
    assert job_parameters["job_id"] == JOB_ID
    assert "INSERT INTO docweave.cloud_analysis_objects" in object_sql
    assert "CAST(:proposal_json AS JSONB)" in object_sql
    assert isinstance(object_parameters, list)
    assert object_parameters[0]["proposed_class"] == "invoice"
    assert object_parameters[0]["confidence_signal"] == "strong"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_sha256", "not-a-digest"),
        ("byte_size", -1),
        ("proposal", "not-an-object"),
    ],
)
def test_cloud_memory_writer_rejects_invalid_untrusted_values(
    field: str,
    value: object,
) -> None:
    classification = _classification()
    classification[field] = value
    writer = CloudCockroachMemoryWriter(_FakeEngine())

    with pytest.raises(ValueError, match="digest|non-negative|object"):
        writer.persist_classifications(
            workspace_id=WORKSPACE_ID,
            job_id=JOB_ID,
            verified_objects=[{"key": "ignored", "content_length": 16}],
            classifications=[classification],
        )


def test_cloud_memory_writer_requires_verified_count_to_match_classifications() -> None:
    writer = CloudCockroachMemoryWriter(_FakeEngine())

    with pytest.raises(ValueError, match="verified object count"):
        writer.persist_classifications(
            workspace_id=WORKSPACE_ID,
            job_id=JOB_ID,
            verified_objects=[],
            classifications=[_classification()],
        )


def test_cloud_memory_writer_is_not_configured_without_database_url() -> None:
    assert build_cloud_memory_writer_from_environment({}) is None


def test_cloud_memory_writer_factory_uses_existing_environment_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_urls: list[str] = []

    def fake_create_engine(database_url: str, **kwargs: object) -> _FakeEngine:
        created_urls.append(database_url)
        assert kwargs == {"future": True, "pool_pre_ping": True}
        return _FakeEngine()

    monkeypatch.setattr("docweave_cloud_api.memory.create_engine", fake_create_engine)

    writer = build_cloud_memory_writer_from_environment(
        {"DOCWEAVE_DATABASE_URL": "cockroachdb+psycopg://example"}
    )

    assert isinstance(writer, CloudCockroachMemoryWriter)
    assert created_urls == ["cockroachdb+psycopg://example"]
