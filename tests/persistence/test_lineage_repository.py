from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.operations import FileLineageAction
from docweave.persistence import (
    CockroachFileLineageRepository,
    PersistenceConflictError,
    PersistenceDisposition,
    PersistFileLineageEvent,
    TransactionRun,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
LINEAGE_ID = UUID("00000000-0000-4000-8000-000000000002")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000003")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000004")
PROPOSAL_ID = UUID("00000000-0000-4000-8000-000000000005")
DIGEST_HEX = "ab" * 32
DIGEST_BYTES = bytes.fromhex(DIGEST_HEX)


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        mapping: Mapping[str, object] | None = None,
    ) -> None:
        self._scalar = scalar
        self._row = mapping

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> Mapping[str, object] | None:
        return self._row


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters))
        if not self._responses:
            raise AssertionError("unexpected database call")
        return self._responses.pop(0)

    def assert_consumed(self) -> None:
        assert self._responses == []


class FakeTransactionRunner:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.run_count = 0

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]:
        self.run_count += 1
        value = work(cast(Connection, self.connection))
        return TransactionRun(value=value, attempts=1)


def command() -> PersistFileLineageEvent:
    return PersistFileLineageEvent(
        workspace_id=WORKSPACE_ID,
        file_lineage_event_id=LINEAGE_ID,
        logical_document_key="sha256:source-document",
        lineage_sequence=2,
        idempotency_key="lineage:batch-001:item-001:2",
        action=FileLineageAction.RENAME_AND_MOVE,
        operation_batch_id=BATCH_ID,
        file_operation_id=OPERATION_ID,
        batch_item_id="item-001",
        proposal_id=PROPOSAL_ID,
        original_relative_path="incoming/scan_0001.pdf",
        previous_relative_path="incoming/scan_0001.pdf",
        next_relative_path="DocWeave Organized/Invoices/invoice_2026_001.pdf",
        original_directory="incoming",
        original_filename="scan_0001.pdf",
        previous_directory="incoming",
        previous_filename="scan_0001.pdf",
        next_directory="DocWeave Organized/Invoices",
        next_filename="invoice_2026_001.pdf",
        status="succeeded",
        occurred_at_utc=NOW,
        plan_fingerprint=DIGEST_HEX,
        source_digest_before=DIGEST_HEX,
        destination_digest_after=DIGEST_HEX,
    )


def persisted_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "file_lineage_event_id": LINEAGE_ID,
        "logical_document_key": "sha256:source-document",
        "lineage_sequence": 2,
        "action": "rename_and_move",
        "operation_batch_id": BATCH_ID,
        "file_operation_id": OPERATION_ID,
        "batch_item_id": "item-001",
        "proposal_id": PROPOSAL_ID,
        "original_relative_path": "incoming/scan_0001.pdf",
        "previous_relative_path": "incoming/scan_0001.pdf",
        "next_relative_path": "DocWeave Organized/Invoices/invoice_2026_001.pdf",
        "original_directory": "incoming",
        "original_filename": "scan_0001.pdf",
        "previous_directory": "incoming",
        "previous_filename": "scan_0001.pdf",
        "next_directory": "DocWeave Organized/Invoices",
        "next_filename": "invoice_2026_001.pdf",
        "status": "succeeded",
        "occurred_at": NOW,
        "plan_sha256": DIGEST_BYTES,
        "source_sha256_before": DIGEST_BYTES,
        "destination_sha256_after": DIGEST_BYTES,
    }
    row.update(overrides)
    return row


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachFileLineageRepository, FakeTransactionRunner]:
    runner = FakeTransactionRunner(FakeConnection(responses))
    return CockroachFileLineageRepository(runner), runner


def test_persists_file_lineage_event_with_bound_parameters() -> None:
    adapter, runner = repository([FakeResult(scalar=LINEAGE_ID)])

    result = adapter.persist(command())

    assert result is PersistenceDisposition.APPLIED
    assert runner.run_count == 1
    runner.connection.assert_consumed()
    query, raw_parameters = runner.connection.calls[0]
    parameters = cast(Mapping[str, object], raw_parameters)
    assert "INSERT INTO docweave.file_lineage_events" in query
    assert "ON CONFLICT" in query
    assert parameters["original_filename"] == "scan_0001.pdf"
    assert parameters["next_filename"] == "invoice_2026_001.pdf"
    assert parameters["plan_sha256"] == DIGEST_BYTES


def test_file_lineage_replay_is_idempotent_for_exact_content() -> None:
    adapter, runner = repository(
        [
            FakeResult(scalar=None),
            FakeResult(mapping=persisted_row()),
        ]
    )

    result = adapter.persist(command())

    assert result is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(runner.connection.calls) == 2
    runner.connection.assert_consumed()


def test_file_lineage_replay_rejects_changed_history() -> None:
    adapter, _ = repository(
        [
            FakeResult(scalar=None),
            FakeResult(mapping=persisted_row(next_filename="different.pdf")),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different content"):
        adapter.persist(command())


def test_untrusted_filename_is_data_not_sql() -> None:
    injection_payload = "x'); DROP TABLE docweave.file_lineage_events; --.pdf"
    malicious = replace(
        command(),
        original_relative_path=f"incoming/{injection_payload}",
        previous_relative_path=f"incoming/{injection_payload}",
        next_relative_path=f"organized/{injection_payload}",
        original_filename=injection_payload,
        previous_filename=injection_payload,
        next_filename=injection_payload,
        next_directory="organized",
    )
    adapter, runner = repository([FakeResult(scalar=LINEAGE_ID)])

    assert adapter.persist(malicious) is PersistenceDisposition.APPLIED

    query, raw_parameters = runner.connection.calls[0]
    parameters = cast(Mapping[str, object], raw_parameters)
    assert injection_payload not in query
    assert parameters["original_filename"] == injection_payload
    assert parameters["next_relative_path"] == f"organized/{injection_payload}"


def test_file_lineage_command_fails_closed_for_unsafe_paths() -> None:
    with pytest.raises(ValueError, match="normalized relative path"):
        replace(command(), next_relative_path="../escape.pdf")


def test_blocked_file_lineage_cannot_change_path() -> None:
    with pytest.raises(ValueError, match="must not change path"):
        replace(
            command(),
            action=FileLineageAction.BLOCKED,
            status="blocked",
        )


def test_operation_batch_requires_batch_item_identity() -> None:
    with pytest.raises(ValueError, match="requires batch_item_id"):
        replace(command(), batch_item_id=None)
