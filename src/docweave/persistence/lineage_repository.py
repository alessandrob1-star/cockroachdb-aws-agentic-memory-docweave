"""Atomic CockroachDB persistence for file lineage memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.row import RowMapping

from docweave.operations.lineage import FileLineageAction
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.operation_repository import PersistenceConflictError
from docweave.persistence.transactions import TransactionRun

_SHA256_HEX_LENGTH = 64
_MAX_HISTORY_ROWS = 1_000
_TERMINAL_STATUSES = frozenset(
    {"blocked", "succeeded", "failed", "verification_failed"}
)


class SerializableTransactionRunner(Protocol):
    """Minimal transaction runner used by the adapter."""

    def run[T](self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Run one retry-safe transaction."""


class TransactionWork[T](Protocol):
    """Callable transaction closure."""

    def __call__(self, connection: Connection) -> T:
        """Execute against one active transaction."""


@dataclass(frozen=True, slots=True)
class PersistFileLineageEvent:
    """Durable command for one append-only file lineage event."""

    workspace_id: UUID
    file_lineage_event_id: UUID
    logical_document_key: str
    lineage_sequence: int
    idempotency_key: str
    action: FileLineageAction
    original_relative_path: str
    previous_relative_path: str
    next_relative_path: str
    original_directory: str
    original_filename: str
    previous_directory: str
    previous_filename: str
    next_directory: str
    next_filename: str
    status: str
    plan_fingerprint: str
    operation_batch_id: UUID | None = None
    file_operation_id: UUID | None = None
    batch_item_id: str | None = None
    proposal_id: UUID | None = None
    occurred_at_utc: datetime | None = None
    source_digest_before: str | None = None
    destination_digest_after: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("logical_document_key", self.logical_document_key),
            ("idempotency_key", self.idempotency_key),
            ("original_filename", self.original_filename),
            ("previous_filename", self.previous_filename),
            ("next_filename", self.next_filename),
        ):
            _require_text(field_name, value)
        if self.lineage_sequence < 1:
            raise ValueError("lineage_sequence must be positive")
        if self.status not in _TERMINAL_STATUSES:
            raise ValueError("status must be a terminal operation state")
        if self.operation_batch_id is not None and self.batch_item_id is None:
            raise ValueError("operation_batch_id requires batch_item_id")
        for field_name, value in (
            ("original_relative_path", self.original_relative_path),
            ("previous_relative_path", self.previous_relative_path),
            ("next_relative_path", self.next_relative_path),
        ):
            _require_relative_path(field_name, value)
        for field_name, value in (
            ("original_directory", self.original_directory),
            ("previous_directory", self.previous_directory),
            ("next_directory", self.next_directory),
        ):
            _require_directory(field_name, value)
        if (
            self.action is FileLineageAction.BLOCKED
            and self.previous_relative_path != self.next_relative_path
        ):
            raise ValueError("blocked lineage events must not change path")
        _validate_fingerprint("plan_fingerprint", self.plan_fingerprint)
        if self.source_digest_before is not None:
            _validate_fingerprint("source_digest_before", self.source_digest_before)
        if self.destination_digest_after is not None:
            _validate_fingerprint(
                "destination_digest_after",
                self.destination_digest_after,
            )
        if self.occurred_at_utc is not None:
            object.__setattr__(
                self,
                "occurred_at_utc",
                _as_utc(self.occurred_at_utc),
            )


@dataclass(frozen=True, slots=True)
class FileLineageHistoryQuery:
    """Bounded workspace-scoped query for one lineage history view."""

    workspace_id: UUID
    logical_document_key: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.logical_document_key is not None:
            _require_text("logical_document_key", self.logical_document_key)
        if not 1 <= self.limit <= _MAX_HISTORY_ROWS:
            raise ValueError("limit must be between 1 and 1000")


@dataclass(frozen=True, slots=True)
class FileLineageEventSnapshot:
    """One durable file lineage event safe to show in history views."""

    file_lineage_event_id: UUID
    workspace_id: UUID
    logical_document_key: str
    lineage_sequence: int
    action: FileLineageAction
    original_relative_path: str
    previous_relative_path: str
    next_relative_path: str
    original_directory: str
    original_filename: str
    previous_directory: str
    previous_filename: str
    next_directory: str
    next_filename: str
    status: str
    occurred_at_utc: datetime | None
    operation_batch_id: UUID | None = None
    file_operation_id: UUID | None = None
    batch_item_id: str | None = None
    proposal_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_text("logical_document_key", self.logical_document_key)
        if self.lineage_sequence < 1:
            raise ValueError("lineage_sequence must be positive")
        if self.status not in _TERMINAL_STATUSES:
            raise ValueError("status must be a terminal operation state")
        for field_name, value in (
            ("original_relative_path", self.original_relative_path),
            ("previous_relative_path", self.previous_relative_path),
            ("next_relative_path", self.next_relative_path),
        ):
            _require_relative_path(field_name, value)
        for field_name, value in (
            ("original_filename", self.original_filename),
            ("previous_filename", self.previous_filename),
            ("next_filename", self.next_filename),
        ):
            _require_text(field_name, value)
        if self.occurred_at_utc is not None:
            object.__setattr__(
                self,
                "occurred_at_utc",
                _as_utc(self.occurred_at_utc),
            )


