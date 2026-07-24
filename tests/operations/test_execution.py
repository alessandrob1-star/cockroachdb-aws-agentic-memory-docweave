from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from docweave.core.fingerprints import ContentFingerprint, compute_sha256_fingerprint
from docweave.operations import (
    ExecutionReason,
    ExecutionStatus,
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    OperationApproval,
    approve_operation_plan,
    execute_file_operation,
    plan_file_operation,
)


def write_file(path: Path, content: bytes = b"content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def approved_plan(
    tmp_path: Path,
    *,
    operation: FileOperation,
    destination_relative_path: str = "organized/invoice.pdf",
) -> tuple[FileOperationPlan, OperationApproval, datetime]:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "workspace"
    write_file(source_root / "invoice.pdf", b"%PDF-1.7\ncontent")
    destination_root.mkdir()
    plan = plan_file_operation(
        FileOperationRequest(
            operation=operation,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path=destination_relative_path,
        ),
    )
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    approval = approve_operation_plan(
        plan,
        approval_id="approval-001",
        approved_by_user_id="reviewer-001",
        approved_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )
    return plan, approval, now


def test_executes_approved_copy_and_verifies_result(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.succeeded is True
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.reason is ExecutionReason.SUCCEEDED
    assert result.source_exists_after is True
    assert result.destination_exists_after is True
    assert plan.source_path is not None
    assert plan.destination_path is not None
    assert plan.source_path.read_bytes() == plan.destination_path.read_bytes()
    assert result.source_digest_before == result.destination_digest_after


def test_executes_approved_move_and_removes_source(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.MOVE)

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.reason is ExecutionReason.SUCCEEDED
    assert result.source_exists_after is False
    assert result.destination_exists_after is True
    assert plan.source_path is not None
    assert plan.destination_path is not None
    assert not plan.source_path.exists()
    assert plan.destination_path.read_bytes() == b"%PDF-1.7\ncontent"


def test_blocks_missing_execution_id(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    result = execute_file_operation(
        plan,
        approval,
        execution_id=" ",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason is ExecutionReason.EXECUTION_ID_MISSING
    assert result.destination_exists_after is False


def test_blocks_invalid_approval_without_mutating_files(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=30),
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason is ExecutionReason.APPROVAL_INVALID
    assert result.error == "approval_expired"
    assert result.destination_exists_after is False


def test_blocks_if_destination_appears_after_approval(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)
    assert plan.destination_path is not None
    write_file(plan.destination_path, b"collision")

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason is ExecutionReason.DESTINATION_COLLISION
    assert plan.destination_path.read_bytes() == b"collision"


def test_blocks_if_source_disappears_after_approval(tmp_path: Path) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)
    assert plan.source_path is not None
    plan.source_path.unlink()

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason is ExecutionReason.PLAN_CHANGED_BEFORE_EXECUTION
    assert result.destination_exists_after is False


def test_reports_file_operation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    def fake_copyfileobj(*_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr(
        "docweave.operations.execution.shutil.copyfileobj", fake_copyfileobj
    )

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.reason is ExecutionReason.FILE_OPERATION_FAILED
    assert result.error == "OSError"


def test_blocks_exclusive_write_race_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    def fake_copy(_plan: FileOperationPlan) -> None:
        raise FileExistsError

    monkeypatch.setattr(
        "docweave.operations.execution._copy_file_exclusively",
        fake_copy,
    )

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason is ExecutionReason.DESTINATION_COLLISION
    assert result.error == "FileExistsError"


def test_reports_digest_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)
    original_compute = compute_sha256_fingerprint

    def fake_compute(path: Path) -> ContentFingerprint:
        fingerprint = original_compute(path)
        if path == plan.destination_path:
            return type(fingerprint)(
                algorithm=fingerprint.algorithm,
                digest=b"x" * 32,
                byte_size=fingerprint.byte_size,
            )
        return fingerprint

    monkeypatch.setattr(
        "docweave.operations.execution.compute_sha256_fingerprint",
        fake_compute,
    )

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.VERIFICATION_FAILED
    assert result.reason is ExecutionReason.SOURCE_DIGEST_MISMATCH


def test_reports_final_state_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.MOVE)

    def fake_source_exists(_plan: FileOperationPlan) -> bool:
        return True

    monkeypatch.setattr(
        "docweave.operations.execution._source_exists",
        fake_source_exists,
    )

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.VERIFICATION_FAILED
    assert result.reason is ExecutionReason.VERIFICATION_FAILED
    assert result.source_exists_after is True
    assert result.destination_exists_after is True


def test_reports_missing_destination_after_copy_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, approval, now = approved_plan(tmp_path, operation=FileOperation.COPY)

    def fake_destination_exists(_plan: FileOperationPlan) -> bool:
        return False

    monkeypatch.setattr(
        "docweave.operations.execution._destination_exists",
        fake_destination_exists,
    )

    result = execute_file_operation(
        plan,
        approval,
        execution_id="execution-001",
        now_utc=now + timedelta(minutes=1),
    )

    assert result.status is ExecutionStatus.VERIFICATION_FAILED
    assert result.reason is ExecutionReason.VERIFICATION_FAILED
    assert result.source_exists_after is True
    assert result.destination_exists_after is False
