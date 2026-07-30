from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.operations import ReviewDecisionAction
from docweave.operations.audit import AuditActorType, AuditEventType
from docweave.persistence import (
    AuditAppend,
    CockroachReviewDecisionRepository,
    PersistenceConflictError,
    PersistenceDisposition,
    PersistReviewDecision,
    TransactionRun,
)

NOW = datetime(2026, 7, 30, 16, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
PROPOSAL_ID = UUID("00000000-0000-4000-8000-000000000002")
REVIEW_DECISION_ID = UUID("00000000-0000-4000-8000-000000000003")
REVIEWER_ID = UUID("00000000-0000-4000-8000-000000000004")
PROPOSAL_FINGERPRINT = "ab" * 32
PLAN_FINGERPRINT = "cd" * 32
AUDIT_EVENT_ID = UUID("00000000-0000-4000-8000-000000000005")


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        mapping: Mapping[str, object] | None = None,
    ) -> None:
        self._scalar = scalar
        self._mapping = mapping

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> Mapping[str, object] | None:
        return self._mapping


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self.responses = list(responses)
        self.calls: list[
            tuple[str, Mapping[str, object] | Sequence[Mapping[str, object]] | None]
        ] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters))
        if not self.responses:
            raise AssertionError("unexpected database call")
        return self.responses.pop(0)


class FakeTransactionRunner:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.run_count = 0

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]:
        self.run_count += 1
        return TransactionRun(
            value=work(cast(Connection, self.connection)),
            attempts=1,
        )


def command() -> PersistReviewDecision:
    return PersistReviewDecision(
        workspace_id=WORKSPACE_ID,
        proposal_id=PROPOSAL_ID,
        review_decision_id=REVIEW_DECISION_ID,
        reviewer_actor_id=REVIEWER_ID,
        action=ReviewDecisionAction.APPROVE,
        proposal_fingerprint=PROPOSAL_FINGERPRINT,
        operation_plan_fingerprint=PLAN_FINGERPRINT,
        decided_at_utc=NOW,
    )


def audit_event() -> AuditAppend:
    return AuditAppend(
        event_id=AUDIT_EVENT_ID,
        workspace_id=WORKSPACE_ID,
        actor_id=REVIEWER_ID,
        actor_type=AuditActorType.HUMAN,
        correlation_id=f"review-decision:{REVIEW_DECISION_ID}",
        event_type=AuditEventType.REVIEW_DECISION_RECORDED,
        subject_kind="classification_proposal",
        subject_id=str(PROPOSAL_ID),
        occurred_at_utc=NOW,
        previous_state="needs_review",
        new_state="approved",
        plan_sha256=bytes.fromhex(PLAN_FINGERPRINT),
    )


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachReviewDecisionRepository, FakeTransactionRunner]:
    runner = FakeTransactionRunner(FakeConnection(responses))
    return CockroachReviewDecisionRepository(runner), runner


def test_persists_review_decision_and_updates_proposal_atomically() -> None:
    adapter, runner = repository(
        [
            FakeResult(
                mapping={
                    "proposal_id": PROPOSAL_ID,
                    "proposal_status": "needs_review",
                }
            ),
            FakeResult(scalar=REVIEW_DECISION_ID),
            FakeResult(scalar=PROPOSAL_ID),
        ]
    )

    result = adapter.persist(command())

    assert result is PersistenceDisposition.APPLIED
    assert runner.run_count == 1
    assert runner.connection.responses == []
    statements = "\n".join(statement for statement, _ in runner.connection.calls)
    assert "FOR UPDATE" in statements
    assert "INSERT INTO docweave.review_decisions" in statements
    assert "UPDATE docweave.proposals" in statements
    first_parameters = cast(Mapping[str, object], runner.connection.calls[1][1])
    assert first_parameters["proposal_sha256"] == bytes.fromhex(PROPOSAL_FINGERPRINT)
    assert first_parameters["operation_plan_sha256"] == bytes.fromhex(PLAN_FINGERPRINT)
    assert PROPOSAL_FINGERPRINT not in runner.connection.calls[1][0]


