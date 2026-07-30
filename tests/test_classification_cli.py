import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from docweave import classification_cli
from docweave.analysis import (
    BedrockClassificationRun,
    BedrockRunProvenance,
    BedrockUsage,
    CandidateMetadata,
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
    discover_batch_pdfs,
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
                candidate_metadata=(
                    CandidateMetadata(
                        name="supplier",
                        value="ACME SRL",
                        evidence_ids=("ev_2",),
                    ),
                ),
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
    assert result.metadata_count == 1
    assert result.metadata_details[0].name == "supplier"
    assert result.metadata_details[0].value == "ACME SRL"
    assert result.metadata_details[0].evidence_ids == ("ev_2",)
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


def test_discover_batch_pdfs_is_bounded_recursive_and_authorized(
    tmp_path: Path,
) -> None:
    authorized = tmp_path / "authorized"
    nested = authorized / "nested"
    outside = tmp_path / "outside"
    nested.mkdir(parents=True)
    outside.mkdir()
    first = authorized / "b.PDF"
    second = nested / "a.pdf"
    ignored = nested / "note.txt"
    external = outside / "x.pdf"
    for path in (first, second, ignored, external):
        path.write_text("sample", encoding="utf-8")

    discovered = discover_batch_pdfs(
        authorized,
        authorized_root=authorized,
        limit=2,
    )

    assert discovered == (first.resolve(), second.resolve())
    with pytest.raises(ValueError, match="source_root must be inside authorized_root"):
        discover_batch_pdfs(outside, authorized_root=authorized)
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        discover_batch_pdfs(authorized, authorized_root=authorized, limit=1_001)


def test_batch_main_continues_after_item_failure_without_secret_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    first = authorized / "first.pdf"
    second = authorized / "second.pdf"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    calls: list[tuple[Path, str]] = []

    def fake_build_configured_classification_runtime() -> object:
        return SimpleNamespace(
            config=RuntimeEnvironmentConfig(
                database_url="cockroachdb://user:secret@example.test/docweave",
                workspace_id=UUID("11111111-1111-4111-8111-111111111111"),
                taxonomy_version_id=UUID("22222222-2222-4222-8222-222222222222"),
                approved_by_actor_id=UUID("33333333-3333-4333-8333-333333333333"),
            ),
            runtime=object(),
        )

    def fake_compute_sha256_fingerprint(source_path: Path) -> object:
        return SimpleNamespace(hex_digest=f"{source_path.stem:0<64}"[:64])

    def fake_classify_pdf_once_with_runtime(
        configured: object,
        source_path: Path,
        *,
        authorized_root: Path,
        idempotency_key: str | None = None,
        source_sha256: str | None = None,
    ) -> ClassificationCommandResult:
        assert authorized_root == authorized.resolve()
        assert idempotency_key is not None
        assert source_sha256 is not None
        calls.append((source_path, idempotency_key))
        if source_path == second.resolve():
            raise RuntimeError("secret model details")
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        classification_cli,
        "build_configured_classification_runtime",
        fake_build_configured_classification_runtime,
    )
    monkeypatch.setattr(
        classification_cli,
        "compute_sha256_fingerprint",
        fake_compute_sha256_fingerprint,
    )
    monkeypatch.setattr(
        classification_cli,
        "_classify_pdf_once_with_runtime",
        fake_classify_pdf_once_with_runtime,
    )

    result = classification_cli.batch_main(
        [
            str(authorized),
            "--authorized-root",
            str(authorized),
            "--limit",
            "2",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert calls[0][0] == first.resolve()
    assert calls[1][0] == second.resolve()
    assert "Discovered PDFs: 2" in captured.out
    assert "Succeeded PDFs: 1" in captured.out
    assert "Failed PDFs: 1" in captured.out
    assert "[OK] first.pdf: class=invoice tokens=15" in captured.out
    assert "[FAIL] second.pdf: RuntimeError" in captured.out
    assert "secret" not in captured.out
    assert "secret" not in captured.err


def test_batch_main_writes_sanitized_json_report_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    source = authorized / "invoice.pdf"
    source.write_text("first", encoding="utf-8")
    report_path = tmp_path / "batch-report.json"

    def fake_build_configured_classification_runtime() -> object:
        return SimpleNamespace(
            config=RuntimeEnvironmentConfig(
                database_url="cockroachdb://user:secret@example.test/docweave",
                workspace_id=UUID("11111111-1111-4111-8111-111111111111"),
                taxonomy_version_id=UUID("22222222-2222-4222-8222-222222222222"),
                approved_by_actor_id=UUID("33333333-3333-4333-8333-333333333333"),
            ),
            runtime=object(),
        )

    def fake_compute_sha256_fingerprint(_: Path) -> object:
        return SimpleNamespace(hex_digest="ab" * 32)

    def fake_classify_pdf_once_with_runtime(
        configured: object,
        source_path: Path,
        *,
        authorized_root: Path,
        idempotency_key: str | None = None,
        source_sha256: str | None = None,
    ) -> ClassificationCommandResult:
        assert configured is not None
        assert source_path == source.resolve()
        assert authorized_root == authorized.resolve()
        assert idempotency_key is not None
        assert source_sha256 == "ab" * 32
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd="0.00001",
            evidence_count=2,
            metadata_count=1,
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="0.70000",
        )

    monkeypatch.setattr(
        classification_cli,
        "build_configured_classification_runtime",
        fake_build_configured_classification_runtime,
    )
    monkeypatch.setattr(
        classification_cli,
        "compute_sha256_fingerprint",
        fake_compute_sha256_fingerprint,
    )
    monkeypatch.setattr(
        classification_cli,
        "_classify_pdf_once_with_runtime",
        fake_classify_pdf_once_with_runtime,
    )

    result = classification_cli.batch_main(
        [
            str(authorized),
            "--authorized-root",
            str(authorized),
            "--json-report",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert f"JSON report: {report_path}" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "docweave.classification_batch_report.v1"
    assert report["succeeded_count"] == 1
    assert report["items"][0]["relative_path"] == "invoice.pdf"
    assert report["items"][0]["proposed_class"] == "invoice"
    assert report["items"][0]["total_tokens"] == 15
    assert "secret" not in report_path.read_text(encoding="utf-8")

    overwrite_result = classification_cli.batch_main(
        [
            str(authorized),
            "--authorized-root",
            str(authorized),
            "--json-report",
            str(report_path),
        ]
    )

    overwrite_captured = capsys.readouterr()
    assert overwrite_result == 2
    assert "target already exists" in overwrite_captured.err
