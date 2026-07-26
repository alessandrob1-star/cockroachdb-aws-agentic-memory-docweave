"""Bedrock-compatible JSON Schema for ``classification.v1``."""

from __future__ import annotations

import json
from typing import Any

from docweave.analysis.contracts import CLASSIFICATION_CONTRACT_VERSION
from docweave.analysis.taxonomy import TAXONOMY_VERSION, TaxonomyClass

_CLASS_CODES = [item.value for item in TaxonomyClass]
_SIGNAL_STRENGTHS = ["weak", "moderate", "strong"]
_EVIDENCE_SUPPORTS = [
    "classification",
    "metadata",
    "language",
    "contradiction",
]

_CLASSIFICATION_V1_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contract_version": {
            "type": "string",
            "const": CLASSIFICATION_CONTRACT_VERSION,
        },
        "taxonomy_version": {"type": "string", "const": TAXONOMY_VERSION},
        "proposed_class": {"type": "string", "enum": _CLASS_CODES},
        "document_language": {"type": "string"},
        "rationale": {"type": "string"},
        "rationale_evidence_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_id": {"type": "string"},
                    "page_index": {"type": "integer"},
                    "quote": {"type": "string"},
                    "supports": {
                        "type": "array",
                        "items": {"type": "string", "enum": _EVIDENCE_SUPPORTS},
                        "minItems": 1,
                    },
                },
                "required": ["evidence_id", "page_index", "quote", "supports"],
                "additionalProperties": False,
            },
        },
        "candidate_metadata": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["name", "value", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "alternative_classes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "class_code": {"type": "string", "enum": _CLASS_CODES},
                    "reason": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["class_code", "reason", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["description", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "missing_expected_evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "raw_signals": {
            "type": "object",
            "properties": {
                "classification_strength": {
                    "type": "string",
                    "enum": _SIGNAL_STRENGTHS,
                },
                "evidence_coverage": {
                    "type": "string",
                    "enum": _SIGNAL_STRENGTHS,
                },
                "ambiguity": {
                    "type": "string",
                    "enum": _SIGNAL_STRENGTHS,
                },
            },
            "required": [
                "classification_strength",
                "evidence_coverage",
                "ambiguity",
            ],
            "additionalProperties": False,
        },
        "abstention_reason": {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        },
    },
    "required": [
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
    ],
    "additionalProperties": False,
}
_CLASSIFICATION_V1_SCHEMA_JSON = json.dumps(
    _CLASSIFICATION_V1_JSON_SCHEMA,
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
)


def classification_v1_json_schema() -> dict[str, Any]:
    """Return an independent copy of the versioned output schema."""
    schema: dict[str, Any] = json.loads(_CLASSIFICATION_V1_SCHEMA_JSON)
    return schema


def classification_v1_output_config() -> dict[str, Any]:
    """Build the Converse ``outputConfig`` value without invoking Bedrock."""
    return {
        "textFormat": {
            "type": "json_schema",
            "structure": {
                "jsonSchema": {
                    "schema": _CLASSIFICATION_V1_SCHEMA_JSON,
                    "name": "docweave_classification_v1",
                    "description": (
                        "Propose one evidence-backed DocWeave document class."
                    ),
                }
            },
        }
    }
