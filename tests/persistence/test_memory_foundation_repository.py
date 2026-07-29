from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.analysis import TAXONOMY_DEFINITIONS
from docweave.persistence import (
    CockroachMemoryFoundationRepository,
    EnsureApprovedTaxonomy,
    PersistenceConflictError,
    PersistenceDisposition,
    RegisterDocumentVersion,
    TransactionRun,
)

NOW = datetime(2026, 7, 26, 18, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000002")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000003")
TAXONOMY_ID = UUID("00000000-0000-4000-8000-000000000004")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000005")
DIGEST = bytes.fromhex("ab" * 32)


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        mapping: Mapping[str, object] | None = None,
        rows: Sequence[Mapping[str, object]] = (),
        rowcount: int = 1,
    ) -> None:
        self._scalar = scalar
        self._mapping = mapping
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> Mapping[str, object] | None:
        return self._mapping

    def all(self) -> list[Mapping[str, object]]:
        return self._rows


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self.responses = list(responses)
        self.calls: list[
            tuple[str, Mapping[str, object] | Sequence[Mapping[str, object]] | None]
        ] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters))
        if not self.responses:
            raise AssertionError("unexpected database call")
        return self.responses.pop(0)


class FakeTransactionRunner:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]:
        return TransactionRun(
            value=work(cast(Connection, self.connection)),
            attempts=1,
        )


def document_command() -> RegisterDocumentVersion:
    return RegisterDocumentVersion(
        workspace_id=WORKSPACE_ID,
        document_id=DOCUMENT_ID,
        document_version_id=VERSION_ID,
        version_number=1,
        sha256=DIGEST,
        byte_size=42,
        page_count=2,
        extraction_status="ready",
        registered_at_utc=NOW,
    )


def taxonomy_command() -> EnsureApprovedTaxonomy:
    return EnsureApprovedTaxonomy(
        workspace_id=WORKSPACE_ID,
        taxonomy_version_id=TAXONOMY_ID,
        approved_by_actor_id=ACTOR_ID,
        approved_at_utc=NOW,
    )


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachMemoryFoundationRepository, FakeConnection]:
    connection = FakeConnection(responses)
    return (
        CockroachMemoryFoundationRepository(FakeTransactionRunner(connection)),
        connection,
    )


def version_row(*, digest: bytes = DIGEST) -> Mapping[str, object]:
    return {
        "document_version_id": VERSION_ID,
        "workspace_id": WORKSPACE_ID,
        "sha256": digest,
        "byte_size": 42,
        "media_type": "application/pdf",
        "page_count": 2,
        "extraction_status": "ready",
    }


def taxonomy_rows() -> list[Mapping[str, object]]:
    command = taxonomy_command()
    return [
        {
            "taxonomy_class_id": command.class_ids[definition.class_code],
            "taxonomy_version_id": TAXONOMY_ID,
            "class_code": definition.class_code.value,
            "display_name": definition.display_name,
            "definition": definition.definition,
            "expected_evidence": definition.expected_evidence,
            "is_abstention": definition.is_abstention,
            "sort_order": order,
        }
        for order, definition in enumerate(TAXONOMY_DEFINITIONS)
    ]


def test_registers_document_and_version_atomically_with_bound_values() -> None:
    adapter, connection = repository(
        [
            FakeResult(),
            FakeResult(
                mapping={
                    "workspace_id": WORKSPACE_ID,
                    "lifecycle_status": "active",
                }
            ),
            FakeResult(scalar=VERSION_ID),
            FakeResult(rowcount=1),
        ]
    )

    result = adapter.register_document_version(document_command())

    assert result is PersistenceDisposition.APPLIED
    assert connection.responses == []
    statements = "\n".join(statement for statement, _ in connection.calls)
    assert "INSERT INTO docweave.documents" in statements
    assert "INSERT INTO docweave.document_versions" in statements
    assert "UPDATE docweave.documents" in statements
    assert DIGEST not in statements.encode()


def test_exact_document_version_replay_is_idempotent() -> None:
    adapter, _ = repository(
        [
            FakeResult(),
            FakeResult(
                mapping={
                    "workspace_id": WORKSPACE_ID,
                    "lifecycle_status": "active",
                }
            ),
            FakeResult(scalar=None),
            FakeResult(mapping=version_row()),
            FakeResult(rowcount=1),
        ]
    )

    assert (
        adapter.register_document_version(document_command())
        is PersistenceDisposition.IDEMPOTENT_REPLAY
    )


def test_document_version_replay_rejects_different_content() -> None:
    adapter, _ = repository(
        [
            FakeResult(),
            FakeResult(
                mapping={
                    "workspace_id": WORKSPACE_ID,
                    "lifecycle_status": "active",
                }
            ),
            FakeResult(scalar=None),
            FakeResult(mapping=version_row(digest=bytes.fromhex("cd" * 32))),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different content"):
        adapter.register_document_version(document_command())


def test_seeds_and_verifies_the_complete_approved_taxonomy() -> None:
    adapter, connection = repository(
        [
            FakeResult(scalar=TAXONOMY_ID),
            FakeResult(),
            FakeResult(rows=taxonomy_rows()),
        ]
    )

    result = adapter.ensure_approved_taxonomy(taxonomy_command())

    assert result is PersistenceDisposition.APPLIED
    class_parameters = cast(
        Sequence[Mapping[str, object]],
        connection.calls[1][1],
    )
    assert len(class_parameters) == len(TAXONOMY_DEFINITIONS)
    assert {item["class_code"] for item in class_parameters} == {
        definition.class_code.value for definition in TAXONOMY_DEFINITIONS
    }
    assert all(":definition" in statement for statement, _ in connection.calls[1:2])


def test_taxonomy_replay_requires_same_human_authority() -> None:
    adapter, _ = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "taxonomy_version_id": TAXONOMY_ID,
                    "status": "active",
                    "approved_by_actor_id": UUID(
                        "00000000-0000-4000-8000-000000000099"
                    ),
                    "approved_at": NOW,
                }
            ),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different authority"):
        adapter.ensure_approved_taxonomy(taxonomy_command())


def test_taxonomy_replay_allows_existing_approval_timestamp() -> None:
    adapter, connection = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "taxonomy_version_id": TAXONOMY_ID,
                    "status": "active",
                    "approved_by_actor_id": ACTOR_ID,
                    "approved_at": datetime(2026, 7, 1, tzinfo=UTC),
                }
            ),
            FakeResult(),
            FakeResult(rows=taxonomy_rows()),
        ]
    )

    assert (
        adapter.ensure_approved_taxonomy(taxonomy_command())
        is PersistenceDisposition.IDEMPOTENT_REPLAY
    )
    statements = "\n".join(statement for statement, _ in connection.calls)
    assert "INSERT INTO docweave.taxonomy_classes" in statements
