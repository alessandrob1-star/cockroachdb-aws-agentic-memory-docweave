"""Human approval contracts for planned local file operations."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from docweave.operations.planning import FileOperationPlan, FileOperationStatus


class ApprovalValidationStatus(StrEnum):
    """Result status for approval validation."""

    VALID = "valid"
    BLOCKED = "blocked"


class ApprovalValidationReason(StrEnum):
    """Machine-readable approval validation reason."""

    VALID = "valid"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_NOT_YET_EFFECTIVE = "approval_not_yet_effective"
    MISSING_APPROVAL_ID = "missing_approval_id"
    MISSING_APPROVER = "missing_approver"
    PLAN_FINGERPRINT_MISMATCH = "plan_fingerprint_mismatch"
    PLAN_NOT_READY = "plan_not_ready"


@dataclass(frozen=True, slots=True)
class OperationApproval:
    """Human approval bound to one exact file operation plan."""

    approval_id: str
    approved_by_user_id: str
    approved_at_utc: datetime
    expires_at_utc: datetime
    plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class ApprovalValidation:
    """Deterministic validation result for a planned operation approval."""

    status: ApprovalValidationStatus
    reason: ApprovalValidationReason
    plan_fingerprint: str
    approval_id: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status is ApprovalValidationStatus.VALID


def approve_operation_plan(
    plan: FileOperationPlan,
    *,
    approval_id: str,
    approved_by_user_id: str,
    approved_at_utc: datetime,
    expires_at_utc: datetime,
) -> OperationApproval:
    """Create an immutable approval for an exact ready operation plan."""
    return OperationApproval(
        approval_id=approval_id,
        approved_by_user_id=approved_by_user_id,
        approved_at_utc=_normalize_utc(approved_at_utc),
        expires_at_utc=_normalize_utc(expires_at_utc),
        plan_fingerprint=operation_plan_fingerprint(plan),
    )


def validate_operation_approval(
    plan: FileOperationPlan,
    approval: OperationApproval,
    *,
    now_utc: datetime,
) -> ApprovalValidation:
    """Validate that an approval still authorizes exactly this operation plan."""
    expected_fingerprint = operation_plan_fingerprint(plan)
    now_utc = _normalize_utc(now_utc)

    status = ApprovalValidationStatus.VALID
    reason = ApprovalValidationReason.VALID

    if plan.status is not FileOperationStatus.READY:
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.PLAN_NOT_READY
    elif approval.approval_id.strip() == "":
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.MISSING_APPROVAL_ID
    elif approval.approved_by_user_id.strip() == "":
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.MISSING_APPROVER
    elif approval.plan_fingerprint != expected_fingerprint:
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.PLAN_FINGERPRINT_MISMATCH
    elif now_utc < _normalize_utc(approval.approved_at_utc):
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.APPROVAL_NOT_YET_EFFECTIVE
    elif now_utc >= _normalize_utc(approval.expires_at_utc):
        status = ApprovalValidationStatus.BLOCKED
        reason = ApprovalValidationReason.APPROVAL_EXPIRED

    return ApprovalValidation(
        status=status,
        reason=reason,
        plan_fingerprint=expected_fingerprint,
        approval_id=approval.approval_id,
    )


def operation_plan_fingerprint(plan: FileOperationPlan) -> str:
    """Return a stable fingerprint for the exact user-visible operation plan."""
    payload = {
        "operation": plan.operation.value,
        "source_root": plan.source_root.as_posix(),
        "source_relative_path": plan.source_relative_path,
        "destination_root": plan.destination_root.as_posix(),
        "destination_relative_path": plan.destination_relative_path,
        "destination_comparison_key": plan.destination_comparison_key,
        "planned_parent_directories": [
            path.as_posix() for path in plan.planned_parent_directories
        ],
        "status": plan.status.value,
        "reason": plan.reason.value,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
