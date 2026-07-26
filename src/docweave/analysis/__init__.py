"""Structured analysis contracts for genuine model-driven proposals."""

from docweave.analysis.contracts import (
    CLASSIFICATION_CONTRACT_VERSION,
    AlternativeClass,
    CandidateMetadata,
    ClassificationProposal,
    Contradiction,
    EvidenceReference,
    RawClassificationSignals,
    SignalStrength,
)
from docweave.analysis.request import (
    CLASSIFICATION_MAXIMUM_OUTPUT_TOKENS,
    MAXIMUM_CLASSIFICATION_INPUT_CHARACTERS,
    MAXIMUM_CLASSIFICATION_INPUT_PAGES,
    ClassificationInputCode,
    ClassificationInputError,
    classification_v1_converse_fields,
)
from docweave.analysis.schema import (
    classification_v1_json_schema,
    classification_v1_output_config,
)
from docweave.analysis.taxonomy import TAXONOMY_VERSION, TaxonomyClass
from docweave.analysis.validation import (
    MAXIMUM_RESPONSE_BYTES,
    ClassificationValidationCode,
    ClassificationValidationError,
    decode_classification_v1,
)

__all__ = [
    "CLASSIFICATION_CONTRACT_VERSION",
    "CLASSIFICATION_MAXIMUM_OUTPUT_TOKENS",
    "MAXIMUM_CLASSIFICATION_INPUT_CHARACTERS",
    "MAXIMUM_CLASSIFICATION_INPUT_PAGES",
    "MAXIMUM_RESPONSE_BYTES",
    "TAXONOMY_VERSION",
    "AlternativeClass",
    "CandidateMetadata",
    "ClassificationInputCode",
    "ClassificationInputError",
    "ClassificationProposal",
    "ClassificationValidationCode",
    "ClassificationValidationError",
    "Contradiction",
    "EvidenceReference",
    "RawClassificationSignals",
    "SignalStrength",
    "TaxonomyClass",
    "classification_v1_converse_fields",
    "classification_v1_json_schema",
    "classification_v1_output_config",
    "decode_classification_v1",
]
