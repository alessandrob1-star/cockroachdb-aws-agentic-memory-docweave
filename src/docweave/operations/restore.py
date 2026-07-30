"""Safe restore planning for previously executed local file operations."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.operations.execution import ExecutionStatus
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
class _RestoreBlockerContext:
    source_path: Path | None = None
    destination_path: Path | None = None
    move_back_plan: FileOperationPlan | None = None


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
