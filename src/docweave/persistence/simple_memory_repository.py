"""Simple CockroachDB memory writes for the DocWeave demo schema."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.transactions import TransactionRun

_DIGEST_SIZE = 32


class SerializableTransactionRunner(Protocol):
    """Minimal transaction runner used by the simple memory adapter."""

    def run[T](self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Run one retry-safe transaction."""


class TransactionWork[T](Protocol):
    """Callable transaction closure."""

    def __call__(self, connection: Connection) -> T:
        """Execute against one active transaction."""


@dataclass(frozen=True, slots=True)
class PersistSimpleAnalysis:
    """One readable Analyze memory write for the simple `docweave` schema."""

    workspace_label: str
    document_id: UUID
    agent_run_id: UUID
    proposal_id: UUID
    original_directory: str
    original_filename: str
    content_sha256: bytes
    page_count: int
    provider: str
    model_id: str
    task: str
    status: str
    started_at_utc: datetime
    completed_at_utc: datetime
    input_sha256: bytes
    output_json: str
    summary: str
    proposed_category: str
    proposed_directory: str
    proposed_filename: str
    confidence: Decimal
    evidence_summary: str

    def __post_init__(self) -> None:
        for name in (
            "workspace_label",
            "original_filename",
            "provider",
            "model_id",
            "task",
            "status",
            "summary",
            "proposed_category",
            "proposed_filename",
            "evidence_summary",
        ):
            _require_text(name, getattr(self, name))
        if len(self.content_sha256) != _DIGEST_SIZE:
            raise ValueError("content_sha256 must contain 32 bytes")
        if len(self.input_sha256) != _DIGEST_SIZE:
            raise ValueError("input_sha256 must contain 32 bytes")
        if self.page_count <= 0:
            raise ValueError("page_count must be positive")
        if not Decimal(0) <= self.confidence <= Decimal(1):
            raise ValueError("confidence must be between zero and one")
        _validate_json_object(self.output_json)
        object.__setattr__(self, "started_at_utc", _as_utc(self.started_at_utc))
        object.__setattr__(self, "completed_at_utc", _as_utc(self.completed_at_utc))


@dataclass(frozen=True, slots=True)
class PersistHumanDecision:
    """One dashboard review decision with optional file path history."""

    proposal_id: UUID
    human_decision_id: UUID
    actor_label: str
    decision: str
    decided_at_utc: datetime
    reason: str | None = None
    document_id: UUID | None = None
    operation: str | None = None
    previous_directory: str | None = None
    previous_filename: str | None = None
    next_directory: str | None = None
    next_filename: str | None = None
    file_status: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_text("actor_label", self.actor_label)
        if self.decision not in {"approve", "reject", "request_changes"}:
            raise ValueError("decision is not supported")
        object.__setattr__(self, "decided_at_utc", _as_utc(self.decided_at_utc))
        history_values = (
            self.document_id,
            self.operation,
            self.previous_directory,
            self.previous_filename,
            self.next_directory,
            self.next_filename,
            self.file_status,
        )
        if any(value is not None for value in history_values) and not all(
            value is not None for value in history_values
        ):
            raise ValueError("file history fields must be supplied together")


