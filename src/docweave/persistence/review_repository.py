"""Atomic CockroachDB persistence for human review decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.row import RowMapping

from docweave.operations import ReviewDecisionAction
from docweave.operations.audit import AuditEventType
from docweave.persistence.contracts import AuditAppend, PersistenceDisposition
from docweave.persistence.operation_repository import (
    PersistenceConflictError,
    append_audit_events_to_connection,
)
from docweave.persistence.transactions import TransactionRun

_SHA256_HEX_LENGTH = 64
_TERMINAL_PROPOSAL_ACTIONS = {
    ReviewDecisionAction.APPROVE,
    ReviewDecisionAction.REJECT,
}


class SerializableTransactionRunner(Protocol):
    """Minimal transaction runner used by the adapter."""

    def run[T](self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Run one retry-safe transaction."""


class TransactionWork[T](Protocol):
    """Callable transaction closure."""

    def __call__(self, connection: Connection) -> T:
        """Execute against one active transaction."""


@dataclass(frozen=True, slots=True)
class PersistReviewDecision:
    """Durable command for one exact human review outcome."""

    workspace_id: UUID
    proposal_id: UUID
    review_decision_id: UUID
    reviewer_actor_id: UUID
    action: ReviewDecisionAction
    proposal_fingerprint: str
    decided_at_utc: datetime
    reason: str | None = None
    operation_plan_fingerprint: str | None = None
    audit_event: AuditAppend | None = None

    def __post_init__(self) -> None:
        if self.action not in _TERMINAL_PROPOSAL_ACTIONS:
            raise ValueError("durable review persistence only accepts approve/reject")
        _validate_fingerprint("proposal_fingerprint", self.proposal_fingerprint)
        if self.operation_plan_fingerprint is not None:
            _validate_fingerprint(
                "operation_plan_fingerprint",
                self.operation_plan_fingerprint,
            )
        normalized_reason = _normalize_reason(self.reason)
        if self.action is ReviewDecisionAction.REJECT and normalized_reason is None:
            raise ValueError("reject decisions require a reason")
        object.__setattr__(self, "reason", normalized_reason)
        object.__setattr__(
            self,
            "decided_at_utc",
            _as_utc(self.decided_at_utc),
        )
        if self.audit_event is not None:
            _validate_audit_event(self.audit_event, self)


_LOCK_PROPOSAL = sa.text(
    """
    SELECT proposal_id, proposal_status
    FROM docweave.proposals
    WHERE workspace_id = :workspace_id
      AND proposal_id = :proposal_id
    FOR UPDATE
    """
)
_INSERT_DECISION = sa.text(
    """
    INSERT INTO docweave.review_decisions (
        review_decision_id, workspace_id, proposal_id, reviewer_actor_id,
        action, proposal_sha256, operation_plan_sha256, reason, decided_at
    ) VALUES (
        :review_decision_id, :workspace_id, :proposal_id, :reviewer_actor_id,
        :action, :proposal_sha256, :operation_plan_sha256, :reason, :decided_at
    )
    ON CONFLICT (workspace_id, proposal_id) DO NOTHING
    RETURNING review_decision_id
    """
)
_SELECT_REPLAY = sa.text(
    """
    SELECT review_decision_id, reviewer_actor_id, action, proposal_sha256,
           operation_plan_sha256, reason, decided_at
    FROM docweave.review_decisions
    WHERE workspace_id = :workspace_id
      AND proposal_id = :proposal_id
    """
)
_UPDATE_PROPOSAL_STATUS = sa.text(
    """
    UPDATE docweave.proposals
    SET proposal_status = :proposal_status
    WHERE workspace_id = :workspace_id
      AND proposal_id = :proposal_id
      AND proposal_status = 'needs_review'
    RETURNING proposal_id
    """
)


