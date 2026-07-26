"""Atomic CockroachDB persistence for non-authoritative classifications."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from docweave.analysis.bedrock_gateway import BedrockClassificationRun
from docweave.analysis.taxonomy import TaxonomyClass
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.operation_repository import PersistenceConflictError
from docweave.persistence.transactions import TransactionRun

_DIGEST_SIZE = 32
_MAX_EVIDENCE_QUOTE_CHARACTERS = 2_000
_MAX_EVIDENCE_ITEMS = 100
_MAX_OUTCOME_JSON_BYTES = 32_768


class SerializableTransactionRunner(Protocol):
    """Minimal transaction runner used by the adapter."""

    def run[T](self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Run one retry-safe transaction."""


class TransactionWork[T](Protocol):
    """Callable transaction closure."""

    def __call__(self, connection: Connection) -> T:
        """Execute against one active transaction."""


@dataclass(frozen=True, slots=True)
class ClassificationScores:
    """Externally versioned deterministic or calibrated confidence values."""

    raw: Decimal
    calibrated: Decimal | None
    extraction: Decimal
    classification: Decimal
    metadata: Decimal
    method_version: str

    def __post_init__(self) -> None:
        for name in ("raw", "extraction", "classification", "metadata"):
            _require_probability(name, getattr(self, name))
        if self.calibrated is not None:
            _require_probability("calibrated", self.calibrated)
        _require_text("method_version", self.method_version)


@dataclass(frozen=True, slots=True)
class ClassificationEvidenceWrite:
    """One minimized, inspectable evidence excerpt."""

    proposal_evidence_id: UUID
    quoted_text: str
    page_number: int

    def __post_init__(self) -> None:
        _require_text("quoted_text", self.quoted_text)
        if len(self.quoted_text) > _MAX_EVIDENCE_QUOTE_CHARACTERS:
            raise ValueError("quoted_text exceeds the persistence limit")
        if self.page_number <= 0:
            raise ValueError("page_number must be positive")


@dataclass(frozen=True, slots=True)
class ClassificationPersistenceIdentity:
    """Caller-owned identities and scoring for a validated model run."""

    workspace_id: UUID
    document_version_id: UUID
    taxonomy_version_id: UUID
    agent_run_id: UUID
    proposal_id: UUID
    idempotency_key: str
    request_sha256: bytes
    prompt_version: str
    completed_at_utc: datetime
    scores: ClassificationScores


@dataclass(frozen=True, slots=True)
class PersistClassificationProposal:
    """Complete atomic write for one validated Bedrock proposal."""

    workspace_id: UUID
    document_version_id: UUID
    taxonomy_version_id: UUID
    proposed_class_id: UUID
    alternative_class_id: UUID | None
    agent_run_id: UUID
    proposal_id: UUID
    idempotency_key: str
    request_sha256: bytes
    model_id: str | None
    inference_profile_id: str | None
    region_name: str
    contract_version: str
    taxonomy_version: str
    prompt_version: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    service_latency_ms: int
    observed_duration_ms: int
    retry_count: int
    observed_cost_usd: Decimal | None
    provider_request_id: str | None
    outcome_json: str
    started_at_utc: datetime
    completed_at_utc: datetime
    scores: ClassificationScores
    abstention_reason: str | None
    contradiction_count: int
    evidence: tuple[ClassificationEvidenceWrite, ...]

    def __post_init__(self) -> None:
        for name in (
            "idempotency_key",
            "region_name",
            "contract_version",
            "taxonomy_version",
            "prompt_version",
            "stop_reason",
        ):
            _require_text(name, getattr(self, name))
        if len(self.request_sha256) != _DIGEST_SIZE:
            raise ValueError("request_sha256 must contain 32 bytes")
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "service_latency_ms",
            "observed_duration_ms",
            "retry_count",
            "contradiction_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must cover input and output tokens")
        if self.observed_cost_usd is not None and self.observed_cost_usd < 0:
            raise ValueError("observed_cost_usd must not be negative")
        started = _as_utc(self.started_at_utc)
        completed = _as_utc(self.completed_at_utc)
        if completed < started:
            raise ValueError("completed_at_utc must not precede started_at_utc")
        object.__setattr__(self, "started_at_utc", started)
        object.__setattr__(self, "completed_at_utc", completed)
        _validate_evidence(self.evidence)
        _validate_outcome_json(self.outcome_json)