_UPSERT_DOCUMENT = sa.text(
    """
    INSERT INTO docweave.documents (
        document_id, workspace_label, original_directory, original_filename,
        current_directory, current_filename, content_sha256, page_count,
        status, discovered_at
    ) VALUES (
        :document_id, :workspace_label, :original_directory, :original_filename,
        :original_directory, :original_filename, :content_sha256, :page_count,
        'proposed', :started_at
    )
    ON CONFLICT (workspace_label, content_sha256) DO UPDATE
    SET current_directory = excluded.current_directory,
        current_filename = excluded.current_filename,
        page_count = excluded.page_count,
        status = 'proposed'
    RETURNING document_id
    """
)
_INSERT_RUN = sa.text(
    """
    INSERT INTO docweave.agent_runs (
        agent_run_id, document_id, provider, model_id, task, status,
        started_at, completed_at, input_sha256, output_json, summary
    ) VALUES (
        :agent_run_id, :document_id, :provider, :model_id, :task, :status,
        :started_at, :completed_at, :input_sha256,
        CAST(:output_json AS JSONB), :summary
    )
    ON CONFLICT (agent_run_id) DO NOTHING
    RETURNING agent_run_id
    """
)
_INSERT_PROPOSAL = sa.text(
    """
    INSERT INTO docweave.proposals (
        proposal_id, document_id, agent_run_id, proposed_category,
        proposed_directory, proposed_filename, confidence, evidence_summary,
        status, created_at
    ) VALUES (
        :proposal_id, :document_id, :agent_run_id, :proposed_category,
        :proposed_directory, :proposed_filename, :confidence, :evidence_summary,
        'needs_review', :completed_at
    )
    ON CONFLICT (proposal_id) DO NOTHING
    RETURNING proposal_id
    """
)
_SELECT_REPLAY = sa.text(
    """
    SELECT proposal_id
    FROM docweave.proposals
    WHERE proposal_id = :proposal_id
      AND document_id = :document_id
      AND agent_run_id = :agent_run_id
    """
)
_LOCK_PROPOSAL = sa.text(
    """
    SELECT proposal_id, document_id, status
    FROM docweave.proposals
    WHERE proposal_id = :proposal_id
    FOR UPDATE
    """
)
_INSERT_DECISION = sa.text(
    """
    INSERT INTO docweave.human_decisions (
        human_decision_id, proposal_id, actor_label, decision, reason, decided_at
    ) VALUES (
        :human_decision_id, :proposal_id, :actor_label, :decision, :reason,
        :decided_at
    )
    ON CONFLICT (human_decision_id) DO NOTHING
    RETURNING human_decision_id
    """
)
_UPDATE_PROPOSAL = sa.text(
    """
    UPDATE docweave.proposals
    SET status = :proposal_status
    WHERE proposal_id = :proposal_id
    """
)
_UPDATE_DOCUMENT_PATH = sa.text(
    """
    UPDATE docweave.documents
    SET current_directory = :next_directory,
        current_filename = :next_filename,
        status = :document_status
    WHERE document_id = :document_id
    """
)
_INSERT_FILE_HISTORY = sa.text(
    """
    INSERT INTO docweave.file_history (
        document_id, proposal_id, human_decision_id, event_sequence, operation,
        previous_directory, previous_filename, next_directory, next_filename,
        status, occurred_at, note
    ) VALUES (
        :document_id, :proposal_id, :human_decision_id,
        (
            SELECT COALESCE(max(event_sequence), 0) + 1
            FROM docweave.file_history
            WHERE document_id = :document_id
        ),
        :operation, :previous_directory, :previous_filename, :next_directory,
        :next_filename, :file_status, :decided_at, :note
    )
    """
)


