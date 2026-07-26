"""Adapter from approved analysis confidence to persistence scores."""

from docweave.analysis import BedrockClassificationRun
from docweave.analysis.confidence import compute_uncalibrated_confidence
from docweave.extraction import PdfExtractionResult
from docweave.persistence.classification_repository import ClassificationScores


def provide_uncalibrated_confidence_v0(
    run: BedrockClassificationRun,
    extraction: PdfExtractionResult,
) -> ClassificationScores:
    """Provide versioned raw scores while keeping calibration explicitly null."""
    result = compute_uncalibrated_confidence(run.proposal, extraction)
    return ClassificationScores(
        raw=result.raw,
        calibrated=result.calibrated,
        extraction=result.extraction,
        classification=result.classification,
        metadata=result.metadata,
        method_version=result.method_version,
    )
