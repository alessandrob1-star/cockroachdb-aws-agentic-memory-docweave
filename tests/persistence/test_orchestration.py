from collections.abc import Callable
from dataclasses import replace
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
    BatchExecutionHooks,
    BatchExecutionRequest,
    BatchItemRequest,
    BatchItemState,
    ExecutionReason,
    ExecutionResult,
    ExecutionStatus,
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    OperationApproval,
    OperationBatch,
    OperationResultRecord,
    ResultDisposition,
    approve_operation_batch,
    create_operation_batch,
    execute_operation_batch,
    operation_execution_key,
    operation_plan_fingerprint,
    plan_file_operation,
)
from docweave.persistence import (
    ActiveExecutionLeaseError,
    AuditAppend,
    CreateBatch,
    DurableExecutionLedger,
    DurableOperationLifecycleRecorder,
    DurableRestoreAuditRecorder,
    OperationExecutionIdentity,
    PersistedOperationExecution,
    PersistenceConflictError,
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
    def __init__(
        self,
        loaded_execution: PersistedOperationExecution | None = None,
    ) -> None:
        self.intents: list[RecordExecutionIntent] = []
        self.results: list[RecordOperationResult] = []
        self.events: list[tuple[AuditAppend, ...]] = []
        self.loaded_execution = loaded_execution
        self.load_identities: list[OperationExecutionIdentity] = []

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

    def load_operation_execution(
        self,
        identity: OperationExecutionIdentity,
    ) -> PersistedOperationExecution | None:
        self.load_identities.append(identity)
        return self.loaded_execution

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


def restore_event(
    event_type: AuditEventType = AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
    *,
    event_id: str = "00000000-0000-4000-8000-000000000031",
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        workspace_id=WORKSPACE_EXTERNAL_ID,
        batch_id=BATCH_EXTERNAL_ID,
        batch_item_id="item-001",
        event_type=event_type,
        actor_type=AuditActorType.SYSTEM,
        actor_id="executor",
        occurred_at_utc=NOW + timedelta(seconds=4),
        correlation_id="restore-correlation-001",
        idempotency_key="restore-batch-001:item-001:restore",
        previous_state="approved",
        new_state="succeeded",
        reason="succeeded",
        plan_fingerprint="cd" * 32,
        approval_id="restore-approval-001",
        source_relative_path="organized/invoice.pdf",
        destination_relative_path="incoming/invoice.pdf",
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


def test_records_restore_audit_events_through_durable_boundary() -> None:
    repository = RecordingRepository()
    recorder = DurableRestoreAuditRecorder(
        repository,
        identities=identities(),
        resolve_actor_identity=lambda external_id: ACTOR_ID,
    )

    recorder.record_events(
        (
            restore_event(
                AuditEventType.RESTORE_APPROVED,
                event_id="00000000-0000-4000-8000-000000000031",
            ),
            restore_event(
                AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
                event_id="00000000-0000-4000-8000-000000000032",
            ),
        )
    )

    assert len(repository.events) == 1
    assert [event.event_type for event in repository.events[0]] == [
        AuditEventType.RESTORE_APPROVED,
        AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
    ]
    assert repository.events[0][0].workspace_id == WORKSPACE_ID
    assert repository.events[0][0].operation_batch_id == BATCH_ID
    assert repository.events[0][0].file_operation_id == OPERATION_ID
    assert repository.events[0][1].actor_id == ACTOR_ID
    assert repository.events[0][1].plan_sha256 == bytes.fromhex("cd" * 32)
    assert (
        repository.events[0][1].idempotency_key == "restore-batch-001:item-001:restore"
    )


def test_restore_audit_recorder_rejects_empty_and_non_restore_events(
    tmp_path: Path,
) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()
    restore_recorder = DurableRestoreAuditRecorder(
        repository,
        identities=identities(),
        resolve_actor_identity=lambda external_id: ACTOR_ID,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        restore_recorder.record_events(())
    with pytest.raises(ValueError, match="only restore events"):
        restore_recorder.record_events(
            (event(batch, AuditEventType.ITEM_EXECUTION_REPLAYED),)
        )

    assert repository.events == []


def persisted_execution(
    batch: OperationBatch,
    *,
    state: BatchItemState,
    lease_expires_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> PersistedOperationExecution:
    item = batch.items[0]
    terminal = state in {
        BatchItemState.BLOCKED,
        BatchItemState.SUCCEEDED,
        BatchItemState.FAILED,
        BatchItemState.VERIFICATION_FAILED,
    }
    return PersistedOperationExecution(
        identity=OperationExecutionIdentity(
            workspace_id=WORKSPACE_ID,
            operation_batch_id=BATCH_ID,
            file_operation_id=OPERATION_ID,
        ),
        state=state,
        idempotency_key=idempotency_key or operation_execution_key(batch, item),
        execution_id=f"{batch.batch_id}:{item.item_id}",
        approval_id="approval-001",
        lease_expires_at_utc=lease_expires_at,
        intent_recorded_at_utc=NOW + timedelta(seconds=2),
        started_at_utc=NOW + timedelta(seconds=2),
        completed_at_utc=NOW + timedelta(seconds=3) if terminal else None,
        result_disposition=ResultDisposition.EXECUTED if terminal else None,
        expected_source_sha256=bytes.fromhex(item.expected_source_digest or ""),
        actual_sha256=(
            bytes.fromhex(item.expected_source_digest or "")
            if state is BatchItemState.SUCCEEDED
            else None
        ),
        actual_size=17 if state is BatchItemState.SUCCEEDED else None,
        source_exists_after=True if terminal else None,
        destination_exists_after=(
            state is BatchItemState.SUCCEEDED if terminal else None
        ),
        safe_error_summary=(
            ExecutionReason.SUCCEEDED.value
            if state is BatchItemState.SUCCEEDED
            else (ExecutionReason.VERIFICATION_FAILED.value if terminal else None)
        ),
        error_category=None,
    )


def fail_if_executed(
    plan: FileOperationPlan,
    approval: OperationApproval,
    *,
    execution_id: str,
    now_utc: datetime,
) -> ExecutionResult:
    raise AssertionError("filesystem executor must not run")


def test_replays_durable_terminal_result_without_filesystem_mutation(
    tmp_path: Path,
) -> None:
    batch, trail = approved_batch(tmp_path)
    repository = RecordingRepository(
        persisted_execution(batch, state=BatchItemState.SUCCEEDED)
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest(
            executed_by_actor_id="executor",
            now_utc=NOW + timedelta(minutes=5),
        ),
        audit_trail=trail,
        execution_ledger=ledger,
        hooks=BatchExecutionHooks(operation_executor=fail_if_executed),
    )

    assert report.replayed_item_count == 1
    assert report.results[0].disposition is ResultDisposition.IDEMPOTENT_REPLAY
    assert len(repository.load_identities) == 1


def test_active_durable_lease_blocks_second_process_before_mutation(
    tmp_path: Path,
) -> None:
    batch, trail = approved_batch(tmp_path)
    active_until = NOW + timedelta(minutes=8)
    repository = RecordingRepository(
        persisted_execution(
            batch,
            state=BatchItemState.EXECUTING,
            lease_expires_at=active_until,
        )
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(ActiveExecutionLeaseError) as captured:
        execute_operation_batch(
            batch,
            BatchExecutionRequest(
                executed_by_actor_id="executor",
                now_utc=NOW + timedelta(minutes=5),
            ),
            audit_trail=trail,
            execution_ledger=ledger,
            hooks=BatchExecutionHooks(operation_executor=fail_if_executed),
        )

    assert captured.value.retry_after_utc == active_until
    assert len(repository.load_identities) == 1
    assert batch.items[0].plan.destination_path is not None
    assert not batch.items[0].plan.destination_path.exists()


def test_expired_durable_lease_reconciles_verified_postcondition(
    tmp_path: Path,
) -> None:
    batch, trail = approved_batch(tmp_path)
    item = batch.items[0]
    assert item.plan.source_path is not None
    assert item.plan.destination_path is not None
    item.plan.destination_path.parent.mkdir(parents=True)
    item.plan.destination_path.write_bytes(item.plan.source_path.read_bytes())
    repository = RecordingRepository(
        persisted_execution(
            batch,
            state=BatchItemState.EXECUTING,
            lease_expires_at=NOW + timedelta(minutes=4),
        )
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest(
            executed_by_actor_id="executor",
            now_utc=NOW + timedelta(minutes=5),
        ),
        audit_trail=trail,
        execution_ledger=ledger,
        hooks=BatchExecutionHooks(
            operation_executor=fail_if_executed,
            lifecycle_recorder=recorder(repository),
        ),
    )

    assert report.results[0].status is ExecutionStatus.SUCCEEDED
    assert report.results[0].disposition is ResultDisposition.RECONCILED
    assert len(repository.load_identities) == 1
    assert len(repository.results) == 1


def test_durable_execution_key_mismatch_fails_closed(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository(
        persisted_execution(
            batch,
            state=BatchItemState.SUCCEEDED,
            idempotency_key="different-key",
        )
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(
        PersistenceConflictError,
        match="execution key does not match",
    ):
        ledger.result_for(operation_execution_key(batch, batch.items[0]))


def test_durable_state_is_loaded_once_across_restart_checks(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository(
        persisted_execution(
            batch,
            state=BatchItemState.EXECUTING,
            lease_expires_at=NOW + timedelta(minutes=4),
        )
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )
    execution_key = operation_execution_key(batch, batch.items[0])

    assert ledger.result_for(execution_key) is None
    assert ledger.is_in_progress(
        execution_key,
        now_utc=NOW + timedelta(minutes=5),
    )
    assert len(repository.load_identities) == 1


def test_missing_durable_state_is_not_in_progress(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )
    execution_key = operation_execution_key(batch, batch.items[0])

    assert ledger.result_for(execution_key) is None
    assert not ledger.is_in_progress(execution_key, now_utc=NOW)
    assert len(repository.load_identities) == 1


def test_locally_owned_intent_and_result_take_precedence(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )
    execution_key = operation_execution_key(batch, batch.items[0])
    result = successful_result(batch)

    ledger.record_intent(execution_key)
    assert ledger.is_in_progress(execution_key, now_utc=NOW)
    ledger.record_result(result)

    assert ledger.result_for(execution_key) is result
    assert repository.load_identities == []


def test_durable_lease_evaluation_requires_current_time(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository(
        persisted_execution(
            batch,
            state=BatchItemState.EXECUTING,
            lease_expires_at=NOW + timedelta(minutes=4),
        )
    )
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(ValueError, match="now_utc"):
        ledger.is_in_progress(operation_execution_key(batch, batch.items[0]))


def _with_wrong_execution_id(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, execution_id="different")


def _with_wrong_approval_id(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, approval_id="different")


def _with_wrong_source_digest(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, expected_source_sha256=bytes.fromhex("ff" * 32))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_with_wrong_execution_id, "execution identity"),
        (_with_wrong_approval_id, "approval identity"),
        (_with_wrong_source_digest, "source identity"),
    ],
)
def test_mismatched_durable_claim_evidence_fails_closed(
    tmp_path: Path,
    mutate: Callable[[PersistedOperationExecution], PersistedOperationExecution],
    message: str,
) -> None:
    batch, _ = approved_batch(tmp_path)
    execution = mutate(persisted_execution(batch, state=BatchItemState.SUCCEEDED))
    ledger = DurableExecutionLedger(
        RecordingRepository(execution),
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(PersistenceConflictError, match=message):
        ledger.result_for(operation_execution_key(batch, batch.items[0]))


def test_invalid_persisted_result_reason_fails_closed(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    execution = replace(
        persisted_execution(batch, state=BatchItemState.SUCCEEDED),
        safe_error_summary="invented_reason",
    )
    ledger = DurableExecutionLedger(
        RecordingRepository(execution),
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(PersistenceConflictError, match="reason is invalid"):
        ledger.result_for(operation_execution_key(batch, batch.items[0]))


def test_unknown_execution_key_is_rejected_without_database_read(
    tmp_path: Path,
) -> None:
    batch, _ = approved_batch(tmp_path)
    repository = RecordingRepository()
    ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities(),
    )

    with pytest.raises(ValueError, match="not bound"):
        ledger.result_for("unknown")

    assert repository.load_identities == []


def test_durable_ledger_rejects_mismatched_identity_map(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    mismatched = replace(identities(), external_batch_id="different")

    with pytest.raises(ValueError, match="does not match"):
        DurableExecutionLedger(
            RecordingRepository(),
            batch=batch,
            identities=mismatched,
        )


def test_durable_ledger_requires_exact_item_identities(tmp_path: Path) -> None:
    batch, _ = approved_batch(tmp_path)
    mismatched = PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id=BATCH_EXTERNAL_ID,
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"different-item": OPERATION_ID},
    )

    with pytest.raises(ValueError, match="exactly match"):
        DurableExecutionLedger(
            RecordingRepository(),
            batch=batch,
            identities=mismatched,
        )
