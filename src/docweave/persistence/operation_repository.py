"""CockroachDB adapter for atomic operation and audit persistence."""

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from docweave.operations.audit import AuditEventType
from docweave.operations.batch import BatchItemState
from docweave.operations.results import ResultDisposition
from docweave.persistence.contracts import (
    AuditAppend,
    BatchItemSnapshot,
    CreateBatch,
    OperationExecutionIdentity,
    OperationPersistenceRepository,
    PersistedOperationExecution,
    PersistenceDisposition,
    RecordExecutionIntent,
    RecordOperationResult,
    RestoreAuditEventSnapshot,
    RestoreAuditQuery,
)
from docweave.persistence.transactions import TransactionRun

_INSERT_BATCH = sa.text(
    """
    INSERT INTO docweave.operation_batches (
        operation_batch_id, workspace_id, external_batch_id, idempotency_key,
        operation_type, preview_sha256, preview_version, policy_version,
        correlation_id, status, created_by_actor_id, total_item_count,
        blocked_item_count, created_at, completed_at
    ) VALUES (
        :operation_batch_id, :workspace_id, :external_batch_id, :idempotency_key,
        :operation_type, :preview_sha256, :preview_version, :policy_version,
        :correlation_id, :status, :created_by_actor_id, :total_item_count,
        :blocked_item_count, :created_at, :completed_at
    )
    ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
    RETURNING operation_batch_id
    """
)
_SELECT_BATCH_REPLAY = sa.text(
    """
    SELECT operation_batch_id, preview_sha256
    FROM docweave.operation_batches
    WHERE workspace_id = :workspace_id AND idempotency_key = :idempotency_key
    """
)
_INSERT_OPERATION = sa.text(
    """
    INSERT INTO docweave.file_operations (
        file_operation_id, workspace_id, operation_batch_id, batch_item_id,
        operation_type, plan_sha256, approval_id, source_root_reference,
        source_relative_path, destination_root_reference,
        destination_relative_path, expected_source_sha256,
        expected_source_size, state, created_at, completed_at
    ) VALUES (
        :file_operation_id, :workspace_id, :operation_batch_id, :batch_item_id,
        :operation_type, :plan_sha256, :approval_id, :source_root_reference,
        :source_relative_path, :destination_root_reference,
        :destination_relative_path, :expected_source_sha256,
        :expected_source_size, :state, :created_at, :completed_at
    )
    """
)
_LOCK_WORKSPACE = sa.text(
    """
    SELECT workspace_id
    FROM docweave.workspaces
    WHERE workspace_id = :workspace_id
    FOR UPDATE
    """
)
_SELECT_AUDIT_PREDECESSOR = sa.text(
    """
    SELECT event_id, event_sha256
    FROM docweave.audit_events
    WHERE workspace_id = :workspace_id
    ORDER BY event_sequence DESC
    LIMIT 1
    """
)
_INSERT_AUDIT_EVENT = sa.text(
    """
    INSERT INTO docweave.audit_events (
        event_id, workspace_id, actor_id, correlation_id, event_type,
        subject_kind, subject_id, operation_batch_id, file_operation_id,
        previous_event_id, previous_event_sha256, event_sha256,
        idempotency_key, previous_state, new_state, reason, plan_sha256,
        approval_id, source_relative_path, destination_relative_path,
        error_class, error_category, occurred_at
    ) VALUES (
        :event_id, :workspace_id, :actor_id, :correlation_id, :event_type,
        :subject_kind, :subject_id, :operation_batch_id, :file_operation_id,
        :previous_event_id, :previous_event_sha256, :event_sha256,
        :idempotency_key, :previous_state, :new_state, :reason, :plan_sha256,
        :approval_id, :source_relative_path, :destination_relative_path,
        :error_class, :error_category, :occurred_at
    )
    """
)
_SELECT_OPERATION_FOR_UPDATE = sa.text(
    """
    SELECT state, execution_id, idempotency_key, result_disposition,
           actual_sha256, actual_size, source_exists_after,
           destination_exists_after
    FROM docweave.file_operations
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
      AND file_operation_id = :file_operation_id
    FOR UPDATE
    """
)
_SELECT_OPERATION_EXECUTION = sa.text(
    """
    SELECT state, idempotency_key, execution_id, approval_id,
           lease_expires_at, intent_recorded_at, started_at, completed_at,
           result_disposition, expected_source_sha256, actual_sha256,
           actual_size, source_exists_after, destination_exists_after,
           safe_error_summary, error_category
    FROM docweave.file_operations
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
      AND file_operation_id = :file_operation_id
    """
)
_SELECT_RESTORE_AUDIT_EVENTS = sa.text(
    """
    SELECT event_sequence, event_id, workspace_id, actor_id, correlation_id,
           event_type, subject_kind, subject_id, operation_batch_id,
           file_operation_id, idempotency_key, previous_state, new_state,
           reason, plan_sha256, approval_id, source_relative_path,
           destination_relative_path, error_class, error_category, occurred_at
    FROM docweave.audit_events
    WHERE workspace_id = :workspace_id
      AND event_type IN (
          'restore_approved',
          'restore_execution_succeeded',
          'restore_execution_blocked',
          'restore_execution_failed',
          'restore_verification_failed'
      )
      AND (:operation_batch_id IS NULL OR operation_batch_id = :operation_batch_id)
      AND (:file_operation_id IS NULL OR file_operation_id = :file_operation_id)
    ORDER BY occurred_at ASC, event_sequence ASC
    LIMIT :limit
    """
)
_RECORD_EXECUTION_INTENT = sa.text(
    """
    UPDATE docweave.file_operations
    SET state = 'executing',
        idempotency_key = :idempotency_key,
        execution_id = :execution_id,
        executor_actor_id = :executor_actor_id,
        lease_token = :lease_token,
        lease_expires_at = :lease_expires_at,
        intent_recorded_at = :intent_recorded_at,
        started_at = :intent_recorded_at,
        attempt_count = attempt_count + 1
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
      AND file_operation_id = :file_operation_id
      AND state = 'approved'
    """
)
_MARK_BATCH_EXECUTING = sa.text(
    """
    UPDATE docweave.operation_batches
    SET status = 'executing'
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
      AND status = 'approved'
    """
)
_RECORD_OPERATION_RESULT = sa.text(
    """
    UPDATE docweave.file_operations
    SET state = :terminal_state,
        idempotency_key = COALESCE(idempotency_key, :idempotency_key),
        execution_id = COALESCE(execution_id, :execution_id),
        actual_sha256 = :actual_sha256,
        actual_size = :actual_size,
        actual_source_relative_path = :actual_source_relative_path,
        actual_destination_relative_path = :actual_destination_relative_path,
        source_exists_after = :source_exists_after,
        destination_exists_after = :destination_exists_after,
        result_disposition = :result_disposition,
        reconciliation_state = :reconciliation_state,
        error_category = :error_category,
        safe_error_summary = :safe_error_summary,
        completed_at = :completed_at,
        lease_token = NULL,
        lease_expires_at = NULL
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
      AND file_operation_id = :file_operation_id
      AND (
          (state = 'executing' AND execution_id = :execution_id)
          OR (state = 'approved' AND :terminal_state = 'blocked')
      )
    """
)
_UPDATE_BATCH_RESULT = sa.text(
    """
    UPDATE docweave.operation_batches
    SET succeeded_item_count = succeeded_item_count + :succeeded_increment,
        blocked_item_count = blocked_item_count + :blocked_increment,
        failed_item_count = failed_item_count + :failed_increment,
        verification_failed_item_count =
            verification_failed_item_count + :verification_failed_increment,
        status = CASE
            WHEN succeeded_item_count + blocked_item_count + failed_item_count
                 + verification_failed_item_count + skipped_item_count + 1
                 = total_item_count
            THEN CASE
                WHEN blocked_item_count + :blocked_increment > 0
                     OR failed_item_count + :failed_increment > 0
                     OR verification_failed_item_count
                        + :verification_failed_increment > 0
                     OR blocked_item_count > 0
                THEN 'completed_with_failures'
                ELSE 'completed'
            END
            ELSE 'executing'
        END,
        completed_at = CASE
            WHEN succeeded_item_count + blocked_item_count + failed_item_count
                 + verification_failed_item_count + skipped_item_count + 1
                 = total_item_count
            THEN :completed_at
            ELSE NULL
        END
    WHERE workspace_id = :workspace_id
      AND operation_batch_id = :operation_batch_id
    """
)


