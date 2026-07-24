from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from docweave.operations import (
    ExecutionReason,
    ExecutionStatus,
    InMemoryExecutionLedger,
    OperationResultRecord,
    ResultDisposition,
)


def result_record(
    *,
    execution_key: str = "execution-key-001",
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
) -> OperationResultRecord:
    timestamp = datetime(2026, 7, 24, 9, 0)
    return OperationResultRecord(
        batch_id="batch-001",
        batch_item_id="item-001",
        execution_key=execution_key,
        execution_id="execution-001",
        status=status,
        reason=ExecutionReason.SUCCEEDED,
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=timestamp,
        completed_at_utc=timestamp,
        approval_id="approval-001",
        source_exists_after=True,
        destination_exists_after=True,
    )


def test_result_normalizes_timestamps_and_reports_success() -> None:
    result = result_record()

    assert result.succeeded is True
    assert result.attempted_at_utc.tzinfo is UTC
    assert result.completed_at_utc.tzinfo is UTC
    assert replace(result, status=ExecutionStatus.FAILED).succeeded is False


@pytest.mark.parametrize(
    "field_name",
    ["batch_id", "batch_item_id", "execution_key", "execution_id"],
)
def test_result_rejects_blank_stable_identifier(field_name: str) -> None:
    values = {
        "batch_id": "batch-001",
        "batch_item_id": "item-001",
        "execution_key": "execution-key-001",
        "execution_id": "execution-001",
    }
    values[field_name] = " "
    timestamp = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        OperationResultRecord(
            **values,
            status=ExecutionStatus.SUCCEEDED,
            reason=ExecutionReason.SUCCEEDED,
            disposition=ResultDisposition.EXECUTED,
            attempted_at_utc=timestamp,
            completed_at_utc=timestamp,
            approval_id=None,
            source_exists_after=True,
            destination_exists_after=True,
        )


def test_result_rejects_completion_before_attempt() -> None:
    timestamp = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="must not precede"):
        OperationResultRecord(
            batch_id="batch-001",
            batch_item_id="item-001",
            execution_key="execution-key-001",
            execution_id="execution-001",
            status=ExecutionStatus.FAILED,
            reason=ExecutionReason.FILE_OPERATION_FAILED,
            disposition=ResultDisposition.EXECUTED,
            attempted_at_utc=timestamp,
            completed_at_utc=timestamp - timedelta(seconds=1),
            approval_id=None,
            source_exists_after=True,
            destination_exists_after=False,
        )


def test_ledger_records_intent_and_terminal_result() -> None:
    ledger = InMemoryExecutionLedger()
    result = result_record()

    assert ledger.result_for(result.execution_key) is None
    assert ledger.is_in_progress(result.execution_key) is False
    ledger.record_intent(result.execution_key)
    assert ledger.is_in_progress(result.execution_key) is True
    ledger.record_result(result)

    assert ledger.result_for(result.execution_key) == result
    assert ledger.is_in_progress(result.execution_key) is False


def test_ledger_rejects_blank_intent_key_and_terminal_key_reuse() -> None:
    ledger = InMemoryExecutionLedger()
    result = result_record()
    ledger.record_result(result)

    with pytest.raises(ValueError, match="must not be empty"):
        ledger.record_intent(" ")
    with pytest.raises(ValueError, match="terminal result"):
        ledger.record_intent(result.execution_key)


def test_ledger_accepts_same_result_but_rejects_conflicting_result() -> None:
    ledger = InMemoryExecutionLedger()
    result = result_record()
    ledger.record_result(result)
    ledger.record_result(result)

    with pytest.raises(ValueError, match="different result"):
        ledger.record_result(
            replace(
                result,
                status=ExecutionStatus.FAILED,
                reason=ExecutionReason.FILE_OPERATION_FAILED,
            )
        )
