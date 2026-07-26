from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.operations import (
    AuditActorType,
    AuditEventType,
    BatchItemState,
    BatchState,
    ExecutionReason,
    FileOperation,
    ResultDisposition,
)
from docweave.persistence import (
    AuditAppend,
    BatchItemSnapshot,
    CockroachOperationRepository,
    CreateBatch,
    PersistenceConflictError,
    PersistenceDisposition,
    PersistenceNotFoundError,
    RecordExecutionIntent,
    RecordOperationResult,
    TransactionRun,
)

NOW = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000002")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000003")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000004")
EVENT_ID = UUID("00000000-0000-4000-8000-000000000005")
SECOND_EVENT_ID = UUID("00000000-0000-4000-8000-000000000006")
LEASE_TOKEN = UUID("00000000-0000-4000-8000-000000000007")
DIGEST = bytes.fromhex("ab" * 32)


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        mapping: Mapping[str, object] | None = None,
        rowcount: int = 1,
    ) -> None:
        self._scalar = scalar
        self._mapping = mapping
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> Mapping[str, object] | None:
        return self._mapping


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self._responses = list(responses)
        self.calls: list[
            tuple[str, Mapping[str, object] | Sequence[Mapping[str, object]] | None]
        ] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
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


def audit_event(
    event_type: AuditEventType,
    *,
    event_id: UUID = EVENT_ID,
    file_operation_id: UUID | None = OPERATION_ID,
    occurred_at: datetime = NOW,
) -> AuditAppend:
    return AuditAppend(
        event_id=event_id,
        workspace_id=WORKSPACE_ID,
        actor_id=ACTOR_ID,
        actor_type=AuditActorType.SYSTEM,
        correlation_id="correlation-001",
        event_type=event_type,
        subject_kind=(
            "operation_batch" if file_operation_id is None else "file_operation"
        ),
        subject_id="batch-001" if file_operation_id is None else "item-001",
        occurred_at_utc=occurred_at,
        operation_batch_id=BATCH_ID,
        file_operation_id=file_operation_id,
        previous_state="approved",
        new_state="executing",
    )


def batch_command(
    *,
    events: tuple[AuditAppend, ...] | None = None,
) -> CreateBatch:
    item = BatchItemSnapshot(
        file_operation_id=OPERATION_ID,
        batch_item_id="item-001",
        operation=FileOperation.COPY,
        plan_sha256=DIGEST,
        source_root_reference="workspace-source",
        source_relative_path="incoming/invoice.pdf",
        destination_root_reference="workspace-organized",
        destination_relative_path="invoices/2026/invoice.pdf",
        state=BatchItemState.PLANNED,
        expected_source_sha256=DIGEST,
        expected_source_size=42,
    )
    return CreateBatch(
        operation_batch_id=BATCH_ID,
        workspace_id=WORKSPACE_ID,
        external_batch_id="batch-001",
        idempotency_key="create-batch-001",
        operation=FileOperation.COPY,
        preview_sha256=DIGEST,
        preview_version=1,
        policy_version="operations.v1",
        correlation_id="correlation-001",
        status=BatchState.READY_FOR_APPROVAL,
        created_by_actor_id=ACTOR_ID,
        created_at_utc=NOW,
        items=(item,),
        audit_events=events
        or (audit_event(AuditEventType.BATCH_CREATED, file_operation_id=None),),
    )


def intent_command() -> RecordExecutionIntent:
    return RecordExecutionIntent(
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_id=OPERATION_ID,
        execution_id="execution-001",
        idempotency_key="execute-item-001",
        executor_actor_id=ACTOR_ID,
        lease_token=LEASE_TOKEN,
        intent_recorded_at_utc=NOW,
        lease_expires_at_utc=NOW + timedelta(minutes=2),
        audit_event=audit_event(
            AuditEventType.ITEM_EXECUTION_INTENT_RECORDED,
        ),
    )