class CockroachReviewDecisionRepository:
    """Persist one review decision and canonical proposal status atomically."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def persist(self, command: PersistReviewDecision) -> PersistenceDisposition:
        """Write one append-only review decision with exact idempotent replay."""

        def persist_once(connection: Connection) -> PersistenceDisposition:
            parameters = _parameters(command)
            existing_proposal = (
                connection.execute(_LOCK_PROPOSAL, parameters).mappings().one_or_none()
            )
            if existing_proposal is None:
                raise PersistenceConflictError(
                    "review decision references an unknown proposal"
                )
            inserted_id = connection.execute(
                _INSERT_DECISION,
                parameters,
            ).scalar_one_or_none()
            if inserted_id is None:
                return _validate_replay(connection, command)
            if inserted_id != command.review_decision_id:
                raise PersistenceConflictError("created review decision mismatch")
            if existing_proposal["proposal_status"] != "needs_review":
                raise PersistenceConflictError("proposal is not open for review")
            updated_id = connection.execute(
                _UPDATE_PROPOSAL_STATUS,
                {
                    **parameters,
                    "proposal_status": _proposal_status(command.action),
                },
            ).scalar_one_or_none()
            if updated_id != command.proposal_id:
                raise PersistenceConflictError("proposal review status was not updated")
            if command.audit_event is not None:
                append_audit_events_to_connection(connection, (command.audit_event,))
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist_once).value


def _parameters(command: PersistReviewDecision) -> dict[str, object]:
    return {
        "workspace_id": command.workspace_id,
        "proposal_id": command.proposal_id,
        "review_decision_id": command.review_decision_id,
        "reviewer_actor_id": command.reviewer_actor_id,
        "action": command.action.value,
        "proposal_sha256": bytes.fromhex(command.proposal_fingerprint),
        "operation_plan_sha256": (
            None
            if command.operation_plan_fingerprint is None
            else bytes.fromhex(command.operation_plan_fingerprint)
        ),
        "reason": command.reason,
        "decided_at": command.decided_at_utc,
    }


def _validate_replay(
    connection: Connection,
    command: PersistReviewDecision,
) -> PersistenceDisposition:
    existing = (
        connection.execute(
            _SELECT_REPLAY,
            {
                "workspace_id": command.workspace_id,
                "proposal_id": command.proposal_id,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing is None:
        raise PersistenceConflictError("review decision replay is unresolved")
    if not _matches_existing(existing, command):
        raise PersistenceConflictError("review decision replay has different content")
    return PersistenceDisposition.IDEMPOTENT_REPLAY


def _matches_existing(
    existing: RowMapping,
    command: PersistReviewDecision,
) -> bool:
    operation_plan_sha256 = existing["operation_plan_sha256"]
    expected_operation_plan_sha256 = (
        None
        if command.operation_plan_fingerprint is None
        else bytes.fromhex(command.operation_plan_fingerprint)
    )
    return (
        existing["review_decision_id"] == command.review_decision_id
        and existing["reviewer_actor_id"] == command.reviewer_actor_id
        and existing["action"] == command.action.value
        and _stored_digest(existing["proposal_sha256"])
        == bytes.fromhex(
            command.proposal_fingerprint,
        )
        and _stored_optional_digest(operation_plan_sha256)
        == expected_operation_plan_sha256
        and existing["reason"] == command.reason
        and _as_utc(existing["decided_at"]) == command.decided_at_utc
    )


def _proposal_status(action: ReviewDecisionAction) -> str:
    return {
        ReviewDecisionAction.APPROVE: "approved",
        ReviewDecisionAction.REJECT: "rejected",
    }[action]


def _validate_audit_event(
    audit_event: AuditAppend,
    command: PersistReviewDecision,
) -> None:
    if audit_event.workspace_id != command.workspace_id:
        raise ValueError("review audit workspace must match decision workspace")
    if audit_event.actor_id != command.reviewer_actor_id:
        raise ValueError("review audit actor must match reviewer")
    if audit_event.event_type is not AuditEventType.REVIEW_DECISION_RECORDED:
        raise ValueError("review audit event type must record review decision")
    if audit_event.subject_kind != "classification_proposal":
        raise ValueError("review audit subject kind must be classification_proposal")
    if audit_event.subject_id != str(command.proposal_id):
        raise ValueError("review audit subject must match proposal")
    if audit_event.previous_state != "needs_review":
        raise ValueError("review audit previous state must be needs_review")
    if audit_event.new_state != _proposal_status(command.action):
        raise ValueError("review audit new state must match action")


def _validate_fingerprint(name: str, value: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest")


def _stored_digest(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    raise ValueError("stored digest must be bytes")


def _stored_optional_digest(value: object) -> bytes | None:
    if value is None:
        return None
    return _stored_digest(value)


def _normalize_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _as_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("timestamps must be datetime values")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