class SerializableTransactionRunner(Protocol):
    """Structural transaction dependency used by the repository."""

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]: ...


class PersistenceConflictError(RuntimeError):
    """A safe conflict that requires reconciliation instead of overwrite."""


class PersistenceNotFoundError(RuntimeError):
    """A workspace or operation identity was not found in the authorized scope."""


class CockroachOperationRepository(OperationPersistenceRepository):
    """Persist operation lifecycle changes and audit evidence atomically."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def create_batch(self, command: CreateBatch) -> PersistenceDisposition:
        """Create one batch atomically or return an exact idempotent replay."""

        def persist(connection: Connection) -> PersistenceDisposition:
            inserted_id = connection.execute(
                _INSERT_BATCH,
                _batch_parameters(command),
            ).scalar_one_or_none()
            if inserted_id is None:
                return _validate_batch_replay(connection, command)
            if inserted_id != command.operation_batch_id:
                raise PersistenceConflictError("created batch identity mismatch")

            connection.execute(
                _INSERT_OPERATION,
                [_item_parameters(command, item) for item in command.items],
            )
            append_audit_events_to_connection(connection, command.audit_events)
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist).value

    def record_execution_intent(
        self,
        command: RecordExecutionIntent,
    ) -> PersistenceDisposition:
        """Claim one approved item and append intent evidence atomically."""

        def persist(connection: Connection) -> PersistenceDisposition:
            current = _locked_operation(connection, command)
            if current["state"] == BatchItemState.EXECUTING.value:
                if (
                    current["execution_id"] == command.execution_id
                    and current["idempotency_key"] == command.idempotency_key
                ):
                    return PersistenceDisposition.IDEMPOTENT_REPLAY
                raise PersistenceConflictError("operation is already executing")
            if current["state"] != BatchItemState.APPROVED.value:
                raise PersistenceConflictError("operation is not approved")
            existing_key = current["idempotency_key"]
            if existing_key is not None and existing_key != command.idempotency_key:
                raise PersistenceConflictError("operation idempotency key mismatch")

            parameters = _operation_identity(command)
            parameters.update(
                {
                    "execution_id": command.execution_id,
                    "idempotency_key": command.idempotency_key,
                    "executor_actor_id": command.executor_actor_id,
                    "lease_token": command.lease_token,
                    "lease_expires_at": command.lease_expires_at_utc,
                    "intent_recorded_at": command.intent_recorded_at_utc,
                }
            )
            if connection.execute(_RECORD_EXECUTION_INTENT, parameters).rowcount != 1:
                raise PersistenceConflictError("operation intent was not recorded")
            connection.execute(_MARK_BATCH_EXECUTING, parameters)
            append_audit_events_to_connection(connection, (command.audit_event,))
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist).value

    def record_operation_result(
        self,
        command: RecordOperationResult,
    ) -> PersistenceDisposition:
        """Record one terminal result and append evidence atomically."""

        def persist(connection: Connection) -> PersistenceDisposition:
            current = _locked_operation(connection, command)
            if current["state"] in {
                BatchItemState.BLOCKED.value,
                BatchItemState.SUCCEEDED.value,
                BatchItemState.FAILED.value,
                BatchItemState.VERIFICATION_FAILED.value,
            }:
                if _is_same_terminal_result(current, command):
                    return PersistenceDisposition.IDEMPOTENT_REPLAY
                raise PersistenceConflictError("operation has a different result")
            executing_claim_matches = (
                current["state"] == BatchItemState.EXECUTING.value
                and current["execution_id"] == command.execution_id
            )
            approved_precondition_block = (
                current["state"] == BatchItemState.APPROVED.value
                and command.terminal_state is BatchItemState.BLOCKED
            )
            if not executing_claim_matches and not approved_precondition_block:
                raise PersistenceConflictError("operation execution identity mismatch")

            parameters = _operation_identity(command)
            parameters.update(_result_parameters(command))
            if connection.execute(_RECORD_OPERATION_RESULT, parameters).rowcount != 1:
                raise PersistenceConflictError("operation result was not recorded")
            if connection.execute(_UPDATE_BATCH_RESULT, parameters).rowcount != 1:
                raise PersistenceNotFoundError("operation batch was not found")
            append_audit_events_to_connection(connection, (command.audit_event,))
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist).value

    def load_operation_execution(
        self,
        identity: OperationExecutionIdentity,
    ) -> PersistedOperationExecution | None:
        """Load one operation state inside its exact authorized scope."""

        def load(connection: Connection) -> PersistedOperationExecution | None:
            row = (
                connection.execute(
                    _SELECT_OPERATION_EXECUTION,
                    _execution_identity(identity),
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            return _map_persisted_execution(
                identity,
                cast(Mapping[str, object], row),
            )

        return self._transactions.run(load).value

    def append_audit_events(
        self,
        events: tuple[AuditAppend, ...],
    ) -> PersistenceDisposition:
        """Append non-result lifecycle evidence in one transaction."""
        if not events:
            raise ValueError("events must not be empty")

        def persist(connection: Connection) -> PersistenceDisposition:
            append_audit_events_to_connection(connection, events)
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist).value


class CockroachRestoreAuditRepository:
    """Read durable restore audit evidence for workspace-scoped history views."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def load_restore_audit_events(
        self,
        query: RestoreAuditQuery,
    ) -> tuple[RestoreAuditEventSnapshot, ...]:
        """Load restore audit events with bounded, parameterized filters."""

        def load(connection: Connection) -> tuple[RestoreAuditEventSnapshot, ...]:
            rows = (
                connection.execute(
                    _SELECT_RESTORE_AUDIT_EVENTS,
                    {
                        "workspace_id": query.workspace_id,
                        "operation_batch_id": query.operation_batch_id,
                        "file_operation_id": query.file_operation_id,
                        "limit": query.limit,
                    },
                )
                .mappings()
                .all()
            )
            return tuple(
                _map_restore_audit_event(cast(Mapping[str, object], row))
                for row in rows
            )

        return self._transactions.run(load).value


