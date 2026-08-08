from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine

from docweave.analysis import (
    BedrockClassificationRun,
    BedrockRunProvenance,
    BedrockUsage,
    ClassificationProposal,
    EvidenceReference,
    RawClassificationSignals,
    SignalStrength,
    TaxonomyClass,
)
from docweave.extraction import (
    ExtractedPage,
    ExtractionStatus,
    PdfExtractionRequest,
    PdfExtractionResult,
)
from docweave.persistence import (
    ClassificationPipelineError,
    ClassificationPipelineErrorCode,
    ClassificationRunIdentity,
    ClassificationRuntime,
    ClassificationScores,
    CockroachClassificationRepository,
    CockroachMemoryFoundationRepository,
    CockroachSimpleMemoryRepository,
    EnsureApprovedTaxonomy,
    PersistClassificationProposal,
    PersistenceDisposition,
    PersistSimpleAnalysis,
    RegisterDocumentVersion,
    build_classification_runtime,
    provide_uncalibrated_confidence_v0,
)

NOW = datetime(2026, 7, 26, 18, 30, tzinfo=UTC)
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000002")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000003")
TAXONOMY_ID = UUID("00000000-0000-4000-8000-000000000004")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000005")
RUN_ID = UUID("00000000-0000-4000-8000-000000000006")
PROPOSAL_ID = UUID("00000000-0000-4000-8000-000000000007")
DIGEST_HEX = "ab" * 32
PAGES = (
    ExtractedPage(
        page_index=0,
        page_label="1",
        text="INVOICE INV-17 Total EUR 42.00",
    ),
)


class FakeFoundationRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.document_command: RegisterDocumentVersion | None = None
        self.taxonomy_command: EnsureApprovedTaxonomy | None = None

    def register_document_version(
        self,
        command: RegisterDocumentVersion,
    ) -> PersistenceDisposition:
        self.events.append("register")
        self.document_command = command
        return PersistenceDisposition.APPLIED

    def ensure_approved_taxonomy(
        self,
        command: EnsureApprovedTaxonomy,
    ) -> PersistenceDisposition:
        self.events.append("taxonomy")
        self.taxonomy_command = command
        return PersistenceDisposition.APPLIED


class FakeClassificationRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.command: PersistClassificationProposal | None = None

    def persist(
        self,
        command: PersistClassificationProposal,
    ) -> PersistenceDisposition:
        self.events.append("persist")
        self.command = command
        return PersistenceDisposition.APPLIED


class FakeSimpleMemoryRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.command: PersistSimpleAnalysis | None = None

    def persist_analysis(
        self,
        command: PersistSimpleAnalysis,
    ) -> PersistenceDisposition:
        self.events.append("simple_memory")
        self.command = command
        return PersistenceDisposition.APPLIED


class FakeGateway:
    def __init__(self, events: list[str], run: BedrockClassificationRun) -> None:
        self.events = events
        self.run = run
        self.pages: tuple[ExtractedPage, ...] | None = None

    def classify(
        self,
        pages: tuple[ExtractedPage, ...],
    ) -> BedrockClassificationRun:
        self.events.append("model")
        self.pages = pages
        return self.run


class NoConnectEngine:
    def __init__(self) -> None:
        self.connect_count = 0

    def connect(self) -> None:
        self.connect_count += 1
        raise AssertionError("runtime construction must not connect")


def extraction_result(
    *,
    status: ExtractionStatus = ExtractionStatus.COMPLETED,
    source_sha256: str | None = DIGEST_HEX,
) -> PdfExtractionResult:
    return PdfExtractionResult(
        status=status,
        pages=PAGES if status is ExtractionStatus.COMPLETED else (),
        source_sha256=source_sha256,
        source_bytes=42,
        document_page_count=1,
        extractor="qt_pdf",
    )


