from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from docweave.core.fingerprints import (
    ContentFingerprint,
    compute_sha256_fingerprint,
)
from docweave.operations import (
    MAX_OPERATION_BATCH_ITEMS,
    AppendOnlyAuditTrail,
    AuditEventType,
    BatchApprovalRequest,
    BatchCreationRequest,
    BatchExecutionRequest,
    BatchItemRequest,
    BatchItemState,
    BatchState,
    ExecutionReason,
    ExecutionResult,
    ExecutionStatus,
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    InMemoryExecutionLedger,
    OperationApproval,
    OperationBatch,
    ResultDisposition,
    approve_operation_batch,
    create_operation_batch,
    derive_batch_state,
    execute_operation_batch,
    operation_batch_fingerprint,
    operation_execution_key,
    plan_file_operation,
    summarize_batch,
)

BASE_TIME = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


def write_file(path: Path, content: bytes = b"%PDF-1.7\ncontent") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def operation_plan(
    tmp_path: Path,
    *,
    item_name: str,
    operation: FileOperation = FileOperation.COPY,
    destination_name: str | None = None,
) -> FileOperationPlan:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / item_name)
    destination_root.mkdir(exist_ok=True)
    return plan_file_operation(
        FileOperationRequest(
            operation=operation,
            source_root=source_root,
            source_relative_path=item_name,
            destination_root=destination_root,
            destination_relative_path=destination_name or f"ready/{item_name}",
        )
    )


def creation_request(
    item_requests: tuple[BatchItemRequest, ...],
) -> BatchCreationRequest:
    return BatchCreationRequest(
        batch_id="batch-001",
        workspace_id="workspace-001",
        created_by_user_id="creator-001",
        created_at_utc=BASE_TIME,
        idempotency_key="batch-request-001",
        correlation_id="correlation-001",
        policy_version="local-policy.v1",
        item_requests=item_requests,
    )


def create_batch(
    item_requests: tuple[BatchItemRequest, ...],
    trail: AppendOnlyAuditTrail,
) -> OperationBatch:
    return create_operation_batch(
        creation_request(item_requests),
        audit_trail=trail,
    )


def approve_batch(
    batch: OperationBatch,
    trail: AppendOnlyAuditTrail,
    *,
    expires_after: timedelta = timedelta(minutes=15),
) -> OperationBatch:
    return approve_operation_batch(
        batch,
        BatchApprovalRequest(
            approval_id="approval-001",
            approved_by_user_id="reviewer-001",
            approved_at_utc=BASE_TIME + timedelta(minutes=1),
            expires_at_utc=BASE_TIME + timedelta(minutes=1) + expires_after,
        ),
        audit_trail=trail,
    )


def test_creates_mixed_ready_and_blocked_preview_with_source_identity(
    tmp_path: Path,
) -> None:
    trail = AppendOnlyAuditTrail()
    ready = operation_plan(tmp_path, item_name="ready.pdf")
    blocked = operation_plan(
        tmp_path,
        item_name="blocked.pdf",
        destination_name="blocked.pdf",
    )
    assert blocked.destination_path is not None
    write_file(blocked.destination_path, b"collision")
    blocked = plan_file_operation(blocked.request)

    batch = create_batch(
        (
            BatchItemRequest("item-ready", ready),
            BatchItemRequest("item-blocked", blocked),
        ),
        trail,
    )

    assert batch.state is BatchState.READY_FOR_APPROVAL
    assert batch.items[0].state is BatchItemState.PLANNED
    assert batch.items[0].expected_source_digest is not None
    assert batch.items[0].expected_source_byte_size == len(b"%PDF-1.7\ncontent")
    assert batch.items[1].state is BatchItemState.BLOCKED
    assert summarize_batch(batch).blocked == 1
    assert [event.event_type for event in trail.events] == [
        AuditEventType.BATCH_CREATED,
        AuditEventType.ITEM_PLANNED,
        AuditEventType.ITEM_BLOCKED,
    ]


