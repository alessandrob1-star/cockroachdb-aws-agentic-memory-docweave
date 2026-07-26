"""Deterministic uncalibrated confidence for review ordering."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from docweave.analysis.contracts import ClassificationProposal, SignalStrength
from docweave.extraction import ExtractionStatus, PdfExtractionResult

CONFIDENCE_METHOD_VERSION = "confidence.raw.v0_1"
_QUANTUM = Decimal("0.00001")
_ZERO = Decimal(0)
_ONE = Decimal(1)
_STRENGTH = {
    SignalStrength.STRONG: Decimal("0.85"),
    SignalStrength.MODERATE: Decimal("0.60"),
    SignalStrength.WEAK: Decimal("0.35"),
}
_AMBIGUITY_CERTAINTY = {
    SignalStrength.STRONG: Decimal("0.35"),
    SignalStrength.MODERATE: Decimal("0.60"),
    SignalStrength.WEAK: Decimal("0.85"),
}


@dataclass(frozen=True, slots=True)
class UncalibratedConfidence:
    """Versioned review-ordering scores that are not probabilities."""

    raw: Decimal
    extraction: Decimal
    classification: Decimal
    metadata: Decimal
    method_version: str = CONFIDENCE_METHOD_VERSION
    calibrated: None = None


def compute_uncalibrated_confidence(
    proposal: ClassificationProposal,
    extraction: PdfExtractionResult,
) -> UncalibratedConfidence:
    """Score only validated observable signals with no filename input."""
    extraction_score = _extraction_score(extraction)
    signals = proposal.raw_signals
    classification_base = (
        Decimal("0.50") * _STRENGTH[signals.classification_strength]
        + Decimal("0.30") * _STRENGTH[signals.evidence_coverage]
        + Decimal("0.20") * _AMBIGUITY_CERTAINTY[signals.ambiguity]
    )
    contradiction_penalty = min(
        Decimal("0.30"),
        Decimal("0.10") * len(proposal.contradictions),
    )
    missing_evidence_penalty = min(
        Decimal("0.15"),
        Decimal("0.03") * len(proposal.missing_expected_evidence),
    )
    alternative_penalty = min(
        Decimal("0.10"),
        Decimal("0.05") * len(proposal.alternative_classes),
    )
    classification_score = _bounded(
        classification_base
        - contradiction_penalty
        - missing_evidence_penalty
        - alternative_penalty
    )
    metadata_score = _metadata_score(proposal)
    return UncalibratedConfidence(
        raw=classification_score,
        extraction=extraction_score,
        classification=classification_score,
        metadata=metadata_score,
    )


def _extraction_score(extraction: PdfExtractionResult) -> Decimal:
    if (
        extraction.status is not ExtractionStatus.COMPLETED
        or extraction.document_page_count is None
        or extraction.document_page_count <= 0
        or extraction.source_sha256 is None
        or extraction.source_bytes is None
    ):
        return _ZERO.quantize(_QUANTUM)
    observed_pages = len(extraction.pages)
    page_coverage = Decimal(observed_pages) / Decimal(extraction.document_page_count)
    return _bounded(page_coverage)


def _metadata_score(proposal: ClassificationProposal) -> Decimal:
    if not proposal.candidate_metadata:
        return _ZERO.quantize(_QUANTUM)
    evidence_ids = {item.evidence_id for item in proposal.evidence}
    supported = sum(
        bool(item.evidence_ids)
        and all(evidence_id in evidence_ids for evidence_id in item.evidence_ids)
        for item in proposal.candidate_metadata
    )
    return _bounded(Decimal(supported) / Decimal(len(proposal.candidate_metadata)))


def _bounded(value: Decimal) -> Decimal:
    return min(_ONE, max(_ZERO, value)).quantize(
        _QUANTUM,
        rounding=ROUND_HALF_UP,
    )