def result_command() -> RecordOperationResult:
    return RecordOperationResult(
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_id=OPERATION_ID,
        execution_id="execution-001",
        idempotency_key="execute-item-001",
        terminal_state=BatchItemState.SUCCEEDED,
        reason=ExecutionReason.SUCCEEDED,
        disposition=ResultDisposition.EXECUTED,
        completed_at_utc=NOW + timedelta(seconds=2),
        source_exists_after=True,
        destination_exists_after=True,
        actual_source_relative_path="incoming/invoice.pdf",
        actual_destination_relative_path="invoices/2026/invoice.pdf",
        actual_sha256=DIGEST,
        actual_size=42,
        error_category=None,
        audit_event=audit_event(
            AuditEventType.ITEM_EXECUTION_SUCCEEDED,
            occurred_at=NOW + timedelta(seconds=2),
        ),
    )


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachOperationRepository, FakeTransactionRunner]:
    transaction_runner = FakeTransactionRunner(FakeConnection(responses))
    return CockroachOperationRepository(transaction_runner), transaction_runner


def test_creates_batch_items_and_hash_chained_audit_atomically() -> None:
    second_event = audit_event(
        AuditEventType.ITEM_PLANNED,
        event_id=SECOND_EVENT_ID,
        occurred_at=NOW + timedelta(milliseconds=1),
    )
    command = batch_command(
        events=(
            audit_event(AuditEventType.BATCH_CREATED, file_operation_id=None),
            second_event,
        )
    )
    adapter, transaction_runner = repository(
        [
            FakeResult(scalar=BATCH_ID),
            FakeResult(),
            FakeResult(scalar=WORKSPACE_ID),
            FakeResult(mapping=None),
            FakeResult(),
            FakeResult(),
        ]
    )

    disposition = adapter.create_batch(command)

    assert disposition is PersistenceDisposition.APPLIED
    assert transaction_runner.run_count == 1
    connection = transaction_runner.connection
    connection.assert_consumed()
    assert len(connection.calls) == 6
    assert "ON CONFLICT" in connection.calls[0][0]
    assert isinstance(connection.calls[1][1], list)
    first_audit = cast(Mapping[str, object], connection.calls[4][1])
    second_audit = cast(Mapping[str, object], connection.calls[5][1])
    assert len(cast(bytes, first_audit["event_sha256"])) == 32
    assert second_audit["previous_event_id"] == EVENT_ID
    assert second_audit["previous_event_sha256"] == first_audit["event_sha256"]


def test_exact_batch_replay_performs_no_duplicate_writes() -> None:
    adapter, transaction_runner = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "operation_batch_id": BATCH_ID,
                    "preview_sha256": DIGEST,
                }
            ),
        ]
    )

    disposition = adapter.create_batch(batch_command())

    assert disposition is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(transaction_runner.connection.calls) == 2
    transaction_runner.connection.assert_consumed()


def test_batch_idempotency_conflict_never_overwrites() -> None:
    adapter, _ = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "operation_batch_id": BATCH_ID,
                    "preview_sha256": bytes.fromhex("cd" * 32),
                }
            ),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different content"):
        adapter.create_batch(batch_command())


def test_batch_creation_fails_closed_when_audit_workspace_is_missing() -> None:
    adapter, _ = repository(
        [
            FakeResult(scalar=BATCH_ID),
            FakeResult(),
            FakeResult(scalar=None),
        ]
    )

    with pytest.raises(PersistenceNotFoundError, match="workspace"):
        adapter.create_batch(batch_command())


def test_records_execution_intent_and_audit_in_one_transaction() -> None:
    command = intent_command()
    adapter, transaction_runner = repository(
        [
            FakeResult(
                mapping={
                    "state": "approved",
                    "execution_id": None,
                    "idempotency_key": None,
                }
            ),
            FakeResult(rowcount=1),
            FakeResult(rowcount=1),
            FakeResult(scalar=WORKSPACE_ID),
            FakeResult(mapping=None),
            FakeResult(),
        ]
    )

    disposition = adapter.record_execution_intent(command)

    assert disposition is PersistenceDisposition.APPLIED
    assert transaction_runner.run_count == 1
    transaction_runner.connection.assert_consumed()
    update_parameters = cast(
        Mapping[str, object],
        transaction_runner.connection.calls[1][1],
    )
    assert update_parameters["lease_token"] == LEASE_TOKEN
    assert update_parameters["execution_id"] == "execution-001"


