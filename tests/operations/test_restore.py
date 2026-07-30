from datetime import UTC, datetime
from pathlib import Path

import pytest

from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.operations import (
    AppendOnlyAuditTrail,
    AuditActorType,
    AuditEventType,
    ExecutionReason,
    ExecutionStatus,
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    OperationResultRecord,
    RestoreAuditContext,
    RestoreBatchExecutionRequest,
    RestoreBatchItemRequest,
    RestoreBatchPlanningRequest,
    RestoreExecutionReason,
    RestoreExecutionStatus,
    RestoreOperation,
    RestorePlanReason,
    RestorePlanStatus,
    ResultDisposition,
    append_restore_approval_audit_event,
    append_restore_execution_audit_event,
    approve_restore_plan,
    execute_file_operation,
    execute_restore_batch,
    execute_restore_operation,
    plan_file_operation,
    plan_restore_batch,
    plan_restore_operation,
    summarize_restore_batch,
)
from docweave.operations.approval import approve_operation_plan

BASE_TIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def restore_audit_context() -> RestoreAuditContext:
    return RestoreAuditContext(
        workspace_id="workspace-001",
        batch_id="batch-001",
        batch_item_id="item-001",
        actor_id="reviewer-001",
        correlation_id="restore-correlation-001",
        occurred_at_utc=BASE_TIME.replace(minute=4),
    )


def write_file(path: Path, content: bytes = b"%PDF-1.7\ncontent") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def execute_original_operation(
    tmp_path: Path,
    *,
    operation: FileOperation,
    source_relative_path: str = "incoming/invoice.pdf",
    destination_relative_path: str = "organized/invoice.pdf",
) -> tuple[FileOperationPlan, OperationResultRecord]:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "workspace"
    write_file(source_root / source_relative_path)
    destination_root.mkdir()
    plan = plan_file_operation(
        FileOperationRequest(
            operation=operation,
            source_root=source_root,
            source_relative_path=source_relative_path,
            destination_root=destination_root,
            destination_relative_path=destination_relative_path,
        )
    )
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME,
        expires_at_utc=BASE_TIME.replace(hour=13),
    )
    execution = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=BASE_TIME.replace(minute=1),
    )
    result = OperationResultRecord(
        batch_id="batch-001",
        batch_item_id="item-001",
        execution_key="execution-key-001",
        execution_id=execution.execution_id,
        status=execution.status,
        reason=execution.reason,
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=BASE_TIME.replace(minute=1),
        completed_at_utc=BASE_TIME.replace(minute=1),
        approval_id=execution.approval_id,
        source_exists_after=execution.source_exists_after,
        destination_exists_after=execution.destination_exists_after,
        source_digest_before=execution.source_digest_before,
        destination_digest_after=execution.destination_digest_after,
    )
    return plan, result


def test_plans_copy_restore_as_generated_copy_removal(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)

    restore = plan_restore_operation(plan, result)

    assert restore.status is RestorePlanStatus.READY
    assert restore.reason is RestorePlanReason.READY
    assert restore.operation is RestoreOperation.REMOVE_GENERATED_COPY
    assert restore.source_path == plan.destination_path
    assert restore.destination_path is None
    assert restore.expected_digest == result.destination_digest_after


