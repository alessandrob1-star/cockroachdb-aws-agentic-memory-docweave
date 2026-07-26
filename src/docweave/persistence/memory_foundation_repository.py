"""CockroachDB registration and approved taxonomy initialization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from docweave.analysis.taxonomy import (
    TAXONOMY_DEFINITIONS,
    TAXONOMY_VERSION,
    TaxonomyClass,
)
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.operation_repository import PersistenceConflictError
from docweave.persistence.transactions import TransactionRun

_DIGEST_SIZE = 32


class TransactionWork[T](Protocol):
    """Callable transaction closure."""

    def __call__(self, connection: Connection) -> T:
        """Execute against one active transaction."""


class SerializableTransactionRunner(Protocol):
    """Minimal transaction runner used by the adapter."""

    def run[T](self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Run one retry-safe transaction."""


@dataclass(frozen=True, slots=True)
class RegisterDocumentVersion:
    """Stable identity and verified content metadata for one PDF version."""

    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    version_number: int
    sha256: bytes
    byte_size: int
    page_count: int
    extraction_status: str
    registered_at_utc: datetime

    def __post_init__(self) -> None:
        if self.version_number <= 0:
            raise ValueError("version_number must be positive")
        if len(self.sha256) != _DIGEST_SIZE:
            raise ValueError("sha256 must contain 32 bytes")
        if self.byte_size < 0:
            raise ValueError("byte_size must not be negative")
        if self.page_count <= 0:
            raise ValueError("page_count must be positive")
        if self.extraction_status not in {"ready", "text_free"}:
            raise ValueError("extraction_status is not registerable")
        object.__setattr__(
            self,
            "registered_at_utc",
            _as_utc(self.registered_at_utc),
        )


@dataclass(frozen=True, slots=True)
class EnsureApprovedTaxonomy:
    """Workspace-scoped activation of the approved fixed taxonomy."""

    workspace_id: UUID
    taxonomy_version_id: UUID
    approved_by_actor_id: UUID
    approved_at_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approved_at_utc",
            _as_utc(self.approved_at_utc),
        )

    @property
    def class_ids(self) -> Mapping[TaxonomyClass, UUID]:
        """Return deterministic identifiers stable across exact retries."""
        return {
            definition.class_code: uuid5(
                self.taxonomy_version_id,
                definition.class_code.value,
            )
            for definition in TAXONOMY_DEFINITIONS
        }