class CockroachSimpleMemoryRepository:
    """Persist the simple memory graph shown in the dashboard and CockroachDB."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def persist_analysis(
        self, command: PersistSimpleAnalysis
    ) -> PersistenceDisposition:
        """Write document, run, and proposal rows without mutating files."""

        def persist_once(connection: Connection) -> PersistenceDisposition:
            parameters = _parameters(command)
            stored_document_id = connection.execute(
                _UPSERT_DOCUMENT,
                parameters,
            ).scalar_one()
            parameters["document_id"] = stored_document_id
            connection.execute(_INSERT_RUN, parameters)
            inserted_proposal_id = connection.execute(
                _INSERT_PROPOSAL,
                parameters,
            ).scalar_one_or_none()
            if inserted_proposal_id is None:
                replay = connection.execute(
                    _SELECT_REPLAY,
                    parameters,
                ).scalar_one_or_none()
                if replay != command.proposal_id:
                    raise ValueError("proposal replay has different identity")
                return PersistenceDisposition.IDEMPOTENT_REPLAY
            if inserted_proposal_id != command.proposal_id:
                raise ValueError("created proposal identity mismatch")
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist_once).value

    def persist_human_decision(
        self,
        command: PersistHumanDecision,
    ) -> PersistenceDisposition:
        """Persist review decision and optional before/after path history."""

        def persist_once(connection: Connection) -> PersistenceDisposition:
            parameters = _decision_parameters(command)
            proposal = (
                connection.execute(_LOCK_PROPOSAL, parameters).mappings().one_or_none()
            )
            if proposal is None:
                raise ValueError("decision references an unknown proposal")
            inserted_id = connection.execute(
                _INSERT_DECISION,
                parameters,
            ).scalar_one_or_none()
            if inserted_id is None:
                return PersistenceDisposition.IDEMPOTENT_REPLAY
            connection.execute(
                _UPDATE_PROPOSAL,
                {
                    **parameters,
                    "proposal_status": _proposal_status(command.decision),
                },
            )
            if command.document_id is not None:
                connection.execute(
                    _UPDATE_DOCUMENT_PATH,
                    {
                        **parameters,
                        "document_status": _document_status(command),
                    },
                )
                connection.execute(_INSERT_FILE_HISTORY, parameters)
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist_once).value


def _parameters(command: PersistSimpleAnalysis) -> dict[str, object]:
    return {
        "workspace_label": command.workspace_label,
        "document_id": command.document_id,
        "agent_run_id": command.agent_run_id,
        "proposal_id": command.proposal_id,
        "original_directory": command.original_directory,
        "original_filename": command.original_filename,
        "content_sha256": command.content_sha256,
        "page_count": command.page_count,
        "provider": command.provider,
        "model_id": command.model_id,
        "task": command.task,
        "status": command.status,
        "started_at": command.started_at_utc,
        "completed_at": command.completed_at_utc,
        "input_sha256": command.input_sha256,
        "output_json": command.output_json,
        "summary": command.summary,
        "proposed_category": command.proposed_category,
        "proposed_directory": command.proposed_directory,
        "proposed_filename": command.proposed_filename,
        "confidence": command.confidence,
        "evidence_summary": command.evidence_summary,
    }


def _decision_parameters(command: PersistHumanDecision) -> dict[str, object]:
    return {
        "proposal_id": command.proposal_id,
        "human_decision_id": command.human_decision_id,
        "actor_label": command.actor_label,
        "decision": command.decision,
        "reason": command.reason,
        "decided_at": command.decided_at_utc,
        "document_id": command.document_id,
        "operation": command.operation,
        "previous_directory": command.previous_directory,
        "previous_filename": command.previous_filename,
        "next_directory": command.next_directory,
        "next_filename": command.next_filename,
        "file_status": command.file_status,
        "note": command.note,
    }


def _proposal_status(decision: str) -> str:
    return {
        "approve": "approved",
        "reject": "rejected",
        "request_changes": "needs_review",
    }[decision]


def _document_status(command: PersistHumanDecision) -> str:
    if command.file_status == "succeeded" and command.operation in {
        "move",
        "rename",
        "rename_and_move",
    }:
        return "moved"
    if command.decision == "approve":
        return "approved"
    if command.decision == "reject":
        return "rejected"
    return "proposed"


def simple_output_json(payload: Mapping[str, object]) -> str:
    """Return compact JSON safe to bind into the simple run table."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def split_relative_path(relative_path: str) -> tuple[str, str]:
    """Return readable directory and filename pieces for simple memory."""
    path = PurePosixPath(relative_path)
    filename = path.name
    directory = "." if str(path.parent) == "." else str(path.parent)
    return directory, filename


def _validate_json_object(value: str) -> None:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("output_json must contain an object")


def _require_text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
