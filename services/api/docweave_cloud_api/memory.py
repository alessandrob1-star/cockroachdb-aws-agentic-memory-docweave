"""CockroachDB writer for DocWeave cloud analysis results."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
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
    """Persist AWS worker analysis observations into the simple memory schema."""

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
        object_rows = [
            _object_parameters(
                workspace_id=workspace_uuid,
                job_id=safe_job_id,
                sequence=index,
                classification=classification,
            )
            for index, classification in enumerate(classifications, start=1)
        ]
        with self._engine.begin() as connection:
            for row in object_rows:
                parameters = {**row, "completed_at": completed_at}
                stored_document_id = connection.execute(
                    _UPSERT_DOCUMENT,
                    parameters,
                ).scalar_one()
                parameters["document_id"] = stored_document_id
                connection.execute(_UPSERT_RUN, parameters)
                connection.execute(_UPSERT_PROPOSAL, parameters)

        return {
            "configured": True,
            "persisted_count": len(object_rows),
            "memory_table": "docweave.proposals",
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
    _non_negative_int("byte_size", classification.get("byte_size"))
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
    original_directory, original_filename = _split_s3_original_path(object_key)
    proposal_json = _json_object("proposal", proposal)
    usage_json = _json_object("usage", usage)
    document_id = uuid5(
        _NAMESPACE,
        f"{workspace_id}:document:{content_sha256.hex()}",
    )

    return {
        "document_id": document_id,
        "agent_run_id": uuid5(
            _NAMESPACE,
            f"{workspace_id}:{job_id}:{sequence}:agent-run:{content_sha256.hex()}",
        ),
        "proposal_id": uuid5(
            _NAMESPACE,
            f"{workspace_id}:{job_id}:{sequence}:proposal:{content_sha256.hex()}",
        ),
        "workspace_label": str(workspace_id),
        "original_directory": original_directory,
        "original_filename": original_filename,
        "content_sha256": content_sha256,
        "page_count": 1,
        "model_id": _required_text(
            "model_id",
            str(classification.get("model_id", "")),
            max_length=256,
        ),
        "output_json": proposal_json,
        "summary": _required_text(
            "rationale",
            str(proposal.get("rationale", "")),
            max_length=1000,
        ),
        "proposed_class": proposed_class,
        "proposed_directory": _proposed_directory(proposed_class),
        "proposed_filename": _proposed_filename(
            proposed_class=proposed_class,
            original_filename=original_filename,
            proposal=proposal,
        ),
        "confidence": _confidence_value(confidence_signal),
        "evidence_summary": _required_text(
            "rationale",
            str(proposal.get("rationale", "")),
            max_length=1000,
        ),
        "input_sha256": content_sha256,
        "usage_json": usage_json,
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


def _split_s3_original_path(object_key: str) -> tuple[str, str]:
    path = PurePosixPath(object_key)
    filename = path.name
    if not filename:
        raise ValueError("object_key filename is missing")
    parts = path.parts
    try:
        originals_index = parts.index("originals")
    except ValueError:
        directory = str(path.parent)
    else:
        relative_parts = parts[originals_index + 1 : -1]
        directory = "/".join(relative_parts) if relative_parts else "."
    return directory, filename


def _proposed_directory(proposed_class: str) -> str:
    words = proposed_class.replace("_", " ").title().replace(" ", "")
    return f"DocWeave Organized/{words}"


def _proposed_filename(
    *,
    proposed_class: str,
    original_filename: str,
    proposal: Mapping[str, object],
) -> str:
    metadata = proposal.get("candidate_metadata")
    suffix = ""
    if isinstance(metadata, list):
        for item in metadata:
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
                if value:
                    suffix = "-" + _safe_filename_token(value)
                    break
    stem = _safe_filename_token(proposed_class.replace("_", "-"))
    extension = PurePosixPath(original_filename).suffix or ".pdf"
    return f"{stem}{suffix}{extension.casefold()}"


def _safe_filename_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in value)
    collapsed = "-".join(part for part in token.strip("-").split("-") if part)
    return (collapsed or "document")[:80].casefold()


def _confidence_value(signal: str) -> str:
    return {
        "weak": "0.350000",
        "moderate": "0.650000",
        "strong": "0.850000",
    }[signal]


_UPSERT_DOCUMENT = text(
    """
    INSERT INTO docweave.documents (
        document_id, workspace_label, original_directory, original_filename,
        current_directory, current_filename, content_sha256, page_count,
        status, discovered_at
    ) VALUES (
        :document_id, :workspace_label, :original_directory, :original_filename,
        :original_directory, :original_filename, :content_sha256, :page_count,
        'proposed', :completed_at
    )
    ON CONFLICT (workspace_label, content_sha256) DO UPDATE SET
        current_directory = excluded.current_directory,
        current_filename = excluded.current_filename,
        page_count = excluded.page_count,
        status = excluded.status
    RETURNING document_id
    """
)

_UPSERT_RUN = text(
    """
    INSERT INTO docweave.agent_runs (
        agent_run_id, document_id, provider, model_id, task, status,
        started_at, completed_at, input_sha256, output_json, summary
    ) VALUES (
        :agent_run_id, :document_id, 'amazon_bedrock', :model_id,
        'aws_worker_classify_uploaded_pdf', 'succeeded', :completed_at,
        :completed_at, :input_sha256, CAST(:output_json AS JSONB), :summary
    )
    ON CONFLICT (agent_run_id) DO NOTHING
    """
)

_UPSERT_PROPOSAL = text(
    """
    INSERT INTO docweave.proposals (
        proposal_id, document_id, agent_run_id, proposed_category,
        proposed_directory, proposed_filename, confidence, evidence_summary,
        status, created_at
    ) VALUES (
        :proposal_id, :document_id, :agent_run_id, :proposed_class,
        :proposed_directory, :proposed_filename, :confidence, :evidence_summary,
        'needs_review', :completed_at
    )
    ON CONFLICT (proposal_id) DO NOTHING
    """
)
