from dataclasses import replace
from decimal import Decimal

from docweave.analysis import (
    CONFIDENCE_METHOD_VERSION,
    AlternativeClass,
    CandidateMetadata,
    ClassificationProposal,
    Contradiction,
    EvidenceReference,
    RawClassificationSignals,
    SignalStrength,
    TaxonomyClass,
    compute_uncalibrated_confidence,
)
from docweave.extraction import (
    ExtractedPage,
    ExtractionStatus,
    PdfExtractionResult,
)

PAGES = (
    ExtractedPage(page_index=0, page_label="1", text="INVOICE INV-17"),
    ExtractedPage(page_index=1, page_label="2", text="Total EUR 42.00"),
)


def proposal(
    *,
    signals: RawClassificationSignals | None = None,
) -> ClassificationProposal:
    return ClassificationProposal(
        contract_version="classification.v1",
        taxonomy_version="docweave_mvp_v0_1",
        proposed_class=TaxonomyClass.INVOICE,
        document_language="en",
        rationale="Invoice evidence is explicit.",
        rationale_evidence_ids=("ev_1",),
        evidence=(
            EvidenceReference(
                evidence_id="ev_1",
                page_index=0,
                quote="INVOICE INV-17",
                supports=("classification",),
            ),
        ),
        candidate_metadata=(
            CandidateMetadata(
                name="invoice_number",
                value="INV-17",
                evidence_ids=("ev_1",),
            ),
        ),
        alternative_classes=(),
        contradictions=(),
        missing_expected_evidence=(),
        raw_signals=signals
        or RawClassificationSignals(
            classification_strength=SignalStrength.STRONG,
            evidence_coverage=SignalStrength.STRONG,
            ambiguity=SignalStrength.WEAK,
        ),
        abstention_reason=None,
    )


def extraction(
    *,
    pages: tuple[ExtractedPage, ...] = PAGES,
    page_count: int = 2,
    status: ExtractionStatus = ExtractionStatus.COMPLETED,
) -> PdfExtractionResult:
    return PdfExtractionResult(
        status=status,
        pages=pages,
        source_sha256="ab" * 32,
        source_bytes=42,
        document_page_count=page_count,
        extractor="qt_pdf",
    )


def test_stronger_signals_produce_a_higher_review_ordering_score() -> None:
    strong = compute_uncalibrated_confidence(proposal(), extraction())
    weak = compute_uncalibrated_confidence(
        proposal(
            signals=RawClassificationSignals(
                classification_strength=SignalStrength.WEAK,
                evidence_coverage=SignalStrength.WEAK,
                ambiguity=SignalStrength.STRONG,
            )
        ),
        extraction(),
    )

    assert strong.classification == Decimal("0.85000")
    assert weak.classification == Decimal("0.35000")
    assert strong.classification > weak.classification
    assert strong.raw == strong.classification
    assert strong.calibrated is None


def test_penalties_are_monotonic_bounded_and_versioned() -> None:
    baseline = compute_uncalibrated_confidence(proposal(), extraction())
    penalized_proposal = replace(
        proposal(),
        contradictions=(
            Contradiction(description="Total conflicts.", evidence_ids=("ev_1",)),
        ),
        missing_expected_evidence=("supplier", "due_date"),
        alternative_classes=(
            AlternativeClass(
                class_code=TaxonomyClass.OTHER,
                reason="Generic commercial record.",
                evidence_ids=("ev_1",),
            ),
        ),
    )
    penalized = compute_uncalibrated_confidence(
        penalized_proposal,
        extraction(),
    )
    saturated = compute_uncalibrated_confidence(
        replace(
            penalized_proposal,
            contradictions=penalized_proposal.contradictions * 20,
            missing_expected_evidence=("missing",) * 20,
            alternative_classes=penalized_proposal.alternative_classes * 20,
        ),
        extraction(),
    )

    assert penalized.classification < baseline.classification
    assert penalized.classification == Decimal("0.64000")
    assert Decimal(0) <= saturated.classification <= Decimal(1)
    assert penalized.method_version == CONFIDENCE_METHOD_VERSION


def test_extraction_score_uses_observed_page_coverage_and_provenance() -> None:
    complete = compute_uncalibrated_confidence(proposal(), extraction())
    partial = compute_uncalibrated_confidence(
        proposal(),
        extraction(pages=PAGES[:1]),
    )
    failed = compute_uncalibrated_confidence(
        proposal(),
        extraction(
            pages=(),
            status=ExtractionStatus.WORKER_FAILED,
        ),
    )

    assert complete.extraction == Decimal("1.00000")
    assert partial.extraction == Decimal("0.50000")
    assert failed.extraction == Decimal("0.00000")


def test_metadata_score_requires_evidence_for_each_candidate() -> None:
    supported = compute_uncalibrated_confidence(proposal(), extraction())
    unsupported = compute_uncalibrated_confidence(
        replace(
            proposal(),
            candidate_metadata=(
                CandidateMetadata(
                    name="invoice_number",
                    value="INV-17",
                    evidence_ids=("missing",),
                ),
            ),
        ),
        extraction(),
    )
    absent = compute_uncalibrated_confidence(
        replace(proposal(), candidate_metadata=()),
        extraction(),
    )

    assert supported.metadata == Decimal("1.00000")
    assert unsupported.metadata == Decimal("0.00000")
    assert absent.metadata == Decimal("0.00000")


def test_uncalibrated_confidence_keeps_calibration_explicitly_null() -> None:
    scores = compute_uncalibrated_confidence(proposal(), extraction())

    assert scores.raw == Decimal("0.85000")
    assert scores.calibrated is None
    assert scores.method_version == CONFIDENCE_METHOD_VERSION