def test_blocks_copy_restore_when_generated_copy_changed(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    assert plan.destination_path is not None
    plan.destination_path.write_bytes(b"%PDF-1.7\nchanged")

    restore = plan_restore_operation(plan, result)

    assert restore.status is RestorePlanStatus.BLOCKED
    assert restore.reason is RestorePlanReason.GENERATED_COPY_CHANGED


def test_plans_move_restore_as_non_overwriting_move_back(tmp_path: Path) -> None:
    plan, result = execute_original_operation(
        tmp_path,
        operation=FileOperation.MOVE,
        source_relative_path="incoming/deep/invoice.pdf",
        destination_relative_path="organized/invoice.pdf",
    )

    restore = plan_restore_operation(plan, result)

    assert restore.status is RestorePlanStatus.READY
    assert restore.operation is RestoreOperation.MOVE_BACK
    assert restore.source_path == plan.destination_path
    assert restore.destination_path == plan.source_path
    assert restore.move_back_plan is not None
    assert restore.move_back_plan.operation is FileOperation.MOVE
    assert restore.destination_relative_path == "incoming/deep/invoice.pdf"


def test_blocks_move_restore_when_original_location_collides(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.MOVE)
    assert plan.source_path is not None
    write_file(plan.source_path, b"%PDF-1.7\nunrelated")

    restore = plan_restore_operation(plan, result)

    assert restore.status is RestorePlanStatus.BLOCKED
    assert restore.reason is RestorePlanReason.ORIGINAL_LOCATION_COLLISION


def test_blocks_move_restore_when_moved_file_changed(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.MOVE)
    assert plan.destination_path is not None
    plan.destination_path.write_bytes(b"%PDF-1.7\nchanged")

    restore = plan_restore_operation(plan, result)

    assert restore.status is RestorePlanStatus.BLOCKED
    assert restore.reason is RestorePlanReason.MOVED_FILE_CHANGED


def test_blocks_restore_for_failed_original_result(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    failed = OperationResultRecord(
        batch_id=result.batch_id,
        batch_item_id=result.batch_item_id,
        execution_key=result.execution_key,
        execution_id=result.execution_id,
        status=ExecutionStatus.BLOCKED,
        reason=ExecutionReason.DESTINATION_COLLISION,
        disposition=result.disposition,
        attempted_at_utc=result.attempted_at_utc,
        completed_at_utc=result.completed_at_utc,
        approval_id=result.approval_id,
        source_exists_after=True,
        destination_exists_after=True,
        source_digest_before=(
            None
            if plan.source_path is None
            else compute_sha256_fingerprint(plan.source_path).hex_digest
        ),
        destination_digest_after=result.destination_digest_after,
    )

    restore = plan_restore_operation(plan, failed)

    assert restore.status is RestorePlanStatus.BLOCKED
    assert restore.reason is RestorePlanReason.ORIGINAL_RESULT_NOT_SUCCEEDED


def test_executes_approved_copy_restore_by_removing_generated_copy(
    tmp_path: Path,
) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(hour=13),
    )

    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )

    assert execution.succeeded is True
    assert execution.status is RestoreExecutionStatus.SUCCEEDED
    assert execution.reason is RestoreExecutionReason.SUCCEEDED
    assert plan.source_path is not None
    assert plan.destination_path is not None
    assert plan.source_path.exists()
    assert not plan.destination_path.exists()


def test_executes_approved_move_restore_without_overwrite(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.MOVE)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(hour=13),
    )

    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )

    assert execution.status is RestoreExecutionStatus.SUCCEEDED
    assert execution.reason is RestoreExecutionReason.SUCCEEDED
    assert plan.source_path is not None
    assert plan.destination_path is not None
    assert plan.source_path.exists()
    assert not plan.destination_path.exists()


def test_blocks_restore_execution_when_approval_expired(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(minute=3),
    )

    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )

    assert execution.status is RestoreExecutionStatus.BLOCKED
    assert execution.reason is RestoreExecutionReason.APPROVAL_EXPIRED
    assert plan.destination_path is not None
    assert plan.destination_path.exists()


def test_blocks_restore_execution_when_plan_changes_after_approval(
    tmp_path: Path,
) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(hour=13),
    )
    assert plan.destination_path is not None
    plan.destination_path.write_bytes(b"%PDF-1.7\nchanged")

    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )

    assert execution.status is RestoreExecutionStatus.BLOCKED
    assert execution.reason is RestoreExecutionReason.RESTORE_PLAN_CHANGED
    assert plan.destination_path.exists()


