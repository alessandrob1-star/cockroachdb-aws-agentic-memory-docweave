from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from docweave.operations import (
    AppendOnlyAuditTrail,
    AuditActorType,
    AuditEvent,
    AuditEventType,
    BatchApprovalRequest,
    BatchCreationRequest,
    BatchItemRequest,
    BatchItemState,
    ExecutionReason,
    ExecutionStatus,
    FileOperation,
    FileOperationRequest,
    OperationBatch,
    OperationResultRecord,
    ResultDisposition,
    approve_operation_batch,
    create_operation_batch,
    operation_plan_fingerprint,
    plan_file_operation,
)
from docweave.persistence import (
    ExecutionIntentMapping,
    OperationResultMapping,
    PersistenceIdentityMap,
    map_audit_event,
    map_create_batch,
    map_execution_intent,
    map_operation_result,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
WORKSPACE_EXTERNAL_ID = str(UUID("00000000-0000-4000-8000-000000000001"))
BATCH_EXTERNAL_ID = str(UUID("00000000-0000-4000-8000-000000000002"))
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000011")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000012")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000013")
CREATOR_ID = UUID("00000000-0000-4000-8000-000000000014")
EXECUTOR_ID = UUID("00000000-0000-4000-8000-000000000015")
LEASE_TOKEN = UUID("00000000-0000-4000-8000-000000000016")


def local_batch(tmp_path: Path) -> tuple[OperationBatch, AppendOnlyAuditTrail]:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    (source_root / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoices/2026/invoice.pdf",
        )
    )
    trail = AppendOnlyAuditTrail()
    batch = create_operation_batch(
        BatchCreationRequest(
            batch_id=BATCH_EXTERNAL_ID,
            workspace_id=WORKSPACE_EXTERNAL_ID,
            created_by_user_id="creator",
            created_at_utc=NOW,
            idempotency_key="create-batch-001",
            correlation_id="correlation-001",
            policy_version="operations.v1",
            item_requests=(BatchItemRequest("item-001", plan),),
        ),
        audit_trail=trail,
    )
    return batch, trail


def identities() -> PersistenceIdentityMap:
    return PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id=BATCH_EXTERNAL_ID,
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"item-001": OPERATION_ID},
    )


def actor_identity(external_id: str) -> UUID:
    if external_id == "creator":
        return CREATOR_ID
    if external_id in {"reviewer", "executor", "local-core", "local-worker"}:
        return EXECUTOR_ID
    raise ValueError("actor is not registered")


def approve(
    batch: OperationBatch,
    trail: AppendOnlyAuditTrail,
) -> OperationBatch:
    return approve_operation_batch(
        batch,
        BatchApprovalRequest(
            approval_id="approval-001",
            approved_by_user_id="reviewer",
            approved_at_utc=NOW + timedelta(seconds=1),
            expires_at_utc=NOW + timedelta(minutes=10),
        ),
        audit_trail=trail,
    )


def item_event(
    batch: OperationBatch,
    *,
    event_type: AuditEventType,
    actor_id: str = "executor",
) -> AuditEvent:
    item = batch.items[0]
    return AuditEvent(
        event_id=str(uuid4()),
        workspace_id=batch.workspace_id,
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        event_type=event_type,
        actor_type=AuditActorType.SYSTEM,
        actor_id=actor_id,
        occurred_at_utc=NOW + timedelta(seconds=2),
        correlation_id=batch.correlation_id,
        idempotency_key="execute-item-001",
        previous_state=BatchItemState.APPROVED.value,
        new_state=(
            BatchItemState.EXECUTING.value
            if event_type is AuditEventType.ITEM_EXECUTION_INTENT_RECORDED
            else BatchItemState.SUCCEEDED.value
        ),
        reason="test_transition",
        plan_fingerprint=operation_plan_fingerprint(item.plan),
        approval_id="approval-001",
        source_relative_path=item.plan.source_relative_path,
        destination_relative_path=item.plan.destination_relative_path,
    )


def test_maps_initial_batch_without_persisting_absolute_roots(
    tmp_path: Path,
) -> None:
    batch, trail = local_batch(tmp_path)

    command = map_create_batch(
        batch,
        trail.events,
        identities=identities(),
        resolve_root_reference=lambda root: f"root-{root.name}",
        resolve_actor_identity=actor_identity,
    )

    assert command.workspace_id == WORKSPACE_ID
    assert command.operation_batch_id == BATCH_ID
    assert command.created_by_actor_id == CREATOR_ID
    assert command.items[0].file_operation_id == OPERATION_ID
    assert command.items[0].source_root_reference == "root-source"
    assert command.items[0].destination_root_reference == "root-organized"
    assert str(tmp_path) not in command.items[0].source_root_reference
    assert len(command.preview_sha256) == 32
    assert len(command.audit_events) == len(trail.events)


