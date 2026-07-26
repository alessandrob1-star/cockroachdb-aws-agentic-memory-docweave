"""Safe local operation batches with explicit audit and idempotency semantics."""

import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.operations.approval import (
    OperationApproval,
    approve_operation_plan,
    operation_plan_fingerprint,
)
from docweave.operations.audit import (
    AppendOnlyAuditTrail,
    AuditActorType,
    AuditEvent,
    AuditEventType,
    normalize_utc,
)
from docweave.operations.execution import (
    ExecutionReason,
    ExecutionResult,
    ExecutionStatus,
    execute_file_operation,
)
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationStatus,
)
from docweave.operations.results import (
    InMemoryExecutionLedger,
    OperationResultRecord,
    ResultDisposition,
)

MAX_OPERATION_BATCH_ITEMS = 1_000


class BatchItemState(StrEnum):
    """Lifecycle states for one local operation batch item."""

    PLANNED = "planned"
    BLOCKED = "blocked"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VERIFICATION_FAILED = "verification_failed"
    SKIPPED = "skipped"


class BatchState(StrEnum):
    """Aggregate local operation batch states."""

    DRAFT = "draft"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class BatchItemRequest:
    """One planned operation selected for a local batch preview."""

    item_id: str
    plan: FileOperationPlan


@dataclass(frozen=True, slots=True)
class BatchCreationRequest:
    """Validated command data for one batch preview."""

    batch_id: str
    workspace_id: str
    created_by_user_id: str
    created_at_utc: datetime
    idempotency_key: str
    correlation_id: str
    policy_version: str
    item_requests: tuple[BatchItemRequest, ...]


@dataclass(frozen=True, slots=True)
class BatchApprovalRequest:
    """Human decision data used to approve an exact batch preview."""

    approval_id: str
    approved_by_user_id: str
    approved_at_utc: datetime
    expires_at_utc: datetime


@dataclass(frozen=True, slots=True)
class BatchExecutionRequest:
    """System execution command data for an approved batch."""

    executed_by_actor_id: str
    now_utc: datetime


@dataclass(frozen=True, slots=True)
class BatchApproval:
    """Human approval bound to the exact batch preview and source identities."""

    approval_id: str
    approved_by_user_id: str
    approved_at_utc: datetime
    expires_at_utc: datetime
    batch_fingerprint: str


@dataclass(frozen=True, slots=True)
class OperationBatchItem:
    """Immutable snapshot of one batch item at its current lifecycle state."""

    item_id: str
    plan: FileOperationPlan
    state: BatchItemState
    expected_source_digest: str | None
    expected_source_byte_size: int | None
    block_reason: str | None = None
    approval: OperationApproval | None = None
    latest_result: OperationResultRecord | None = None


@dataclass(frozen=True, slots=True)
class OperationBatch:
    """Local operation batch contract before CockroachDB persistence exists."""

    batch_id: str
    workspace_id: str
    operation: FileOperation
    created_by_user_id: str
    created_at_utc: datetime
    idempotency_key: str
    correlation_id: str
    policy_version: str
    state: BatchState
    items: tuple[OperationBatchItem, ...]
    approval: BatchApproval | None = None


@dataclass(frozen=True, slots=True)
class BatchSummary:
    """Aggregate counts that never hide per-item outcomes."""

    total: int
    planned: int
    blocked: int
    approved: int
    executing: int
    succeeded: int
    failed: int
    verification_failed: int
    skipped: int


@dataclass(frozen=True, slots=True)
class BatchExecutionReport:
    """Result of one bounded local batch execution request."""

    batch: OperationBatch
    summary: BatchSummary
    results: tuple[OperationResultRecord, ...]
    replayed_item_count: int


class OperationExecutor(Protocol):
    """Callable boundary for the existing single-operation executor."""

    def __call__(
        self,
        plan: FileOperationPlan,
        approval: OperationApproval,
        *,
        execution_id: str,
        now_utc: datetime,
    ) -> ExecutionResult: ...