def _batch_parameters(command: CreateBatch) -> dict[str, object]:
    return {
        "operation_batch_id": command.operation_batch_id,
        "workspace_id": command.workspace_id,
        "external_batch_id": command.external_batch_id,
        "idempotency_key": command.idempotency_key,
        "operation_type": command.operation.value,
        "preview_sha256": command.preview_sha256,
        "preview_version": command.preview_version,
        "policy_version": command.policy_version,
        "correlation_id": command.correlation_id,
        "status": command.status.value,
        "created_by_actor_id": command.created_by_actor_id,
        "total_item_count": len(command.items),
        "blocked_item_count": sum(
            item.state is BatchItemState.BLOCKED for item in command.items
        ),
        "created_at": command.created_at_utc,
        "completed_at": command.completed_at_utc,
    }


def _item_parameters(
    command: CreateBatch,
    item: BatchItemSnapshot,
) -> dict[str, object]:
    return {
        "file_operation_id": item.file_operation_id,
        "workspace_id": command.workspace_id,
        "operation_batch_id": command.operation_batch_id,
        "batch_item_id": item.batch_item_id,
        "operation_type": item.operation.value,
        "plan_sha256": item.plan_sha256,
        "approval_id": item.approval_id,
        "source_root_reference": item.source_root_reference,
        "source_relative_path": item.source_relative_path,
        "destination_root_reference": item.destination_root_reference,
        "destination_relative_path": item.destination_relative_path,
        "expected_source_sha256": item.expected_source_sha256,
        "expected_source_size": item.expected_source_size,
        "state": item.state.value,
        "created_at": command.created_at_utc,
        "completed_at": item.completed_at_utc,
    }


