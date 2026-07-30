"""Typed application contracts for durable operation persistence."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

from docweave.operations.audit import AuditActorType, AuditEventType, normalize_utc
from docweave.operations.batch import BatchItemState, BatchState
from docweave.operations.execution import ExecutionReason
from docweave.operations.planning import FileOperation
from docweave.operations.results import ResultDisposition

_SHA256_BYTES = 32
_MAX_BATCH_ITEMS = 1_000


class PersistenceDisposition(StrEnum):
    """Outcome of an idempotent persistence command."""

    APPLIED = "applied"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True, slots=True)
class OperationExecutionIdentity:
    """Workspace-scoped identity for one persisted file operation."""

    workspace_id: UUID
    operation_batch_id: UUID
    file_operation_id: UUID


@dataclass(frozen=True, slots=True)
class PersistedOperationExecution:
    """Validated durable execution state used during restart recovery."""

    identity: OperationExecutionIdentity
    state: BatchItemState
    idempotency_key: str | None
    execution_id: str | None
    approval_id: str | None
    lease_expires_at_utc: datetime | None
    intent_recorded_at_utc: datetime | None
    started_at_utc: datetime | None
    completed_at_utc: datetime | None
    result_disposition: ResultDisposition | None
    expected_source_sha256: bytes | None
    actual_sha256: bytes | None
    actual_size: int | None
    source_exists_after: bool | None
    destination_exists_after: bool | None
    safe_error_summary: str | None
    error_category: str | None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("idempotency_key", self.idempotency_key),
            ("execution_id", self.execution_id),
        ):
            if value is not None:
                _require_text(field_name, value)
        _require_optional_digest(
            "expected_source_sha256",
            self.expected_source_sha256,
        )
        _require_optional_digest("actual_sha256", self.actual_sha256)
        if self.actual_size is not None and self.actual_size < 0:
            raise ValueError("actual_size must not be negative")

        for field_name in (
            "lease_expires_at_utc",
            "intent_recorded_at_utc",
            "started_at_utc",
            "completed_at_utc",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, normalize_utc(value))

        if self.state is BatchItemState.EXECUTING and (
            self.idempotency_key is None
            or self.execution_id is None
            or self.lease_expires_at_utc is None
            or self.intent_recorded_at_utc is None
        ):
            raise ValueError("executing state requires durable claim evidence")

        execution_terminal_states = {
            BatchItemState.BLOCKED,
            BatchItemState.SUCCEEDED,
            BatchItemState.FAILED,
            BatchItemState.VERIFICATION_FAILED,
        }
        if self.state in execution_terminal_states and (
            self.idempotency_key is None
            or self.execution_id is None
            or self.completed_at_utc is None
            or self.result_disposition is None
            or self.source_exists_after is None
            or self.destination_exists_after is None
            or self.safe_error_summary is None
        ):
            raise ValueError("terminal execution state requires result evidence")
        if self.state is BatchItemState.SUCCEEDED and (
            self.actual_sha256 is None
            or self.actual_size is None
            or self.destination_exists_after is not True
        ):
            raise ValueError(
                "successful persisted result requires destination evidence"
            )


@dataclass(frozen=True, slots=True)
class AuditAppend:
    """One append-only audit event without caller-controlled chain fields."""

    event_id: UUID
    workspace_id: UUID
    actor_id: UUID
    actor_type: AuditActorType
    correlation_id: str
    event_type: AuditEventType
    subject_kind: str
    subject_id: str
    occurred_at_utc: datetime
    operation_batch_id: UUID | None = None
    file_operation_id: UUID | None = None
    idempotency_key: str | None = None
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    plan_sha256: bytes | None = None
    approval_id: str | None = None
    source_relative_path: str | None = None
    destination_relative_path: str | None = None
    error_class: str | None = None
    error_category: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("correlation_id", self.correlation_id),
            ("subject_kind", self.subject_kind),
            ("subject_id", self.subject_id),
        ):
            _require_text(field_name, value)
        _require_optional_digest("plan_sha256", self.plan_sha256)
        _require_optional_relative_path(
            "source_relative_path",
            self.source_relative_path,
        )
        _require_optional_relative_path(
            "destination_relative_path",
            self.destination_relative_path,
        )
        object.__setattr__(self, "occurred_at_utc", normalize_utc(self.occurred_at_utc))


@dataclass(frozen=True, slots=True)
class BatchItemSnapshot:
    """Database-ready snapshot of one planned operation."""

    file_operation_id: UUID
    batch_item_id: str
    operation: FileOperation
    plan_sha256: bytes
    source_root_reference: str
    source_relative_path: str
    destination_root_reference: str
    destination_relative_path: str
    state: BatchItemState
    expected_source_sha256: bytes | None
    expected_source_size: int | None
    approval_id: str | None = None
    completed_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("batch_item_id", self.batch_item_id),
            ("source_root_reference", self.source_root_reference),
            ("destination_root_reference", self.destination_root_reference),
        ):
            _require_text(field_name, value)
        _require_relative_path("source_relative_path", self.source_relative_path)
        _require_relative_path(
            "destination_relative_path",
            self.destination_relative_path,
        )
        _require_digest("plan_sha256", self.plan_sha256)
        _require_optional_digest(
            "expected_source_sha256",
            self.expected_source_sha256,
        )
        if self.expected_source_size is not None and self.expected_source_size < 0:
            raise ValueError("expected_source_size must not be negative")
        if self.state in {
            BatchItemState.APPROVED,
            BatchItemState.EXECUTING,
            BatchItemState.SUCCEEDED,
        } and (
            self.approval_id is None
            or self.expected_source_sha256 is None
            or self.expected_source_size is None
        ):
            raise ValueError("approved or executing item requires bound preconditions")
        terminal = self.state in {
            BatchItemState.BLOCKED,
            BatchItemState.SUCCEEDED,
            BatchItemState.FAILED,
            BatchItemState.VERIFICATION_FAILED,
            BatchItemState.SKIPPED,
        }
        if terminal != (self.completed_at_utc is not None):
            raise ValueError("terminal item state and completed_at_utc must agree")
        if self.completed_at_utc is not None:
            object.__setattr__(
                self,
                "completed_at_utc",
                normalize_utc(self.completed_at_utc),
            )


@dataclass(frozen=True, slots=True)
class CreateBatch:
    """Atomic command for a batch, its items, and initial audit evidence."""

    operation_batch_id: UUID
    workspace_id: UUID
    external_batch_id: str
    idempotency_key: str
    operation: FileOperation
    preview_sha256: bytes
    preview_version: int
    policy_version: str
    correlation_id: str
    status: BatchState
    created_by_actor_id: UUID
    created_at_utc: datetime
    items: tuple[BatchItemSnapshot, ...]
    audit_events: tuple[AuditAppend, ...]
    completed_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("external_batch_id", self.external_batch_id),
            ("idempotency_key", self.idempotency_key),
            ("policy_version", self.policy_version),
            ("correlation_id", self.correlation_id),
        ):
            _require_text(field_name, value)
        _require_digest("preview_sha256", self.preview_sha256)
        if self.preview_version < 1:
            raise ValueError("preview_version must be positive")
        all_blocked = _validate_initial_batch_items(self)
        _validate_initial_batch_events(self)
        created_at = normalize_utc(self.created_at_utc)
        completed_at = _validate_batch_completion(self, all_blocked=all_blocked)
        if completed_at is not None and completed_at < created_at:
            raise ValueError("completed_at_utc must not precede created_at_utc")
        object.__setattr__(self, "created_at_utc", created_at)
        object.__setattr__(self, "completed_at_utc", completed_at)


@dataclass(frozen=True, slots=True)
class RecordExecutionIntent:
    """Atomic command that claims one approved item before file mutation."""

    workspace_id: UUID
    operation_batch_id: UUID
    file_operation_id: UUID
    execution_id: str
    idempotency_key: str
    executor_actor_id: UUID
    lease_token: UUID
    intent_recorded_at_utc: datetime
    lease_expires_at_utc: datetime
    audit_event: AuditAppend

    def __post_init__(self) -> None:
        _require_text("execution_id", self.execution_id)
        _require_text("idempotency_key", self.idempotency_key)
        intent_at = normalize_utc(self.intent_recorded_at_utc)
        lease_expires_at = normalize_utc(self.lease_expires_at_utc)
        if lease_expires_at <= intent_at:
            raise ValueError("lease_expires_at_utc must follow intent_recorded_at_utc")
        _require_matching_event(
            self.audit_event,
            workspace_id=self.workspace_id,
            operation_batch_id=self.operation_batch_id,
            file_operation_id=self.file_operation_id,
        )
        if (
            self.audit_event.event_type
            is not AuditEventType.ITEM_EXECUTION_INTENT_RECORDED
        ):
            raise ValueError("audit event must record execution intent")
        object.__setattr__(self, "intent_recorded_at_utc", intent_at)
        object.__setattr__(self, "lease_expires_at_utc", lease_expires_at)


@dataclass(frozen=True, slots=True)
class RecordOperationResult:
    """Atomic terminal result command paired with append-only evidence."""

    workspace_id: UUID
    operation_batch_id: UUID
    file_operation_id: UUID
    execution_id: str
    idempotency_key: str
    terminal_state: BatchItemState
    reason: ExecutionReason
    disposition: ResultDisposition
    completed_at_utc: datetime
    source_exists_after: bool
    destination_exists_after: bool
    actual_source_relative_path: str
    actual_destination_relative_path: str
    actual_sha256: bytes | None
    actual_size: int | None
    error_category: str | None
    audit_event: AuditAppend

    def __post_init__(self) -> None:
        _require_text("execution_id", self.execution_id)
        _require_text("idempotency_key", self.idempotency_key)
        _require_relative_path(
            "actual_source_relative_path",
            self.actual_source_relative_path,
        )
        _require_relative_path(
            "actual_destination_relative_path",
            self.actual_destination_relative_path,
        )
        if self.terminal_state not in {
            BatchItemState.BLOCKED,
            BatchItemState.SUCCEEDED,
            BatchItemState.FAILED,
            BatchItemState.VERIFICATION_FAILED,
        }:
            raise ValueError("terminal_state must be an execution result state")
        _require_optional_digest("actual_sha256", self.actual_sha256)
        if self.actual_size is not None and self.actual_size < 0:
            raise ValueError("actual_size must not be negative")
        if self.terminal_state is BatchItemState.SUCCEEDED and (
            self.actual_sha256 is None
            or self.actual_size is None
            or not self.destination_exists_after
        ):
            raise ValueError("successful result requires verified destination evidence")
        expected_event_type = (
            AuditEventType.ITEM_EXECUTION_RECONCILED
            if self.disposition is ResultDisposition.RECONCILED
            else {
                BatchItemState.BLOCKED: AuditEventType.ITEM_BLOCKED,
                BatchItemState.SUCCEEDED: AuditEventType.ITEM_EXECUTION_SUCCEEDED,
                BatchItemState.FAILED: AuditEventType.ITEM_EXECUTION_FAILED,
                BatchItemState.VERIFICATION_FAILED: (
                    AuditEventType.ITEM_VERIFICATION_FAILED
                ),
            }[self.terminal_state]
        )
        if self.audit_event.event_type is not expected_event_type:
            raise ValueError("terminal result requires matching audit event")
        _require_matching_event(
            self.audit_event,
            workspace_id=self.workspace_id,
            operation_batch_id=self.operation_batch_id,
            file_operation_id=self.file_operation_id,
        )
        object.__setattr__(
            self,
            "completed_at_utc",
            normalize_utc(self.completed_at_utc),
        )


class OperationPersistenceRepository(Protocol):
    """Application-facing durable operation persistence port."""

    def create_batch(self, command: CreateBatch) -> PersistenceDisposition: ...

    def record_execution_intent(
        self,
        command: RecordExecutionIntent,
    ) -> PersistenceDisposition: ...

    def record_operation_result(
        self,
        command: RecordOperationResult,
    ) -> PersistenceDisposition: ...

    def load_operation_execution(
        self,
        identity: OperationExecutionIdentity,
    ) -> PersistedOperationExecution | None: ...

    def append_audit_events(
        self,
        events: tuple[AuditAppend, ...],
    ) -> PersistenceDisposition: ...


def _validate_initial_batch_items(command: CreateBatch) -> bool:
    if not 1 <= len(command.items) <= _MAX_BATCH_ITEMS:
        raise ValueError("items must contain between 1 and 1000 entries")
    if len({item.batch_item_id for item in command.items}) != len(command.items):
        raise ValueError("batch_item_id must be unique within a batch")
    if len({item.file_operation_id for item in command.items}) != len(command.items):
        raise ValueError("file_operation_id must be unique within a batch")
    if any(item.operation is not command.operation for item in command.items):
        raise ValueError("all batch items must use the batch operation")
    if any(
        item.state not in {BatchItemState.PLANNED, BatchItemState.BLOCKED}
        for item in command.items
    ):
        raise ValueError("new batch items must be planned or blocked")
    return all(item.state is BatchItemState.BLOCKED for item in command.items)


def _validate_initial_batch_events(command: CreateBatch) -> None:
    if len({event.event_id for event in command.audit_events}) != len(
        command.audit_events
    ):
        raise ValueError("audit event_id must be unique within a command")
    if any(
        event.workspace_id != command.workspace_id for event in command.audit_events
    ):
        raise ValueError("audit event workspace must match the batch workspace")
    if any(
        event.operation_batch_id != command.operation_batch_id
        for event in command.audit_events
    ):
        raise ValueError("audit event batch identity must match the batch")
    operation_ids = {item.file_operation_id for item in command.items}
    if any(
        event.file_operation_id is not None
        and event.file_operation_id not in operation_ids
        for event in command.audit_events
    ):
        raise ValueError("audit event operation must belong to the batch")
    event_times = [event.occurred_at_utc for event in command.audit_events]
    if event_times != sorted(event_times):
        raise ValueError("audit events must be ordered by occurred_at_utc")


def _validate_batch_completion(
    command: CreateBatch,
    *,
    all_blocked: bool,
) -> datetime | None:
    permitted_statuses = (
        {BatchState.COMPLETED_WITH_FAILURES}
        if all_blocked
        else {BatchState.DRAFT, BatchState.READY_FOR_APPROVAL}
    )
    if command.status not in permitted_statuses:
        raise ValueError("new batch status must agree with its initial items")
    completed_at = (
        None
        if command.completed_at_utc is None
        else normalize_utc(command.completed_at_utc)
    )
    if all_blocked != (completed_at is not None):
        raise ValueError("completed_at_utc must be set only for terminal batches")
    return completed_at


def _require_matching_event(
    event: AuditAppend,
    *,
    workspace_id: UUID,
    operation_batch_id: UUID,
    file_operation_id: UUID,
) -> None:
    if (
        event.workspace_id != workspace_id
        or event.operation_batch_id != operation_batch_id
        or event.file_operation_id != file_operation_id
    ):
        raise ValueError("audit event identities must match the operation command")


def _require_digest(field_name: str, value: bytes) -> None:
    if len(value) != _SHA256_BYTES:
        raise ValueError(f"{field_name} must contain a 32-byte SHA-256 digest")


def _require_optional_digest(field_name: str, value: bytes | None) -> None:
    if value is not None:
        _require_digest(field_name, value)


def _require_text(field_name: str, value: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")


def _require_relative_path(field_name: str, value: str) -> None:
    path = PurePosixPath(value)
    if (
        value.strip() == ""
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")


def _require_optional_relative_path(field_name: str, value: str | None) -> None:
    if value is not None:
        _require_relative_path(field_name, value)