def test_rejects_empty_and_oversized_batches(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    with pytest.raises(ValueError, match="at least one"):
        create_batch((), trail)

    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    oversized = tuple(
        BatchItemRequest(f"item-{index}", plan)
        for index in range(MAX_OPERATION_BATCH_ITEMS + 1)
    )
    with pytest.raises(ValueError, match="at most 1000"):
        create_batch(oversized, trail)


def test_unreadable_source_fingerprint_blocks_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = operation_plan(tmp_path, item_name="invoice.pdf")

    def fail_fingerprint(_path: Path) -> ContentFingerprint:
        raise OSError

    monkeypatch.setattr(
        "docweave.operations.batch.compute_sha256_fingerprint",
        fail_fingerprint,
    )
    batch = create_batch(
        (BatchItemRequest("item-001", plan),),
        AppendOnlyAuditTrail(),
    )

    assert batch.items[0].state is BatchItemState.BLOCKED
    assert batch.items[0].block_reason == "source_fingerprint_unavailable"


def test_rejects_blank_batch_command_identifier(tmp_path: Path) -> None:
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    request = creation_request((BatchItemRequest("item-001", plan),))

    with pytest.raises(ValueError, match="batch_id must not be empty"):
        create_operation_batch(
            replace(request, batch_id=" "),
            audit_trail=AppendOnlyAuditTrail(),
        )


def test_rejects_blank_duplicate_and_mixed_operation_items(tmp_path: Path) -> None:
    copy_plan = operation_plan(tmp_path, item_name="copy.pdf")
    move_plan = operation_plan(
        tmp_path,
        item_name="move.pdf",
        operation=FileOperation.MOVE,
    )

    with pytest.raises(ValueError, match="item_id must not be empty"):
        create_batch(
            (BatchItemRequest(" ", copy_plan),),
            AppendOnlyAuditTrail(),
        )
    with pytest.raises(ValueError, match="must be unique"):
        create_batch(
            (
                BatchItemRequest("item-001", copy_plan),
                BatchItemRequest("item-001", copy_plan),
            ),
            AppendOnlyAuditTrail(),
        )
    with pytest.raises(ValueError, match="one operation type"):
        create_batch(
            (
                BatchItemRequest("item-copy", copy_plan),
                BatchItemRequest("item-move", move_plan),
            ),
            AppendOnlyAuditTrail(),
        )


def test_approval_binds_exact_item_plans_and_source_identities(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = create_batch((BatchItemRequest("item-001", plan),), trail)
    fingerprint = operation_batch_fingerprint(batch)

    approved = approve_batch(batch, trail)

    assert approved.state is BatchState.APPROVED
    assert approved.approval is not None
    assert approved.approval.batch_fingerprint == fingerprint
    assert approved.items[0].approval is not None
    assert approved.items[0].state is BatchItemState.APPROVED
    assert AuditEventType.ITEM_APPROVED in {event.event_type for event in trail.events}
    assert operation_execution_key(approved, approved.items[0]) == (
        operation_execution_key(approved, approved.items[0])
    )


def test_approval_and_execution_preserve_previously_blocked_item(
    tmp_path: Path,
) -> None:
    trail = AppendOnlyAuditTrail()
    ready = operation_plan(tmp_path, item_name="ready.pdf")
    blocked = operation_plan(
        tmp_path,
        item_name="blocked.pdf",
        destination_name="blocked.pdf",
    )
    assert blocked.destination_path is not None
    write_file(blocked.destination_path, b"collision")
    blocked = plan_file_operation(blocked.request)
    batch = approve_batch(
        create_batch(
            (
                BatchItemRequest("item-ready", ready),
                BatchItemRequest("item-blocked", blocked),
            ),
            trail,
        ),
        trail,
    )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
    )

    assert report.summary.succeeded == 1
    assert report.summary.blocked == 1
    assert report.batch.items[1].latest_result is None


@pytest.mark.parametrize(
    ("approval_request", "message"),
    [
        (
            BatchApprovalRequest(
                " ",
                "reviewer-001",
                BASE_TIME,
                BASE_TIME + timedelta(minutes=1),
            ),
            "approval_id must not be empty",
        ),
        (
            BatchApprovalRequest(
                "approval-001",
                " ",
                BASE_TIME,
                BASE_TIME + timedelta(minutes=1),
            ),
            "approved_by_user_id must not be empty",
        ),
        (
            BatchApprovalRequest(
                "approval-001",
                "reviewer-001",
                BASE_TIME,
                BASE_TIME,
            ),
            "expiry must follow",
        ),
    ],
)
def test_rejects_invalid_batch_approval(
    tmp_path: Path,
    approval_request: BatchApprovalRequest,
    message: str,
) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = create_batch((BatchItemRequest("item-001", plan),), trail)

    with pytest.raises(ValueError, match=message):
        approve_operation_batch(batch, approval_request, audit_trail=trail)


def test_cannot_approve_batch_without_executable_item(tmp_path: Path) -> None:
    plan = operation_plan(
        tmp_path,
        item_name="invoice.pdf",
        destination_name="invoice.pdf",
    )
    assert plan.destination_path is not None
    write_file(plan.destination_path, b"collision")
    blocked_plan = plan_file_operation(plan.request)
    trail = AppendOnlyAuditTrail()
    batch = create_batch(
        (BatchItemRequest("item-001", blocked_plan),),
        trail,
    )

    assert batch.state is BatchState.COMPLETED_WITH_FAILURES
    with pytest.raises(ValueError, match="ready for approval"):
        approve_batch(batch, trail)


def test_stale_source_after_approval_blocks_only_that_item(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    first = operation_plan(tmp_path, item_name="first.pdf")
    second = operation_plan(tmp_path, item_name="second.pdf")
    batch = approve_batch(
        create_batch(
            (
                BatchItemRequest("item-first", first),
                BatchItemRequest("item-second", second),
            ),
            trail,
        ),
        trail,
    )
    assert second.source_path is not None
    write_file(second.source_path, b"changed-after-approval")

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
    )

    assert report.batch.state is BatchState.COMPLETED_WITH_FAILURES
    assert report.summary.succeeded == 1
    assert report.summary.blocked == 1
    assert report.results[1].reason is ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION
    assert report.results[1].disposition is ResultDisposition.PRECONDITION_BLOCKED
    assert report.results[1].error_class == "source_identity_changed"


def test_missing_source_after_approval_is_a_blocked_result(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    assert plan.source_path is not None
    plan.source_path.unlink()

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
    )

    assert report.results[0].status is ExecutionStatus.BLOCKED
    assert report.results[0].error_class == "FileNotFoundError"


def test_destination_collision_isolated_and_batch_reports_partial_outcome(
    tmp_path: Path,
) -> None:
    trail = AppendOnlyAuditTrail()
    first = operation_plan(tmp_path, item_name="first.pdf")
    second = operation_plan(tmp_path, item_name="second.pdf")
    batch = approve_batch(
        create_batch(
            (
                BatchItemRequest("item-first", first),
                BatchItemRequest("item-second", second),
            ),
            trail,
        ),
        trail,
    )
    assert second.destination_path is not None
    write_file(second.destination_path, b"late-collision")

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
    )

    assert report.summary.succeeded == 1
    assert report.summary.blocked == 1
    assert report.results[1].reason is ExecutionReason.DESTINATION_COLLISION
    assert report.batch.state is BatchState.COMPLETED_WITH_FAILURES


