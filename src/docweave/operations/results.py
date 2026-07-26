"""Operation result records and local idempotency ledger contracts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Protocol

from docweave.operations.audit import normalize_utc
from docweave.operations.execution import ExecutionReason, ExecutionStatus


class ResultDisposition(StrEnum):
    """How an operation result was obtained."""

    EXECUTED = "executed"
    PRECONDITION_BLOCKED = "precondition_blocked"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    RECONCILED = "reconciled"


@dataclass(frozen=True, slots=True)
class OperationResultRecord:
    """Normalized per-item outcome suitable for later durable persistence."""

    batch_id: str
    batch_item_id: str
    execution_key: str
    execution_id: str
    status: ExecutionStatus
    reason: ExecutionReason
    disposition: ResultDisposition
    attempted_at_utc: datetime
    completed_at_utc: datetime
    approval_id: str | None
    source_exists_after: bool
    destination_exists_after: bool
    source_digest_before: str | None = None
    destination_digest_after: str | None = None
    error_class: str | None = None

    def __post_init__(self) -> None:
        """Normalize timestamps and validate stable identifiers."""
        for field_name, value in (
            ("batch_id", self.batch_id),
            ("batch_item_id", self.batch_item_id),
            ("execution_key", self.execution_key),
            ("execution_id", self.execution_id),
        ):
            if value.strip() == "":
                raise ValueError(f"{field_name} must not be empty")
        attempted_at = normalize_utc(self.attempted_at_utc)
        completed_at = normalize_utc(self.completed_at_utc)
        if completed_at < attempted_at:
            raise ValueError("completed_at_utc must not precede attempted_at_utc")
        object.__setattr__(self, "attempted_at_utc", attempted_at)
        object.__setattr__(self, "completed_at_utc", completed_at)

    @property
    def succeeded(self) -> bool:
        """Return whether execution has a verified successful outcome."""
        return self.status is ExecutionStatus.SUCCEEDED


class ExecutionLedger(Protocol):
    """Idempotency and interrupted-execution state used by batch execution."""

    def result_for(self, execution_key: str) -> OperationResultRecord | None: ...

    def is_in_progress(
        self,
        execution_key: str,
        *,
        now_utc: datetime | None = None,
    ) -> bool: ...

    def record_intent(self, execution_key: str) -> None: ...

    def record_result(self, result: OperationResultRecord) -> None: ...


class InMemoryExecutionLedger(ExecutionLedger):
    """Thread-safe non-persistent intent and result registry.

    This object models idempotency and interrupted execution semantics locally.
    CockroachDB must replace it as the durable authority in the product.
    """

    def __init__(self) -> None:
        self._in_progress: set[str] = set()
        self._results: dict[str, OperationResultRecord] = {}
        self._lock = RLock()

    def result_for(self, execution_key: str) -> OperationResultRecord | None:
        """Return the prior terminal result for an execution key."""
        with self._lock:
            return self._results.get(execution_key)

    def is_in_progress(
        self,
        execution_key: str,
        *,
        now_utc: datetime | None = None,
    ) -> bool:
        """Return whether intent exists without a terminal result."""
        with self._lock:
            return execution_key in self._in_progress

    def record_intent(self, execution_key: str) -> None:
        """Record pre-mutation intent, rejecting terminal-key reuse."""
        if execution_key.strip() == "":
            raise ValueError("execution_key must not be empty")
        with self._lock:
            if execution_key in self._results:
                raise ValueError("execution_key already has a terminal result")
            self._in_progress.add(execution_key)

    def record_result(self, result: OperationResultRecord) -> None:
        """Complete an intent exactly once with a terminal result."""
        with self._lock:
            existing = self._results.get(result.execution_key)
            if existing is not None and existing != result:
                raise ValueError("execution_key already has a different result")
            self._results[result.execution_key] = result
            self._in_progress.discard(result.execution_key)