def model_run() -> BedrockClassificationRun:
    return BedrockClassificationRun(
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
            candidate_metadata=(),
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


def scores() -> ClassificationScores:
    return ClassificationScores(
        raw=Decimal("0.80000"),
        calibrated=None,
        extraction=Decimal("0.90000"),
        classification=Decimal("0.80000"),
        metadata=Decimal("0.70000"),
        method_version="confidence.v1-test-provider",
    )


def identity() -> ClassificationRunIdentity:
    return ClassificationRunIdentity(
        workspace_id=WORKSPACE_ID,
        document_id=DOCUMENT_ID,
        document_version_id=VERSION_ID,
        taxonomy_version_id=TAXONOMY_ID,
        approved_by_actor_id=ACTOR_ID,
        agent_run_id=RUN_ID,
        proposal_id=PROPOSAL_ID,
        version_number=1,
        idempotency_key="classify-version-001",
        prompt_version="classification-prompt.v1",
    )


def request() -> PdfExtractionRequest:
    return PdfExtractionRequest(
        source_path=Path("D:/authorized/invoice.pdf"),
        authorized_root=Path("D:/authorized"),
    )


def test_runs_boundaries_in_order_and_persists_explicit_scores(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    foundation = FakeFoundationRepository(events)
    classification = FakeClassificationRepository(events)
    simple_memory = FakeSimpleMemoryRepository(events)
    gateway = FakeGateway(events, model_run())
    supplied_scores = scores()
    source = tmp_path / "incoming" / "invoice.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")

    def extract(_: PdfExtractionRequest) -> PdfExtractionResult:
        events.append("extract")
        return extraction_result()

    def score(
        _: BedrockClassificationRun,
        __: PdfExtractionResult,
    ) -> ClassificationScores:
        events.append("score")
        return supplied_scores

    runtime = ClassificationRuntime(
        gateway=gateway,
        foundation_repository=cast(
            CockroachMemoryFoundationRepository,
            foundation,
        ),
        classification_repository=cast(
            CockroachClassificationRepository,
            classification,
        ),
        simple_memory_repository=cast(
            CockroachSimpleMemoryRepository,
            simple_memory,
        ),
        score_provider=score,
        extractor=extract,
        clock=lambda: NOW,
    )

    result = runtime.classify_and_persist(
        PdfExtractionRequest(source_path=source, authorized_root=tmp_path),
        identity=identity(),
    )

    assert events == [
        "extract",
        "register",
        "taxonomy",
        "model",
        "score",
        "persist",
        "simple_memory",
    ]
    assert result.proposal_disposition is PersistenceDisposition.APPLIED
    assert result.simple_memory_disposition is PersistenceDisposition.APPLIED
    assert gateway.pages == PAGES
    assert foundation.document_command is not None
    assert foundation.document_command.sha256 == bytes.fromhex(DIGEST_HEX)
    assert foundation.taxonomy_command is not None
    assert classification.command is not None
    assert classification.command.scores is supplied_scores
    assert (
        classification.command.proposed_class_id
        == (foundation.taxonomy_command.class_ids[TaxonomyClass.INVOICE])
    )
    assert simple_memory.command is not None
    assert simple_memory.command.original_directory == "incoming"
    assert simple_memory.command.original_filename == "invoice.pdf"
    assert simple_memory.command.proposed_category == "invoice"
    assert simple_memory.command.proposed_directory == "DocWeave Organized/Invoices"


def test_composes_runtime_without_database_or_model_io() -> None:
    events: list[str] = []
    engine = NoConnectEngine()
    gateway = FakeGateway(events, model_run())

    runtime = build_classification_runtime(
        cast(Engine, engine),
        gateway=gateway,
    )

    assert isinstance(
        runtime.foundation_repository, CockroachMemoryFoundationRepository
    )
    assert isinstance(
        runtime.classification_repository,
        CockroachClassificationRepository,
    )
    assert engine.connect_count == 0
    assert events == []
    assert runtime.score_provider is provide_uncalibrated_confidence_v0


@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        (
            extraction_result(status=ExtractionStatus.NO_EXTRACTABLE_TEXT),
            ClassificationPipelineErrorCode.EXTRACTION_NOT_CLASSIFIABLE,
        ),
        (
            extraction_result(source_sha256=None),
            ClassificationPipelineErrorCode.EXTRACTION_PROVENANCE_MISSING,
        ),
    ],
)
def test_fails_before_model_or_database_when_extraction_is_not_usable(
    result: PdfExtractionResult,
    expected_code: ClassificationPipelineErrorCode,
) -> None:
    events: list[str] = []
    runtime = ClassificationRuntime(
        gateway=FakeGateway(events, model_run()),
        foundation_repository=cast(
            CockroachMemoryFoundationRepository,
            FakeFoundationRepository(events),
        ),
        classification_repository=cast(
            CockroachClassificationRepository,
            FakeClassificationRepository(events),
        ),
        score_provider=lambda _run, _extraction: scores(),
        extractor=lambda _request: result,
        clock=lambda: NOW,
    )

    with pytest.raises(ClassificationPipelineError) as captured:
        runtime.classify_and_persist(request(), identity=identity())

    assert captured.value.code is expected_code
    assert events == []