def test_persists_review_decision_and_audit_event_in_one_transaction() -> None:
    adapter, runner = repository(
        [
            FakeResult(
                mapping={
                    "proposal_id": PROPOSAL_ID,
                    "proposal_status": "needs_review",
                }
            ),
            FakeResult(scalar=REVIEW_DECISION_ID),
            FakeResult(scalar=PROPOSAL_ID),
            FakeResult(scalar=WORKSPACE_ID),
            FakeResult(mapping=None),
            FakeResult(),
        ]
    )

    result = adapter.persist(replace(command(), audit_event=audit_event()))

    assert result is PersistenceDisposition.APPLIED
    assert runner.run_count == 1
    assert runner.connection.responses == []
    statements = "\n".join(statement for statement, _ in runner.connection.calls)
    assert "INSERT INTO docweave.review_decisions" in statements
    assert "INSERT INTO docweave.audit_events" in statements
    audit_parameters = cast(Mapping[str, object], runner.connection.calls[5][1])
    assert audit_parameters["event_type"] == "review_decision_recorded"
    assert audit_parameters["subject_kind"] == "classification_proposal"
    assert audit_parameters["subject_id"] == str(PROPOSAL_ID)
    assert len(cast(bytes, audit_parameters["event_sha256"])) == 32


def test_exact_idempotent_replay_does_not_update_proposal_again() -> None:
    adapter, runner = repository(
        [
            FakeResult(
                mapping={
                    "proposal_id": PROPOSAL_ID,
                    "proposal_status": "approved",
                }
            ),
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "review_decision_id": REVIEW_DECISION_ID,
                    "reviewer_actor_id": REVIEWER_ID,
                    "action": "approve",
                    "proposal_sha256": bytes.fromhex(PROPOSAL_FINGERPRINT),
                    "operation_plan_sha256": bytes.fromhex(PLAN_FINGERPRINT),
                    "reason": None,
                    "decided_at": NOW,
                }
            ),
        ]
    )

    result = adapter.persist(command())

    assert result is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(runner.connection.calls) == 3


def test_reused_proposal_decision_with_different_content_is_rejected() -> None:
    adapter, _ = repository(
        [
            FakeResult(
                mapping={
                    "proposal_id": PROPOSAL_ID,
                    "proposal_status": "rejected",
                }
            ),
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "review_decision_id": REVIEW_DECISION_ID,
                    "reviewer_actor_id": REVIEWER_ID,
                    "action": "reject",
                    "proposal_sha256": bytes.fromhex(PROPOSAL_FINGERPRINT),
                    "operation_plan_sha256": bytes.fromhex(PLAN_FINGERPRINT),
                    "reason": "Not enough evidence",
                    "decided_at": NOW,
                }
            ),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different content"):
        adapter.persist(command())


def test_reject_requires_reason_and_updates_to_rejected() -> None:
    reject = replace(
        command(),
        action=ReviewDecisionAction.REJECT,
        reason="  wrong category   ",
    )
    adapter, runner = repository(
        [
            FakeResult(
                mapping={
                    "proposal_id": PROPOSAL_ID,
                    "proposal_status": "needs_review",
                }
            ),
            FakeResult(scalar=REVIEW_DECISION_ID),
            FakeResult(scalar=PROPOSAL_ID),
        ]
    )

    result = adapter.persist(reject)

    assert result is PersistenceDisposition.APPLIED
    update_parameters = cast(Mapping[str, object], runner.connection.calls[2][1])
    insert_parameters = cast(Mapping[str, object], runner.connection.calls[1][1])
    assert update_parameters["proposal_status"] == "rejected"
    assert insert_parameters["reason"] == "wrong category"


def test_contract_blocks_unsupported_actions_and_bad_fingerprints() -> None:
    with pytest.raises(ValueError, match="only accepts approve/reject"):
        replace(command(), action=ReviewDecisionAction.ESCALATE, reason="manager")

    with pytest.raises(ValueError, match="lowercase sha256"):
        replace(command(), proposal_fingerprint="AB")

    with pytest.raises(ValueError, match="subject"):
        replace(
            command(),
            audit_event=replace(audit_event(), subject_id=str(REVIEW_DECISION_ID)),
        )
