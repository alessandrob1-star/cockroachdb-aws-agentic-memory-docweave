from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.analysis import TaxonomyClass
from docweave.analysis.bedrock_gateway import (
    BedrockClassificationRun,
    BedrockRunProvenance,
    BedrockUsage,
)
from docweave.analysis.contracts import (
    CandidateMetadata,
    ClassificationProposal,
    EvidenceReference,
    RawClassificationSignals,
    SignalStrength,
)
from docweave.persistence import (
    ClassificationEvidenceWrite,
    ClassificationPersistenceIdentity,
    ClassificationScores,
    CockroachClassificationRepository,
    PersistClassificationProposal,
    PersistenceConflictError,
    PersistenceDisposition,
    TransactionRun,
    map_bedrock_classification_run,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000002")
TAXONOMY_VERSION_ID = UUID("00000000-0000-4000-8000-000000000003")
CLASS_ID = UUID("00000000-0000-4000-8000-000000000004")
RUN_ID = UUID("00000000-0000-4000-8000-000000000005")
PROPOSAL_ID = UUID("00000000-0000-4000-8000-000000000006")
EVIDENCE_ID = UUID("00000000-0000-4000-8000-000000000007")
DIGEST = bytes.fromhex("ab" * 32)


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        mapping: Mapping[str, object] | None = None,
    ) -> None:
        self._scalar = scalar
        self._mapping = mapping

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> Mapping[str, object] | None:
        return self._mapping


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self.responses = list(responses)
        self.calls: list[
            tuple[str, Mapping[str, object] | Sequence[Mapping[str, object]] | None]
        ] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters))
        if not self.responses:
            raise AssertionError("unexpected database call")
        return self.responses.pop(0)


class FakeTransactionRunner:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.run_count = 0

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]:
        self.run_count += 1
        return TransactionRun(
            value=work(cast(Connection, self.connection)),
            attempts=1,
        )


def command() -> PersistClassificationProposal:
    return PersistClassificationProposal(
        workspace_id=WORKSPACE_ID,
        document_version_id=VERSION_ID,
        taxonomy_version_id=TAXONOMY_VERSION_ID,
        proposed_class_id=CLASS_ID,
        alternative_class_id=None,
        agent_run_id=RUN_ID,
        proposal_id=PROPOSAL_ID,
        idempotency_key="classify-version-001",
        request_sha256=DIGEST,
        model_id="eu.amazon.nova-2-lite-v1:0",
        inference_profile_id="eu.amazon.nova-2-lite-v1:0",
        region_name="eu-central-1",
        contract_version="classification.v1",
        taxonomy_version="docweave_mvp_v0_1",
        prompt_version="classification-prompt.v1",
        stop_reason="tool_use",
        input_tokens=500,
        output_tokens=200,
        total_tokens=700,
        service_latency_ms=321,
        observed_duration_ms=350,
        retry_count=0,
        observed_cost_usd=Decimal("0.0072"),
        provider_request_id="request-123",
        outcome_json='{"rationale":"Evidence-backed proposal"}',
        started_at_utc=NOW,
        completed_at_utc=NOW,
        scores=ClassificationScores(
            raw=Decimal("0.80000"),
            calibrated=None,
            extraction=Decimal("0.90000"),
            classification=Decimal("0.80000"),
            metadata=Decimal("0.70000"),
            method_version="confidence.v1",
        ),
        abstention_reason=None,
        contradiction_count=0,
        evidence=(
            ClassificationEvidenceWrite(
                proposal_evidence_id=EVIDENCE_ID,
                quoted_text="INVOICE INV-17",
                page_number=1,
            ),
        ),
    )


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachClassificationRepository, FakeTransactionRunner]:
    runner = FakeTransactionRunner(FakeConnection(responses))
    return CockroachClassificationRepository(runner), runner