_INSERT_DOCUMENT = sa.text(
    """
    INSERT INTO docweave.documents (
        document_id, workspace_id, lifecycle_status, created_at
    ) VALUES (
        :document_id, :workspace_id, 'active', :registered_at
    )
    ON CONFLICT (document_id) DO NOTHING
    """
)
_SELECT_DOCUMENT = sa.text(
    """
    SELECT workspace_id, lifecycle_status
    FROM docweave.documents
    WHERE document_id = :document_id
    FOR UPDATE
    """
)
_INSERT_VERSION = sa.text(
    """
    INSERT INTO docweave.document_versions (
        document_version_id, workspace_id, document_id, version_number,
        sha256, byte_size, media_type, page_count, extraction_status,
        registered_at
    ) VALUES (
        :document_version_id, :workspace_id, :document_id, :version_number,
        :sha256, :byte_size, 'application/pdf', :page_count,
        :extraction_status, :registered_at
    )
    ON CONFLICT (document_id, version_number) DO NOTHING
    RETURNING document_version_id
    """
)
_SELECT_VERSION = sa.text(
    """
    SELECT document_version_id, workspace_id, sha256, byte_size, media_type,
           page_count, extraction_status
    FROM docweave.document_versions
    WHERE document_id = :document_id AND version_number = :version_number
    """
)
_SET_CURRENT_VERSION = sa.text(
    """
    UPDATE docweave.documents
    SET current_version_id = :document_version_id
    WHERE document_id = :document_id
      AND workspace_id = :workspace_id
      AND lifecycle_status = 'active'
      AND (
          current_version_id IS NULL
          OR current_version_id = :document_version_id
      )
    """
)
_INSERT_TAXONOMY_VERSION = sa.text(
    """
    INSERT INTO docweave.taxonomy_versions (
        taxonomy_version_id, workspace_id, version_label, status,
        approved_by_actor_id, approved_at, created_at
    ) VALUES (
        :taxonomy_version_id, :workspace_id, :version_label, 'active',
        :approved_by_actor_id, :approved_at, :approved_at
    )
    ON CONFLICT (workspace_id, version_label) DO NOTHING
    RETURNING taxonomy_version_id
    """
)
_SELECT_TAXONOMY_VERSION = sa.text(
    """
    SELECT taxonomy_version_id, status, approved_by_actor_id, approved_at
    FROM docweave.taxonomy_versions
    WHERE workspace_id = :workspace_id AND version_label = :version_label
    FOR UPDATE
    """
)
_INSERT_TAXONOMY_CLASS = sa.text(
    """
    INSERT INTO docweave.taxonomy_classes (
        taxonomy_class_id, taxonomy_version_id, class_code, display_name,
        definition, expected_evidence, is_abstention, sort_order
    ) VALUES (
        :taxonomy_class_id, :taxonomy_version_id, :class_code, :display_name,
        :definition, :expected_evidence, :is_abstention, :sort_order
    )
    ON CONFLICT (taxonomy_version_id, class_code) DO NOTHING
    """
)
_SELECT_TAXONOMY_CLASSES = sa.text(
    """
    SELECT taxonomy_class_id, taxonomy_version_id, class_code, display_name, definition,
           expected_evidence, is_abstention, sort_order
    FROM docweave.taxonomy_classes
    WHERE taxonomy_version_id = :taxonomy_version_id
    ORDER BY sort_order
    """
)