def map_bedrock_classification_run(
    run: BedrockClassificationRun,
    *,
    identity: ClassificationPersistenceIdentity,
    taxonomy_class_ids: Mapping[TaxonomyClass, UUID],
) -> PersistClassificationProposal:
    """Map a validated real run without inventing confidence values."""
    proposal = run.proposal
    provenance = run.provenance
    proposed_class_id = taxonomy_class_ids[proposal.proposed_class]
    alternative_class_id = (
        None
        if not proposal.alternative_classes
        else taxonomy_class_ids[proposal.alternative_classes[0].class_code]
    )
    evidence = tuple(
        ClassificationEvidenceWrite(
            proposal_evidence_id=uuid5(identity.proposal_id, item.evidence_id),
            quoted_text=item.quote,
            page_number=item.page_index + 1,
        )
        for item in proposal.evidence
    )
    outcome = {
        "document_language": proposal.document_language,
        "rationale": proposal.rationale,
        "rationale_evidence_ids": proposal.rationale_evidence_ids,
        "candidate_metadata": [
            {
                "name": item.name,
                "value": item.value,
                "evidence_ids": item.evidence_ids,
            }
            for item in proposal.candidate_metadata
        ],
        "alternative_classes": [
            {
                "class_code": item.class_code.value,
                "reason": item.reason,
                "evidence_ids": item.evidence_ids,
            }
            for item in proposal.alternative_classes
        ],
        "contradictions": [
            {
                "description": item.description,
                "evidence_ids": item.evidence_ids,
            }
            for item in proposal.contradictions
        ],
        "missing_expected_evidence": proposal.missing_expected_evidence,
        "raw_signals": {
            "classification_strength": (
                proposal.raw_signals.classification_strength.value
            ),
            "evidence_coverage": proposal.raw_signals.evidence_coverage.value,
            "ambiguity": proposal.raw_signals.ambiguity.value,
        },
    }
    completed = _as_utc(identity.completed_at_utc)
    return PersistClassificationProposal(
        workspace_id=identity.workspace_id,
        document_version_id=identity.document_version_id,
        taxonomy_version_id=identity.taxonomy_version_id,
        proposed_class_id=proposed_class_id,
        alternative_class_id=alternative_class_id,
        agent_run_id=identity.agent_run_id,
        proposal_id=identity.proposal_id,
        idempotency_key=identity.idempotency_key,
        request_sha256=identity.request_sha256,
        model_id=None,
        inference_profile_id=provenance.model_id,
        region_name=provenance.region_name,
        contract_version=provenance.contract_version,
        taxonomy_version=provenance.taxonomy_version,
        prompt_version=identity.prompt_version,
        stop_reason=provenance.stop_reason,
        input_tokens=provenance.usage.input_tokens,
        output_tokens=provenance.usage.output_tokens,
        total_tokens=provenance.usage.total_tokens,
        service_latency_ms=provenance.service_latency_ms,
        observed_duration_ms=provenance.observed_duration_ms,
        retry_count=provenance.retry_attempts,
        observed_cost_usd=provenance.estimated_cost_usd,
        provider_request_id=provenance.request_id,
        outcome_json=json.dumps(
            outcome,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        started_at_utc=completed
        - timedelta(milliseconds=provenance.observed_duration_ms),
        completed_at_utc=completed,
        scores=identity.scores,
        abstention_reason=proposal.abstention_reason,
        contradiction_count=len(proposal.contradictions),
        evidence=evidence,
    )


_INSERT_RUN = sa.text(
    """
    INSERT INTO docweave.agent_runs (
        agent_run_id, workspace_id, document_version_id, idempotency_key,
        request_sha256, agent_responsibility, contract_version,
        taxonomy_version, model_provider, model_id, inference_profile_id,
        region_name, prompt_version, status, stop_reason, input_tokens,
        output_tokens, total_tokens, service_latency_ms, observed_duration_ms,
        retry_count, observed_cost_usd, provider_request_id, outcome,
        started_at, completed_at
    ) VALUES (
        :agent_run_id, :workspace_id, :document_version_id, :idempotency_key,
        :request_sha256, 'classification', :contract_version,
        :taxonomy_version, 'amazon_bedrock', :model_id, :inference_profile_id,
        :region_name, :prompt_version, 'succeeded', :stop_reason, :input_tokens,
        :output_tokens, :total_tokens, :service_latency_ms, :observed_duration_ms,
        :retry_count, :observed_cost_usd, :provider_request_id,
        CAST(:outcome_json AS JSONB), :started_at, :completed_at
    )
    ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
    RETURNING agent_run_id
    """
)
_SELECT_REPLAY = sa.text(
    """
    SELECT r.agent_run_id, r.request_sha256, p.proposal_id
    FROM docweave.agent_runs AS r
    LEFT JOIN docweave.proposals AS p
      ON p.workspace_id = r.workspace_id AND p.agent_run_id = r.agent_run_id
    WHERE r.workspace_id = :workspace_id
      AND r.idempotency_key = :idempotency_key
    """
)
_LOCK_TAXONOMY = sa.text(
    """
    SELECT taxonomy_version_id
    FROM docweave.taxonomy_versions
    WHERE workspace_id = :workspace_id
      AND taxonomy_version_id = :taxonomy_version_id
    FOR UPDATE
    """
)
_INSERT_PROPOSAL = sa.text(
    """
    INSERT INTO docweave.proposals (
        proposal_id, workspace_id, document_version_id, proposal_type,
        proposal_status, agent_run_id, raw_confidence, calibrated_confidence,
        confidence_method_version, created_at
    ) VALUES (
        :proposal_id, :workspace_id, :document_version_id, 'classification',
        'needs_review', :agent_run_id, :raw_confidence,
        :calibrated_confidence, :confidence_method_version, :completed_at
    )
    """
)
_INSERT_CLASSIFICATION = sa.text(
    """
    INSERT INTO docweave.classification_proposals (
        proposal_id, taxonomy_version_id, proposed_class_id,
        alternative_class_id, abstention_reason, extraction_confidence,
        classification_confidence, metadata_confidence, contradiction_count
    ) VALUES (
        :proposal_id, :taxonomy_version_id, :proposed_class_id,
        :alternative_class_id, :abstention_reason, :extraction_confidence,
        :classification_confidence, :metadata_confidence, :contradiction_count
    )
    """
)
_INSERT_EVIDENCE = sa.text(
    """
    INSERT INTO docweave.proposal_evidence (
        proposal_evidence_id, workspace_id, proposal_id, evidence_kind,
        quoted_text, page_number, created_at
    ) VALUES (
        :proposal_evidence_id, :workspace_id, :proposal_id, 'span',
        :quoted_text, :page_number, :completed_at
    )
    """
)


class CockroachClassificationRepository:
    """Persist a run and proposal as one idempotent serializable transaction."""

    def __init__(self, transaction_runner: SerializableTransactionRunner) -> None:
        self._transactions = transaction_runner

    def persist(
        self,
        command: PersistClassificationProposal,
    ) -> PersistenceDisposition:
        """Write no canonical classification and never partially persist."""

        def persist_once(connection: Connection) -> PersistenceDisposition:
            parameters = _parameters(command)
            inserted_id = connection.execute(
                _INSERT_RUN,
                parameters,
            ).scalar_one_or_none()
            if inserted_id is None:
                return _validate_replay(connection, command)
            if inserted_id != command.agent_run_id:
                raise PersistenceConflictError("created agent run identity mismatch")
            taxonomy_id = connection.execute(
                _LOCK_TAXONOMY,
                parameters,
            ).scalar_one_or_none()
            if taxonomy_id != command.taxonomy_version_id:
                raise PersistenceConflictError(
                    "classification taxonomy is outside the workspace"
                )
            connection.execute(_INSERT_PROPOSAL, parameters)
            connection.execute(_INSERT_CLASSIFICATION, parameters)
            connection.execute(
                _INSERT_EVIDENCE,
                [
                    {
                        "proposal_evidence_id": item.proposal_evidence_id,
                        "workspace_id": command.workspace_id,
                        "proposal_id": command.proposal_id,
                        "quoted_text": item.quoted_text,
                        "page_number": item.page_number,
                        "completed_at": command.completed_at_utc,
                    }
                    for item in command.evidence
                ],
            )
            return PersistenceDisposition.APPLIED

        return self._transactions.run(persist_once).value


def _parameters(command: PersistClassificationProposal) -> dict[str, object]:
    return {
        "agent_run_id": command.agent_run_id,
        "workspace_id": command.workspace_id,
        "document_version_id": command.document_version_id,
        "idempotency_key": command.idempotency_key,
        "request_sha256": command.request_sha256,
        "contract_version": command.contract_version,
        "taxonomy_version": command.taxonomy_version,
        "model_id": command.model_id,
        "inference_profile_id": command.inference_profile_id,
        "region_name": command.region_name,
        "prompt_version": command.prompt_version,
        "stop_reason": command.stop_reason,
        "input_tokens": command.input_tokens,
        "output_tokens": command.output_tokens,
        "total_tokens": command.total_tokens,
        "service_latency_ms": command.service_latency_ms,
        "observed_duration_ms": command.observed_duration_ms,
        "retry_count": command.retry_count,
        "observed_cost_usd": command.observed_cost_usd,
        "provider_request_id": command.provider_request_id,
        "outcome_json": command.outcome_json,
        "started_at": command.started_at_utc,
        "completed_at": command.completed_at_utc,
        "proposal_id": command.proposal_id,
        "raw_confidence": command.scores.raw,
        "calibrated_confidence": command.scores.calibrated,
        "confidence_method_version": command.scores.method_version,
        "taxonomy_version_id": command.taxonomy_version_id,
        "proposed_class_id": command.proposed_class_id,
        "alternative_class_id": command.alternative_class_id,
        "abstention_reason": command.abstention_reason,
        "extraction_confidence": command.scores.extraction,
        "classification_confidence": command.scores.classification,
        "metadata_confidence": command.scores.metadata,
        "contradiction_count": command.contradiction_count,
    }


def _validate_replay(
    connection: Connection,
    command: PersistClassificationProposal,
) -> PersistenceDisposition:
    existing = (
        connection.execute(
            _SELECT_REPLAY,
            {
                "workspace_id": command.workspace_id,
                "idempotency_key": command.idempotency_key,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing is None:
        raise PersistenceConflictError("classification replay is unresolved")
    if (
        existing["agent_run_id"] != command.agent_run_id
        or bytes(existing["request_sha256"]) != command.request_sha256
        or existing["proposal_id"] != command.proposal_id
    ):
        raise PersistenceConflictError(
            "classification idempotency key has different content"
        )
    return PersistenceDisposition.IDEMPOTENT_REPLAY


def _require_probability(name: str, value: Decimal) -> None:
    if not Decimal(0) <= value <= Decimal(1):
        raise ValueError(f"{name} must be between zero and one")


def _validate_evidence(evidence: tuple[ClassificationEvidenceWrite, ...]) -> None:
    if not evidence:
        raise ValueError("classification persistence requires evidence")
    if len(evidence) > _MAX_EVIDENCE_ITEMS:
        raise ValueError("classification evidence exceeds the item limit")
    if len({item.proposal_evidence_id for item in evidence}) != len(evidence):
        raise ValueError("proposal evidence identifiers must be unique")


def _validate_outcome_json(outcome_json: str) -> None:
    try:
        decoded = json.loads(outcome_json)
    except json.JSONDecodeError as error:
        raise ValueError("outcome_json must be valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("outcome_json must contain an object")
    if len(outcome_json.encode("utf-8")) > _MAX_OUTCOME_JSON_BYTES:
        raise ValueError("outcome_json exceeds the persistence limit")


def _require_text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
