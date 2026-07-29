from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from docweave import classification_cli
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
from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeConfigurationErrorCode,
    RuntimeEnvironmentConfig,
)
from docweave.classification_cli import (
    ClassificationCommandResult,
    build_content_addressed_identity,
)
from docweave.extraction import ExtractionStatus, PdfExtractionResult
from docweave.persistence import PersistedClassificationRun
from docweave.persistence.contracts import PersistenceDisposition


def test_content_addressed_identity_is_stable_and_workspace_scoped() -> None:
    source_sha256 = "ab" * 32
    config = RuntimeEnvironmentConfig(
        database_url="cockroachdb://user:secret@example.test/docweave",
        workspace_id=UUID("11111111-1111-4111-8111-111111111111"),
        taxonomy_version_id=UUID("22222222-2222-4222-8222-222222222222"),
        approved_by_actor_id=UUID("33333333-3333-4333-8333-333333333333"),
    )

    first = build_content_addressed_identity(
        config,
        source_sha256=source_sha256,
        idempotency_key=None,
    )
    second = build_content_addressed_identity(
        config,
        source_sha256=source_sha256,
        idempotency_key=None,
    )
    changed = build_content_addressed_identity(
        config,
        source_sha256="cd" * 32,
        idempotency_key=None,
    )

    assert first == second
    assert first.document_id != changed.document_id
    assert first.version_number == 1
    assert (
        first.idempotency_key
        == f"classification.v1:{config.workspace_id}:{source_sha256}"
    )


def test_main_prints_sanitized_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_classify_pdf_once(
        source_path: Path,
        *,
        authorized_root: Path,
        idempotency_key: str | None = None,
    ) -> ClassificationCommandResult:
        assert source_path == Path("sample.pdf")
        assert authorized_root == Path("pdf_sintetici")
        assert idempotency_key == "retry-key"
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="idempotent_replay",
            proposal_disposition="applied",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            estimated_cost_usd="0.00001",
        )

    monkeypatch.setattr(
        classification_cli,
        "classify_pdf_once",
        fake_classify_pdf_once,
    )

    result = classification_cli.main(
        [
            "sample.pdf",
            "--authorized-root",
            "pdf_sintetici",
            "--idempotency-key",
            "retry-key",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Proposed class: invoice" in captured.out
    assert "Bedrock tokens: input=100 output=50 total=150" in captured.out
    assert "secret" not in captured.out
    assert captured.err == ""


def test_command_result_includes_validated_evidence_details() -> None:
    persisted = PersistedClassificationRun(
        extraction=PdfExtractionResult(
            status=ExtractionStatus.COMPLETED,
            pages=(),
            source_sha256="ab" * 32,
            source_bytes=100,
            document_page_count=1,
            extractor="test",
        ),
        model_run=BedrockClassificationRun(
            proposal=ClassificationProposal(
                contract_version="classification.v1",
                taxonomy_version="docweave_mvp_v0_1",
                proposed_class=TaxonomyClass.INVOICE,
                document_language="en",
                rationale="Invoice heading and total are explicit.",
                rationale_evidence_ids=("ev_1",),
                evidence=(
                    EvidenceReference(
                        evidence_id="ev_1",
                        page_index=0,
                        quote="Invoice heading and total are explicit.",
                        supports=("classification",),
                    ),
                    EvidenceReference(
                        evidence_id="ev_2",
                        page_index=1,
                        quote="Supplier name is visible.",
                        supports=("metadata",),
                    ),
                ),
                candidate_metadata=(),
                alternative_classes=(),
                contradictions=(),
                missing_expected_evidence=(),
                raw_signals=RawClassificationSignals(
                    classification_strength=SignalStrength.STRONG,
                    evidence_coverage=SignalStrength.STRONG,
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
                usage=BedrockUsage(10, 5, 15),
                service_latency_ms=100,
                observed_duration_ms=110,
                request_id="request-123",
                retry_attempts=1,
                estimated_cost_usd=Decimal("0.00001"),
            ),
        ),
        document_disposition=PersistenceDisposition.APPLIED,
        taxonomy_disposition=PersistenceDisposition.IDEMPOTENT_REPLAY,
        proposal_disposition=PersistenceDisposition.APPLIED,
    )

    result = classification_cli._command_result(persisted)

    assert result.evidence_count == 2
    assert result.evidence_details[0].evidence_id == "ev_1"
    assert result.evidence_details[0].page_number == 1
    assert result.evidence_details[0].quote == (
        "Invoice heading and total are explicit."
    )
    assert result.evidence_details[1].page_number == 2
    assert result.retry_attempts == 1


def test_main_reports_configuration_errors_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_classify_pdf_once(
        source_path: Path,
        *,
        authorized_root: Path,
        idempotency_key: str | None = None,
    ) -> ClassificationCommandResult:
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
            variable_name="DOCWEAVE_DATABASE_URL",
        )

    monkeypatch.setattr(
        classification_cli,
        "classify_pdf_once",
        fail_classify_pdf_once,
    )

    result = classification_cli.main(
        ["sample.pdf", "--authorized-root", "pdf_sintetici"]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "database_url_missing" in captured.err
    assert "DOCWEAVE_DATABASE_URL" in captured.err
    assert "secret" not in captured.err