def _validate_batch_replay(
    connection: Connection,
    command: CreateBatch,
) -> PersistenceDisposition:
    existing = (
        connection.execute(
            _SELECT_BATCH_REPLAY,
            {
                "workspace_id": command.workspace_id,
                "idempotency_key": command.idempotency_key,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing is None:
        raise PersistenceConflictError("batch idempotency conflict is unresolved")
    if (
        existing["operation_batch_id"] != command.operation_batch_id
        or bytes(existing["preview_sha256"]) != command.preview_sha256
    ):
        raise PersistenceConflictError("batch idempotency key has different content")
    return PersistenceDisposition.IDEMPOTENT_REPLAY


def _locked_operation(
    connection: Connection,
    command: RecordExecutionIntent | RecordOperationResult,
) -> Mapping[str, object]:
    current = (
        connection.execute(
            _SELECT_OPERATION_FOR_UPDATE,
            _operation_identity(command),
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise PersistenceNotFoundError("operation was not found")
    return cast(Mapping[str, object], current)


def _operation_identity(
    command: RecordExecutionIntent | RecordOperationResult,
) -> dict[str, object]:
    return {
        "workspace_id": command.workspace_id,
        "operation_batch_id": command.operation_batch_id,
        "file_operation_id": command.file_operation_id,
    }


def _execution_identity(
    identity: OperationExecutionIdentity,
) -> dict[str, object]:
    return {
        "workspace_id": identity.workspace_id,
        "operation_batch_id": identity.operation_batch_id,
        "file_operation_id": identity.file_operation_id,
    }


def _map_persisted_execution(
    identity: OperationExecutionIdentity,
    row: Mapping[str, object],
) -> PersistedOperationExecution:
    try:
        disposition_value = row["result_disposition"]
        return PersistedOperationExecution(
            identity=identity,
            state=BatchItemState(str(row["state"])),
            idempotency_key=_optional_text(row["idempotency_key"]),
            execution_id=_optional_text(row["execution_id"]),
            approval_id=_optional_text(row["approval_id"]),
            lease_expires_at_utc=_optional_datetime(row["lease_expires_at"]),
            intent_recorded_at_utc=_optional_datetime(row["intent_recorded_at"]),
            started_at_utc=_optional_datetime(row["started_at"]),
            completed_at_utc=_optional_datetime(row["completed_at"]),
            result_disposition=(
                None
                if disposition_value is None
                else ResultDisposition(str(disposition_value))
            ),
            expected_source_sha256=_optional_bytes(row["expected_source_sha256"]),
            actual_sha256=_optional_bytes(row["actual_sha256"]),
            actual_size=_optional_int(row["actual_size"]),
            source_exists_after=_optional_bool(row["source_exists_after"]),
            destination_exists_after=_optional_bool(row["destination_exists_after"]),
            safe_error_summary=_optional_text(row["safe_error_summary"]),
            error_category=_optional_text(row["error_category"]),
        )
    except (KeyError, TypeError, ValueError):
        raise PersistenceConflictError(
            "persisted operation execution state is invalid"
        ) from None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError
    return value


def _optional_bytes(value: object) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, bytes | bytearray | memoryview):
        raise TypeError
    return bytes(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError
    return value


def _result_parameters(command: RecordOperationResult) -> dict[str, object]:
    return {
        "execution_id": command.execution_id,
        "idempotency_key": command.idempotency_key,
        "terminal_state": command.terminal_state.value,
        "actual_sha256": command.actual_sha256,
        "actual_size": command.actual_size,
        "actual_source_relative_path": command.actual_source_relative_path,
        "actual_destination_relative_path": (command.actual_destination_relative_path),
        "source_exists_after": command.source_exists_after,
        "destination_exists_after": command.destination_exists_after,
        "result_disposition": command.disposition.value,
        "reconciliation_state": (
            "required"
            if command.terminal_state is BatchItemState.VERIFICATION_FAILED
            else "not_required"
        ),
        "error_category": command.error_category,
        "safe_error_summary": command.reason.value,
        "completed_at": command.completed_at_utc,
        "succeeded_increment": int(command.terminal_state is BatchItemState.SUCCEEDED),
        "blocked_increment": int(command.terminal_state is BatchItemState.BLOCKED),
        "failed_increment": int(command.terminal_state is BatchItemState.FAILED),
        "verification_failed_increment": int(
            command.terminal_state is BatchItemState.VERIFICATION_FAILED
        ),
    }


def _is_same_terminal_result(
    current: Mapping[str, object],
    command: RecordOperationResult,
) -> bool:
    current_digest = current["actual_sha256"]
    return (
        current["state"] == command.terminal_state.value
        and current["execution_id"] == command.execution_id
        and current["result_disposition"] == command.disposition.value
        and (None if current_digest is None else bytes(cast(bytes, current_digest)))
        == command.actual_sha256
        and current["actual_size"] == command.actual_size
        and current["source_exists_after"] == command.source_exists_after
        and current["destination_exists_after"] == command.destination_exists_after
    )


def _map_restore_audit_event(
    row: Mapping[str, object],
) -> RestoreAuditEventSnapshot:
    try:
        event_type = AuditEventType(str(row["event_type"]))
    except ValueError as error:
        raise PersistenceConflictError("restore audit event type is invalid") from error
    try:
        return RestoreAuditEventSnapshot(
            event_sequence=cast(int, row["event_sequence"]),
            event_id=cast(UUID, row["event_id"]),
            workspace_id=cast(UUID, row["workspace_id"]),
            actor_id=cast(UUID, row["actor_id"]),
            correlation_id=cast(str, row["correlation_id"]),
            event_type=event_type,
            subject_kind=cast(str, row["subject_kind"]),
            subject_id=cast(str, row["subject_id"]),
            occurred_at_utc=cast(datetime, row["occurred_at"]),
            operation_batch_id=cast(UUID | None, row["operation_batch_id"]),
            file_operation_id=cast(UUID | None, row["file_operation_id"]),
            idempotency_key=cast(str | None, row["idempotency_key"]),
            previous_state=cast(str | None, row["previous_state"]),
            new_state=cast(str | None, row["new_state"]),
            reason=cast(str | None, row["reason"]),
            plan_sha256=(
                None
                if row["plan_sha256"] is None
                else bytes(cast(bytes, row["plan_sha256"]))
            ),
            approval_id=cast(str | None, row["approval_id"]),
            source_relative_path=cast(str | None, row["source_relative_path"]),
            destination_relative_path=cast(
                str | None,
                row["destination_relative_path"],
            ),
            error_class=cast(str | None, row["error_class"]),
            error_category=cast(str | None, row["error_category"]),
        )
    except ValueError as error:
        raise PersistenceConflictError("restore audit row is invalid") from error


def append_audit_events_to_connection(
    connection: Connection,
    events: tuple[AuditAppend, ...],
) -> None:
    if not events:
        return
    workspace_id = events[0].workspace_id
    if any(event.workspace_id != workspace_id for event in events):
        raise PersistenceConflictError("audit events cross workspace boundaries")
    locked_workspace = connection.execute(
        _LOCK_WORKSPACE,
        {"workspace_id": workspace_id},
    ).scalar_one_or_none()
    if locked_workspace is None:
        raise PersistenceNotFoundError("audit workspace was not found")

    predecessor = (
        connection.execute(
            _SELECT_AUDIT_PREDECESSOR,
            {"workspace_id": workspace_id},
        )
        .mappings()
        .one_or_none()
    )
    previous_event_id: UUID | None = None
    previous_digest: bytes | None = None
    if predecessor is not None:
        previous_event_id = cast(UUID, predecessor["event_id"])
        previous_digest = bytes(cast(bytes, predecessor["event_sha256"]))

    for event in events:
        event_digest = _audit_digest(event, previous_digest)
        parameters = _audit_parameters(
            event,
            previous_event_id=previous_event_id,
            previous_digest=previous_digest,
            event_digest=event_digest,
        )
        connection.execute(_INSERT_AUDIT_EVENT, parameters)
        previous_event_id = event.event_id
        previous_digest = event_digest


def _audit_digest(event: AuditAppend, previous_digest: bytes | None) -> bytes:
    payload = {
        "event_id": str(event.event_id),
        "workspace_id": str(event.workspace_id),
        "actor_id": str(event.actor_id),
        "actor_type": event.actor_type.value,
        "correlation_id": event.correlation_id,
        "event_type": event.event_type.value,
        "subject_kind": event.subject_kind,
        "subject_id": event.subject_id,
        "operation_batch_id": _uuid_text(event.operation_batch_id),
        "file_operation_id": _uuid_text(event.file_operation_id),
        "idempotency_key": event.idempotency_key,
        "previous_state": event.previous_state,
        "new_state": event.new_state,
        "reason": event.reason,
        "plan_sha256": (None if event.plan_sha256 is None else event.plan_sha256.hex()),
        "approval_id": event.approval_id,
        "source_relative_path": event.source_relative_path,
        "destination_relative_path": event.destination_relative_path,
        "error_class": event.error_class,
        "error_category": event.error_category,
        "occurred_at": event.occurred_at_utc.isoformat(),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return sha256((previous_digest or b"") + canonical).digest()


def _audit_parameters(
    event: AuditAppend,
    *,
    previous_event_id: UUID | None,
    previous_digest: bytes | None,
    event_digest: bytes,
) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "workspace_id": event.workspace_id,
        "actor_id": event.actor_id,
        "correlation_id": event.correlation_id,
        "event_type": event.event_type.value,
        "subject_kind": event.subject_kind,
        "subject_id": event.subject_id,
        "operation_batch_id": event.operation_batch_id,
        "file_operation_id": event.file_operation_id,
        "previous_event_id": previous_event_id,
        "previous_event_sha256": previous_digest,
        "event_sha256": event_digest,
        "idempotency_key": event.idempotency_key,
        "previous_state": event.previous_state,
        "new_state": event.new_state,
        "reason": event.reason,
        "plan_sha256": event.plan_sha256,
        "approval_id": event.approval_id,
        "source_relative_path": event.source_relative_path,
        "destination_relative_path": event.destination_relative_path,
        "error_class": event.error_class,
        "error_category": event.error_category,
        "occurred_at": event.occurred_at_utc,
    }


def _uuid_text(value: UUID | None) -> str | None:
    return None if value is None else str(value)
