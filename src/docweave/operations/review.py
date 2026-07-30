"""Human review decisions for non-authoritative model proposals."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from docweave.analysis.contracts import ClassificationProposal
from docweave.operations.approval import operation_plan_fingerprint
from docweave.operations.planning import FileOperationPlan

_SHA256_HEX_LENGTH = 64


class ReviewDecisionAction(StrEnum):
    """Explicit reviewer actions for one visible proposal."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"


class ReviewDecisionValidationStatus(StrEnum):
    """Validation result for a review decision before later persistence."""

    VALID = "valid"
    BLOCKED = "blocked"


class ReviewDecisionValidationReason(StrEnum):
    """Machine-readable reason for review decision validation."""

    VALID = "valid"
    MISSING_DECISION_ID = "missing_decision_id"
    MISSING_PROPOSAL_ID = "missing_proposal_id"
    MISSING_REVIEWER = "missing_reviewer"
    MISSING_REASON = "missing_reason"
    PROPOSAL_FINGERPRINT_MISMATCH = "proposal_fingerprint_mismatch"
    OPERATION_PLAN_FINGERPRINT_MISMATCH = "operation_plan_fingerprint_mismatch"


@dataclass(frozen=True, slots=True)
class ProposalReviewDecision:
    """Append-only human decision bound to one exact proposal preview."""

    review_decision_id: str
    proposal_id: str
    reviewer_actor_id: str
    decided_at_utc: datetime
    action: ReviewDecisionAction
    proposal_fingerprint: str
    reason: str | None = None
    operation_plan_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalReviewDecisionRequest:
    """Reviewed command fields that are independent from the proposal payload."""

    review_decision_id: str
    proposal_id: str
    reviewer_actor_id: str
    decided_at_utc: datetime
    action: ReviewDecisionAction
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewDecisionValidation:
    """Deterministic validation result for a review decision."""

    status: ReviewDecisionValidationStatus
    reason: ReviewDecisionValidationReason
    proposal_fingerprint: str
    review_decision_id: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status is ReviewDecisionValidationStatus.VALID


class InMemoryReviewDecisionLedger:
    """Append-only review decision ledger for local workflow tests."""

    def __init__(self) -> None:
        self._decisions: tuple[ProposalReviewDecision, ...] = ()

    def append(self, decision: ProposalReviewDecision) -> None:
        """Append one already validated decision without overwriting history."""
        self._decisions = (*self._decisions, decision)

    def decisions_for_proposal(
        self,
        proposal_id: str,
    ) -> tuple[ProposalReviewDecision, ...]:
        """Return all decisions recorded for one proposal in append order."""
        return tuple(
            decision
            for decision in self._decisions
            if decision.proposal_id == proposal_id
        )

    def all_decisions(self) -> tuple[ProposalReviewDecision, ...]:
        """Return the complete immutable review history."""
        return self._decisions


def create_proposal_review_decision(
    proposal: ClassificationProposal,
    *,
    request: ProposalReviewDecisionRequest,
    operation_plan: FileOperationPlan | None = None,
) -> ProposalReviewDecision:
    """Create a review decision bound to the proposal the reviewer saw."""
    return ProposalReviewDecision(
        review_decision_id=request.review_decision_id,
        proposal_id=request.proposal_id,
        reviewer_actor_id=request.reviewer_actor_id,
        decided_at_utc=_normalize_utc(request.decided_at_utc),
        action=request.action,
        proposal_fingerprint=classification_proposal_fingerprint(proposal),
        reason=_normalize_reason(request.reason),
        operation_plan_fingerprint=(
            None
            if operation_plan is None
            else operation_plan_fingerprint(operation_plan)
        ),
    )


def create_proposal_review_decision_from_fingerprint(
    proposal_fingerprint: str,
    *,
    request: ProposalReviewDecisionRequest,
    operation_plan_fingerprint: str | None = None,
) -> ProposalReviewDecision:
    """Create a review decision when only the reviewed fingerprint is retained."""
    _validate_fingerprint(proposal_fingerprint)
    if operation_plan_fingerprint is not None:
        _validate_fingerprint(operation_plan_fingerprint)
    return ProposalReviewDecision(
        review_decision_id=request.review_decision_id,
        proposal_id=request.proposal_id,
        reviewer_actor_id=request.reviewer_actor_id,
        decided_at_utc=_normalize_utc(request.decided_at_utc),
        action=request.action,
        proposal_fingerprint=proposal_fingerprint,
        reason=_normalize_reason(request.reason),
        operation_plan_fingerprint=operation_plan_fingerprint,
    )


