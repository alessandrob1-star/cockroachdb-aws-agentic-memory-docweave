"""Explicit mapping from local operation contracts to persistence commands."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from uuid import UUID

from docweave.operations.approval import operation_plan_fingerprint
from docweave.operations.audit import AuditEvent
from docweave.operations.batch import (
    BatchItemState,
    OperationBatch,
    OperationBatchItem,
    operation_batch_fingerprint,
    operation_execution_key,
)
from docweave.operations.execution import ExecutionStatus
from docweave.operations.results import OperationResultRecord
from docweave.persistence.contracts import (
    AuditAppend,
    BatchItemSnapshot,
    CreateBatch,
    RecordExecutionIntent,
    RecordOperationResult,
)

RootReferenceResolver = Callable[[Path], str]
ActorIdentityResolver = Callable[[str], UUID]
_SHA256_BYTES = 32


@dataclass(frozen=True, slots=True)
class PersistenceIdentityMap:
    """Bind external domain identities to internal database UUIDs."""

    external_workspace_id: str
    external_batch_id: str
    workspace_id: UUID
    operation_batch_id: UUID
    file_operation_ids: Mapping[str, UUID]

    def __post_init__(self) -> None:
        if self.external_workspace_id.strip() == "":
            raise ValueError("external_workspace_id must not be empty")
        if self.external_batch_id.strip() == "":
            raise ValueError("external_batch_id must not be empty")
        if not self.file_operation_ids:
            raise ValueError("file_operation_ids must not be empty")
        if any(key.strip() == "" for key in self.file_operation_ids):
            raise ValueError("file_operation_ids keys must not be empty")
        if len(set(self.file_operation_ids.values())) != len(self.file_operation_ids):
            raise ValueError("file operation UUIDs must be unique")
        object.__setattr__(
            self,
            "file_operation_ids",
            MappingProxyType(dict(self.file_operation_ids)),
        )

    def operation_id_for(self, batch_item_id: str) -> UUID:
        """Resolve one item inside the explicitly bound batch."""
        try:
            return self.file_operation_ids[batch_item_id]
        except KeyError:
            raise ValueError("batch item has no persistence identity") from None


@dataclass(frozen=True, slots=True)
class ExecutionIntentMapping:
    """Database identities and lease data for one execution claim."""

    identities: PersistenceIdentityMap
    executor_actor_id: UUID
    lease_token: UUID
    lease_expires_at_utc: datetime


@dataclass(frozen=True, slots=True)
class OperationResultMapping:
    """Database identities and observed size for one terminal result."""

    identities: PersistenceIdentityMap
    event_actor_id: UUID
    actual_size: int | None

    def __post_init__(self) -> None:
        if self.actual_size is not None and self.actual_size < 0:
            raise ValueError("actual_size must not be negative")


def map_create_batch(
    batch: OperationBatch,
    audit_events: tuple[AuditEvent, ...],
    *,
    identities: PersistenceIdentityMap,
    resolve_root_reference: RootReferenceResolver,
    resolve_actor_identity: ActorIdentityResolver,
) -> CreateBatch:
    """Map an initial local batch without persisting absolute root paths."""
    _validate_batch_identity(batch, identities)
    item_ids = {item.item_id for item in batch.items}
    if item_ids != set(identities.file_operation_ids):
        raise ValueError("persistence item identities must exactly match the batch")

    items = tuple(
        _map_batch_item(
            item,
            identities=identities,
            resolve_root_reference=resolve_root_reference,
            created_at=batch.created_at_utc,
        )
        for item in batch.items
    )
    mapped_events = tuple(
        map_audit_event(
            event,
            identities=identities,
            resolve_actor_identity=resolve_actor_identity,
        )
        for event in audit_events
    )
    completed_at = (
        batch.created_at_utc
        if batch.state.value in {"completed", "completed_with_failures"}
        else None
    )
    return CreateBatch(
        operation_batch_id=identities.operation_batch_id,
        workspace_id=identities.workspace_id,
        external_batch_id=batch.batch_id,
        idempotency_key=batch.idempotency_key,
        operation=batch.operation,
        preview_sha256=_digest_bytes(
            "batch fingerprint",
            operation_batch_fingerprint(batch),
        ),
        preview_version=1,
        policy_version=batch.policy_version,
        correlation_id=batch.correlation_id,
        status=batch.state,
        created_by_actor_id=resolve_actor_identity(batch.created_by_user_id),
        created_at_utc=batch.created_at_utc,
        items=items,
        audit_events=mapped_events,
        completed_at_utc=completed_at,
    )


def map_execution_intent(
    batch: OperationBatch,
    item: OperationBatchItem,
    event: AuditEvent,
    *,
    mapping: ExecutionIntentMapping,
) -> RecordExecutionIntent:
    """Map a pre-mutation execution claim and its audit evidence."""
    identities = mapping.identities
    _validate_batch_identity(batch, identities)
    _validate_item_membership(batch, item)
    if item.state is not BatchItemState.APPROVED or item.approval is None:
        raise ValueError("execution intent requires an approved batch item")
    return RecordExecutionIntent(
        workspace_id=identities.workspace_id,
        operation_batch_id=identities.operation_batch_id,
        file_operation_id=identities.operation_id_for(item.item_id),
        execution_id=f"{batch.batch_id}:{item.item_id}",
        idempotency_key=operation_execution_key(batch, item),
        executor_actor_id=mapping.executor_actor_id,
        lease_token=mapping.lease_token,
        intent_recorded_at_utc=event.occurred_at_utc,
        lease_expires_at_utc=mapping.lease_expires_at_utc,
        audit_event=_map_audit_event_with_actor(
            event,
            identities=identities,
            actor_id=mapping.executor_actor_id,
        ),
    )


def map_operation_result(
    batch: OperationBatch,
    item: OperationBatchItem,
    result: OperationResultRecord,
    event: AuditEvent,
    *,
    mapping: OperationResultMapping,
) -> RecordOperationResult:
    """Map one observed terminal result without inventing file evidence."""
    identities = mapping.identities
    _validate_batch_identity(batch, identities)
    _validate_item_membership(batch, item)
    if item.approval is None:
        raise ValueError("operation result requires the bound item approval")
    if result.batch_id != batch.batch_id or result.batch_item_id != item.item_id:
        raise ValueError("operation result identity must match the batch item")
    terminal_state = _terminal_state(result.status)
    return RecordOperationResult(
        workspace_id=identities.workspace_id,
        operation_batch_id=identities.operation_batch_id,
        file_operation_id=identities.operation_id_for(item.item_id),
        execution_id=result.execution_id,
        idempotency_key=result.execution_key,
        terminal_state=terminal_state,
        reason=result.reason,
        disposition=result.disposition,
        completed_at_utc=result.completed_at_utc,
        source_exists_after=result.source_exists_after,
        destination_exists_after=result.destination_exists_after,
        actual_source_relative_path=item.plan.source_relative_path,
        actual_destination_relative_path=item.plan.destination_relative_path,
        actual_sha256=_optional_digest_bytes(
            "destination digest",
            result.destination_digest_after,
        ),
        actual_size=mapping.actual_size,
        error_category=(None if result.succeeded else result.reason.value),
        audit_event=_map_audit_event_with_actor(
            event,
            identities=identities,
            actor_id=mapping.event_actor_id,
        ),
    )


def map_audit_event(
    event: AuditEvent,
    *,
    identities: PersistenceIdentityMap,
    resolve_actor_identity: ActorIdentityResolver,
) -> AuditAppend:
    """Map one minimized local audit event to database identities."""
    return _map_audit_event_with_actor(
        event,
        identities=identities,
        actor_id=resolve_actor_identity(event.actor_id),
    )


def _map_batch_item(
    item: OperationBatchItem,
    *,
    identities: PersistenceIdentityMap,
    resolve_root_reference: RootReferenceResolver,
    created_at: datetime,
) -> BatchItemSnapshot:
    source_reference = _safe_root_reference(
        item.plan.source_root,
        resolve_root_reference,
    )
    destination_reference = _safe_root_reference(
        item.plan.destination_root,
        resolve_root_reference,
    )
    return BatchItemSnapshot(
        file_operation_id=identities.operation_id_for(item.item_id),
        batch_item_id=item.item_id,
        operation=item.plan.operation,
        plan_sha256=_digest_bytes(
            "plan fingerprint",
            operation_plan_fingerprint(item.plan),
        ),
        source_root_reference=source_reference,
        source_relative_path=item.plan.source_relative_path,
        destination_root_reference=destination_reference,
        destination_relative_path=item.plan.destination_relative_path,
        state=item.state,
        expected_source_sha256=_optional_digest_bytes(
            "expected source digest",
            item.expected_source_digest,
        ),
        expected_source_size=item.expected_source_byte_size,
        approval_id=None if item.approval is None else item.approval.approval_id,
        completed_at_utc=(created_at if item.state is BatchItemState.BLOCKED else None),
    )


def _map_audit_event_with_actor(
    event: AuditEvent,
    *,
    identities: PersistenceIdentityMap,
    actor_id: UUID,
) -> AuditAppend:
    if (
        event.workspace_id != identities.external_workspace_id
        or event.batch_id != identities.external_batch_id
    ):
        raise ValueError("audit event identity must match the persistence batch")
    file_operation_id = (
        None
        if event.batch_item_id is None
        else identities.operation_id_for(event.batch_item_id)
    )
    return AuditAppend(
        event_id=_uuid(event.event_id, field_name="audit event_id"),
        workspace_id=identities.workspace_id,
        actor_id=actor_id,
        actor_type=event.actor_type,
        correlation_id=event.correlation_id,
        event_type=event.event_type,
        subject_kind=(
            "operation_batch" if event.batch_item_id is None else "file_operation"
        ),
        subject_id=event.batch_id
        if event.batch_item_id is None
        else event.batch_item_id,
        occurred_at_utc=event.occurred_at_utc,
        operation_batch_id=identities.operation_batch_id,
        file_operation_id=file_operation_id,
        idempotency_key=event.idempotency_key,
        previous_state=event.previous_state,
        new_state=event.new_state,
        reason=event.reason,
        plan_sha256=_optional_digest_bytes(
            "audit plan fingerprint",
            event.plan_fingerprint,
        ),
        approval_id=event.approval_id,
        source_relative_path=event.source_relative_path,
        destination_relative_path=event.destination_relative_path,
        error_class=event.error_class,
        error_category=event.error_category,
    )


def _validate_batch_identity(
    batch: OperationBatch,
    identities: PersistenceIdentityMap,
) -> None:
    if (
        batch.workspace_id != identities.external_workspace_id
        or batch.batch_id != identities.external_batch_id
    ):
        raise ValueError("batch identity does not match the persistence identity map")


def _validate_item_membership(
    batch: OperationBatch,
    item: OperationBatchItem,
) -> None:
    if not any(candidate is item for candidate in batch.items):
        raise ValueError("operation item must be the exact batch snapshot member")


def _safe_root_reference(
    root: Path,
    resolver: RootReferenceResolver,
) -> str:
    reference = resolver(root)
    if (
        reference.strip() == ""
        or reference == str(root)
        or Path(reference).is_absolute()
        or PureWindowsPath(reference).is_absolute()
    ):
        raise ValueError("root resolver must return an opaque non-path reference")
    return reference


def _terminal_state(status: ExecutionStatus) -> BatchItemState:
    return {
        ExecutionStatus.BLOCKED: BatchItemState.BLOCKED,
        ExecutionStatus.SUCCEEDED: BatchItemState.SUCCEEDED,
        ExecutionStatus.FAILED: BatchItemState.FAILED,
        ExecutionStatus.VERIFICATION_FAILED: BatchItemState.VERIFICATION_FAILED,
    }[status]


def _digest_bytes(field_name: str, value: str) -> bytes:
    try:
        digest = bytes.fromhex(value)
    except ValueError:
        raise ValueError(f"{field_name} must be hexadecimal") from None
    if len(digest) != _SHA256_BYTES:
        raise ValueError(f"{field_name} must contain a SHA-256 digest")
    return digest


def _optional_digest_bytes(field_name: str, value: str | None) -> bytes | None:
    return None if value is None else _digest_bytes(field_name, value)


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a UUID") from None
