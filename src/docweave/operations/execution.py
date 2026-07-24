"""Approved local file operation execution primitives."""

import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.operations.approval import (
    ApprovalValidationStatus,
    OperationApproval,
    operation_plan_fingerprint,
    validate_operation_approval,
)
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationReason,
    plan_file_operation,
)


class ExecutionStatus(StrEnum):
    """Result status for an approved local file operation execution."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    VERIFICATION_FAILED = "verification_failed"


class ExecutionReason(StrEnum):
    """Machine-readable execution result reason."""

    SUCCEEDED = "succeeded"
    APPROVAL_INVALID = "approval_invalid"
    DESTINATION_COLLISION = "destination_collision"
    EXECUTION_ID_MISSING = "execution_id_missing"
    FILE_OPERATION_FAILED = "file_operation_failed"
    PLAN_CHANGED_BEFORE_EXECUTION = "plan_changed_before_execution"
    PLAN_NOT_READY = "plan_not_ready"
    SOURCE_DIGEST_MISMATCH = "source_digest_mismatch"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of one approved local file operation."""

    execution_id: str
    status: ExecutionStatus
    reason: ExecutionReason
    plan_fingerprint: str
    approval_id: str | None
    source_exists_after: bool
    destination_exists_after: bool
    source_digest_before: str | None = None
    destination_digest_after: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is ExecutionStatus.SUCCEEDED


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    plan: FileOperationPlan
    approval: OperationApproval
    execution_id: str


@dataclass(frozen=True, slots=True)
class _ExecutionEvidence:
    source_digest_before: str | None = None
    destination_digest_after: str | None = None
    error: str | None = None


def execute_file_operation(
    plan: FileOperationPlan,
    approval: OperationApproval,
    *,
    execution_id: str,
    now_utc: datetime,
) -> ExecutionResult:
    """Execute one approved local file operation and verify the filesystem state."""
    context = _ExecutionContext(
        plan=plan,
        approval=approval,
        execution_id=execution_id,
    )
    blocker = _pre_execution_blocker(context, now_utc)
    if blocker is not None:
        return blocker

    return _perform_execution(context)


def _pre_execution_blocker(
    context: _ExecutionContext,
    now_utc: datetime,
) -> ExecutionResult | None:
    plan = context.plan
    if context.execution_id.strip() == "":
        return _result(
            context,
            status=ExecutionStatus.BLOCKED,
            reason=ExecutionReason.EXECUTION_ID_MISSING,
        )

    approval_validation = validate_operation_approval(
        plan,
        context.approval,
        now_utc=now_utc,
    )
    if approval_validation.status is ApprovalValidationStatus.BLOCKED:
        return _result(
            status=ExecutionStatus.BLOCKED,
            reason=ExecutionReason.APPROVAL_INVALID,
            context=context,
            evidence=_ExecutionEvidence(error=approval_validation.reason.value),
        )

    try:
        current_plan = plan_file_operation(plan.request)
    except (OSError, ValueError) as exc:
        return _result(
            context,
            status=ExecutionStatus.BLOCKED,
            reason=ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION,
            evidence=_ExecutionEvidence(error=exc.__class__.__name__),
        )
    if operation_plan_fingerprint(current_plan) != operation_plan_fingerprint(plan):
        return _result(
            context,
            status=ExecutionStatus.BLOCKED,
            reason=_changed_plan_reason(current_plan),
        )

    return None


