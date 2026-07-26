"""Durable lifecycle recorder used around local filesystem execution."""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from docweave.operations.audit import AuditEvent, normalize_utc
from docweave.operations.batch import (
    BatchItemState,
    OperationBatch,
    OperationBatchItem,
    OperationLifecycleRecorder,
    operation_execution_key,
)
from docweave.operations.execution import ExecutionReason, ExecutionStatus
from docweave.operations.results import (
    ExecutionLedger,
    InMemoryExecutionLedger,
    OperationResultRecord,
)
from docweave.persistence.contracts import (
    OperationExecutionIdentity,
    OperationPersistenceRepository,
    PersistedOperationExecution,
)
from docweave.persistence.mappers import (
    ActorIdentityResolver,
    ExecutionIntentMapping,
    OperationResultMapping,
    PersistenceIdentityMap,
    map_audit_event,
    map_execution_intent,
    map_operation_result,
)
from docweave.persistence.operation_repository import PersistenceConflictError

LeaseTokenFactory = Callable[[], UUID]


class PersistenceEvidenceError(RuntimeError):
    """Required post-mutation evidence could not be observed safely."""


class ActiveExecutionLeaseError(RuntimeError):
    """A different process may still own the durable execution claim."""

    def __init__(self, retry_after_utc: datetime) -> None:
        super().__init__("operation execution lease is still active")
        self.retry_after_utc = normalize_utc(retry_after_utc)


class DurableExecutionLedger(ExecutionLedger):
    """Load restart state without allowing active claims to be reconciled."""

    def __init__(
        self,
        repository: OperationPersistenceRepository,
        *,
        batch: OperationBatch,
        identities: PersistenceIdentityMap,
    ) -> None:
        if (
            batch.workspace_id != identities.external_workspace_id
            or batch.batch_id != identities.external_batch_id
        ):
            raise ValueError("batch does not match persistence identities")
        if {item.item_id for item in batch.items} != set(identities.file_operation_ids):
            raise ValueError("persistence item identities must exactly match the batch")

        self._repository = repository
        self._local = InMemoryExecutionLedger()
        self._external_batch_id = batch.batch_id
        self._items: dict[
            str, tuple[OperationBatchItem, OperationExecutionIdentity]
        ] = {}
        for item in batch.items:
            execution_key = operation_execution_key(batch, item)
            if execution_key in self._items:
                raise ValueError("batch contains duplicate operation execution keys")
            self._items[execution_key] = (
                item,
                OperationExecutionIdentity(
                    workspace_id=identities.workspace_id,
                    operation_batch_id=identities.operation_batch_id,
                    file_operation_id=identities.operation_id_for(item.item_id),
                ),
            )
        self._loaded: dict[str, PersistedOperationExecution | None] = {}

    def result_for(self, execution_key: str) -> OperationResultRecord | None:
        """Return a validated terminal result from local or durable state."""
        local_result = self._local.result_for(execution_key)
        if local_result is not None:
            return local_result
        persisted = self._persisted_for(execution_key)
        if persisted is None or persisted.state not in _EXECUTION_TERMINAL_STATES:
            return None
        self._validate_execution_claim(execution_key, persisted)
        return self._terminal_result(execution_key, persisted)

    def is_in_progress(
        self,
        execution_key: str,
        *,
        now_utc: datetime | None = None,
    ) -> bool:
        """Return expired or locally owned intent and reject active remote leases."""
        if self._local.is_in_progress(execution_key):
            return True
        persisted = self._persisted_for(execution_key)
        if persisted is None or persisted.state is not BatchItemState.EXECUTING:
            return False
        self._validate_execution_claim(execution_key, persisted)
        if now_utc is None:
            raise ValueError("now_utc is required for durable lease evaluation")
        lease_expires_at = persisted.lease_expires_at_utc
        if lease_expires_at is None:
            raise PersistenceConflictError("persisted execution lease is missing")
        if lease_expires_at > normalize_utc(now_utc):
            raise ActiveExecutionLeaseError(lease_expires_at)
        return True

    def record_intent(self, execution_key: str) -> None:
        """Record an intent owned by this process after durable persistence."""
        self._require_item(execution_key)
        self._local.record_intent(execution_key)

    def record_result(self, result: OperationResultRecord) -> None:
        """Record a terminal result produced by this process."""
        self._require_item(result.execution_key)
        self._local.record_result(result)

    def _persisted_for(
        self,
        execution_key: str,
    ) -> PersistedOperationExecution | None:
        _, identity = self._require_item(execution_key)
        if execution_key not in self._loaded:
            self._loaded[execution_key] = self._repository.load_operation_execution(
                identity
            )
        return self._loaded[execution_key]

    def _require_item(
        self,
        execution_key: str,
    ) -> tuple[OperationBatchItem, OperationExecutionIdentity]:
        try:
            return self._items[execution_key]
        except KeyError:
            raise ValueError("execution key is not bound to this batch") from None

    def _validate_execution_claim(
        self,
        execution_key: str,
        persisted: PersistedOperationExecution,
    ) -> None:
        item, _ = self._require_item(execution_key)
        if persisted.idempotency_key != execution_key:
            raise PersistenceConflictError("persisted execution key does not match")
        expected_domain_execution_id = f"{self._external_batch_id}:{item.item_id}"
        if persisted.execution_id != expected_domain_execution_id:
            raise PersistenceConflictError(
                "persisted execution identity does not match"
            )
        approval_id = None if item.approval is None else item.approval.approval_id
        if persisted.approval_id != approval_id:
            raise PersistenceConflictError("persisted approval identity does not match")
        expected_digest = item.expected_source_digest
        persisted_digest = (
            None
            if persisted.expected_source_sha256 is None
            else persisted.expected_source_sha256.hex()
        )
        if persisted_digest != expected_digest:
            raise PersistenceConflictError("persisted source identity does not match")

    def _terminal_result(
        self,
        execution_key: str,
        persisted: PersistedOperationExecution,
    ) -> OperationResultRecord:
        item, _ = self._require_item(execution_key)
        if persisted.safe_error_summary is None:
            raise PersistenceConflictError(
                "persisted operation result reason is missing"
            )
        try:
            reason = ExecutionReason(persisted.safe_error_summary)
        except (TypeError, ValueError):
            raise PersistenceConflictError(
                "persisted operation result reason is invalid"
            ) from None
        attempted_at = (
            persisted.started_at_utc
            or persisted.intent_recorded_at_utc
            or persisted.completed_at_utc
        )
        if (
            attempted_at is None
            or persisted.completed_at_utc is None
            or persisted.execution_id is None
            or persisted.result_disposition is None
            or persisted.source_exists_after is None
            or persisted.destination_exists_after is None
        ):
            raise PersistenceConflictError(
                "persisted terminal result evidence is incomplete"
            )
        return OperationResultRecord(
            batch_id=self._external_batch_id,
            batch_item_id=item.item_id,
            execution_key=execution_key,
            execution_id=persisted.execution_id,
            status=_EXECUTION_STATUS_BY_ITEM_STATE[persisted.state],
            reason=reason,
            disposition=persisted.result_disposition,
            attempted_at_utc=attempted_at,
            completed_at_utc=persisted.completed_at_utc,
            approval_id=persisted.approval_id,
            source_exists_after=persisted.source_exists_after,
            destination_exists_after=persisted.destination_exists_after,
            source_digest_before=(
                None
                if persisted.expected_source_sha256 is None
                else persisted.expected_source_sha256.hex()
            ),
            destination_digest_after=(
                None
                if persisted.actual_sha256 is None
                else persisted.actual_sha256.hex()
            ),
        )