_INSERT_LINEAGE = sa.text(
    """
    INSERT INTO docweave.file_lineage_events (
        file_lineage_event_id, workspace_id, logical_document_key,
        lineage_sequence, idempotency_key, action, operation_batch_id,
        file_operation_id, batch_item_id, proposal_id, original_relative_path,
        previous_relative_path, next_relative_path, original_directory,
        original_filename, previous_directory, previous_filename,
        next_directory, next_filename, status, occurred_at, plan_sha256,
        source_sha256_before, destination_sha256_after
    ) VALUES (
        :file_lineage_event_id, :workspace_id, :logical_document_key,
        :lineage_sequence, :idempotency_key, :action, :operation_batch_id,
        :file_operation_id, :batch_item_id, :proposal_id,
        :original_relative_path, :previous_relative_path, :next_relative_path,
        :original_directory, :original_filename, :previous_directory,
        :previous_filename, :next_directory, :next_filename, :status,
        :occurred_at, :plan_sha256, :source_sha256_before,
        :destination_sha256_after
    )
    ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
    RETURNING file_lineage_event_id
    """
)
_SELECT_REPLAY = sa.text(
    """
    SELECT file_lineage_event_id, logical_document_key, lineage_sequence,
           action, operation_batch_id, file_operation_id, batch_item_id,
           proposal_id, original_relative_path, previous_relative_path,
           next_relative_path, original_directory, original_filename,
           previous_directory, previous_filename, next_directory, next_filename,
           status, occurred_at, plan_sha256, source_sha256_before,
           destination_sha256_after
    FROM docweave.file_lineage_events
    WHERE workspace_id = :workspace_id
      AND idempotency_key = :idempotency_key
    """
)
_SELECT_HISTORY = sa.text(
    """
    SELECT file_lineage_event_id, workspace_id, logical_document_key,
           lineage_sequence, action, operation_batch_id, file_operation_id,
           batch_item_id, proposal_id, original_relative_path,
           previous_relative_path, next_relative_path, original_directory,
           original_filename, previous_directory, previous_filename,
           next_directory, next_filename, status, occurred_at
    FROM docweave.file_lineage_events
    WHERE workspace_id = :workspace_id
      AND (
          :logical_document_key IS NULL
          OR logical_document_key = :logical_document_key
      )
    ORDER BY logical_document_key ASC, lineage_sequence ASC,
             file_lineage_event_id ASC
    LIMIT :limit
    """
)


