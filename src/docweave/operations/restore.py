"""Safe restore planning for previously executed local file operations."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.operations.approval import approve_operation_plan
from docweave.operations.execution import (
    ExecutionReason,
    ExecutionResult,
    ExecutionStatus,
    execute_file_operation,
)
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    FileOperationStatus,
    plan_file_operation,
)
from docweave.operations.results import OperationResultRecord


class RestoreOperation(StrEnum):
    """Supported restore operation previews."""

    REMOVE_GENERATED_COPY = "remove_generated_copy"
    MOVE_BACK = "move_back"


class RestorePlanStatus(StrEnum):
    """Pre-execution restore planning status."""

    READY = "ready"
    BLOCKED = "blocked"


class RestorePlanReason(StrEnum):
    """Machine-readable restore planning reason."""

    READY = "ready"
    ORIGINAL_RESULT_NOT_SUCCEEDED = "original_result_not_succeeded"
    ORIGINAL_RESULT_DIGEST_MISSING = "original_result_digest_missing"
    ORIGINAL_SOURCE_MISSING = "original_source_missing"
    GENERATED_COPY_MISSING = "generated_copy_missing"
    GENERATED_COPY_CHANGED = "generated_copy_changed"
    MOVED_FILE_MISSING = "moved_file_missing"
    MOVED_FILE_CHANGED = "moved_file_changed"
    ORIGINAL_LOCATION_COLLISION = "original_location_collision"
    ORIGINAL_PLAN_NOT_READY = "original_plan_not_ready"
    RESTORE_PARENT_BLOCKED = "restore_parent_blocked"
    UNSUPPORTED_ORIGINAL_OPERATION = "unsupported_original_operation"


class RestoreExecutionStatus(StrEnum):
    """Terminal status for one approved restore execution."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    VERIFICATION_FAILED = "verification_failed"


class RestoreExecutionReason(StrEnum):
    """Machine-readable restore execution result reason."""

    SUCCEEDED = "succeeded"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_NOT_YET_EFFECTIVE = "approval_not_yet_effective"
    FILE_OPERATION_FAILED = "file_operation_failed"
    GENERATED_COPY_REMOVE_FAILED = "generated_copy_remove_failed"
    MISSING_APPROVAL_ID = "missing_approval_id"
    MISSING_APPROVER = "missing_approver"
    RESTORE_FINGERPRINT_MISMATCH = "restore_fingerprint_mismatch"
    RESTORE_ID_MISSING = "restore_id_missing"
    RESTORE_PLAN_CHANGED = "restore_plan_changed"
    RESTORE_PLAN_NOT_READY = "restore_plan_not_ready"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True, slots=True)
class RestorePlan:
    """Immutable preview of a restore action before human approval."""

    operation: RestoreOperation
    status: RestorePlanStatus
    reason: RestorePlanReason
    original_plan: FileOperationPlan
    original_result: OperationResultRecord
    source_path: Path | None
    destination_path: Path | None
    source_relative_path: str | None
    destination_relative_path: str | None
    expected_digest: str | None
    planned_parent_directories: tuple[Path, ...] = ()
    move_back_plan: FileOperationPlan | None = None

    @property
    def is_ready(self) -> bool:
        """Return whether this restore preview can be sent for approval."""
        return self.status is RestorePlanStatus.READY


@dataclass(frozen=True, slots=True)
class RestoreApproval:
    """Human approval bound to one exact restore preview."""

    approval_id: str
    approved_by_user_id: str
    approved_at_utc: datetime
    expires_at_utc: datetime
    restore_fingerprint: str


