from datetime import UTC, datetime, timedelta
from pathlib import Path

from docweave.operations import (
    ApprovalValidationReason,
    ApprovalValidationStatus,
    FileOperation,
    FileOperationPlan,
    FileOperationReason,
    FileOperationRequest,
    FileOperationStatus,
    OperationApproval,
    approve_operation_plan,
    operation_plan_fingerprint,
    plan_file_operation,
    validate_operation_approval,
)


def write_file(path: Path, content: bytes = b"content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def ready_plan(tmp_path: Path) -> FileOperationPlan:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()
    return plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="Invoices/invoice.pdf",
        ),
    )


def test_validates_current_human_approval_for_exact_ready_plan(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    approved_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=approved_at,
        expires_at_utc=approved_at + timedelta(minutes=15),
    )

    validation = validate_operation_approval(
        plan,
        approval,
        now_utc=approved_at + timedelta(minutes=1),
    )

    assert validation.is_valid is True
    assert validation.status is ApprovalValidationStatus.VALID
    assert validation.reason is ApprovalValidationReason.VALID
    assert validation.approval_id == "approval-001"
    assert validation.plan_fingerprint == operation_plan_fingerprint(plan)
    assert approval.plan_fingerprint == validation.plan_fingerprint


def test_blocks_approval_for_non_ready_plan(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "invoice.pdf", b"collision")
    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )
    assert plan.status is FileOperationStatus.COLLISION
    assert plan.reason is FileOperationReason.DESTINATION_COLLISION
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )

    validation = validate_operation_approval(plan, approval, now_utc=now)

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.PLAN_NOT_READY


def test_blocks_missing_approval_id(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id=" ",
        approved_by_user_id="reviewer-001",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )

    validation = validate_operation_approval(plan, approval, now_utc=now)

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.MISSING_APPROVAL_ID


def test_blocks_missing_approver(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id=" ",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )

    validation = validate_operation_approval(plan, approval, now_utc=now)

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.MISSING_APPROVER


def test_blocks_approval_for_changed_plan(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )
    changed_plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=plan.source_root,
            source_relative_path="invoice.pdf",
            destination_root=plan.destination_root,
            destination_relative_path="Invoices/changed.pdf",
        ),
    )

    validation = validate_operation_approval(changed_plan, approval, now_utc=now)

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.PLAN_FINGERPRINT_MISMATCH


def test_blocks_approval_before_effective_time(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    approved_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=approved_at,
        expires_at_utc=approved_at + timedelta(minutes=15),
    )

    validation = validate_operation_approval(
        plan,
        approval,
        now_utc=approved_at - timedelta(seconds=1),
    )

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.APPROVAL_NOT_YET_EFFECTIVE


def test_blocks_expired_approval(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    approved_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=approved_at,
        expires_at_utc=approved_at + timedelta(minutes=15),
    )

    validation = validate_operation_approval(
        plan,
        approval,
        now_utc=approved_at + timedelta(minutes=15),
    )

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.APPROVAL_EXPIRED


def test_normalizes_naive_datetimes_as_utc(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    approved_at = datetime(2026, 7, 24, 8, 0)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=approved_at,
        expires_at_utc=approved_at + timedelta(minutes=15),
    )

    validation = validate_operation_approval(
        plan,
        approval,
        now_utc=approved_at + timedelta(minutes=1),
    )

    assert approval.approved_at_utc.tzinfo is UTC
    assert approval.expires_at_utc.tzinfo is UTC
    assert validation.status is ApprovalValidationStatus.VALID


def test_blocks_manually_tampered_fingerprint(tmp_path: Path) -> None:
    plan = ready_plan(tmp_path)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval = OperationApproval(
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
        plan_fingerprint="not-the-plan",
    )

    validation = validate_operation_approval(plan, approval, now_utc=now)

    assert validation.status is ApprovalValidationStatus.BLOCKED
    assert validation.reason is ApprovalValidationReason.PLAN_FINGERPRINT_MISMATCH