def test_execution_intent_is_idempotent_for_same_claim() -> None:
    adapter, transaction_runner = repository(
        [
            FakeResult(
                mapping={
                    "state": "executing",
                    "execution_id": "execution-001",
                    "idempotency_key": "execute-item-001",
                }
            )
        ]
    )

    disposition = adapter.record_execution_intent(intent_command())

    assert disposition is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(transaction_runner.connection.calls) == 1


def test_execution_intent_rejects_competing_claim() -> None:
    adapter, _ = repository(
        [
            FakeResult(
                mapping={
                    "state": "executing",
                    "execution_id": "different-execution",
                    "idempotency_key": "different-key",
                }
            )
        ]
    )

    with pytest.raises(PersistenceConflictError, match="already executing"):
        adapter.record_execution_intent(intent_command())


def test_execution_intent_fails_closed_when_operation_is_missing() -> None:
    adapter, _ = repository([FakeResult(mapping=None)])

    with pytest.raises(PersistenceNotFoundError, match="operation"):
        adapter.record_execution_intent(intent_command())


def test_records_terminal_result_batch_counts_and_audit_atomically() -> None:
    command = result_command()
    adapter, transaction_runner = repository(
        [
            FakeResult(
                mapping={
                    "state": "executing",
                    "execution_id": "execution-001",
                    "idempotency_key": "execute-item-001",
                }
            ),
            FakeResult(rowcount=1),
            FakeResult(rowcount=1),
            FakeResult(scalar=WORKSPACE_ID),
            FakeResult(mapping=None),
            FakeResult(),
        ]
    )

    disposition = adapter.record_operation_result(command)

    assert disposition is PersistenceDisposition.APPLIED
    assert transaction_runner.run_count == 1
    transaction_runner.connection.assert_consumed()
    result_parameters = cast(
        Mapping[str, object],
        transaction_runner.connection.calls[1][1],
    )
    assert result_parameters["succeeded_increment"] == 1
    assert result_parameters["verification_failed_increment"] == 0
    assert result_parameters["actual_sha256"] == DIGEST


def test_exact_terminal_result_replay_does_not_increment_batch_twice() -> None:
    adapter, transaction_runner = repository(
        [
            FakeResult(
                mapping={
                    "state": "succeeded",
                    "execution_id": "execution-001",
                    "idempotency_key": "execute-item-001",
                    "result_disposition": "executed",
                    "actual_sha256": DIGEST,
                    "actual_size": 42,
                    "source_exists_after": True,
                    "destination_exists_after": True,
                }
            )
        ]
    )

    disposition = adapter.record_operation_result(result_command())

    assert disposition is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(transaction_runner.connection.calls) == 1


def test_terminal_result_rejects_different_prior_evidence() -> None:
    adapter, _ = repository(
        [
            FakeResult(
                mapping={
                    "state": "succeeded",
                    "execution_id": "execution-001",
                    "idempotency_key": "execute-item-001",
                    "result_disposition": "executed",
                    "actual_sha256": bytes.fromhex("cd" * 32),
                    "actual_size": 42,
                    "source_exists_after": True,
                    "destination_exists_after": True,
                }
            )
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different result"):
        adapter.record_operation_result(result_command())


def test_verification_failure_marks_reconciliation_required() -> None:
    command = replace(
        result_command(),
        terminal_state=BatchItemState.VERIFICATION_FAILED,
        reason=ExecutionReason.VERIFICATION_FAILED,
        actual_sha256=None,
        actual_size=None,
        audit_event=audit_event(
            AuditEventType.ITEM_VERIFICATION_FAILED,
            occurred_at=NOW + timedelta(seconds=2),
        ),
    )
    adapter, transaction_runner = repository(
        [
            FakeResult(
                mapping={
                    "state": "executing",
                    "execution_id": "execution-001",
                    "idempotency_key": "execute-item-001",
                }
            ),
            FakeResult(rowcount=1),
            FakeResult(rowcount=1),
            FakeResult(scalar=WORKSPACE_ID),
            FakeResult(mapping=None),
            FakeResult(),
        ]
    )

    disposition = adapter.record_operation_result(command)

    assert disposition is PersistenceDisposition.APPLIED
    result_parameters = cast(
        Mapping[str, object],
        transaction_runner.connection.calls[1][1],
    )
    assert result_parameters["reconciliation_state"] == "required"
    assert result_parameters["verification_failed_increment"] == 1