def test_appends_restore_approval_and_execution_audit_events(
    tmp_path: Path,
) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(hour=13),
    )
    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )
    trail = AppendOnlyAuditTrail()
    context = restore_audit_context()

    approval_event = append_restore_approval_audit_event(
        trail,
        restore,
        approval,
        context,
    )
    execution_event = append_restore_execution_audit_event(
        trail,
        restore,
        execution,
        context,
    )

    assert trail.events == (approval_event, execution_event)
    assert approval_event.event_type is AuditEventType.RESTORE_APPROVED
    assert approval_event.actor_type is AuditActorType.HUMAN
    assert approval_event.plan_fingerprint == approval.restore_fingerprint
    assert execution_event.event_type is AuditEventType.RESTORE_EXECUTION_SUCCEEDED
    assert execution_event.actor_type is AuditActorType.SYSTEM
    assert execution_event.idempotency_key == "restore-001"
    assert execution_event.error_category is None


def test_restore_execution_audit_records_blocked_reason(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    restore = plan_restore_operation(plan, result)
    approval = approve_restore_plan(
        restore,
        approval_id="restore-approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=BASE_TIME.replace(minute=2),
        expires_at_utc=BASE_TIME.replace(minute=3),
    )
    execution = execute_restore_operation(
        restore,
        approval,
        restore_id="restore-001",
        now_utc=BASE_TIME.replace(minute=3),
    )
    trail = AppendOnlyAuditTrail()

    event = append_restore_execution_audit_event(
        trail,
        restore,
        execution,
        restore_audit_context(),
    )

    assert event.event_type is AuditEventType.RESTORE_EXECUTION_BLOCKED
    assert event.error_category == RestoreExecutionReason.APPROVAL_EXPIRED.value
    assert event.reason == RestoreExecutionReason.APPROVAL_EXPIRED.value


def test_executes_restore_batch_with_per_item_audit_events(tmp_path: Path) -> None:
    copy_plan, copy_result = execute_original_operation(
        tmp_path / "copy",
        operation=FileOperation.COPY,
    )
    move_plan, move_result = execute_original_operation(
        tmp_path / "move",
        operation=FileOperation.MOVE,
    )
    trail = AppendOnlyAuditTrail()
    batch = plan_restore_batch(
        RestoreBatchPlanningRequest(
            batch_id="restore-batch-001",
            workspace_id="workspace-001",
            planned_by_user_id="reviewer-001",
            planned_at_utc=BASE_TIME.replace(minute=2),
            correlation_id="restore-batch-correlation-001",
            item_requests=(
                RestoreBatchItemRequest("copy-item", copy_plan, copy_result),
                RestoreBatchItemRequest("move-item", move_plan, move_result),
            ),
        )
    )

    report = execute_restore_batch(
        batch,
        request=RestoreBatchExecutionRequest(
            approved_by_user_id="reviewer-001",
            approved_at_utc=BASE_TIME.replace(minute=3),
            expires_at_utc=BASE_TIME.replace(hour=13),
            executed_by_actor_id="local-worker-001",
            now_utc=BASE_TIME.replace(minute=4),
        ),
        audit_trail=trail,
    )

    assert report.summary.total == 2
    assert report.summary.ready == 2
    assert report.summary.succeeded == 2
    assert report.summary.blocked == 0
    assert all(
        item.result is not None and item.result.succeeded for item in report.items
    )
    assert len(trail.events) == 4
    assert [event.event_type for event in trail.events] == [
        AuditEventType.RESTORE_APPROVED,
        AuditEventType.RESTORE_APPROVED,
        AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
        AuditEventType.RESTORE_EXECUTION_SUCCEEDED,
    ]
    assert trail.events[2].actor_id == "local-worker-001"
    assert copy_plan.source_path is not None
    assert copy_plan.destination_path is not None
    assert move_plan.source_path is not None
    assert move_plan.destination_path is not None
    assert copy_plan.source_path.exists()
    assert not copy_plan.destination_path.exists()
    assert move_plan.source_path.exists()
    assert not move_plan.destination_path.exists()


def test_restore_batch_keeps_blocked_items_visible_and_executes_ready_items(
    tmp_path: Path,
) -> None:
    ready_plan, ready_result = execute_original_operation(
        tmp_path / "ready",
        operation=FileOperation.COPY,
    )
    blocked_plan, blocked_result = execute_original_operation(
        tmp_path / "blocked",
        operation=FileOperation.COPY,
    )
    assert blocked_plan.destination_path is not None
    blocked_plan.destination_path.write_bytes(b"%PDF-1.7\nchanged")
    batch = plan_restore_batch(
        RestoreBatchPlanningRequest(
            batch_id="restore-batch-001",
            workspace_id="workspace-001",
            planned_by_user_id="reviewer-001",
            planned_at_utc=BASE_TIME.replace(minute=2),
            correlation_id="restore-batch-correlation-001",
            item_requests=(
                RestoreBatchItemRequest("ready-item", ready_plan, ready_result),
                RestoreBatchItemRequest("blocked-item", blocked_plan, blocked_result),
            ),
        )
    )
    trail = AppendOnlyAuditTrail()

    report = execute_restore_batch(
        batch,
        request=RestoreBatchExecutionRequest(
            approved_by_user_id="reviewer-001",
            approved_at_utc=BASE_TIME.replace(minute=3),
            expires_at_utc=BASE_TIME.replace(hour=13),
            executed_by_actor_id="local-worker-001",
            now_utc=BASE_TIME.replace(minute=4),
        ),
        audit_trail=trail,
    )

    assert report.summary.total == 2
    assert report.summary.ready == 1
    assert report.summary.blocked == 1
    assert report.summary.succeeded == 1
    assert report.items[0].result is not None
    assert report.items[0].result.succeeded is True
    assert report.items[1].approval is None
    assert report.items[1].result is None
    assert report.items[1].plan.reason is RestorePlanReason.GENERATED_COPY_CHANGED
    assert len(trail.events) == 2


def test_restore_batch_rejects_empty_and_oversized_requests(
    tmp_path: Path,
) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)

    with pytest.raises(
        ValueError,
        match="restore batch must contain at least one item",
    ):
        plan_restore_batch(
            RestoreBatchPlanningRequest(
                batch_id="restore-batch-001",
                workspace_id="workspace-001",
                planned_by_user_id="reviewer-001",
                planned_at_utc=BASE_TIME,
                correlation_id="restore-batch-correlation-001",
                item_requests=(),
            )
        )

    oversized = tuple(
        RestoreBatchItemRequest(f"item-{index}", plan, result) for index in range(1_001)
    )
    with pytest.raises(
        ValueError,
        match="restore batch cannot contain more than 1000 items",
    ):
        plan_restore_batch(
            RestoreBatchPlanningRequest(
                batch_id="restore-batch-001",
                workspace_id="workspace-001",
                planned_by_user_id="reviewer-001",
                planned_at_utc=BASE_TIME,
                correlation_id="restore-batch-correlation-001",
                item_requests=oversized,
            )
        )


def test_summarizes_restore_batch_before_execution(tmp_path: Path) -> None:
    plan, result = execute_original_operation(tmp_path, operation=FileOperation.COPY)
    batch = plan_restore_batch(
        RestoreBatchPlanningRequest(
            batch_id="restore-batch-001",
            workspace_id="workspace-001",
            planned_by_user_id="reviewer-001",
            planned_at_utc=BASE_TIME,
            correlation_id="restore-batch-correlation-001",
            item_requests=(RestoreBatchItemRequest("item-001", plan, result),),
        )
    )

    summary = summarize_restore_batch(batch)

    assert summary.total == 1
    assert summary.ready == 1
    assert summary.blocked == 0
    assert summary.succeeded == 0