def test_rejects_root_resolver_that_returns_absolute_path(tmp_path: Path) -> None:
    batch, trail = local_batch(tmp_path)

    with pytest.raises(ValueError, match="opaque"):
        map_create_batch(
            batch,
            trail.events,
            identities=identities(),
            resolve_root_reference=str,
            resolve_actor_identity=actor_identity,
        )


def test_maps_approved_execution_intent_to_database_identities(
    tmp_path: Path,
) -> None:
    batch, trail = local_batch(tmp_path)
    approved = approve(batch, trail)
    event = item_event(
        approved,
        event_type=AuditEventType.ITEM_EXECUTION_INTENT_RECORDED,
    )
    item = approved.items[0]

    command = map_execution_intent(
        approved,
        item,
        event,
        mapping=ExecutionIntentMapping(
            identities=identities(),
            executor_actor_id=EXECUTOR_ID,
            lease_token=LEASE_TOKEN,
            lease_expires_at_utc=NOW + timedelta(minutes=2),
        ),
    )

    assert command.file_operation_id == OPERATION_ID
    assert command.executor_actor_id == EXECUTOR_ID
    assert command.audit_event.actor_id == EXECUTOR_ID
    assert len(command.idempotency_key) == 64


def test_maps_observed_result_paths_digest_and_size(tmp_path: Path) -> None:
    batch, trail = local_batch(tmp_path)
    approved = approve(batch, trail)
    item = approved.items[0]
    event = item_event(
        approved,
        event_type=AuditEventType.ITEM_EXECUTION_SUCCEEDED,
    )
    result = OperationResultRecord(
        batch_id=BATCH_EXTERNAL_ID,
        batch_item_id="item-001",
        execution_key="ab" * 32,
        execution_id=f"{BATCH_EXTERNAL_ID}:item-001",
        status=ExecutionStatus.SUCCEEDED,
        reason=ExecutionReason.SUCCEEDED,
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=NOW + timedelta(seconds=2),
        completed_at_utc=NOW + timedelta(seconds=3),
        approval_id="approval-001",
        source_exists_after=True,
        destination_exists_after=True,
        destination_digest_after=item.expected_source_digest,
    )

    command = map_operation_result(
        approved,
        item,
        result,
        event,
        mapping=OperationResultMapping(
            identities=identities(),
            event_actor_id=EXECUTOR_ID,
            actual_size=item.expected_source_byte_size,
        ),
    )

    assert command.actual_source_relative_path == "invoice.pdf"
    assert command.actual_destination_relative_path == "invoices/2026/invoice.pdf"
    assert item.expected_source_digest is not None
    assert command.actual_sha256 == bytes.fromhex(item.expected_source_digest)
    assert command.actual_size == item.expected_source_byte_size


def test_maps_restore_execution_audit_event_to_database_identities() -> None:
    event = AuditEvent(
        event_id=str(uuid4()),
        workspace_id=WORKSPACE_EXTERNAL_ID,
        batch_id=BATCH_EXTERNAL_ID,
        batch_item_id="item-001",
        event_type=AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
        actor_type=AuditActorType.SYSTEM,
        actor_id="local-worker",
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

    command = map_audit_event(
        event,
        identities=identities(),
        resolve_actor_identity=actor_identity,
    )

    assert command.workspace_id == WORKSPACE_ID
    assert command.operation_batch_id == BATCH_ID
    assert command.file_operation_id == OPERATION_ID
    assert command.actor_id == EXECUTOR_ID
    assert command.event_type is AuditEventType.RESTORE_EXECUTION_SUCCEEDED
    assert command.subject_kind == "file_operation"
    assert command.subject_id == "item-001"
    assert command.plan_sha256 == bytes.fromhex("cd" * 32)
    assert command.idempotency_key == "restore-batch-001:item-001:restore"
    assert command.approval_id == "restore-approval-001"
    assert command.source_relative_path == "organized/invoice.pdf"
    assert command.destination_relative_path == "incoming/invoice.pdf"


def test_requires_exact_item_identity_map(tmp_path: Path) -> None:
    batch, trail = local_batch(tmp_path)
    mismatched = PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id=BATCH_EXTERNAL_ID,
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"different-item": OPERATION_ID},
    )

    with pytest.raises(ValueError, match="exactly match"):
        map_create_batch(
            batch,
            trail.events,
            identities=mismatched,
            resolve_root_reference=lambda root: f"root-{root.name}",
            resolve_actor_identity=actor_identity,
        )