class CockroachFileLineageRepository:
    """Persist append-only file lineage rows atomically and idempotently."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def persist(self, command: PersistFileLineageEvent) -> PersistenceDisposition:
        """Write one lineage event or confirm an exact idempotent replay."""

        def persist_once(connection: Connection) -> PersistenceDisposition:
            parameters = _parameters(command)
            inserted_id = connection.execute(
                _INSERT_LINEAGE,
                parameters,
            ).scalar_one_or_none()
            if inserted_id is None:
                return _validate_replay(connection, command)
            if inserted_id != command.file_lineage_event_id:
                raise PersistenceConflictError("created file lineage identity mismatch")
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist_once).value

    def load_history(
        self,
        query: FileLineageHistoryQuery,
    ) -> tuple[FileLineageEventSnapshot, ...]:
        """Load bounded file lineage history inside one workspace."""

        def load(connection: Connection) -> tuple[FileLineageEventSnapshot, ...]:
            rows = (
                connection.execute(
                    _SELECT_HISTORY,
                    {
                        "workspace_id": query.workspace_id,
                        "logical_document_key": query.logical_document_key,
                        "limit": query.limit,
                    },
                )
                .mappings()
                .all()
            )
            return tuple(_snapshot_from_row(row) for row in rows)

        return self._transactions.run(load).value


def _parameters(command: PersistFileLineageEvent) -> dict[str, object]:
    return {
        "file_lineage_event_id": command.file_lineage_event_id,
        "workspace_id": command.workspace_id,
        "logical_document_key": command.logical_document_key,
        "lineage_sequence": command.lineage_sequence,
        "idempotency_key": command.idempotency_key,
        "action": command.action.value,
        "operation_batch_id": command.operation_batch_id,
        "file_operation_id": command.file_operation_id,
        "batch_item_id": command.batch_item_id,
        "proposal_id": command.proposal_id,
        "original_relative_path": command.original_relative_path,
        "previous_relative_path": command.previous_relative_path,
        "next_relative_path": command.next_relative_path,
        "original_directory": command.original_directory,
        "original_filename": command.original_filename,
        "previous_directory": command.previous_directory,
        "previous_filename": command.previous_filename,
        "next_directory": command.next_directory,
        "next_filename": command.next_filename,
        "status": command.status,
        "occurred_at": command.occurred_at_utc,
        "plan_sha256": bytes.fromhex(command.plan_fingerprint),
        "source_sha256_before": (
            None
            if command.source_digest_before is None
            else bytes.fromhex(command.source_digest_before)
        ),
        "destination_sha256_after": (
            None
            if command.destination_digest_after is None
            else bytes.fromhex(command.destination_digest_after)
        ),
    }


def _validate_replay(
    connection: Connection,
    command: PersistFileLineageEvent,
) -> PersistenceDisposition:
    existing = (
        connection.execute(
            _SELECT_REPLAY,
            {
                "workspace_id": command.workspace_id,
                "idempotency_key": command.idempotency_key,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing is None:
        raise PersistenceConflictError("file lineage replay is unresolved")
    if not _matches_existing(existing, command):
        raise PersistenceConflictError("file lineage replay has different content")
    return PersistenceDisposition.IDEMPOTENT_REPLAY


def _snapshot_from_row(row: RowMapping) -> FileLineageEventSnapshot:
    try:
        action = FileLineageAction(str(row["action"]))
    except ValueError:
        raise PersistenceConflictError("file lineage row action is invalid") from None
    try:
        return FileLineageEventSnapshot(
            file_lineage_event_id=_uuid(row["file_lineage_event_id"]),
            workspace_id=_uuid(row["workspace_id"]),
            logical_document_key=str(row["logical_document_key"]),
            lineage_sequence=int(row["lineage_sequence"]),
            action=action,
            operation_batch_id=_optional_uuid(row["operation_batch_id"]),
            file_operation_id=_optional_uuid(row["file_operation_id"]),
            batch_item_id=_optional_text(row["batch_item_id"]),
            proposal_id=_optional_uuid(row["proposal_id"]),
            original_relative_path=str(row["original_relative_path"]),
            previous_relative_path=str(row["previous_relative_path"]),
            next_relative_path=str(row["next_relative_path"]),
            original_directory=str(row["original_directory"]),
            original_filename=str(row["original_filename"]),
            previous_directory=str(row["previous_directory"]),
            previous_filename=str(row["previous_filename"]),
            next_directory=str(row["next_directory"]),
            next_filename=str(row["next_filename"]),
            status=str(row["status"]),
            occurred_at_utc=_stored_optional_time(row["occurred_at"]),
        )
    except (TypeError, ValueError) as error:
        raise PersistenceConflictError("file lineage row is invalid") from error


def _matches_existing(
    existing: RowMapping,
    command: PersistFileLineageEvent,
) -> bool:
    return (
        existing["file_lineage_event_id"] == command.file_lineage_event_id
        and existing["logical_document_key"] == command.logical_document_key
        and existing["lineage_sequence"] == command.lineage_sequence
        and existing["action"] == command.action.value
        and existing["operation_batch_id"] == command.operation_batch_id
        and existing["file_operation_id"] == command.file_operation_id
        and existing["batch_item_id"] == command.batch_item_id
        and existing["proposal_id"] == command.proposal_id
        and existing["original_relative_path"] == command.original_relative_path
        and existing["previous_relative_path"] == command.previous_relative_path
        and existing["next_relative_path"] == command.next_relative_path
        and existing["original_directory"] == command.original_directory
        and existing["original_filename"] == command.original_filename
        and existing["previous_directory"] == command.previous_directory
        and existing["previous_filename"] == command.previous_filename
        and existing["next_directory"] == command.next_directory
        and existing["next_filename"] == command.next_filename
        and existing["status"] == command.status
        and _stored_optional_time(existing["occurred_at"]) == command.occurred_at_utc
        and _stored_digest(existing["plan_sha256"])
        == bytes.fromhex(command.plan_fingerprint)
        and _stored_optional_digest(existing["source_sha256_before"])
        == (
            None
            if command.source_digest_before is None
            else bytes.fromhex(command.source_digest_before)
        )
        and _stored_optional_digest(existing["destination_sha256_after"])
        == (
            None
            if command.destination_digest_after is None
            else bytes.fromhex(command.destination_digest_after)
        )
    )


def _require_text(field_name: str, value: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")


def _require_relative_path(field_name: str, value: str) -> None:
    path = PurePosixPath(value)
    if (
        value.strip() == ""
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")


def _require_directory(field_name: str, value: str) -> None:
    if value == "":
        return
    _require_relative_path(field_name, value)


def _validate_fingerprint(name: str, value: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest")


def _stored_digest(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    raise ValueError("stored digest must be bytes")


def _stored_optional_digest(value: object) -> bytes | None:
    if value is None:
        return None
    return _stored_digest(value)


def _stored_optional_time(value: object) -> datetime | None:
    if value is None:
        return None
    return _as_utc(value)


def _as_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("timestamps must be datetime values")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError("identifier must be UUID")


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return _uuid(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    _require_text("optional text", text)
    return text
