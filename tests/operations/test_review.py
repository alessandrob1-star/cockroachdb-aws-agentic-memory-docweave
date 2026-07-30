from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from docweave.analysis import (
    CandidateMetadata,
    ClassificationProposal,
    EvidenceReference,
    RawClassificationSignals,
    SignalStrength,
    TaxonomyClass,
)
from docweave.operations import (
    FileOperation,
    FileOperationRequest,
    InMemoryReviewDecisionLedger,
    ProposalReviewDecisionRequest,
    ReviewDecisionAction,
    ReviewDecisionValidationReason,
    ReviewDecisionValidationStatus,
    classification_proposal_fingerprint,
    create_proposal_review_decision,
    create_proposal_review_decision_from_fingerprint,
    plan_file_operation,
    validate_proposal_review_decision,
    validate_proposal_review_decision_fingerprint,
)
from docweave.operations.planning import FileOperationPlan

NOW = datetime(2026, 7, 30, 16, 45, tzinfo=UTC)


def proposal() -> ClassificationProposal:
    return ClassificationProposal(
        contract_version="classification.v1",
        taxonomy_version="docweave_mvp_v0_1",
        proposed_class=TaxonomyClass.INVOICE,
        document_language="en",
        rationale="The document states an invoice number and amount.",
        rationale_evidence_ids=("ev_1",),
        evidence=(
            EvidenceReference(
                evidence_id="ev_1",
                page_index=0,
                quote="Invoice INV-2026-004 total EUR 1200",
                supports=("classification", "amount"),
            ),
        ),
        candidate_metadata=(
            CandidateMetadata(
                name="invoice_number",
                value="INV-2026-004",
                evidence_ids=("ev_1",),
            ),
        ),
        alternative_classes=(),
        contradictions=(),
        missing_expected_evidence=(),
        raw_signals=RawClassificationSignals(
            classification_strength=SignalStrength.STRONG,
            evidence_coverage=SignalStrength.STRONG,
            ambiguity=SignalStrength.WEAK,
        ),
        abstention_reason=None,
    )


def ready_plan(tmp_path: Path) -> FileOperationPlan:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    (source_root / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    return plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="DocWeave Organized/Invoices/invoice.pdf",
        )
    )


def test_accepts_review_decision_for_exact_visible_proposal(
    tmp_path: Path,
) -> None:
    reviewed_proposal = proposal()
    operation_plan = ready_plan(tmp_path)

    decision = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.APPROVE,
        ),
        operation_plan=operation_plan,
    )
    validation = validate_proposal_review_decision(
        reviewed_proposal,
        decision,
        operation_plan=operation_plan,
    )

    assert validation.is_valid is True
    assert validation.status is ReviewDecisionValidationStatus.VALID
    assert validation.reason is ReviewDecisionValidationReason.VALID
    assert decision.proposal_fingerprint == classification_proposal_fingerprint(
        reviewed_proposal
    )
    assert decision.decided_at_utc.tzinfo is UTC


def test_blocks_rejection_without_human_reason() -> None:
    reviewed_proposal = proposal()
    decision = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.REJECT,
            reason=" \n ",
        ),
    )

    validation = validate_proposal_review_decision(reviewed_proposal, decision)

    assert validation.status is ReviewDecisionValidationStatus.BLOCKED
    assert validation.reason is ReviewDecisionValidationReason.MISSING_REASON


def test_blocks_review_decision_for_changed_proposal() -> None:
    reviewed_proposal = proposal()
    changed_proposal = replace(
        reviewed_proposal,
        proposed_class=TaxonomyClass.CONTRACT,
    )
    decision = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.APPROVE,
        ),
    )

    validation = validate_proposal_review_decision(changed_proposal, decision)

    assert validation.status is ReviewDecisionValidationStatus.BLOCKED
    assert (
        validation.reason
        is ReviewDecisionValidationReason.PROPOSAL_FINGERPRINT_MISMATCH
    )


def test_blocks_review_decision_for_changed_operation_plan(tmp_path: Path) -> None:
    reviewed_proposal = proposal()
    operation_plan = ready_plan(tmp_path)
    changed_plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=operation_plan.source_root,
            source_relative_path="invoice.pdf",
            destination_root=operation_plan.destination_root,
            destination_relative_path="DocWeave Organized/Invoices/changed.pdf",
        )
    )
    decision = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.APPROVE,
        ),
        operation_plan=operation_plan,
    )

    validation = validate_proposal_review_decision(
        reviewed_proposal,
        decision,
        operation_plan=changed_plan,
    )

    assert validation.status is ReviewDecisionValidationStatus.BLOCKED
    assert (
        validation.reason
        is ReviewDecisionValidationReason.OPERATION_PLAN_FINGERPRINT_MISMATCH
    )


def test_review_ledger_is_append_only_for_repeated_decisions() -> None:
    reviewed_proposal = proposal()
    first = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.ESCALATE,
            reason="Needs second reviewer.",
        ),
    )
    second = create_proposal_review_decision(
        reviewed_proposal,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-002",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-002",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.APPROVE,
        ),
    )
    ledger = InMemoryReviewDecisionLedger()

    ledger.append(first)
    ledger.append(second)

    assert ledger.decisions_for_proposal("proposal-001") == (first, second)
    assert ledger.all_decisions() == (first, second)


def test_validates_review_decision_from_retained_fingerprint() -> None:
    fingerprint = "b" * 64
    decision = create_proposal_review_decision_from_fingerprint(
        fingerprint,
        request=ProposalReviewDecisionRequest(
            review_decision_id="review-001",
            proposal_id="proposal-001",
            reviewer_actor_id="reviewer-001",
            decided_at_utc=NOW,
            action=ReviewDecisionAction.APPROVE,
        ),
    )

    validation = validate_proposal_review_decision_fingerprint(
        fingerprint,
        decision,
    )

    assert validation.status is ReviewDecisionValidationStatus.VALID
    assert validation.proposal_fingerprint == fingerprint