def _perform_execution(context: _ExecutionContext) -> ExecutionResult:
    plan = context.plan
    source_path = cast(Path, plan.source_path)
    destination_path = cast(Path, plan.destination_path)
    try:
        source_digest_before = compute_sha256_fingerprint(source_path).hex_digest
    except OSError as exc:
        return _result(
            context,
            status=ExecutionStatus.BLOCKED,
            reason=ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION,
            evidence=_ExecutionEvidence(error=exc.__class__.__name__),
        )
    try:
        for directory in plan.planned_parent_directories:
            directory.mkdir(exist_ok=True)
        _copy_file_exclusively(plan)
        destination_digest_after = compute_sha256_fingerprint(
            destination_path,
        ).hex_digest
        if source_digest_before != destination_digest_after:
            return _result(
                context,
                status=ExecutionStatus.VERIFICATION_FAILED,
                reason=ExecutionReason.SOURCE_DIGEST_MISMATCH,
                evidence=_ExecutionEvidence(
                    source_digest_before=source_digest_before,
                    destination_digest_after=destination_digest_after,
                ),
            )

        if plan.operation is FileOperation.MOVE:
            source_path.unlink()
    except FileExistsError as exc:
        return _result(
            context,
            status=ExecutionStatus.BLOCKED,
            reason=ExecutionReason.DESTINATION_COLLISION,
            evidence=_ExecutionEvidence(
                source_digest_before=source_digest_before,
                error=exc.__class__.__name__,
            ),
        )
    except OSError as exc:
        destination_may_exist = _destination_exists(plan)
        return _result(
            context,
            status=(
                ExecutionStatus.VERIFICATION_FAILED
                if destination_may_exist
                else ExecutionStatus.FAILED
            ),
            reason=(
                ExecutionReason.VERIFICATION_FAILED
                if destination_may_exist
                else ExecutionReason.FILE_OPERATION_FAILED
            ),
            evidence=_ExecutionEvidence(
                source_digest_before=source_digest_before,
                error=exc.__class__.__name__,
            ),
        )

    return _verify_result(
        context,
        source_digest_before=source_digest_before,
        destination_digest_after=destination_digest_after,
    )


def _copy_file_exclusively(plan: FileOperationPlan) -> None:
    source_path = cast(Path, plan.source_path)
    destination_path = cast(Path, plan.destination_path)

    with (
        source_path.open("rb") as source,
        destination_path.open("xb") as destination,
    ):
        shutil.copyfileobj(source, destination)
    shutil.copystat(source_path, destination_path)


def _verify_result(
    context: _ExecutionContext,
    *,
    source_digest_before: str,
    destination_digest_after: str,
) -> ExecutionResult:
    plan = context.plan
    source_exists_after = _source_exists(plan)
    destination_exists_after = _destination_exists(plan)
    expected_source_exists = plan.operation is FileOperation.COPY
    if (
        source_exists_after is not expected_source_exists
        or not destination_exists_after
    ):
        return _result(
            context,
            status=ExecutionStatus.VERIFICATION_FAILED,
            reason=ExecutionReason.VERIFICATION_FAILED,
            evidence=_ExecutionEvidence(
                source_digest_before=source_digest_before,
                destination_digest_after=destination_digest_after,
            ),
        )

    return _result(
        context,
        status=ExecutionStatus.SUCCEEDED,
        reason=ExecutionReason.SUCCEEDED,
        evidence=_ExecutionEvidence(
            source_digest_before=source_digest_before,
            destination_digest_after=destination_digest_after,
        ),
    )


def _changed_plan_reason(current_plan: FileOperationPlan) -> ExecutionReason:
    if current_plan.reason is FileOperationReason.DESTINATION_COLLISION:
        return ExecutionReason.DESTINATION_COLLISION
    return ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION


def _result(
    context: _ExecutionContext,
    status: ExecutionStatus,
    reason: ExecutionReason,
    evidence: _ExecutionEvidence | None = None,
) -> ExecutionResult:
    plan = context.plan
    active_evidence = evidence or _ExecutionEvidence()
    return ExecutionResult(
        execution_id=context.execution_id,
        status=status,
        reason=reason,
        plan_fingerprint=operation_plan_fingerprint(plan),
        approval_id=context.approval.approval_id,
        source_exists_after=_source_exists(plan),
        destination_exists_after=_destination_exists(plan),
        source_digest_before=active_evidence.source_digest_before,
        destination_digest_after=active_evidence.destination_digest_after,
        error=active_evidence.error,
    )


def _source_exists(plan: FileOperationPlan) -> bool:
    return plan.source_path is not None and plan.source_path.exists()


def _destination_exists(plan: FileOperationPlan) -> bool:
    return plan.destination_path is not None and plan.destination_path.exists()
