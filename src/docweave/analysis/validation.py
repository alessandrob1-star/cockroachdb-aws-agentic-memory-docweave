"""Fail-closed decoder for untrusted ``classification.v1`` model output."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

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
from docweave.analysis.taxonomy import TAXONOMY_VERSION, TaxonomyClass
from docweave.extraction import ExtractedPage

MAXIMUM_RESPONSE_BYTES = 256 * 1024
_MAXIMUM_EVIDENCE = 50
_MAXIMUM_METADATA = 50
_MAXIMUM_ALTERNATIVES = 3
_MAXIMUM_CONTRADICTIONS = 10
_MAXIMUM_MISSING_EVIDENCE = 20
_MAXIMUM_QUOTE_CHARACTERS = 1_000
_MAXIMUM_TEXT_CHARACTERS = 2_000
_EVIDENCE_ID = re.compile(r"ev_[1-9][0-9]{0,2}\Z")
_METADATA_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_LANGUAGE_TAG = re.compile(r"(?:[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*|und)\Z")
_SUPPORTED_EVIDENCE_ROLES = {
    "classification",
    "metadata",
    "language",
    "contradiction",
}

_TOP_LEVEL_KEYS = {
    "contract_version",
    "taxonomy_version",
    "proposed_class",
    "document_language",
    "rationale",
    "rationale_evidence_ids",
    "evidence",
    "candidate_metadata",
    "alternative_classes",
    "contradictions",
    "missing_expected_evidence",
    "raw_signals",
    "abstention_reason",
}


class ClassificationValidationCode(StrEnum):
    """Stable, content-free reason for rejecting model output."""

    ABSTENTION_INVALID = "abstention_invalid"
    ALTERNATIVE_INVALID = "alternative_invalid"
    CONTRACT_VERSION_INVALID = "contract_version_invalid"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    EVIDENCE_INVALID = "evidence_invalid"
    EVIDENCE_REFERENCE_INVALID = "evidence_reference_invalid"
    INVALID_JSON = "invalid_json"
    LANGUAGE_INVALID = "language_invalid"
    METADATA_INVALID = "metadata_invalid"
    RESPONSE_TOO_LARGE = "response_too_large"
    SCHEMA_INVALID = "schema_invalid"
    TAXONOMY_INVALID = "taxonomy_invalid"
    TEXT_LIMIT_EXCEEDED = "text_limit_exceeded"


class ClassificationValidationError(ValueError):
    """Reject a response without retaining document or response content."""

    def __init__(self, code: ClassificationValidationCode) -> None:
        super().__init__(code.value)
        self.code = code


def decode_classification_v1(
    response_text: str,
    *,
    extracted_pages: tuple[ExtractedPage, ...],
) -> ClassificationProposal:
    """Decode and validate one non-authoritative model proposal."""
    if len(response_text.encode("utf-8")) > MAXIMUM_RESPONSE_BYTES:
        raise ClassificationValidationError(
            ClassificationValidationCode.RESPONSE_TOO_LARGE
        )
    try:
        payload = json.loads(
            response_text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_number,
        )
    except ClassificationValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ClassificationValidationError(
            ClassificationValidationCode.INVALID_JSON
        ) from error
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_KEYS:
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)

    _validate_versions(payload)
    proposed_class = _taxonomy_class(payload["proposed_class"])
    document_language = _bounded_string(payload["document_language"])
    if _LANGUAGE_TAG.fullmatch(document_language) is None:
        raise ClassificationValidationError(
            ClassificationValidationCode.LANGUAGE_INVALID
        )

    evidence = _decode_evidence(payload["evidence"], extracted_pages)
    evidence_ids = {item.evidence_id for item in evidence}
    rationale = _nonblank_string(payload["rationale"])
    rationale_ids = _evidence_ids(payload["rationale_evidence_ids"], evidence_ids)
    if not rationale_ids:
        raise ClassificationValidationError(
            ClassificationValidationCode.EVIDENCE_REFERENCE_INVALID
        )

    metadata = _decode_metadata(payload["candidate_metadata"], evidence_ids)
    alternatives = _decode_alternatives(
        payload["alternative_classes"],
        evidence_ids,
        proposed_class,
    )
    contradictions = _decode_contradictions(
        payload["contradictions"],
        evidence_ids,
    )
    missing = _string_list(
        payload["missing_expected_evidence"],
        maximum_items=_MAXIMUM_MISSING_EVIDENCE,
    )
    if any(not item.strip() for item in missing):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    signals = _decode_signals(payload["raw_signals"])
    abstention_reason = _decode_abstention(
        payload["abstention_reason"],
        proposed_class,
    )

    return ClassificationProposal(
        contract_version=CLASSIFICATION_CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        proposed_class=proposed_class,
        document_language=document_language,
        rationale=rationale,
        rationale_evidence_ids=rationale_ids,
        evidence=evidence,
        candidate_metadata=metadata,
        alternative_classes=alternatives,
        contradictions=contradictions,
        missing_expected_evidence=missing,
        raw_signals=signals,
        abstention_reason=abstention_reason,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClassificationValidationError(
                ClassificationValidationCode.DUPLICATE_JSON_KEY
            )
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise ClassificationValidationError(ClassificationValidationCode.INVALID_JSON)


def _validate_versions(payload: dict[str, Any]) -> None:
    if payload["contract_version"] != CLASSIFICATION_CONTRACT_VERSION:
        raise ClassificationValidationError(
            ClassificationValidationCode.CONTRACT_VERSION_INVALID
        )
    if payload["taxonomy_version"] != TAXONOMY_VERSION:
        raise ClassificationValidationError(
            ClassificationValidationCode.TAXONOMY_INVALID
        )


def _taxonomy_class(value: Any) -> TaxonomyClass:
    if not isinstance(value, str):
        raise ClassificationValidationError(
            ClassificationValidationCode.TAXONOMY_INVALID
        )
    try:
        return TaxonomyClass(value)
    except ValueError as error:
        raise ClassificationValidationError(
            ClassificationValidationCode.TAXONOMY_INVALID
        ) from error


def _decode_evidence(
    value: Any,
    pages: tuple[ExtractedPage, ...],
) -> tuple[EvidenceReference, ...]:
    items = _object_list(value, _MAXIMUM_EVIDENCE)
    page_text = {page.page_index: page.text for page in pages}
    evidence: list[EvidenceReference] = []
    seen_ids: set[str] = set()
    for item in items:
        _exact_keys(item, {"evidence_id", "page_index", "quote", "supports"})
        evidence_id = _bounded_string(item["evidence_id"])
        page_index = item["page_index"]
        quote = _nonblank_string(
            item["quote"],
            maximum_characters=_MAXIMUM_QUOTE_CHARACTERS,
        )
        supports = _string_list(item["supports"], maximum_items=4)
        if (
            _EVIDENCE_ID.fullmatch(evidence_id) is None
            or evidence_id in seen_ids
            or type(page_index) is not int
            or page_index not in page_text
            or quote not in page_text[page_index]
            or not supports
            or not set(supports).issubset(_SUPPORTED_EVIDENCE_ROLES)
        ):
            raise ClassificationValidationError(
                ClassificationValidationCode.EVIDENCE_INVALID
            )
        seen_ids.add(evidence_id)
        evidence.append(
            EvidenceReference(
                evidence_id=evidence_id,
                page_index=page_index,
                quote=quote,
                supports=supports,
            )
        )
    return tuple(evidence)


def _decode_metadata(
    value: Any,
    evidence_ids: set[str],
) -> tuple[CandidateMetadata, ...]:
    items = _object_list(value, _MAXIMUM_METADATA)
    metadata: list[CandidateMetadata] = []
    seen_names: set[str] = set()
    for item in items:
        _exact_keys(item, {"name", "value", "evidence_ids"})
        name = _bounded_string(item["name"])
        proposed_value = _nonblank_string(item["value"])
        references = _evidence_ids(item["evidence_ids"], evidence_ids)
        if (
            _METADATA_NAME.fullmatch(name) is None
            or name in seen_names
            or not references
        ):
            raise ClassificationValidationError(
                ClassificationValidationCode.METADATA_INVALID
            )
        seen_names.add(name)
        metadata.append(
            CandidateMetadata(
                name=name,
                value=proposed_value,
                evidence_ids=references,
            )
        )
    return tuple(metadata)


def _decode_alternatives(
    value: Any,
    evidence_ids: set[str],
    proposed_class: TaxonomyClass,
) -> tuple[AlternativeClass, ...]:
    items = _object_list(value, _MAXIMUM_ALTERNATIVES)
    alternatives: list[AlternativeClass] = []
    seen_classes: set[TaxonomyClass] = set()
    for item in items:
        _exact_keys(item, {"class_code", "reason", "evidence_ids"})
        class_code = _taxonomy_class(item["class_code"])
        reason = _nonblank_string(item["reason"])
        references = _evidence_ids(item["evidence_ids"], evidence_ids)
        if (
            class_code is proposed_class
            or class_code in seen_classes
            or class_code is TaxonomyClass.UNCLASSIFIED
        ):
            raise ClassificationValidationError(
                ClassificationValidationCode.ALTERNATIVE_INVALID
            )
        seen_classes.add(class_code)
        alternatives.append(
            AlternativeClass(
                class_code=class_code,
                reason=reason,
                evidence_ids=references,
            )
        )
    return tuple(alternatives)


def _decode_contradictions(
    value: Any,
    evidence_ids: set[str],
) -> tuple[Contradiction, ...]:
    items = _object_list(value, _MAXIMUM_CONTRADICTIONS)
    contradictions: list[Contradiction] = []
    for item in items:
        _exact_keys(item, {"description", "evidence_ids"})
        description = _nonblank_string(item["description"])
        references = _evidence_ids(item["evidence_ids"], evidence_ids)
        if not references:
            raise ClassificationValidationError(
                ClassificationValidationCode.EVIDENCE_REFERENCE_INVALID
            )
        contradictions.append(
            Contradiction(description=description, evidence_ids=references)
        )
    return tuple(contradictions)


def _decode_signals(value: Any) -> RawClassificationSignals:
    if not isinstance(value, dict):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    _exact_keys(
        value,
        {"classification_strength", "evidence_coverage", "ambiguity"},
    )
    try:
        return RawClassificationSignals(
            classification_strength=SignalStrength(value["classification_strength"]),
            evidence_coverage=SignalStrength(value["evidence_coverage"]),
            ambiguity=SignalStrength(value["ambiguity"]),
        )
    except (TypeError, ValueError) as error:
        raise ClassificationValidationError(
            ClassificationValidationCode.SCHEMA_INVALID
        ) from error


def _decode_abstention(
    value: Any,
    proposed_class: TaxonomyClass,
) -> str | None:
    if proposed_class is TaxonomyClass.UNCLASSIFIED:
        if not isinstance(value, str) or not value.strip():
            raise ClassificationValidationError(
                ClassificationValidationCode.ABSTENTION_INVALID
            )
        return _bounded_string(value)
    if value is not None:
        raise ClassificationValidationError(
            ClassificationValidationCode.ABSTENTION_INVALID
        )
    return None


def _evidence_ids(value: Any, available: set[str]) -> tuple[str, ...]:
    references = _string_list(value, maximum_items=_MAXIMUM_EVIDENCE)
    if len(set(references)) != len(references) or not set(references).issubset(
        available
    ):
        raise ClassificationValidationError(
            ClassificationValidationCode.EVIDENCE_REFERENCE_INVALID
        )
    return references


def _object_list(value: Any, maximum_items: int) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or len(value) > maximum_items
        or any(not isinstance(item, dict) for item in value)
    ):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    return value


def _string_list(value: Any, *, maximum_items: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    result = tuple(_bounded_string(item) for item in value)
    if len(set(result)) != len(result):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    return result


def _bounded_string(
    value: Any,
    *,
    maximum_characters: int = _MAXIMUM_TEXT_CHARACTERS,
) -> str:
    if not isinstance(value, str):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    if len(value) > maximum_characters:
        raise ClassificationValidationError(
            ClassificationValidationCode.TEXT_LIMIT_EXCEEDED
        )
    return value


def _nonblank_string(
    value: Any,
    *,
    maximum_characters: int = _MAXIMUM_TEXT_CHARACTERS,
) -> str:
    result = _bounded_string(value, maximum_characters=maximum_characters)
    if not result.strip():
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    return result


def _exact_keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