_EXECUTION_TERMINAL_STATES = {
    BatchItemState.BLOCKED,
    BatchItemState.SUCCEEDED,
    BatchItemState.FAILED,
    BatchItemState.VERIFICATION_FAILED,
}
_EXECUTION_STATUS_BY_ITEM_STATE = {
    BatchItemState.BLOCKED: ExecutionStatus.BLOCKED,
    BatchItemState.SUCCEEDED: ExecutionStatus.SUCCEEDED,
    BatchItemState.FAILED: ExecutionStatus.FAILED,
    BatchItemState.VERIFICATION_FAILED: ExecutionStatus.VERIFICATION_FAILED,
}


class DurableOperationLifecycleRecorder(OperationLifecycleRecorder):
    """Bridge local execution transitions to the durable repository boundary."""

    def __init__(
        self,
        repository: OperationPersistenceRepository,
        *,
        identities: PersistenceIdentityMap,
        resolve_actor_identity: ActorIdentityResolver,
        lease_duration: timedelta = timedelta(minutes=2),
        lease_token_factory: LeaseTokenFactory = uuid4,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._repository = repository
        self._identities = identities
        self._resolve_actor_identity = resolve_actor_identity
        self._lease_duration = lease_duration
        self._lease_token_factory = lease_token_factory

    def record_intent(
        self,
        batch: OperationBatch,
        item: OperationBatchItem,
        event: AuditEvent,
    ) -> None:
        """Persist intent and audit evidence before filesystem mutation."""
        actor_id = self._resolve_actor_identity(event.actor_id)
        command = map_execution_intent(
            batch,
            item,
            event,
            mapping=ExecutionIntentMapping(
                identities=self._identities,
                executor_actor_id=actor_id,
                lease_token=self._lease_token_factory(),
                lease_expires_at_utc=event.occurred_at_utc + self._lease_duration,
            ),
        )
        self._repository.record_execution_intent(command)

    def record_result(
        self,
        batch: OperationBatch,
        item: OperationBatchItem,
        result: OperationResultRecord,
        event: AuditEvent,
    ) -> None:
        """Persist observed result and audit evidence after filesystem mutation."""
        actual_size = _observed_destination_size(item, result)
        if result.succeeded and actual_size is None:
            raise PersistenceEvidenceError(
                "successful operation result requires observed destination size"
            )
        command = map_operation_result(
            batch,
            item,
            result,
            event,
            mapping=OperationResultMapping(
                identities=self._identities,
                event_actor_id=self._resolve_actor_identity(event.actor_id),
                actual_size=actual_size,
            ),
        )
        self._repository.record_operation_result(command)

    def record_event(
        self,
        batch: OperationBatch,
        event: AuditEvent,
    ) -> None:
        """Persist a replay, reconciliation, or aggregate lifecycle event."""
        if (
            batch.workspace_id != self._identities.external_workspace_id
            or batch.batch_id != self._identities.external_batch_id
        ):
            raise ValueError("event batch does not match persistence identities")
        mapped = map_audit_event(
            event,
            identities=self._identities,
            resolve_actor_identity=self._resolve_actor_identity,
        )
        self._repository.append_audit_events((mapped,))


def _observed_destination_size(
    item: OperationBatchItem,
    result: OperationResultRecord,
) -> int | None:
    destination_path = item.plan.destination_path
    if not result.destination_exists_after or destination_path is None:
        return None
    return _safe_file_size(destination_path)


def _safe_file_size(path: Path) -> int | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.stat().st_size
    except OSError:
        return None
