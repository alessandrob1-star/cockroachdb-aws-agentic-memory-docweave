"""Typed, non-authoritative classification proposal contracts."""

from dataclasses import dataclass
from enum import StrEnum

from docweave.analysis.taxonomy import TaxonomyClass

CLASSIFICATION_CONTRACT_VERSION = "classification.v1"


class SignalStrength(StrEnum):
    """Ordinal raw model signal, not a calibrated probability."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Exact text evidence anchored to one extracted page."""

    evidence_id: str
    page_index: int
    quote: str
    supports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    """Untrusted class-specific metadata proposed from cited evidence."""

    name: str
    value: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlternativeClass:
    """A distinct taxonomy alternative considered by the model."""

    class_code: TaxonomyClass
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Contradiction:
    """A conflict observed within the document evidence."""

    description: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawClassificationSignals:
    """Uncalibrated ordinal signals retained from the model response."""

    classification_strength: SignalStrength
    evidence_coverage: SignalStrength
    ambiguity: SignalStrength


@dataclass(frozen=True, slots=True)
class ClassificationProposal:
    """Validated proposal that remains non-authoritative until human review."""

    contract_version: str
    taxonomy_version: str
    proposed_class: TaxonomyClass
    document_language: str
    rationale: str
    rationale_evidence_ids: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]
    candidate_metadata: tuple[CandidateMetadata, ...]
    alternative_classes: tuple[AlternativeClass, ...]
    contradictions: tuple[Contradiction, ...]
    missing_expected_evidence: tuple[str, ...]
    raw_signals: RawClassificationSignals
    abstention_reason: str | None