def test_duplicate_execution_returns_prior_result_without_second_effect(
    tmp_path: Path,
) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    request = BatchExecutionRequest(
        "local-executor",
        BASE_TIME + timedelta(minutes=2),
    )

    first = execute_operation_batch(
        batch,
        request,
        audit_trail=trail,
        execution_ledger=ledger,
    )
    second = execute_operation_batch(
        batch,
        replace(request, now_utc=BASE_TIME + timedelta(minutes=3)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert first.results[0].disposition is ResultDisposition.EXECUTED
    assert second.results[0].disposition is ResultDisposition.IDEMPOTENT_REPLAY
    assert second.replayed_item_count == 1
    assert second.summary.succeeded == 1
    assert AuditEventType.ITEM_EXECUTION_REPLAYED in {
        event.event_type for event in trail.events
    }


def test_interrupted_execution_reconciles_verified_copy(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    item = batch.items[0]
    key = operation_execution_key(batch, item)
    ledger.record_intent(key)
    assert plan.source_path is not None
    assert plan.destination_path is not None
    plan.destination_path.parent.mkdir(parents=True)
    plan.destination_path.write_bytes(plan.source_path.read_bytes())

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("reconciler", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert report.results[0].status is ExecutionStatus.SUCCEEDED
    assert report.results[0].disposition is ResultDisposition.RECONCILED
    assert report.batch.state is BatchState.COMPLETED


def test_interrupted_no_effect_reconciles_then_retries_safely(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    ledger.record_intent(operation_execution_key(batch, batch.items[0]))

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("reconciler", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert report.results[0].status is ExecutionStatus.SUCCEEDED
    assert report.results[0].disposition is ResultDisposition.EXECUTED
    reconciliations = [
        event
        for event in trail.events
        if event.event_type is AuditEventType.ITEM_EXECUTION_RECONCILED
    ]
    assert reconciliations[-1].reason == "no_effect_observed_safe_to_retry"


def test_interrupted_ambiguous_state_requires_reconciliation(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    ledger.record_intent(operation_execution_key(batch, batch.items[0]))
    assert plan.destination_path is not None
    write_file(plan.destination_path, b"unexpected-content")

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("reconciler", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert report.results[0].status is ExecutionStatus.VERIFICATION_FAILED
    assert report.results[0].error_class == "reconciliation_required"
    assert report.summary.verification_failed == 1
    assert report.batch.state is BatchState.COMPLETED_WITH_FAILURES


def test_interrupted_changed_source_requires_reconciliation(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    ledger.record_intent(operation_execution_key(batch, batch.items[0]))
    assert plan.source_path is not None
    write_file(plan.source_path, b"changed-during-interruption")

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("reconciler", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert report.results[0].status is ExecutionStatus.VERIFICATION_FAILED
    reconciled = [
        event
        for event in trail.events
        if event.event_type is AuditEventType.ITEM_EXECUTION_RECONCILED
    ]
    assert reconciled[-1].reason == ("source_identity_changed_during_reconciliation")


def test_unreadable_reconciliation_destination_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trail = AppendOnlyAuditTrail()
    ledger = InMemoryExecutionLedger()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )
    ledger.record_intent(operation_execution_key(batch, batch.items[0]))
    assert plan.destination_path is not None
    write_file(plan.destination_path)

    def fail_destination_fingerprint(path: Path) -> ContentFingerprint:
        if path == plan.destination_path:
            raise OSError
        return compute_sha256_fingerprint(path)

    monkeypatch.setattr(
        "docweave.operations.batch.compute_sha256_fingerprint",
        fail_destination_fingerprint,
    )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("reconciler", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=ledger,
    )

    assert report.results[0].status is ExecutionStatus.VERIFICATION_FAILED
    assert report.results[0].destination_digest_after is None


@pytest.mark.parametrize(
    ("status", "reason", "expected_state", "event_type"),
    [
        (
            ExecutionStatus.FAILED,
            ExecutionReason.FILE_OPERATION_FAILED,
            BatchItemState.FAILED,
            AuditEventType.ITEM_EXECUTION_FAILED,
        ),
        (
            ExecutionStatus.VERIFICATION_FAILED,
            ExecutionReason.VERIFICATION_FAILED,
            BatchItemState.VERIFICATION_FAILED,
            AuditEventType.ITEM_VERIFICATION_FAILED,
        ),
    ],
)
def test_maps_executor_failure_outcomes_without_false_success(
    tmp_path: Path,
    status: ExecutionStatus,
    reason: ExecutionReason,
    expected_state: BatchItemState,
    event_type: AuditEventType,
) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
    )

    def controlled_executor(
        plan: FileOperationPlan,
        approval: OperationApproval,
        *,
        execution_id: str,
        now_utc: datetime,
    ) -> ExecutionResult:
        del approval, now_utc, plan
        return ExecutionResult(
            execution_id=execution_id,
            status=status,
            reason=reason,
            plan_fingerprint="controlled",
            approval_id="approval-001",
            source_exists_after=True,
            destination_exists_after=False,
            error="ControlledFailure",
        )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=2)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
        operation_executor=controlled_executor,
    )

    assert report.batch.items[0].state is expected_state
    assert report.batch.state is BatchState.COMPLETED_WITH_FAILURES
    assert event_type in {event.event_type for event in trail.events}


def test_expired_approval_blocks_execution(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = approve_batch(
        create_batch((BatchItemRequest("item-001", plan),), trail),
        trail,
        expires_after=timedelta(minutes=1),
    )

    report = execute_operation_batch(
        batch,
        BatchExecutionRequest("local-executor", BASE_TIME + timedelta(minutes=3)),
        audit_trail=trail,
        execution_ledger=InMemoryExecutionLedger(),
    )

    assert report.results[0].status is ExecutionStatus.BLOCKED
    assert report.results[0].error_class == "approval_expired"


def test_rejects_unapproved_or_tampered_batch_execution(tmp_path: Path) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = create_batch((BatchItemRequest("item-001", plan),), trail)
    execution_request = BatchExecutionRequest(
        "local-executor",
        BASE_TIME + timedelta(minutes=2),
    )

    with pytest.raises(ValueError, match="current approval"):
        execute_operation_batch(
            batch,
            execution_request,
            audit_trail=trail,
            execution_ledger=InMemoryExecutionLedger(),
        )
    with pytest.raises(ValueError, match="executed_by_actor_id must not be empty"):
        execute_operation_batch(
            replace(batch, state=BatchState.APPROVED),
            BatchExecutionRequest(" ", BASE_TIME + timedelta(minutes=2)),
            audit_trail=trail,
            execution_ledger=InMemoryExecutionLedger(),
        )

    approved = approve_batch(batch, trail)
    tampered_item = replace(approved.items[0], expected_source_digest="tampered")
    tampered = replace(approved, items=(tampered_item,))
    with pytest.raises(ValueError, match="does not match"):
        execute_operation_batch(
            tampered,
            execution_request,
            audit_trail=trail,
            execution_ledger=InMemoryExecutionLedger(),
        )


def test_batch_summary_and_derived_states_cover_terminal_variants(
    tmp_path: Path,
) -> None:
    trail = AppendOnlyAuditTrail()
    plan = operation_plan(tmp_path, item_name="invoice.pdf")
    batch = create_batch((BatchItemRequest("item-001", plan),), trail)
    item = batch.items[0]

    assert derive_batch_state(()) is BatchState.DRAFT
    assert derive_batch_state((replace(item, state=BatchItemState.EXECUTING),)) is (
        BatchState.EXECUTING
    )
    skipped = replace(item, state=BatchItemState.SKIPPED)
    completed = replace(batch, items=(skipped,), state=BatchState.COMPLETED)
    summary = summarize_batch(completed)

    assert summary.total == 1
    assert summary.skipped == 1
    assert summary.planned == 0