def validate_proposal_review_decision(
    proposal: ClassificationProposal,
    decision: ProposalReviewDecision,
    *,
    operation_plan: FileOperationPlan | None = None,
) -> ReviewDecisionValidation:
    """Validate that a review decision still matches the visible proposal."""
    expected_proposal_fingerprint = classification_proposal_fingerprint(proposal)
    status = ReviewDecisionValidationStatus.VALID
    reason = ReviewDecisionValidationReason.VALID

    if not decision.review_decision_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_DECISION_ID
    elif not decision.proposal_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_PROPOSAL_ID
    elif not decision.reviewer_actor_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_REVIEWER
    elif (
        decision.action
        in {
            ReviewDecisionAction.REJECT,
            ReviewDecisionAction.REQUEST_CHANGES,
            ReviewDecisionAction.ESCALATE,
        }
        and not (decision.reason or "").strip()
    ):
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_REASON
    elif decision.proposal_fingerprint != expected_proposal_fingerprint:
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.PROPOSAL_FINGERPRINT_MISMATCH
    elif operation_plan is not None and decision.operation_plan_fingerprint != (
        operation_plan_fingerprint(operation_plan)
    ):
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.OPERATION_PLAN_FINGERPRINT_MISMATCH

    return ReviewDecisionValidation(
        status=status,
        reason=reason,
        proposal_fingerprint=expected_proposal_fingerprint,
        review_decision_id=decision.review_decision_id,
    )


def validate_proposal_review_decision_fingerprint(
    expected_proposal_fingerprint: str,
    decision: ProposalReviewDecision,
    *,
    expected_operation_plan_fingerprint: str | None = None,
) -> ReviewDecisionValidation:
    """Validate a decision against retained reviewed fingerprints."""
    _validate_fingerprint(expected_proposal_fingerprint)
    if expected_operation_plan_fingerprint is not None:
        _validate_fingerprint(expected_operation_plan_fingerprint)
    return _validate_decision_fields(
        decision,
        expected_proposal_fingerprint=expected_proposal_fingerprint,
        expected_operation_plan_fingerprint=expected_operation_plan_fingerprint,
    )


def classification_proposal_fingerprint(proposal: ClassificationProposal) -> str:
    """Return a stable fingerprint for the exact model proposal under review."""
    payload = {
        "contract_version": proposal.contract_version,
        "taxonomy_version": proposal.taxonomy_version,
        "proposed_class": proposal.proposed_class.value,
        "document_language": proposal.document_language,
        "rationale": proposal.rationale,
        "rationale_evidence_ids": proposal.rationale_evidence_ids,
        "evidence": tuple(
            {
                "evidence_id": evidence.evidence_id,
                "page_index": evidence.page_index,
                "quote": evidence.quote,
                "supports": evidence.supports,
            }
            for evidence in proposal.evidence
        ),
        "candidate_metadata": tuple(
            {
                "name": metadata.name,
                "value": metadata.value,
                "evidence_ids": metadata.evidence_ids,
            }
            for metadata in proposal.candidate_metadata
        ),
        "alternative_classes": tuple(
            {
                "class_code": alternative.class_code.value,
                "reason": alternative.reason,
                "evidence_ids": alternative.evidence_ids,
            }
            for alternative in proposal.alternative_classes
        ),
        "contradictions": tuple(
            {
                "description": contradiction.description,
                "evidence_ids": contradiction.evidence_ids,
            }
            for contradiction in proposal.contradictions
        ),
        "missing_expected_evidence": proposal.missing_expected_evidence,
        "raw_signals": {
            "classification_strength": (
                proposal.raw_signals.classification_strength.value
            ),
            "evidence_coverage": proposal.raw_signals.evidence_coverage.value,
            "ambiguity": proposal.raw_signals.ambiguity.value,
        },
        "abstention_reason": proposal.abstention_reason,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def _validate_decision_fields(
    decision: ProposalReviewDecision,
    *,
    expected_proposal_fingerprint: str,
    expected_operation_plan_fingerprint: str | None,
) -> ReviewDecisionValidation:
    status = ReviewDecisionValidationStatus.VALID
    reason = ReviewDecisionValidationReason.VALID

    if not decision.review_decision_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_DECISION_ID
    elif not decision.proposal_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_PROPOSAL_ID
    elif not decision.reviewer_actor_id.strip():
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_REVIEWER
    elif (
        decision.action
        in {
            ReviewDecisionAction.REJECT,
            ReviewDecisionAction.REQUEST_CHANGES,
            ReviewDecisionAction.ESCALATE,
        }
        and not (decision.reason or "").strip()
    ):
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.MISSING_REASON
    elif decision.proposal_fingerprint != expected_proposal_fingerprint:
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.PROPOSAL_FINGERPRINT_MISMATCH
    elif expected_operation_plan_fingerprint is not None and (
        decision.operation_plan_fingerprint != expected_operation_plan_fingerprint
    ):
        status = ReviewDecisionValidationStatus.BLOCKED
        reason = ReviewDecisionValidationReason.OPERATION_PLAN_FINGERPRINT_MISMATCH

    return ReviewDecisionValidation(
        status=status,
        reason=reason,
        proposal_fingerprint=expected_proposal_fingerprint,
        review_decision_id=decision.review_decision_id,
    )


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _validate_fingerprint(value: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("fingerprint must be a lowercase sha256 hex digest")
