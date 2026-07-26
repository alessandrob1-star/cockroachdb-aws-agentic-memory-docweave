from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from docweave.operations import (
    AppendOnlyAuditTrail,
    AuditActorType,
    AuditEvent,
    AuditEventType,
    BatchApprovalRequest,
    BatchCreationRequest,
    BatchItemRequest,
    ExecutionReason,
    ExecutionStatus,
    FileOperation,
    FileOperationRequest,
    OperationBatch,
    OperationResultRecord,
    ResultDisposition,
    approve_operation_batch,
    create_operation_batch,
    operation_execution_key,
    operation_plan_fingerprint,
    plan_file_operation,
)
from docweave.persistence import (
    AuditAppend,
    CreateBatch,
    DurableOperationLifecycleRecorder,
    PersistenceDisposition,
    PersistenceEvidenceError,
    PersistenceIdentityMap,
    RecordExecutionIntent,
    RecordOperationResult,
)

NOW = datetime(2026, 7, 26, 14, 0, tzinfo=UTC)
WORKSPACE_EXTERNAL_ID = str(UUID("00000000-0000-4000-8000-000000000001"))
BATCH_EXTERNAL_ID = str(UUID("00000000-0000-4000-8000-000000000002"))
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000011")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000012")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000013")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000014")
LEASE_TOKEN = UUID("00000000-0000-4000-8000-000000000015")


class RecordingRepository:
    def __init__(self) -> None:
        self.intents: list[RecordExecutionIntent] = []
        self.results: list[RecordOperationResult] = []
        self.events: list[tuple[AuditAppend, ...]] = []

    def create_batch(self, command: CreateBatch) -> PersistenceDisposition:
        raise AssertionError("batch creation is outside this recorder test")

    def record_execution_intent(
        self,
        command: RecordExecutionIntent,
    ) -> PersistenceDisposition:
        self.intents.append(command)
        return PersistenceDisposition.APPLIED

    def record_operation_result(
        self,
        command: RecordOperationResult,
    ) -> PersistenceDisposition:
        self.results.append(command)
        return PersistenceDisposition.APPLIED

    def append_audit_events(
        self,
        events: tuple[AuditAppend, ...],
    ) -> PersistenceDisposition:
        self.events.append(events)
        return PersistenceDisposition.APPLIED


def approved_batch(tmp_path: Path) -> tuple[OperationBatch, AppendOnlyAuditTrail]:
    source = tmp_path / "source"
    destination = tmp_path / "organized"
    source.mkdir()
    destination.mkdir()
    (source / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source,
            source_relative_path="invoice.pdf",
            destination_root=destination,
            destination_relative_path="invoices/invoice.pdf",
        )
    )
    trail = AppendOnlyAuditTrail()
    batch = create_operation_batch(
        BatchCreationRequest(
            batch_id=BATCH_EXTERNAL_ID,
            workspace_id=WORKSPACE_EXTERNAL_ID,
            created_by_user_id="creator",
            created_at_utc=NOW,
            idempotency_key="batch-001",
            correlation_id="correlation-001",
            policy_version="operations.v1",
            item_requests=(BatchItemRequest("item-001", plan),),
        ),
        audit_trail=trail,
    )
    return (
        approve_operation_batch(
            batch,
            BatchApprovalRequest(
                approval_id="approval-001",
                approved_by_user_id="reviewer",
                approved_at_utc=NOW + timedelta(seconds=1),
                expires_at_utc=NOW + timedelta(minutes=10),
            ),
            audit_trail=trail,
        ),
        trail,
    )


def identities() -> PersistenceIdentityMap:
    return PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id=BATCH_EXTERNAL_ID,
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"item-001": OPERATION_ID},
    )


def recorder(
    repository: RecordingRepository,
) -> DurableOperationLifecycleRecorder:
    return DurableOperationLifecycleRecorder(
        repository,
        identities=identities(),
        resolve_actor_identity=lambda external_id: ACTOR_ID,
        lease_duration=timedelta(minutes=3),
        lease_token_factory=lambda: LEASE_TOKEN,
    )


def event(
    batch: OperationBatch,
    event_type: AuditEventType,
) -> AuditEvent:
    item = batch.items[0]
    return AuditEvent(
        event_id="00000000-0000-4000-8000-000000000021",
        workspace_id=batch.workspace_id,
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        event_type=event_type,
        actor_type=AuditActorType.SYSTEM,
        actor_id="executor",
        occurred_at_utc=NOW + timedelta(seconds=2),
        correlation_id=batch.correlation_id,
        idempotency_key=operation_execution_key(batch, item),
        previous_state="approved",
        new_state=(
            "executing"
            if event_type is AuditEventType.ITEM_EXECUTION_INTENT_RECORDED
            else "succeeded"
        ),
        reason="test_transition",
        plan_fingerprint=operation_plan_fingerprint(item.plan),
        approval_id="approval-001",
        source_relative_path=item.plan.source_relative_path,
        destination_relative_path=item.plan.destination_relative_path,
    )


def successful_result(batch: OperationBatch) -> OperationResultRecord:
    item = batch.items[0]
    return OperationResultRecord(
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        execution_key=operation_execution_key(batch, item),
        execution_id=f"{batch.batch_id}:{item.item_id}",
        status=ExecutionStatus.SUCCEEDED,
        reason=ExecutionReason.SUCCEEDED,
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=NOW + timedelta(seconds=2),
        completed_at_utc=NOW + timedelta(seconds=3),
        approval_id="approval-001",
        source_exists_after=True,
        destination_exists_after=True,
        source_digest_before=item.expected_source_digest,
        destination_digest_after=item.expected_source_digest,
    )


def test_records_bounded_execution_lease_before_mutation(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()

    recorder(repository).record_intent(
        batch,
        batch.items[0],
        event(batch, AuditEventType.ITEM_EXECUTION_INTENT_RECORDED),
    )

    command = repository.intents[0]
    assert command.lease_token == LEASE_TOKEN
    assert command.lease_expires_at_utc == NOW + timedelta(minutes=3, seconds=2)
    assert command.file_operation_id == OPERATION_ID


def test_records_observed_destination_size_with_terminal_result(
    tmp_path: Path,
) -> None:
    batch, _ = approved_batch(tmp_path)
    item = batch.items[0]
    assert item.plan.destination_path is not None
    payload = b"%PDF-1.7\ninvoice"
    item.plan.destination_path.parent.mkdir(parents=True)
    item.plan.destination_path.write_bytes(payload)
    repository = RecordingRepository()

    recorder(repository).record_result(
        batch,
        item,
        successful_result(batch),
        event(batch, AuditEventType.ITEM_EXECUTION_SUCCEEDED),
    )

    command = repository.results[0]
    assert command.actual_size == len(payload)
    assert command.actual_destination_relative_path == "invoices/invoice.pdf"


def test_success_without_observable_destination_fails_for_reconciliation(
    tmp_path: Path,
) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()

    with pytest.raises(PersistenceEvidenceError, match="destination size"):
        recorder(repository).record_result(
            batch,
            batch.items[0],
            successful_result(batch),
            event(batch, AuditEventType.ITEM_EXECUTION_SUCCEEDED),
        )

    assert repository.results == []


def test_records_non_result_lifecycle_event(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()

    recorder(repository).record_event(
        batch,
        event(batch, AuditEventType.ITEM_EXECUTION_REPLAYED),
    )

    assert repository.events[0][0].event_type is (
        AuditEventType.ITEM_EXECUTION_REPLAYED
    )
