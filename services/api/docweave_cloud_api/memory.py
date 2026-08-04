"""CockroachDB memory writer for DocWeave cloud analysis results."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid5

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DOCWEAVE_DATABASE_URL = "DOCWEAVE_DATABASE_URL"
_NAMESPACE = UUID("019f8f17-3864-7893-a01b-204ac412fac0")
_MAX_OBJECTS = 1000
_MAX_JSON_BYTES = 32768
_SHA256_BYTES = 32


class _Connection(Protocol):
    def execute(self, statement: object, parameters: object | None = None) -> object:
        """Execute a parameterized statement."""


class _BeginContext(Protocol):
    def __enter__(self) -> _Connection:
        """Open the transaction."""

    def __exit__(self, *args: object) -> None:
        """Close the transaction."""


class _EngineLike(Protocol):
    def begin(self) -> Any:
        """Return a transaction context."""


class CloudCockroachMemoryWriter:
    """Persist AWS worker analysis observations with bound SQL parameters."""

    def __init__(self, engine: _EngineLike) -> None:
        self._engine = engine

    def persist_classifications(
        self,
        *,
        workspace_id: str,
        job_id: str,
        verified_objects: Sequence[Mapping[str, int | str]],
        classifications: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        workspace_uuid = _parse_uuid("workspace_id", workspace_id)
        safe_job_id = _required_text("job_id", job_id, max_length=64)
        if len(classifications) > _MAX_OBJECTS:
            raise ValueError("classification batch exceeds cloud memory limit")
        if len(verified_objects) != len(classifications):
            raise ValueError("verified object count must match classifications")

        completed_at = datetime.now(UTC)
        cloud_job_id = uuid5(_NAMESPACE, f"{workspace_uuid}:{safe_job_id}")
        object_rows = [
            _object_parameters(
                workspace_id=workspace_uuid,
                cloud_job_id=cloud_job_id,
                job_id=safe_job_id,
                sequence=index,
                classification=classification,
            )
            for index, classification in enumerate(classifications, start=1)
        ]
        job_parameters = {
            "cloud_analysis_job_id": cloud_job_id,
            "workspace_id": workspace_uuid,
            "job_id": safe_job_id,
            "status": "persisted",
            "source_service": "aws_lambda_worker",
            "result_artifact_key": (
                f"workspaces/{workspace_uuid}/analysis-results/{safe_job_id}.json"
            ),
            "completed_at": completed_at,
        }

        with self._engine.begin() as connection:
            connection.execute(_UPSERT_JOB, job_parameters)
            if object_rows:
                connection.execute(_UPSERT_OBJECT, object_rows)

        return {
            "configured": True,
            "persisted_count": len(object_rows),
            "memory_table": "docweave.cloud_analysis_objects",
        }


def build_cloud_memory_writer_from_environment(
    environ: Mapping[str, str] | None = None,
) -> CloudCockroachMemoryWriter | None:
    """Build the writer only when an explicit database URL is already present."""
    values = os.environ if environ is None else environ
    database_url = values.get(DOCWEAVE_DATABASE_URL, "").strip()
    if not database_url:
        return None
    engine: Engine = create_engine(database_url, pool_pre_ping=True, future=True)
    return CloudCockroachMemoryWriter(engine)


def _object_parameters(
    *,
    workspace_id: UUID,
    cloud_job_id: UUID,
    job_id: str,
    sequence: int,
    classification: Mapping[str, object],
) -> dict[str, object]:
    object_key = _required_text(
        "object_key",
        str(classification.get("object_key", "")),
        max_length=1024,
    )
    content_sha256 = _required_hex_digest(
        "content_sha256",
        str(classification.get("content_sha256", "")),
    )
    proposal = _mapping_value("proposal", classification.get("proposal"))
    usage = _mapping_value("usage", classification.get("usage"))
    proposed_class = _required_text(
        "proposed_class",
        str(proposal.get("proposed_class", "")),
        max_length=64,
    )
    confidence_signal = _required_text(
        "confidence_signal",
        str(proposal.get("confidence_signal", "")),
        max_length=32,
    )
    if confidence_signal not in {"weak", "moderate", "strong"}:
        raise ValueError("confidence_signal is invalid")

    return {
        "cloud_analysis_object_id": uuid5(
            _NAMESPACE,
            f"{workspace_id}:{job_id}:{sequence}:{object_key}:{content_sha256.hex()}",
        ),
        "workspace_id": workspace_id,
        "cloud_analysis_job_id": cloud_job_id,
        "object_sequence": sequence,
        "s3_object_key": object_key,
        "content_sha256": content_sha256,
        "byte_size": _non_negative_int("byte_size", classification.get("byte_size")),
        "model_id": _required_text(
            "model_id",
            str(classification.get("model_id", "")),
            max_length=256,
        ),
        "proposed_class": proposed_class,
        "confidence_signal": confidence_signal,
        "proposal_json": _json_object("proposal", proposal),
        "usage_json": _json_object("usage", usage),
    }


def _required_text(name: str, value: str, *, max_length: int) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be empty")
    if len(stripped) > max_length:
        raise ValueError(f"{name} exceeds the persistence limit")
    return stripped


def _parse_uuid(name: str, value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a UUID") from error


def _required_hex_digest(name: str, value: str) -> bytes:
    try:
        digest = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a SHA-256 hex digest") from error
    if len(digest) != _SHA256_BYTES:
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return digest


def _mapping_value(name: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _non_negative_int(name: str, value: object) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _json_object(name: str, value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError(f"{name} exceeds the persistence limit")
    return encoded


_UPSERT_JOB = text(
    """
    INSERT INTO docweave.cloud_analysis_jobs (
        cloud_analysis_job_id, workspace_id, job_id, status, source_service,
        result_artifact_key, completed_at
    ) VALUES (
        :cloud_analysis_job_id, :workspace_id, :job_id, :status, :source_service,
        :result_artifact_key, :completed_at
    )
    ON CONFLICT (workspace_id, job_id) DO UPDATE SET
        status = excluded.status,
        result_artifact_key = excluded.result_artifact_key,
        completed_at = excluded.completed_at
    """
)

_UPSERT_OBJECT = text(
    """
    INSERT INTO docweave.cloud_analysis_objects (
        cloud_analysis_object_id, workspace_id, cloud_analysis_job_id,
        object_sequence, s3_object_key, content_sha256, byte_size, model_id,
        proposed_class, confidence_signal, proposal, usage
    ) VALUES (
        :cloud_analysis_object_id, :workspace_id, :cloud_analysis_job_id,
        :object_sequence, :s3_object_key, :content_sha256, :byte_size, :model_id,
        :proposed_class, :confidence_signal, CAST(:proposal_json AS JSONB),
        CAST(:usage_json AS JSONB)
    )
    ON CONFLICT (workspace_id, cloud_analysis_job_id, object_sequence) DO UPDATE SET
        s3_object_key = excluded.s3_object_key,
        content_sha256 = excluded.content_sha256,
        byte_size = excluded.byte_size,
        model_id = excluded.model_id,
        proposed_class = excluded.proposed_class,
        confidence_signal = excluded.confidence_signal,
        proposal = excluded.proposal,
        usage = excluded.usage,
        persisted_at = now()
    """
)