class OperationLifecycleRecorder(Protocol):
    """Optional durable boundary around filesystem execution side effects."""

    def record_intent(
        self,
        batch: OperationBatch,
        item: OperationBatchItem,
        event: AuditEvent,
    ) -> None: ...

    def record_result(
        self,
        batch: OperationBatch,
        item: OperationBatchItem,
        result: OperationResultRecord,
        event: AuditEvent,
    ) -> None: ...

    def record_event(
        self,
        batch: OperationBatch,
        event: AuditEvent,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BatchExecutionHooks:
    """Injectable execution and durable lifecycle boundaries."""

    operation_executor: OperationExecutor = execute_file_operation
    lifecycle_recorder: OperationLifecycleRecorder | None = None


@dataclass(frozen=True, slots=True)
class _BatchExecutionContext:
    batch: OperationBatch
    request: BatchExecutionRequest
    now_utc: datetime
    audit_trail: AppendOnlyAuditTrail
    execution_ledger: InMemoryExecutionLedger
    operation_executor: OperationExecutor
    lifecycle_recorder: OperationLifecycleRecorder | None


@dataclass(frozen=True, slots=True)
class _EventTransition:
    event_type: AuditEventType
    actor_type: AuditActorType
    actor_id: str
    occurred_at_utc: datetime
    previous_state: str | None
    new_state: str | None
    reason: str
    idempotency_key: str | None = None
    approval_id: str | None = None
    error_class: str | None = None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class _ObservedFilesystemState:
    source_exists: bool
    destination_exists: bool
    destination_digest: str | None


@dataclass(frozen=True, slots=True)
class _ResultAudit:
    event_type: AuditEventType
    previous_state: str
    reason: str


def create_operation_batch(
    request: BatchCreationRequest,
    *,
    audit_trail: AppendOnlyAuditTrail,
) -> OperationBatch:
    """Create a bounded preview and record its append-only local evidence."""
    for field_name, value in (
        ("batch_id", request.batch_id),
        ("workspace_id", request.workspace_id),
        ("created_by_user_id", request.created_by_user_id),
        ("idempotency_key", request.idempotency_key),
        ("correlation_id", request.correlation_id),
        ("policy_version", request.policy_version),
    ):
        _require_non_empty(field_name, value)
    if not request.item_requests:
        raise ValueError("operation batch must contain at least one item")
    if len(request.item_requests) > MAX_OPERATION_BATCH_ITEMS:
        raise ValueError(
            f"operation batch must contain at most {MAX_OPERATION_BATCH_ITEMS} items"
        )
    item_ids = [item_request.item_id for item_request in request.item_requests]
    if any(item_id.strip() == "" for item_id in item_ids):
        raise ValueError("batch item_id must not be empty")
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("batch item_id values must be unique")

    operations = {item_request.plan.operation for item_request in request.item_requests}
    if len(operations) != 1:
        raise ValueError("operation batch items must use one operation type")

    timestamp = normalize_utc(request.created_at_utc)
    items = tuple(_preview_item(item_request) for item_request in request.item_requests)
    state = derive_batch_state(items)
    batch = OperationBatch(
        batch_id=request.batch_id,
        workspace_id=request.workspace_id,
        operation=operations.pop(),
        created_by_user_id=request.created_by_user_id,
        created_at_utc=timestamp,
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
        policy_version=request.policy_version,
        state=state,
        items=items,
    )
    _append_batch_event(
        audit_trail,
        batch,
        _EventTransition(
            event_type=AuditEventType.BATCH_CREATED,
            actor_type=AuditActorType.HUMAN,
            actor_id=request.created_by_user_id,
            occurred_at_utc=timestamp,
            previous_state=None,
            new_state=state.value,
            reason="batch_preview_created",
            idempotency_key=request.idempotency_key,
        ),
    )
    for item in items:
        _append_item_event(
            audit_trail,
            batch,
            item,
            _EventTransition(
                event_type=(
                    AuditEventType.ITEM_PLANNED
                    if item.state is BatchItemState.PLANNED
                    else AuditEventType.ITEM_BLOCKED
                ),
                actor_type=AuditActorType.SYSTEM,
                actor_id="local-core",
                occurred_at_utc=timestamp,
                previous_state=None,
                new_state=item.state.value,
                reason=item.block_reason or "plan_ready",
            ),
        )
    return batch


def approve_operation_batch(
    batch: OperationBatch,
    request: BatchApprovalRequest,
    *,
    audit_trail: AppendOnlyAuditTrail,
) -> OperationBatch:
    """Approve every executable item in one exact batch preview."""
    if batch.state is not BatchState.READY_FOR_APPROVAL:
        raise ValueError("batch must be ready for approval")
    _require_non_empty("approval_id", request.approval_id)
    _require_non_empty("approved_by_user_id", request.approved_by_user_id)
    approved_at = normalize_utc(request.approved_at_utc)
    expires_at = normalize_utc(request.expires_at_utc)
    if expires_at <= approved_at:
        raise ValueError("batch approval expiry must follow approval time")

    fingerprint = operation_batch_fingerprint(batch)
    approval = BatchApproval(
        approval_id=request.approval_id,
        approved_by_user_id=request.approved_by_user_id,
        approved_at_utc=approved_at,
        expires_at_utc=expires_at,
        batch_fingerprint=fingerprint,
    )
    _append_batch_event(
        audit_trail,
        batch,
        _EventTransition(
            event_type=AuditEventType.BATCH_SUBMITTED_FOR_APPROVAL,
            actor_type=AuditActorType.HUMAN,
            actor_id=request.approved_by_user_id,
            occurred_at_utc=approved_at,
            previous_state=batch.state.value,
            new_state=batch.state.value,
            reason="batch_preview_reviewed",
        ),
    )

    approved_items: list[OperationBatchItem] = []
    for item in batch.items:
        if item.state is not BatchItemState.PLANNED:
            approved_items.append(item)
            continue
        item_approval = approve_operation_plan(
            item.plan,
            approval_id=request.approval_id,
            approved_by_user_id=request.approved_by_user_id,
            approved_at_utc=approved_at,
            expires_at_utc=expires_at,
        )
        approved_item = replace(
            item,
            state=BatchItemState.APPROVED,
            approval=item_approval,
        )
        approved_items.append(approved_item)
        _append_item_event(
            audit_trail,
            batch,
            approved_item,
            _EventTransition(
                event_type=AuditEventType.ITEM_APPROVED,
                actor_type=AuditActorType.HUMAN,
                actor_id=request.approved_by_user_id,
                occurred_at_utc=approved_at,
                previous_state=BatchItemState.PLANNED.value,
                new_state=BatchItemState.APPROVED.value,
                reason="human_approval_recorded",
                approval_id=request.approval_id,
            ),
        )

    updated_items = tuple(approved_items)
    updated_batch = replace(
        batch,
        state=derive_batch_state(updated_items),
        items=updated_items,
        approval=approval,
    )
    _append_batch_event(
        audit_trail,
        updated_batch,
        _EventTransition(
            event_type=AuditEventType.BATCH_APPROVED,
            actor_type=AuditActorType.HUMAN,
            actor_id=request.approved_by_user_id,
            occurred_at_utc=approved_at,
            previous_state=batch.state.value,
            new_state=updated_batch.state.value,
            reason="human_approval_recorded",
            approval_id=request.approval_id,
        ),
    )
    return updated_batch


def execute_operation_batch(
    batch: OperationBatch,
    request: BatchExecutionRequest,
    *,
    audit_trail: AppendOnlyAuditTrail,
    execution_ledger: InMemoryExecutionLedger,
    hooks: BatchExecutionHooks | None = None,
) -> BatchExecutionReport:
    """Execute independent approved items with fail-closed local idempotency."""
    _require_non_empty("executed_by_actor_id", request.executed_by_actor_id)
    if batch.state is not BatchState.APPROVED or batch.approval is None:
        raise ValueError("batch must have a current approval before execution")
    if batch.approval.batch_fingerprint != operation_batch_fingerprint(batch):
        raise ValueError("batch approval does not match the current preview")

    timestamp = normalize_utc(request.now_utc)
    execution_hooks = hooks or BatchExecutionHooks()
    context = _BatchExecutionContext(
        batch=batch,
        request=request,
        now_utc=timestamp,
        audit_trail=audit_trail,
        execution_ledger=execution_ledger,
        operation_executor=execution_hooks.operation_executor,
        lifecycle_recorder=execution_hooks.lifecycle_recorder,
    )
    updated_items: list[OperationBatchItem] = []
    results: list[OperationResultRecord] = []
    replayed_item_count = 0

    for item in batch.items:
        if item.state is not BatchItemState.APPROVED:
            updated_items.append(item)
            continue
        updated_item, result, was_replayed = _execute_batch_item(
            context,
            item,
        )
        updated_items.append(updated_item)
        results.append(result)
        replayed_item_count += int(was_replayed)

    final_items = tuple(updated_items)
    final_state = derive_batch_state(final_items)
    final_batch = replace(batch, state=final_state, items=final_items)
    completion_type = (
        AuditEventType.BATCH_COMPLETED
        if final_state is BatchState.COMPLETED
        else AuditEventType.BATCH_COMPLETED_WITH_FAILURES
    )
    _record_batch_event(
        context,
        final_batch,
        _EventTransition(
            event_type=completion_type,
            actor_type=AuditActorType.SYSTEM,
            actor_id=request.executed_by_actor_id,
            occurred_at_utc=timestamp,
            previous_state=batch.state.value,
            new_state=final_state.value,
            reason="all_executable_items_reached_terminal_state",
        ),
    )
    return BatchExecutionReport(
        batch=final_batch,
        summary=summarize_batch(final_batch),
        results=tuple(results),
        replayed_item_count=replayed_item_count,
    )


def operation_batch_fingerprint(batch: OperationBatch) -> str:
    """Bind approval to ordered plans and observed source identities."""
    payload = {
        "batch_id": batch.batch_id,
        "workspace_id": batch.workspace_id,
        "operation": batch.operation.value,
        "policy_version": batch.policy_version,
        "items": [
            {
                "item_id": item.item_id,
                "plan_fingerprint": operation_plan_fingerprint(item.plan),
                "expected_source_digest": item.expected_source_digest,
                "expected_source_byte_size": item.expected_source_byte_size,
            }
            for item in batch.items
        ],
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def operation_execution_key(batch: OperationBatch, item: OperationBatchItem) -> str:
    """Derive one stable idempotency key for an approved item execution."""
    payload = {
        "batch_id": batch.batch_id,
        "item_id": item.item_id,
        "operation": item.plan.operation.value,
        "plan_fingerprint": operation_plan_fingerprint(item.plan),
        "source_digest": item.expected_source_digest,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def summarize_batch(batch: OperationBatch) -> BatchSummary:
    """Count each item state exactly once."""
    counts = dict.fromkeys(BatchItemState, 0)
    for item in batch.items:
        counts[item.state] += 1
    return BatchSummary(
        total=len(batch.items),
        planned=counts[BatchItemState.PLANNED],
        blocked=counts[BatchItemState.BLOCKED],
        approved=counts[BatchItemState.APPROVED],
        executing=counts[BatchItemState.EXECUTING],
        succeeded=counts[BatchItemState.SUCCEEDED],
        failed=counts[BatchItemState.FAILED],
        verification_failed=counts[BatchItemState.VERIFICATION_FAILED],
        skipped=counts[BatchItemState.SKIPPED],
    )


def derive_batch_state(items: tuple[OperationBatchItem, ...]) -> BatchState:
    """Derive aggregate state without concealing terminal failures."""
    batch_state = BatchState.DRAFT
    if not items:
        return batch_state

    states = {item.state for item in items}
    failure_states = {
        BatchItemState.BLOCKED,
        BatchItemState.FAILED,
        BatchItemState.VERIFICATION_FAILED,
    }
    terminal_states = failure_states | {
        BatchItemState.SUCCEEDED,
        BatchItemState.SKIPPED,
    }
    if states <= terminal_states:
        batch_state = (
            BatchState.COMPLETED_WITH_FAILURES
            if states & failure_states
            else BatchState.COMPLETED
        )
    elif BatchItemState.EXECUTING in states:
        batch_state = BatchState.EXECUTING
    elif BatchItemState.APPROVED in states:
        batch_state = BatchState.APPROVED
    elif BatchItemState.PLANNED in states:
        batch_state = BatchState.READY_FOR_APPROVAL
    return batch_state


def _preview_item(request: BatchItemRequest) -> OperationBatchItem:
    plan = request.plan
    if plan.status is not FileOperationStatus.READY or plan.source_path is None:
        return OperationBatchItem(
            item_id=request.item_id,
            plan=plan,
            state=BatchItemState.BLOCKED,
            expected_source_digest=None,
            expected_source_byte_size=None,
            block_reason=plan.reason.value,
        )
    try:
        fingerprint = compute_sha256_fingerprint(plan.source_path)
    except OSError:
        return OperationBatchItem(
            item_id=request.item_id,
            plan=plan,
            state=BatchItemState.BLOCKED,
            expected_source_digest=None,
            expected_source_byte_size=None,
            block_reason="source_fingerprint_unavailable",
        )
    return OperationBatchItem(
        item_id=request.item_id,
        plan=plan,
        state=BatchItemState.PLANNED,
        expected_source_digest=fingerprint.hex_digest,
        expected_source_byte_size=fingerprint.byte_size,
    )


def _execute_batch_item(
    context: _BatchExecutionContext,
    item: OperationBatchItem,
) -> tuple[OperationBatchItem, OperationResultRecord, bool]:
    batch = context.batch
    execution_key = operation_execution_key(batch, item)
    prior_result = context.execution_ledger.result_for(execution_key)
    if prior_result is not None:
        replay = replace(
            prior_result,
            disposition=ResultDisposition.IDEMPOTENT_REPLAY,
            attempted_at_utc=context.now_utc,
            completed_at_utc=context.now_utc,
        )
        replayed_item = replace(
            item,
            state=_item_state_for_status(replay.status),
            latest_result=replay,
        )
        _record_result_event(
            context,
            replayed_item,
            replay,
            _ResultAudit(
                event_type=AuditEventType.ITEM_EXECUTION_REPLAYED,
                previous_state=item.state.value,
                reason="terminal_result_returned_without_reexecution",
            ),
        )
        return replayed_item, replay, True

    if context.execution_ledger.is_in_progress(execution_key):
        reconciled = _reconcile_interrupted_item(
            context,
            item,
            execution_key=execution_key,
        )
        if reconciled is not None:
            reconciled_item = replace(
                item,
                state=_item_state_for_status(reconciled.status),
                latest_result=reconciled,
            )
            return reconciled_item, reconciled, False
    else:
        stale_result = _stale_source_result(
            batch,
            item,
            now_utc=context.now_utc,
        )
        if stale_result is not None:
            blocked_item = replace(
                item,
                state=BatchItemState.BLOCKED,
                latest_result=stale_result,
                block_reason=stale_result.reason.value,
            )
            _record_result_event(
                context,
                blocked_item,
                stale_result,
                _ResultAudit(
                    event_type=AuditEventType.ITEM_BLOCKED,
                    previous_state=item.state.value,
                    reason=stale_result.reason.value,
                ),
            )
            return blocked_item, stale_result, False

        _record_intent_event(
            context,
            batch,
            item,
            _EventTransition(
                event_type=AuditEventType.ITEM_EXECUTION_INTENT_RECORDED,
                actor_type=AuditActorType.SYSTEM,
                actor_id=context.request.executed_by_actor_id,
                occurred_at_utc=context.now_utc,
                previous_state=item.state.value,
                new_state=BatchItemState.EXECUTING.value,
                reason="pre_mutation_intent_recorded",
                idempotency_key=execution_key,
                approval_id=cast(OperationApproval, item.approval).approval_id,
            ),
        )

    item_approval = cast(OperationApproval, item.approval)
    execution_id = f"{batch.batch_id}:{item.item_id}"
    execution = context.operation_executor(
        item.plan,
        item_approval,
        execution_id=execution_id,
        now_utc=context.now_utc,
    )
    result = _record_from_execution(
        context,
        item,
        execution_key,
        execution,
    )
    updated_item = replace(
        item,
        state=_item_state_for_status(result.status),
        latest_result=result,
        block_reason=(
            result.reason.value if result.status is ExecutionStatus.BLOCKED else None
        ),
    )
    _record_result_event(
        context,
        updated_item,
        result,
        _ResultAudit(
            event_type=_event_type_for_status(result.status),
            previous_state=BatchItemState.EXECUTING.value,
            reason=result.reason.value,
        ),
    )
    return updated_item, result, False


def _stale_source_result(
    batch: OperationBatch,
    item: OperationBatchItem,
    *,
    now_utc: datetime,
) -> OperationResultRecord | None:
    source_path = item.plan.source_path
    if source_path is None:
        return _blocked_source_result(batch, item, now_utc, "source_path_missing")
    try:
        fingerprint = compute_sha256_fingerprint(source_path)
    except OSError as exc:
        return _blocked_source_result(
            batch,
            item,
            now_utc,
            exc.__class__.__name__,
        )
    if (
        fingerprint.hex_digest != item.expected_source_digest
        or fingerprint.byte_size != item.expected_source_byte_size
    ):
        return _blocked_source_result(batch, item, now_utc, "source_identity_changed")
    return None


def _blocked_source_result(
    batch: OperationBatch,
    item: OperationBatchItem,
    now_utc: datetime,
    error_class: str,
) -> OperationResultRecord:
    return OperationResultRecord(
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        execution_key=operation_execution_key(batch, item),
        execution_id=f"{batch.batch_id}:{item.item_id}",
        status=ExecutionStatus.BLOCKED,
        reason=ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION,
        disposition=ResultDisposition.PRECONDITION_BLOCKED,
        attempted_at_utc=now_utc,
        completed_at_utc=now_utc,
        approval_id=item.approval.approval_id if item.approval else None,
        source_exists_after=_path_exists(item.plan.source_path),
        destination_exists_after=_path_exists(item.plan.destination_path),
        error_class=error_class,
    )


def _reconcile_interrupted_item(
    context: _BatchExecutionContext,
    item: OperationBatchItem,
    *,
    execution_key: str,
) -> OperationResultRecord | None:
    batch = context.batch
    source_exists = _path_exists(item.plan.source_path)
    destination_exists = _path_exists(item.plan.destination_path)
    destination_digest: str | None = None
    if destination_exists and item.plan.destination_path is not None:
        try:
            destination_digest = compute_sha256_fingerprint(
                item.plan.destination_path
            ).hex_digest
        except OSError:
            destination_digest = None

    expected_source_exists = item.plan.operation is FileOperation.COPY
    postcondition_matches = (
        destination_exists
        and destination_digest == item.expected_source_digest
        and source_exists is expected_source_exists
    )
    if postcondition_matches:
        result = OperationResultRecord(
            batch_id=batch.batch_id,
            batch_item_id=item.item_id,
            execution_key=execution_key,
            execution_id=f"{batch.batch_id}:{item.item_id}",
            status=ExecutionStatus.SUCCEEDED,
            reason=ExecutionReason.SUCCEEDED,
            disposition=ResultDisposition.RECONCILED,
            attempted_at_utc=context.now_utc,
            completed_at_utc=context.now_utc,
            approval_id=item.approval.approval_id if item.approval else None,
            source_exists_after=source_exists,
            destination_exists_after=destination_exists,
            source_digest_before=item.expected_source_digest,
            destination_digest_after=destination_digest,
        )
        event_reason = "verified_postcondition_after_interruption"
    elif not destination_exists and source_exists:
        source_matches = _source_still_matches(item)
        if source_matches:
            _record_item_event(
                context,
                batch,
                item,
                _EventTransition(
                    event_type=AuditEventType.ITEM_EXECUTION_RECONCILED,
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=context.request.executed_by_actor_id,
                    occurred_at_utc=context.now_utc,
                    previous_state=BatchItemState.EXECUTING.value,
                    new_state=BatchItemState.EXECUTING.value,
                    reason="no_effect_observed_safe_to_retry",
                    idempotency_key=execution_key,
                ),
            )
            return None
        result = _reconciliation_failure(
            batch,
            item,
            execution_key,
            context.now_utc,
            _ObservedFilesystemState(
                source_exists=source_exists,
                destination_exists=destination_exists,
                destination_digest=destination_digest,
            ),
        )
        event_reason = "source_identity_changed_during_reconciliation"
    else:
        result = _reconciliation_failure(
            batch,
            item,
            execution_key,
            context.now_utc,
            _ObservedFilesystemState(
                source_exists=source_exists,
                destination_exists=destination_exists,
                destination_digest=destination_digest,
            ),
        )
        event_reason = "ambiguous_filesystem_state_after_interruption"

    _record_result_event(
        context,
        item,
        result,
        _ResultAudit(
            event_type=AuditEventType.ITEM_EXECUTION_RECONCILED,
            previous_state=BatchItemState.EXECUTING.value,
            reason=event_reason,
        ),
    )
    return result


def _reconciliation_failure(
    batch: OperationBatch,
    item: OperationBatchItem,
    execution_key: str,
    now_utc: datetime,
    observed: _ObservedFilesystemState,
) -> OperationResultRecord:
    return OperationResultRecord(
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        execution_key=execution_key,
        execution_id=f"{batch.batch_id}:{item.item_id}",
        status=ExecutionStatus.VERIFICATION_FAILED,
        reason=ExecutionReason.VERIFICATION_FAILED,
        disposition=ResultDisposition.RECONCILED,
        attempted_at_utc=now_utc,
        completed_at_utc=now_utc,
        approval_id=item.approval.approval_id if item.approval else None,
        source_exists_after=observed.source_exists,
        destination_exists_after=observed.destination_exists,
        source_digest_before=item.expected_source_digest,
        destination_digest_after=observed.destination_digest,
        error_class="reconciliation_required",
    )


def _source_still_matches(item: OperationBatchItem) -> bool:
    if item.plan.source_path is None:
        return False
    try:
        fingerprint = compute_sha256_fingerprint(item.plan.source_path)
    except OSError:
        return False
    return (
        fingerprint.hex_digest == item.expected_source_digest
        and fingerprint.byte_size == item.expected_source_byte_size
    )


def _record_from_execution(
    context: _BatchExecutionContext,
    item: OperationBatchItem,
    execution_key: str,
    execution: ExecutionResult,
) -> OperationResultRecord:
    batch = context.batch
    return OperationResultRecord(
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        execution_key=execution_key,
        execution_id=execution.execution_id,
        status=execution.status,
        reason=execution.reason,
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=context.now_utc,
        completed_at_utc=context.now_utc,
        approval_id=execution.approval_id,
        source_exists_after=execution.source_exists_after,
        destination_exists_after=execution.destination_exists_after,
        source_digest_before=execution.source_digest_before,
        destination_digest_after=execution.destination_digest_after,
        error_class=execution.error,
    )


def _item_state_for_status(status: ExecutionStatus) -> BatchItemState:
    return {
        ExecutionStatus.SUCCEEDED: BatchItemState.SUCCEEDED,
        ExecutionStatus.BLOCKED: BatchItemState.BLOCKED,
        ExecutionStatus.FAILED: BatchItemState.FAILED,
        ExecutionStatus.VERIFICATION_FAILED: BatchItemState.VERIFICATION_FAILED,
    }[status]


def _event_type_for_status(status: ExecutionStatus) -> AuditEventType:
    return {
        ExecutionStatus.SUCCEEDED: AuditEventType.ITEM_EXECUTION_SUCCEEDED,
        ExecutionStatus.BLOCKED: AuditEventType.ITEM_BLOCKED,
        ExecutionStatus.FAILED: AuditEventType.ITEM_EXECUTION_FAILED,
        ExecutionStatus.VERIFICATION_FAILED: (AuditEventType.ITEM_VERIFICATION_FAILED),
    }[status]


def _record_result_event(
    context: _BatchExecutionContext,
    item: OperationBatchItem,
    result: OperationResultRecord,
    result_audit: _ResultAudit,
) -> None:
    event = _item_event(
        context.batch,
        item,
        _EventTransition(
            event_type=result_audit.event_type,
            actor_type=AuditActorType.SYSTEM,
            actor_id=context.request.executed_by_actor_id,
            occurred_at_utc=context.now_utc,
            previous_state=result_audit.previous_state,
            new_state=_item_state_for_status(result.status).value,
            reason=result_audit.reason,
            idempotency_key=result.execution_key,
            approval_id=result.approval_id,
            error_class=result.error_class,
            error_category=(
                result.reason.value
                if result.status is not ExecutionStatus.SUCCEEDED
                else None
            ),
        ),
    )
    if context.lifecycle_recorder is not None:
        if result.disposition is ResultDisposition.IDEMPOTENT_REPLAY:
            context.lifecycle_recorder.record_event(context.batch, event)
        else:
            context.lifecycle_recorder.record_result(
                context.batch,
                item,
                result,
                event,
            )
    if result.disposition is not ResultDisposition.IDEMPOTENT_REPLAY:
        context.execution_ledger.record_result(result)
    context.audit_trail.append(event)


def _record_intent_event(
    context: _BatchExecutionContext,
    batch: OperationBatch,
    item: OperationBatchItem,
    transition: _EventTransition,
) -> None:
    event = _item_event(batch, item, transition)
    if transition.idempotency_key is None:
        raise ValueError("execution intent requires an idempotency key")
    if context.lifecycle_recorder is not None:
        context.lifecycle_recorder.record_intent(batch, item, event)
    context.execution_ledger.record_intent(transition.idempotency_key)
    context.audit_trail.append(event)


def _record_item_event(
    context: _BatchExecutionContext,
    batch: OperationBatch,
    item: OperationBatchItem,
    transition: _EventTransition,
) -> None:
    event = _item_event(batch, item, transition)
    if context.lifecycle_recorder is not None:
        context.lifecycle_recorder.record_event(batch, event)
    context.audit_trail.append(event)


def _record_batch_event(
    context: _BatchExecutionContext,
    batch: OperationBatch,
    transition: _EventTransition,
) -> None:
    event = _batch_event(batch, transition)
    if context.lifecycle_recorder is not None:
        context.lifecycle_recorder.record_event(batch, event)
    context.audit_trail.append(event)


def _append_batch_event(
    audit_trail: AppendOnlyAuditTrail,
    batch: OperationBatch,
    transition: _EventTransition,
) -> None:
    audit_trail.append(_batch_event(batch, transition))


def _append_item_event(
    audit_trail: AppendOnlyAuditTrail,
    batch: OperationBatch,
    item: OperationBatchItem,
    transition: _EventTransition,
) -> None:
    audit_trail.append(_item_event(batch, item, transition))


def _batch_event(
    batch: OperationBatch,
    transition: _EventTransition,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid4()),
        workspace_id=batch.workspace_id,
        batch_id=batch.batch_id,
        event_type=transition.event_type,
        actor_type=transition.actor_type,
        actor_id=transition.actor_id,
        occurred_at_utc=transition.occurred_at_utc,
        correlation_id=batch.correlation_id,
        idempotency_key=transition.idempotency_key,
        previous_state=transition.previous_state,
        new_state=transition.new_state,
        reason=transition.reason,
        approval_id=transition.approval_id,
    )


def _item_event(
    batch: OperationBatch,
    item: OperationBatchItem,
    transition: _EventTransition,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid4()),
        workspace_id=batch.workspace_id,
        batch_id=batch.batch_id,
        batch_item_id=item.item_id,
        event_type=transition.event_type,
        actor_type=transition.actor_type,
        actor_id=transition.actor_id,
        occurred_at_utc=transition.occurred_at_utc,
        correlation_id=batch.correlation_id,
        idempotency_key=transition.idempotency_key,
        previous_state=transition.previous_state,
        new_state=transition.new_state,
        reason=transition.reason,
        plan_fingerprint=operation_plan_fingerprint(item.plan),
        approval_id=transition.approval_id,
        source_relative_path=item.plan.source_relative_path,
        destination_relative_path=item.plan.destination_relative_path,
        error_class=transition.error_class,
        error_category=transition.error_category,
    )


def _path_exists(path: Path | None) -> bool:
    return path is not None and path.exists()


def _require_non_empty(field_name: str, value: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