def test_persists_run_proposal_subtype_and_evidence_atomically() -> None:
    adapter, runner = repository(
        [
            FakeResult(scalar=RUN_ID),
            FakeResult(scalar=TAXONOMY_VERSION_ID),
            FakeResult(),
            FakeResult(),
            FakeResult(),
        ]
    )

    result = adapter.persist(command())

    assert result is PersistenceDisposition.APPLIED
    assert runner.run_count == 1
    assert runner.connection.responses == []
    statements = "\n".join(statement for statement, _ in runner.connection.calls)
    assert "INSERT INTO docweave.agent_runs" in statements
    assert "INSERT INTO docweave.proposals" in statements
    assert "INSERT INTO docweave.classification_proposals" in statements
    assert "INSERT INTO docweave.proposal_evidence" in statements
    assert "document_classifications" not in statements
    first_parameters = cast(Mapping[str, object], runner.connection.calls[0][1])
    assert first_parameters["outcome_json"] == (
        '{"rationale":"Evidence-backed proposal"}'
    )
    assert "Evidence-backed proposal" not in runner.connection.calls[0][0]


def test_exact_idempotent_replay_writes_no_child_rows() -> None:
    adapter, runner = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "agent_run_id": RUN_ID,
                    "request_sha256": DIGEST,
                    "proposal_id": PROPOSAL_ID,
                }
            ),
        ]
    )

    result = adapter.persist(command())

    assert result is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(runner.connection.calls) == 2


def test_reused_idempotency_key_with_different_request_is_rejected() -> None:
    adapter, _ = repository(
        [
            FakeResult(scalar=None),
            FakeResult(
                mapping={
                    "agent_run_id": RUN_ID,
                    "request_sha256": bytes.fromhex("cd" * 32),
                    "proposal_id": PROPOSAL_ID,
                }
            ),
        ]
    )

    with pytest.raises(PersistenceConflictError, match="different content"):
        adapter.persist(command())


def test_contract_rejects_unbounded_evidence_and_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="persistence limit"):
        ClassificationEvidenceWrite(
            proposal_evidence_id=EVIDENCE_ID,
            quoted_text="x" * 2_001,
            page_number=1,
        )

    with pytest.raises(ValueError, match="between zero and one"):
        replace(command().scores, raw=Decimal("1.1"))


def test_maps_validated_bedrock_run_without_inventing_confidence() -> None:
    scores = command().scores
    run = BedrockClassificationRun(
        proposal=ClassificationProposal(
            contract_version="classification.v1",
            taxonomy_version="docweave_mvp_v0_1",
            proposed_class=TaxonomyClass.INVOICE,
            document_language="en",
            rationale="Invoice number and total are explicit.",
            rationale_evidence_ids=("ev_1",),
            evidence=(
                EvidenceReference(
                    evidence_id="ev_1",
                    page_index=0,
                    quote="INVOICE INV-17 Total EUR 42.00",
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
            missing_expected_evidence=("supplier",),
            raw_signals=RawClassificationSignals(
                classification_strength=SignalStrength.STRONG,
                evidence_coverage=SignalStrength.MODERATE,
                ambiguity=SignalStrength.WEAK,
            ),
            abstention_reason=None,
        ),
        provenance=BedrockRunProvenance(
            region_name="eu-central-1",
            model_id="eu.amazon.nova-2-lite-v1:0",
            contract_version="classification.v1",
            taxonomy_version="docweave_mvp_v0_1",
            stop_reason="tool_use",
            usage=BedrockUsage(
                input_tokens=500,
                output_tokens=200,
                total_tokens=700,
            ),
            service_latency_ms=321,
            observed_duration_ms=350,
            request_id="request-123",
            retry_attempts=0,
            estimated_cost_usd=Decimal("0.0072"),
        ),
    )

    mapped = map_bedrock_classification_run(
        run,
        identity=ClassificationPersistenceIdentity(
            workspace_id=WORKSPACE_ID,
            document_version_id=VERSION_ID,
            taxonomy_version_id=TAXONOMY_VERSION_ID,
            agent_run_id=RUN_ID,
            proposal_id=PROPOSAL_ID,
            idempotency_key="classify-version-001",
            request_sha256=DIGEST,
            prompt_version="classification-prompt.v1",
            completed_at_utc=NOW,
            scores=scores,
        ),
        taxonomy_class_ids={TaxonomyClass.INVOICE: CLASS_ID},
    )

    assert mapped.proposed_class_id == CLASS_ID
    assert mapped.scores is scores
    assert mapped.evidence[0].quoted_text == "INVOICE INV-17 Total EUR 42.00"
    assert mapped.evidence[0].page_number == 1
    assert mapped.started_at_utc < mapped.completed_at_utc
    assert '"rationale":"Invoice number and total are explicit."' in (
        mapped.outcome_json
    )