@dataclass(frozen=True, slots=True)
class RestoreExecutionResult:
    """Outcome of one approved restore operation."""

    restore_id: str
    status: RestoreExecutionStatus
    reason: RestoreExecutionReason
    restore_fingerprint: str
    approval_id: str | None
    source_exists_after: bool
    destination_exists_after: bool
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the restore completed and verified successfully."""
        return self.status is RestoreExecutionStatus.SUCCEEDED


@dataclass(frozen=True, slots=True)
class _RestoreBlockerContext:
    source_path: Path | None = None
    destination_path: Path | None = None
    move_back_plan: FileOperationPlan | None = None


@dataclass(frozen=True, slots=True)
class _RestoreOutcome:
    status: RestoreExecutionStatus
    reason: RestoreExecutionReason
    approval_id: str | None
    error: str | None = None


def plan_restore_operation(
    original_plan: FileOperationPlan,
    original_result: OperationResultRecord,
) -> RestorePlan:
    """Plan a safe restore preview without mutating the filesystem."""
    blocker = _common_blocker(original_plan, original_result)
    if blocker is not None:
        return blocker
    assert original_result.destination_digest_after is not None

    if original_plan.operation is FileOperation.COPY:
        return _plan_copy_restore(original_plan, original_result)
    if original_plan.operation is FileOperation.MOVE:
        return _plan_move_restore(original_plan, original_result)
    return _blocked(
        RestoreOperation.MOVE_BACK,
        RestorePlanReason.UNSUPPORTED_ORIGINAL_OPERATION,
        original_plan,
        original_result,
    )


def _common_blocker(
    original_plan: FileOperationPlan,
    original_result: OperationResultRecord,
) -> RestorePlan | None:
    if original_plan.status is not FileOperationStatus.READY:
        return _blocked(
            _operation_for(original_plan),
            RestorePlanReason.ORIGINAL_PLAN_NOT_READY,
            original_plan,
            original_result,
        )
    if original_result.status is not ExecutionStatus.SUCCEEDED:
        return _blocked(
            _operation_for(original_plan),
            RestorePlanReason.ORIGINAL_RESULT_NOT_SUCCEEDED,
            original_plan,
            original_result,
        )
    if original_result.destination_digest_after is None:
        return _blocked(
            _operation_for(original_plan),
            RestorePlanReason.ORIGINAL_RESULT_DIGEST_MISSING,
            original_plan,
            original_result,
        )
    return None


def _plan_copy_restore(
    original_plan: FileOperationPlan,
    original_result: OperationResultRecord,
) -> RestorePlan:
    expected_digest = original_result.destination_digest_after
    if expected_digest is None:
        return _blocked(
            RestoreOperation.REMOVE_GENERATED_COPY,
            RestorePlanReason.ORIGINAL_RESULT_DIGEST_MISSING,
            original_plan,
            original_result,
        )
    source_path = original_plan.source_path
    destination_path = original_plan.destination_path
    if source_path is None or not source_path.exists():
        return _blocked(
            RestoreOperation.REMOVE_GENERATED_COPY,
            RestorePlanReason.ORIGINAL_SOURCE_MISSING,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=source_path,
                destination_path=destination_path,
            ),
        )
    if destination_path is None or not destination_path.exists():
        return _blocked(
            RestoreOperation.REMOVE_GENERATED_COPY,
            RestorePlanReason.GENERATED_COPY_MISSING,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=source_path,
                destination_path=destination_path,
            ),
        )
    if not _path_matches_digest(destination_path, expected_digest):
        return _blocked(
            RestoreOperation.REMOVE_GENERATED_COPY,
            RestorePlanReason.GENERATED_COPY_CHANGED,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=source_path,
                destination_path=destination_path,
            ),
        )
    return RestorePlan(
        operation=RestoreOperation.REMOVE_GENERATED_COPY,
        status=RestorePlanStatus.READY,
        reason=RestorePlanReason.READY,
        original_plan=original_plan,
        original_result=original_result,
        source_path=destination_path,
        destination_path=None,
        source_relative_path=original_plan.destination_relative_path,
        destination_relative_path=None,
        expected_digest=expected_digest,
    )


def _plan_move_restore(
    original_plan: FileOperationPlan,
    original_result: OperationResultRecord,
) -> RestorePlan:
    expected_digest = original_result.destination_digest_after
    if expected_digest is None:
        return _blocked(
            RestoreOperation.MOVE_BACK,
            RestorePlanReason.ORIGINAL_RESULT_DIGEST_MISSING,
            original_plan,
            original_result,
        )
    moved_path = original_plan.destination_path
    original_path = original_plan.source_path
    if moved_path is None or not moved_path.exists():
        return _blocked(
            RestoreOperation.MOVE_BACK,
            RestorePlanReason.MOVED_FILE_MISSING,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=moved_path,
                destination_path=original_path,
            ),
        )
    if not _path_matches_digest(moved_path, expected_digest):
        return _blocked(
            RestoreOperation.MOVE_BACK,
            RestorePlanReason.MOVED_FILE_CHANGED,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=moved_path,
                destination_path=original_path,
            ),
        )
    restore_move = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.MOVE,
            source_root=original_plan.destination_root,
            source_relative_path=original_plan.destination_relative_path,
            destination_root=original_plan.source_root,
            destination_relative_path=original_plan.source_relative_path,
            allow_missing_parent_directories=True,
            case_sensitive_paths=original_plan.request.case_sensitive_paths,
        )
    )
    if restore_move.status is FileOperationStatus.COLLISION:
        return _blocked(
            RestoreOperation.MOVE_BACK,
            RestorePlanReason.ORIGINAL_LOCATION_COLLISION,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=moved_path,
                destination_path=original_path,
                move_back_plan=restore_move,
            ),
        )
    if restore_move.status is not FileOperationStatus.READY:
        return _blocked(
            RestoreOperation.MOVE_BACK,
            RestorePlanReason.RESTORE_PARENT_BLOCKED,
            original_plan,
            original_result,
            _RestoreBlockerContext(
                source_path=moved_path,
                destination_path=original_path,
                move_back_plan=restore_move,
            ),
        )
    return RestorePlan(
        operation=RestoreOperation.MOVE_BACK,
        status=RestorePlanStatus.READY,
        reason=RestorePlanReason.READY,
        original_plan=original_plan,
        original_result=original_result,
        source_path=restore_move.source_path,
        destination_path=restore_move.destination_path,
        source_relative_path=restore_move.source_relative_path,
        destination_relative_path=restore_move.destination_relative_path,
        expected_digest=expected_digest,
        planned_parent_directories=restore_move.planned_parent_directories,
        move_back_plan=restore_move,
    )


def _path_matches_digest(path: Path, expected_digest: str) -> bool:
    try:
        return compute_sha256_fingerprint(path).hex_digest == expected_digest
    except OSError:
        return False


def _operation_for(original_plan: FileOperationPlan) -> RestoreOperation:
    if original_plan.operation is FileOperation.COPY:
        return RestoreOperation.REMOVE_GENERATED_COPY
    return RestoreOperation.MOVE_BACK


def _blocked(
    operation: RestoreOperation,
    reason: RestorePlanReason,
    original_plan: FileOperationPlan,
    original_result: OperationResultRecord,
    blocker: _RestoreBlockerContext | None = None,
) -> RestorePlan:
    active_blocker = blocker or _RestoreBlockerContext()
    return RestorePlan(
        operation=operation,
        status=RestorePlanStatus.BLOCKED,
        reason=reason,
        original_plan=original_plan,
        original_result=original_result,
        source_path=active_blocker.source_path,
        destination_path=active_blocker.destination_path,
        source_relative_path=(
            active_blocker.move_back_plan.source_relative_path
            if active_blocker.move_back_plan is not None
            else None
        ),
        destination_relative_path=(
            active_blocker.move_back_plan.destination_relative_path
            if active_blocker.move_back_plan is not None
            else None
        ),
        expected_digest=original_result.destination_digest_after,
        planned_parent_directories=(
            active_blocker.move_back_plan.planned_parent_directories
            if active_blocker.move_back_plan is not None
            else ()
        ),
        move_back_plan=active_blocker.move_back_plan,
    )


def approve_restore_plan(
    plan: RestorePlan,
    *,
    approval_id: str,
    approved_by_user_id: str,
    approved_at_utc: datetime,
    expires_at_utc: datetime,
) -> RestoreApproval:
    """Create an immutable approval for an exact ready restore preview."""
    return RestoreApproval(
        approval_id=approval_id,
        approved_by_user_id=approved_by_user_id,
        approved_at_utc=_normalize_utc(approved_at_utc),
        expires_at_utc=_normalize_utc(expires_at_utc),
        restore_fingerprint=restore_plan_fingerprint(plan),
    )


def execute_restore_operation(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    now_utc: datetime,
) -> RestoreExecutionResult:
    """Execute one approved restore preview and verify the final state."""
    now_utc = _normalize_utc(now_utc)
    precondition = _restore_precondition_blocker(
        plan,
        approval,
        restore_id=restore_id,
        now_utc=now_utc,
    )
    if precondition is not None:
        return precondition
    current_plan = plan_restore_operation(plan.original_plan, plan.original_result)
    if restore_plan_fingerprint(current_plan) != restore_plan_fingerprint(plan):
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_PLAN_CHANGED,
                approval.approval_id,
            ),
        )
    if plan.operation is RestoreOperation.REMOVE_GENERATED_COPY:
        return _execute_copy_restore(plan, approval, restore_id=restore_id)
    return _execute_move_restore(plan, approval, restore_id=restore_id, now_utc=now_utc)


def restore_plan_fingerprint(plan: RestorePlan) -> str:
    """Return a stable fingerprint for the exact user-visible restore preview."""
    payload = {
        "operation": plan.operation.value,
        "status": plan.status.value,
        "reason": plan.reason.value,
        "source_root": plan.original_plan.source_root.as_posix(),
        "source_relative_path": plan.source_relative_path,
        "destination_root": plan.original_plan.destination_root.as_posix(),
        "destination_relative_path": plan.destination_relative_path,
        "expected_digest": plan.expected_digest,
        "original_batch_id": plan.original_result.batch_id,
        "original_batch_item_id": plan.original_result.batch_item_id,
        "original_execution_key": plan.original_result.execution_key,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def _restore_precondition_blocker(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    now_utc: datetime,
) -> RestoreExecutionResult | None:
    expected_fingerprint = restore_plan_fingerprint(plan)
    if restore_id.strip() == "":
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_ID_MISSING,
                approval.approval_id,
            ),
        )
    if plan.status is not RestorePlanStatus.READY:
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_PLAN_NOT_READY,
                approval.approval_id,
            ),
        )
    approval_blocker = _restore_approval_blocker(
        plan,
        approval,
        restore_id=restore_id,
        expected_fingerprint=expected_fingerprint,
    )
    if approval_blocker is not None:
        return approval_blocker
    return _restore_approval_time_blocker(
        plan,
        approval,
        restore_id=restore_id,
        now_utc=now_utc,
    )


def _restore_approval_blocker(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    expected_fingerprint: str,
) -> RestoreExecutionResult | None:
    if approval.approval_id.strip() == "":
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.MISSING_APPROVAL_ID,
                None,
            ),
        )
    if approval.approved_by_user_id.strip() == "":
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.MISSING_APPROVER,
                approval.approval_id,
            ),
        )
    if approval.restore_fingerprint != expected_fingerprint:
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_FINGERPRINT_MISMATCH,
                approval.approval_id,
            ),
        )
    return None


def _restore_approval_time_blocker(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    now_utc: datetime,
) -> RestoreExecutionResult | None:
    if now_utc < _normalize_utc(approval.approved_at_utc):
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.APPROVAL_NOT_YET_EFFECTIVE,
                approval.approval_id,
            ),
        )
    if now_utc >= _normalize_utc(approval.expires_at_utc):
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.APPROVAL_EXPIRED,
                approval.approval_id,
            ),
        )
    return None


def _execute_copy_restore(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
) -> RestoreExecutionResult:
    copied_path = plan.source_path
    if copied_path is None:
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_PLAN_NOT_READY,
                approval.approval_id,
            ),
        )
    try:
        copied_path.unlink()
    except OSError as error:
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.FAILED,
                RestoreExecutionReason.GENERATED_COPY_REMOVE_FAILED,
                approval.approval_id,
                error.__class__.__name__,
            ),
        )
    if copied_path.exists() or not _path_exists(plan.original_plan.source_path):
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.VERIFICATION_FAILED,
                RestoreExecutionReason.VERIFICATION_FAILED,
                approval.approval_id,
            ),
        )
    return _restore_result(
        plan,
        restore_id=restore_id,
        outcome=_RestoreOutcome(
            RestoreExecutionStatus.SUCCEEDED,
            RestoreExecutionReason.SUCCEEDED,
            approval.approval_id,
        ),
    )


def _execute_move_restore(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    now_utc: datetime,
) -> RestoreExecutionResult:
    if plan.move_back_plan is None:
        return _restore_result(
            plan,
            restore_id=restore_id,
            outcome=_RestoreOutcome(
                RestoreExecutionStatus.BLOCKED,
                RestoreExecutionReason.RESTORE_PLAN_NOT_READY,
                approval.approval_id,
            ),
        )
    operation_approval = approve_operation_plan(
        plan.move_back_plan,
        approval_id=approval.approval_id,
        approved_by_user_id=approval.approved_by_user_id,
        approved_at_utc=approval.approved_at_utc,
        expires_at_utc=approval.expires_at_utc,
    )
    execution = execute_file_operation(
        plan.move_back_plan,
        operation_approval,
        execution_id=restore_id,
        now_utc=now_utc,
    )
    return _restore_result_from_execution(
        plan,
        approval,
        restore_id=restore_id,
        execution=execution,
    )


def _restore_result_from_execution(
    plan: RestorePlan,
    approval: RestoreApproval,
    *,
    restore_id: str,
    execution: ExecutionResult,
) -> RestoreExecutionResult:
    status = {
        ExecutionStatus.SUCCEEDED: RestoreExecutionStatus.SUCCEEDED,
        ExecutionStatus.BLOCKED: RestoreExecutionStatus.BLOCKED,
        ExecutionStatus.FAILED: RestoreExecutionStatus.FAILED,
        ExecutionStatus.VERIFICATION_FAILED: RestoreExecutionStatus.VERIFICATION_FAILED,
    }[execution.status]
    reason = (
        RestoreExecutionReason.SUCCEEDED
        if execution.reason is ExecutionReason.SUCCEEDED
        else RestoreExecutionReason.FILE_OPERATION_FAILED
    )
    return _restore_result(
        plan,
        restore_id=restore_id,
        outcome=_RestoreOutcome(status, reason, approval.approval_id, execution.error),
    )


def _restore_result(
    plan: RestorePlan,
    *,
    restore_id: str,
    outcome: _RestoreOutcome,
) -> RestoreExecutionResult:
    return RestoreExecutionResult(
        restore_id=restore_id,
        status=outcome.status,
        reason=outcome.reason,
        restore_fingerprint=restore_plan_fingerprint(plan),
        approval_id=outcome.approval_id,
        source_exists_after=_path_exists(plan.source_path),
        destination_exists_after=_path_exists(plan.destination_path),
        error=outcome.error,
    )


def _path_exists(path: Path | None) -> bool:
    return path is not None and path.exists()


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
