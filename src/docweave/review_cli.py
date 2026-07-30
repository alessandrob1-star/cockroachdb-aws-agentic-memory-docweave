"""Command-line entrypoint for durable human review decisions."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from docweave.application_runtime import (
    ConfiguredReviewDecisionRuntime,
    RuntimeConfigurationError,
    build_configured_review_decision_runtime,
)
from docweave.operations import (
    AuditActorType,
    AuditEventType,
    ProposalReviewDecision,
    ProposalReviewDecisionRequest,
    ReviewDecisionAction,
    ReviewDecisionValidationReason,
    ReviewDecisionValidationStatus,
    create_proposal_review_decision_from_fingerprint,
    validate_proposal_review_decision_fingerprint,
)
from docweave.persistence import AuditAppend, PersistReviewDecision
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.operation_repository import PersistenceConflictError


@dataclass(frozen=True, slots=True)
class ReviewDecisionCommandResult:
    """Content-minimized result safe for terminal output."""

    action: str
    proposal_id: UUID
    review_decision_id: UUID
    disposition: PersistenceDisposition


@dataclass(frozen=True, slots=True)
class ReviewDecisionCommandInput:
    """Validated command fields supplied by a human review boundary."""

    proposal_id: UUID
    action: ReviewDecisionAction
    proposal_fingerprint: str
    reason: str | None = None
    operation_plan_fingerprint: str | None = None
    review_decision_id: UUID | None = None
    decided_at_utc: datetime | None = None


def persist_review_decision(
    command_input: ReviewDecisionCommandInput,
) -> ReviewDecisionCommandResult:
    """Persist one human decision through the configured CockroachDB runtime."""
    configured = build_configured_review_decision_runtime()
    return _persist_review_decision_with_runtime(
        configured,
        command_input,
    )


def _persist_review_decision_with_runtime(
    configured: ConfiguredReviewDecisionRuntime,
    command_input: ReviewDecisionCommandInput,
) -> ReviewDecisionCommandResult:
    review_decision_id = command_input.review_decision_id or uuid4()
    decided_at_utc = command_input.decided_at_utc or datetime.now(UTC)
    request = ProposalReviewDecisionRequest(
        review_decision_id=str(review_decision_id),
        proposal_id=str(command_input.proposal_id),
        reviewer_actor_id=str(configured.config.approved_by_actor_id),
        decided_at_utc=decided_at_utc,
        action=command_input.action,
        reason=command_input.reason,
    )
    decision = create_proposal_review_decision_from_fingerprint(
        command_input.proposal_fingerprint,
        request=request,
        operation_plan_fingerprint=command_input.operation_plan_fingerprint,
    )
    validation = validate_proposal_review_decision_fingerprint(
        command_input.proposal_fingerprint,
        decision,
        expected_operation_plan_fingerprint=command_input.operation_plan_fingerprint,
    )
    if validation.status is not ReviewDecisionValidationStatus.VALID:
        raise ValueError(_validation_error_message(validation.reason))
    disposition = configured.repository.persist(
        _persist_command(configured, decision),
    )
    return ReviewDecisionCommandResult(
        action=decision.action.value,
        proposal_id=command_input.proposal_id,
        review_decision_id=review_decision_id,
        disposition=disposition,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the command and print sanitized, reproducible outcome fields."""
    parser = argparse.ArgumentParser(
        description=(
            "Persist one approved or rejected DocWeave proposal review decision "
            "through the configured CockroachDB runtime."
        )
    )
    parser.add_argument("--proposal-id", type=UUID, required=True)
    parser.add_argument(
        "--action",
        choices=(ReviewDecisionAction.APPROVE.value, ReviewDecisionAction.REJECT.value),
        required=True,
    )
    parser.add_argument("--proposal-fingerprint", required=True)
    parser.add_argument("--operation-plan-fingerprint")
    parser.add_argument("--reason")
    parser.add_argument("--review-decision-id", type=UUID)
    args = parser.parse_args(argv)

    try:
        result = persist_review_decision(
            ReviewDecisionCommandInput(
                proposal_id=args.proposal_id,
                action=ReviewDecisionAction(args.action),
                proposal_fingerprint=args.proposal_fingerprint,
                operation_plan_fingerprint=args.operation_plan_fingerprint,
                reason=args.reason,
                review_decision_id=args.review_decision_id,
            ),
        )
    except RuntimeConfigurationError as error:
        print(
            f"Configuration failed: {error.code.value} ({error.variable_name})",
            file=sys.stderr,
        )
        return 2
    except (PersistenceConflictError, ValueError) as error:
        print(f"Review decision failed: {type(error).__name__}", file=sys.stderr)
        return 3

    print(f"Review decision: {result.action}")
    print(f"Proposal id: {result.proposal_id}")
    print(f"Review decision id: {result.review_decision_id}")
    print(f"Review memory: {result.disposition.value}")
    return 0


def _persist_command(
    configured: ConfiguredReviewDecisionRuntime,
    decision: ProposalReviewDecision,
) -> PersistReviewDecision:
    return PersistReviewDecision(
        workspace_id=configured.config.workspace_id,
        proposal_id=UUID(decision.proposal_id),
        review_decision_id=UUID(decision.review_decision_id),
        reviewer_actor_id=UUID(decision.reviewer_actor_id),
        action=decision.action,
        proposal_fingerprint=decision.proposal_fingerprint,
        operation_plan_fingerprint=decision.operation_plan_fingerprint,
        reason=decision.reason,
        decided_at_utc=decision.decided_at_utc,
        audit_event=AuditAppend(
            event_id=uuid4(),
            workspace_id=configured.config.workspace_id,
            actor_id=configured.config.approved_by_actor_id,
            actor_type=AuditActorType.HUMAN,
            correlation_id=f"review-decision:{decision.review_decision_id}",
            event_type=AuditEventType.REVIEW_DECISION_RECORDED,
            subject_kind="classification_proposal",
            subject_id=decision.proposal_id,
            occurred_at_utc=decision.decided_at_utc,
            previous_state="needs_review",
            new_state=_proposal_status(decision.action),
            reason=decision.reason,
            plan_sha256=(
                None
                if decision.operation_plan_fingerprint is None
                else bytes.fromhex(decision.operation_plan_fingerprint)
            ),
        ),
    )


def _validation_error_message(reason: ReviewDecisionValidationReason) -> str:
    return f"review decision validation blocked: {reason.value}"


def _proposal_status(action: ReviewDecisionAction) -> str:
    return {
        ReviewDecisionAction.APPROVE: "approved",
        ReviewDecisionAction.REJECT: "rejected",
    }[action]


if __name__ == "__main__":
    raise SystemExit(main())
