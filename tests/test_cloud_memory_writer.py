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
        return self

    def scalar_one(self) -> object:
        return "00000000-0000-4000-8000-000000000001"


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
        "memory_table": "docweave.proposals",
        "persisted_count": 1,
    }
    document_sql, document_parameters = engine.connection.calls[0]
    run_sql, run_parameters = engine.connection.calls[1]
    proposal_sql, proposal_parameters = engine.connection.calls[2]
    assert "INSERT INTO docweave.documents" in document_sql
    assert "ON CONFLICT (workspace_label, content_sha256) DO UPDATE" in document_sql
    assert isinstance(document_parameters, dict)
    assert document_parameters["original_filename"] == "document.pdf"
    assert "INSERT INTO docweave.agent_runs" in run_sql
    assert "CAST(:output_json AS JSONB)" in run_sql
    assert isinstance(run_parameters, dict)
    assert run_parameters["document_id"] == "00000000-0000-4000-8000-000000000001"
    assert "INSERT INTO docweave.proposals" in proposal_sql
    assert isinstance(proposal_parameters, dict)
    assert proposal_parameters["proposed_class"] == "invoice"
    assert proposal_parameters["confidence"] == "0.850000"


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

    with pytest.raises(ValueError, match=r"digest|non-negative|object"):
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


def test_cloud_memory_writer_factory_adds_lambda_ca_bundle_for_verify_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_urls: list[str] = []

    def fake_create_engine(database_url: str, **kwargs: object) -> _FakeEngine:
        created_urls.append(database_url)
        assert kwargs == {"future": True, "pool_pre_ping": True}
        return _FakeEngine()

    monkeypatch.setattr("docweave_cloud_api.memory.create_engine", fake_create_engine)
    monkeypatch.setattr(
        "docweave_cloud_api.memory.certifi.where",
        lambda: "/var/task/certifi/cacert.pem",
    )

    writer = build_cloud_memory_writer_from_environment(
        {
            "DOCWEAVE_DATABASE_URL": (
                "cockroachdb+psycopg://user:secret@example.test/docweave"
                "?sslmode=verify-full"
            )
        }
    )

    assert isinstance(writer, CloudCockroachMemoryWriter)
    assert created_urls == [
        "cockroachdb+psycopg://user:secret@example.test/docweave"
        "?sslmode=verify-full&sslrootcert=%2Fvar%2Ftask%2Fcertifi%2Fcacert.pem"
    ]


def test_cloud_memory_writer_factory_replaces_system_ca_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_urls: list[str] = []

    def fake_create_engine(database_url: str, **kwargs: object) -> _FakeEngine:
        created_urls.append(database_url)
        assert kwargs == {"future": True, "pool_pre_ping": True}
        return _FakeEngine()

    monkeypatch.setattr("docweave_cloud_api.memory.create_engine", fake_create_engine)
    monkeypatch.setattr(
        "docweave_cloud_api.memory.certifi.where",
        lambda: "/var/task/certifi/cacert.pem",
    )

    writer = build_cloud_memory_writer_from_environment(
        {
            "DOCWEAVE_DATABASE_URL": (
                "cockroachdb+psycopg://user:secret@example.test/docweave"
                "?sslmode=verify-full&sslrootcert=system"
            )
        }
    )

    assert isinstance(writer, CloudCockroachMemoryWriter)
    assert created_urls == [
        "cockroachdb+psycopg://user:secret@example.test/docweave"
        "?sslmode=verify-full&sslrootcert=%2Fvar%2Ftask%2Fcertifi%2Fcacert.pem"
    ]
