"""Durable lifecycle recorder used around local filesystem execution."""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from docweave.operations.audit import AuditEvent
from docweave.operations.batch import (
    OperationBatch,
    OperationBatchItem,
    OperationLifecycleRecorder,
)
from docweave.operations.results import OperationResultRecord
from docweave.persistence.contracts import OperationPersistenceRepository
from docweave.persistence.mappers import (
    ActorIdentityResolver,
    ExecutionIntentMapping,
    OperationResultMapping,
    PersistenceIdentityMap,
    map_audit_event,
    map_execution_intent,
    map_operation_result,
)

LeaseTokenFactory = Callable[[], UUID]


class PersistenceEvidenceError(RuntimeError):
    """Required post-mutation evidence could not be observed safely."""


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