class CockroachMemoryFoundationRepository:
    """Persist document identity and approved taxonomy without external effects."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def register_document_version(
        self,
        command: RegisterDocumentVersion,
    ) -> PersistenceDisposition:
        """Register verified content or return an exact idempotent replay."""

        def persist(connection: Connection) -> PersistenceDisposition:
            parameters = _document_parameters(command)
            connection.execute(_INSERT_DOCUMENT, parameters)
            document = (
                connection.execute(_SELECT_DOCUMENT, parameters)
                .mappings()
                .one_or_none()
            )
            if document is None or (
                document["workspace_id"] != command.workspace_id
                or document["lifecycle_status"] != "active"
            ):
                raise PersistenceConflictError(
                    "document identity is unavailable in the workspace"
                )

            inserted_id = connection.execute(
                _INSERT_VERSION,
                parameters,
            ).scalar_one_or_none()
            disposition = PersistenceDisposition.APPLIED
            if inserted_id is None:
                _validate_version_replay(connection, command)
                disposition = PersistenceDisposition.IDEMPOTENT_REPLAY
            elif inserted_id != command.document_version_id:
                raise PersistenceConflictError(
                    "created document version identity mismatch"
                )

            if connection.execute(_SET_CURRENT_VERSION, parameters).rowcount != 1:
                raise PersistenceConflictError(
                    "document has a different current version"
                )
            return disposition

        return self._transactions.run(persist).value

    def ensure_approved_taxonomy(
        self,
        command: EnsureApprovedTaxonomy,
    ) -> PersistenceDisposition:
        """Create or verify the approved workspace taxonomy atomically."""

        def persist(connection: Connection) -> PersistenceDisposition:
            parameters = _taxonomy_parameters(command)
            inserted_id = connection.execute(
                _INSERT_TAXONOMY_VERSION,
                parameters,
            ).scalar_one_or_none()
            disposition = PersistenceDisposition.APPLIED
            if inserted_id is None:
                _validate_taxonomy_version_replay(connection, command)
                disposition = PersistenceDisposition.IDEMPOTENT_REPLAY
            elif inserted_id != command.taxonomy_version_id:
                raise PersistenceConflictError(
                    "created taxonomy version identity mismatch"
                )

            connection.execute(
                _INSERT_TAXONOMY_CLASS,
                _taxonomy_class_parameters(command),
            )
            _validate_taxonomy_classes(connection, command)
            return disposition

        return self._transactions.run(persist).value


def _document_parameters(command: RegisterDocumentVersion) -> dict[str, object]:
    return {
        "workspace_id": command.workspace_id,
        "document_id": command.document_id,
        "document_version_id": command.document_version_id,
        "version_number": command.version_number,
        "sha256": command.sha256,
        "byte_size": command.byte_size,
        "page_count": command.page_count,
        "extraction_status": command.extraction_status,
        "registered_at": command.registered_at_utc,
    }


def _validate_version_replay(
    connection: Connection,
    command: RegisterDocumentVersion,
) -> None:
    existing = (
        connection.execute(
            _SELECT_VERSION,
            _document_parameters(command),
        )
        .mappings()
        .one_or_none()
    )
    if existing is None:
        raise PersistenceConflictError("document version replay is unresolved")
    expected = {
        "document_version_id": command.document_version_id,
        "workspace_id": command.workspace_id,
        "sha256": command.sha256,
        "byte_size": command.byte_size,
        "media_type": "application/pdf",
        "page_count": command.page_count,
        "extraction_status": command.extraction_status,
    }
    actual = dict(cast(Mapping[str, object], existing))
    if bytes(cast(bytes, actual["sha256"])) != command.sha256:
        raise PersistenceConflictError("document version has different content")
    actual["sha256"] = command.sha256
    if actual != expected:
        raise PersistenceConflictError("document version replay has different metadata")


def _taxonomy_parameters(command: EnsureApprovedTaxonomy) -> dict[str, object]:
    return {
        "workspace_id": command.workspace_id,
        "taxonomy_version_id": command.taxonomy_version_id,
        "version_label": TAXONOMY_VERSION,
        "approved_by_actor_id": command.approved_by_actor_id,
        "approved_at": command.approved_at_utc,
    }


def _taxonomy_class_parameters(
    command: EnsureApprovedTaxonomy,
) -> list[dict[str, object]]:
    class_ids = command.class_ids
    return [
        {
            "taxonomy_class_id": class_ids[definition.class_code],
            "taxonomy_version_id": command.taxonomy_version_id,
            "class_code": definition.class_code.value,
            "display_name": definition.display_name,
            "definition": definition.definition,
            "expected_evidence": definition.expected_evidence,
            "is_abstention": definition.is_abstention,
            "sort_order": sort_order,
        }
        for sort_order, definition in enumerate(TAXONOMY_DEFINITIONS)
    ]


def _validate_taxonomy_version_replay(
    connection: Connection,
    command: EnsureApprovedTaxonomy,
) -> None:
    existing = (
        connection.execute(
            _SELECT_TAXONOMY_VERSION,
            _taxonomy_parameters(command),
        )
        .mappings()
        .one_or_none()
    )
    if existing is None or (
        existing["taxonomy_version_id"] != command.taxonomy_version_id
        or existing["status"] != "active"
        or existing["approved_by_actor_id"] != command.approved_by_actor_id
        or existing["approved_at"] != command.approved_at_utc
    ):
        raise PersistenceConflictError(
            "approved taxonomy replay has different authority or identity"
        )


def _validate_taxonomy_classes(
    connection: Connection,
    command: EnsureApprovedTaxonomy,
) -> None:
    rows = (
        connection.execute(
            _SELECT_TAXONOMY_CLASSES,
            _taxonomy_parameters(command),
        )
        .mappings()
        .all()
    )
    expected = _taxonomy_class_parameters(command)
    actual = [dict(cast(Mapping[str, object], row)) for row in rows]
    if actual != expected:
        raise PersistenceConflictError("persisted taxonomy classes do not match")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
