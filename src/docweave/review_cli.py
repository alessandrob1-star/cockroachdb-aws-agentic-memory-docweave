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
    ProposalReviewDecisionRequest,
    ReviewDecisionAction,
    ReviewDecisionValidationReason,
    ReviewDecisionValidationStatus,
    create_proposal_review_decision_from_fingerprint,
    validate_proposal_review_decision_fingerprint,
)
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.simple_memory_repository import (
    CockroachSimpleMemoryRepository,
    PersistHumanDecision,
)


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
    document_id: UUID | None = None
    operation: str | None = None
    previous_directory: str | None = None
    previous_filename: str | None = None
    next_directory: str | None = None
    next_filename: str | None = None
    file_status: str | None = None
    note: str | None = None


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
    repository = CockroachSimpleMemoryRepository(configured.transaction_runner)
    disposition = repository.persist_human_decision(
        PersistHumanDecision(
            proposal_id=command_input.proposal_id,
            human_decision_id=review_decision_id,
            actor_label="local-cockpit-reviewer",
            decision=decision.action.value,
            reason=decision.reason,
            decided_at_utc=decision.decided_at_utc,
            document_id=command_input.document_id,
            operation=command_input.operation,
            previous_directory=command_input.previous_directory,
            previous_filename=command_input.previous_filename,
            next_directory=command_input.next_directory,
            next_filename=command_input.next_filename,
            file_status=command_input.file_status,
            note=command_input.note,
        )
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
    except ValueError as error:
        print(f"Review decision failed: {type(error).__name__}", file=sys.stderr)
        return 3

    print(f"Review decision: {result.action}")
    print(f"Proposal id: {result.proposal_id}")
    print(f"Review decision id: {result.review_decision_id}")
    print(f"Review memory: {result.disposition.value}")
    return 0


def _validation_error_message(reason: ReviewDecisionValidationReason) -> str:
    return f"review decision validation blocked: {reason.value}"


if __name__ == "__main__":
    raise SystemExit(main())
