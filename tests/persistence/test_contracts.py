from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

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
    CreateBatch,
    OperationExecutionIdentity,
    PersistedOperationExecution,
    RecordExecutionIntent,
    RecordOperationResult,
)

NOW = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000002")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000003")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000004")
EVENT_ID = UUID("00000000-0000-4000-8000-000000000005")
LEASE_TOKEN = UUID("00000000-0000-4000-8000-000000000006")
DIGEST = bytes.fromhex("ab" * 32)


def audit_event(
    event_type: AuditEventType,
    *,
    workspace_id: UUID = WORKSPACE_ID,
    operation_batch_id: UUID | None = BATCH_ID,
    file_operation_id: UUID | None = OPERATION_ID,
) -> AuditAppend:
    return AuditAppend(
        event_id=EVENT_ID,
        workspace_id=workspace_id,
        actor_id=ACTOR_ID,
        actor_type=AuditActorType.SYSTEM,
        correlation_id="correlation-001",
        event_type=event_type,
        subject_kind="file_operation",
        subject_id="item-001",
        occurred_at_utc=NOW,
        operation_batch_id=operation_batch_id,
        file_operation_id=file_operation_id,
    )


def item() -> BatchItemSnapshot:
    return BatchItemSnapshot(
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


def create_batch(
    *,
    preview_sha256: bytes = DIGEST,
    items: tuple[BatchItemSnapshot, ...] | None = None,
    audit_events: tuple[AuditAppend, ...] | None = None,
) -> CreateBatch:
    return CreateBatch(
        operation_batch_id=BATCH_ID,
        workspace_id=WORKSPACE_ID,
        external_batch_id="batch-001",
        idempotency_key="create-batch-001",
        operation=FileOperation.COPY,
        preview_sha256=preview_sha256,
        preview_version=1,
        policy_version="operations.v1",
        correlation_id="correlation-001",
        status=BatchState.READY_FOR_APPROVAL,
        created_by_actor_id=ACTOR_ID,
        created_at_utc=NOW,
        items=(item(),) if items is None else items,
        audit_events=(
            (
                audit_event(
                    AuditEventType.BATCH_CREATED,
                    file_operation_id=None,
                ),
            )
            if audit_events is None
            else audit_events
        ),
    )


def test_accepts_consistent_batch_snapshot() -> None:
    command = create_batch()

    assert command.created_at_utc == NOW
    assert command.items[0].plan_sha256 == DIGEST


@pytest.mark.parametrize("digest", [b"", b"x" * 31, b"x" * 33])
def test_rejects_invalid_sha256_lengths(digest: bytes) -> None:
    with pytest.raises(ValueError, match="32-byte"):
        create_batch(preview_sha256=digest)


def test_rejects_empty_or_oversized_batches() -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        create_batch(items=())
    with pytest.raises(ValueError, match="between 1 and 1000"):
        create_batch(items=(item(),) * 1_001)


def test_rejects_duplicate_item_identity() -> None:
    with pytest.raises(ValueError, match="batch_item_id"):
        create_batch(items=(item(), item()))


def test_rejects_mixed_operation_types() -> None:
    with pytest.raises(ValueError, match="batch operation"):
        create_batch(items=(replace(item(), operation=FileOperation.MOVE),))


def test_rejects_cross_workspace_audit_event() -> None:
    other_workspace = UUID("00000000-0000-4000-8000-000000000099")
    with pytest.raises(ValueError, match="workspace"):
        create_batch(
            audit_events=(
                audit_event(
                    AuditEventType.BATCH_CREATED,
                    workspace_id=other_workspace,
                    file_operation_id=None,
                ),
            )
        )


def test_terminal_item_requires_completion_time() -> None:
    with pytest.raises(ValueError, match="completed_at"):
        replace(item(), state=BatchItemState.BLOCKED)


def test_approved_item_requires_approval_and_source_preconditions() -> None:
    with pytest.raises(ValueError, match="bound preconditions"):
        replace(
            item(),
            state=BatchItemState.APPROVED,
            approval_id=None,
            expected_source_sha256=None,
        )


def test_execution_intent_requires_positive_lease_and_matching_event() -> None:
    event = audit_event(AuditEventType.ITEM_EXECUTION_INTENT_RECORDED)
    command = RecordExecutionIntent(
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_id=OPERATION_ID,
        execution_id="execution-001",
        idempotency_key="execute-item-001",
        executor_actor_id=ACTOR_ID,
        lease_token=LEASE_TOKEN,
        intent_recorded_at_utc=NOW,
        lease_expires_at_utc=NOW + timedelta(minutes=2),
        audit_event=event,
    )

    assert command.lease_expires_at_utc > command.intent_recorded_at_utc

    with pytest.raises(ValueError, match="must follow"):
        replace(command, lease_expires_at_utc=NOW)
    with pytest.raises(ValueError, match="identities"):
        replace(
            command,
            audit_event=audit_event(
                AuditEventType.ITEM_EXECUTION_INTENT_RECORDED,
                file_operation_id=UUID("00000000-0000-4000-8000-000000000099"),
            ),
        )


def test_successful_result_requires_verified_destination_evidence() -> None:
    event = audit_event(AuditEventType.ITEM_EXECUTION_SUCCEEDED)
    command = RecordOperationResult(
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_id=OPERATION_ID,
        execution_id="execution-001",
        idempotency_key="execute-item-001",
        terminal_state=BatchItemState.SUCCEEDED,
        reason=ExecutionReason.SUCCEEDED,
        disposition=ResultDisposition.EXECUTED,
        completed_at_utc=NOW,
        source_exists_after=True,
        destination_exists_after=True,
        actual_source_relative_path="incoming/invoice.pdf",
        actual_destination_relative_path="invoices/2026/invoice.pdf",
        actual_sha256=DIGEST,
        actual_size=42,
        error_category=None,
        audit_event=event,
    )

    assert command.actual_sha256 == DIGEST

    with pytest.raises(ValueError, match="destination evidence"):
        replace(command, destination_exists_after=False)


def test_verification_failure_requires_matching_event_type() -> None:
    with pytest.raises(ValueError, match="matching audit event"):
        RecordOperationResult(
            workspace_id=WORKSPACE_ID,
            operation_batch_id=BATCH_ID,
            file_operation_id=OPERATION_ID,
            execution_id="execution-001",
            idempotency_key="execute-item-001",
            terminal_state=BatchItemState.VERIFICATION_FAILED,
            reason=ExecutionReason.VERIFICATION_FAILED,
            disposition=ResultDisposition.EXECUTED,
            completed_at_utc=NOW,
            source_exists_after=True,
            destination_exists_after=True,
            actual_source_relative_path="incoming/invoice.pdf",
            actual_destination_relative_path="invoices/2026/invoice.pdf",
            actual_sha256=None,
            actual_size=None,
            error_category="verification_failed",
            audit_event=audit_event(AuditEventType.ITEM_EXECUTION_FAILED),
        )


def persisted_success() -> PersistedOperationExecution:
    return PersistedOperationExecution(
        identity=OperationExecutionIdentity(
            workspace_id=WORKSPACE_ID,
            operation_batch_id=BATCH_ID,
            file_operation_id=OPERATION_ID,
        ),
        state=BatchItemState.SUCCEEDED,
        idempotency_key="execute-item-001",
        execution_id="batch-001:item-001",
        approval_id="approval-001",
        lease_expires_at_utc=None,
        intent_recorded_at_utc=NOW,
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(seconds=1),
        result_disposition=ResultDisposition.EXECUTED,
        expected_source_sha256=DIGEST,
        actual_sha256=DIGEST,
        actual_size=42,
        source_exists_after=True,
        destination_exists_after=True,
        safe_error_summary=ExecutionReason.SUCCEEDED.value,
        error_category=None,
    )


def test_accepts_complete_persisted_terminal_execution() -> None:
    execution = persisted_success()

    assert execution.completed_at_utc == NOW + timedelta(seconds=1)
    assert execution.actual_sha256 == DIGEST


def test_executing_persisted_state_requires_complete_claim() -> None:
    with pytest.raises(ValueError, match="claim evidence"):
        replace(
            persisted_success(),
            state=BatchItemState.EXECUTING,
            lease_expires_at_utc=None,
            completed_at_utc=None,
            result_disposition=None,
            actual_sha256=None,
            actual_size=None,
            source_exists_after=None,
            destination_exists_after=None,
            safe_error_summary=None,
        )


def _without_execution_key(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, idempotency_key=None)


def _with_negative_size(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, actual_size=-1)


def _without_actual_digest(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, actual_sha256=None)


def _without_destination(
    execution: PersistedOperationExecution,
) -> PersistedOperationExecution:
    return replace(execution, destination_exists_after=False)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_without_execution_key, "result evidence"),
        (_with_negative_size, "must not be negative"),
        (_without_actual_digest, "destination evidence"),
        (_without_destination, "destination evidence"),
    ],
)
def test_rejects_incomplete_persisted_terminal_evidence(
    mutate: Callable[[PersistedOperationExecution], PersistedOperationExecution],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        mutate(persisted_success())


def test_rejects_invalid_persisted_digest_length() -> None:
    with pytest.raises(ValueError, match="32-byte"):
        replace(persisted_success(), expected_source_sha256=b"short")
