from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from docweave.application_runtime import RuntimeIntegrationSnapshot
from docweave.classification_cli import (
    ClassificationCommandResult,
    ClassificationEvidenceDetail,
    ClassificationMetadataDetail,
)
from docweave.desktop.cockpit import CockpitWindow, Document
from docweave.desktop.scan import DesktopScanResult
from docweave.discovery import DiscoveredFile, DiscoveryResult, DiscoveryStatus
from docweave.intake import IntakeRecord, IntakeResult, IntakeStatus
from docweave.persistence.contracts import PersistenceDisposition
from docweave.review_cli import (
    ReviewDecisionCommandInput,
    ReviewDecisionCommandResult,
)
from docweave.runtime_preflight import (
    PreflightCheck,
    PreflightState,
    RuntimePreflightReport,
)


def wait_for_cockpit_scan(window: CockpitWindow) -> None:
    loop = QEventLoop()
    timed_out = False

    def mark_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    window.scan_finished.connect(loop.quit)
    QTimer.singleShot(3_000, mark_timeout)
    window.start_scan()
    loop.exec()
    assert not timed_out


def wait_for_cockpit_classification(window: CockpitWindow) -> None:
    loop = QEventLoop()
    timed_out = False

    def mark_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    window.classification_finished.connect(loop.quit)
    QTimer.singleShot(3_000, mark_timeout)
    loop.exec()
    assert not timed_out


def close_cockpit_window(window: CockpitWindow) -> None:
    window.close()
    window.deleteLater()
    QCoreApplication.processEvents()


def ready_runtime_preflight_report() -> RuntimePreflightReport:
    return RuntimePreflightReport(
        checks=(
            PreflightCheck("runtime_config", PreflightState.OK, "loaded"),
            PreflightCheck(
                "bedrock_client",
                PreflightState.OK,
                "eu-central-1:configured",
            ),
            PreflightCheck(
                "cockroachdb_connection",
                PreflightState.SKIP,
                "not_requested",
            ),
        )
    )


def assert_visible_classification_proposal(window: CockpitWindow) -> None:
    assert not window.center.analysis_panel.isHidden()
    assert window.center.analysis_title.text() == "AI PROPOSAL"
    assert "invoice · confidence 0.80000" in window.center.analysis_summary.text()
    assert "2 evidence · 1 metadata" in window.center.analysis_summary.text()
    assert "1 validation retry" in window.center.analysis_summary.text()
    assert "The document contains invoice wording" in (
        window.center.analysis_rationale.text()
    )
    assert "ev_1 p1: Invoice heading and total are explicit" in (
        window.center.analysis_evidence.text()
    )
    assert "ev_2 p1: Supplier name is visible" in (
        window.center.analysis_evidence.text()
    )

    log_text = window.console.log_text.text()
    assert "Classification batch complete: 30 of 30" in log_text

    proposed_class_item = window.left.table.item(0, 1)
    review_status_item = window.left.table.item(0, 3)
    assert proposed_class_item is not None
    assert review_status_item is not None
    assert proposed_class_item.text() == "invoice"
    assert review_status_item.text() == "REVIEW"
    assert "Proposed copy target: DocWeave Organized/Invoices/" in (
        proposed_class_item.toolTip()
    )
    assert "invoice_acme-srl_inv-2026-004.pdf" in proposed_class_item.toolTip()

    ready_metric = cast(Any, window.right.metric_frames[1]).number
    review_metric = cast(Any, window.right.metric_frames[2]).number
    assert ready_metric.text() == "0"
    assert review_metric.text() == "30"
    assert cast(Any, window.right.event_rows[0]).event_text.text() == (
        "30/30 persisted"
    )
    assert cast(Any, window.right.event_rows[1]).event_text.text() == "0 item(s)"
    assert cast(Any, window.right.event_rows[2]).event_text.text() == (
        "30 awaiting human review"
    )
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "0 ready remaining"
    )
    assert cast(Any, window.right.event_rows[4]).event_text.text() == (
        "Proposals persisted"
    )


def test_cockpit_starts_with_definitive_local_surface(
    qt_application: object,
) -> None:
    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=True,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        )
    )

    assert window.windowTitle() == "DocWeave Cockpit"
    assert window.left.table.rowCount() == 0
    assert "CockroachDB      Configured" in window.console.status_text.text()
    assert "Bedrock          Client configured" in window.console.status_text.text()

    close_cockpit_window(window)


def test_cockpit_surfaces_runtime_preflight_fail_closed(
    qt_application: object,
) -> None:
    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=False,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        ),
        runtime_preflight_function=lambda: RuntimePreflightReport(
            checks=(
                PreflightCheck(
                    "runtime_config",
                    PreflightState.FAIL,
                    "database_url_missing:DOCWEAVE_DATABASE_URL",
                ),
            )
        ),
    )

    status = window.console.status_text.text()
    assert "Runtime config   Blocked (database url missing)" in status
    assert "CockroachDB      Not configured" in status
    assert "Bedrock          Blocked by config" in status
    assert "DOCWEAVE_DATABASE_URL" not in status

    close_cockpit_window(window)


def test_cockpit_blocks_analyze_when_runtime_preflight_failed(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    calls = 0

    def unexpected_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        nonlocal calls
        calls += 1
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
            document_language="en",
            rationale="The document contains invoice wording and a total.",
            evidence_count=2,
            metadata_count=1,
            metadata_details=(
                ClassificationMetadataDetail(
                    name="supplier",
                    value="ACME SRL",
                    evidence_ids=("ev_1",),
                ),
                ClassificationMetadataDetail(
                    name="invoice_number",
                    value="INV-2026-004",
                    evidence_ids=("ev_1",),
                ),
            ),
            evidence_details=(
                ClassificationEvidenceDetail(
                    evidence_id="ev_1",
                    page_number=1,
                    quote="Invoice heading and total are explicit.",
                ),
            ),
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="1.00000",
        )

    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=False,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        ),
        classification_function=unexpected_classification,
        runtime_preflight_function=lambda: RuntimePreflightReport(
            checks=(
                PreflightCheck(
                    "runtime_config",
                    PreflightState.FAIL,
                    "database_url_missing:DOCWEAVE_DATABASE_URL",
                ),
            )
        ),
    )
    window.set_authorized_root(corpus)
    window.left.set_documents(
        [
            Document(
                name=first_pdf.name,
                category="PDF",
                pages="-",
                status="READY",
                path=first_pdf,
            )
        ]
    )
    window._selected_document_row = 0
    window._set_busy(False)

    assert window.console.buttons[3].isEnabled()
    assert "preflight" in window.console.buttons[3].toolTip().lower()

    window._analyze_selected_document()

    assert calls == 0
    assert not window.classification_in_progress
    assert "Runtime is not ready for classification" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[0]).event_text.text() == "Not started"
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "No model invocation"
    )

    close_cockpit_window(window)


def test_cockpit_retries_runtime_preflight_before_analyze(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    calls = 0
    preflight_calls = 0

    def fake_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        nonlocal calls
        calls += 1
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
            document_language="en",
            rationale="The document contains invoice wording and a total.",
            evidence_count=2,
            metadata_count=1,
            metadata_details=(
                ClassificationMetadataDetail(
                    name="supplier",
                    value="ACME SRL",
                    evidence_ids=("ev_1",),
                ),
            ),
            evidence_details=(
                ClassificationEvidenceDetail(
                    evidence_id="ev_1",
                    page_number=1,
                    quote="Invoice heading and total are explicit.",
                ),
            ),
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="1.00000",
        )

    def changing_preflight() -> RuntimePreflightReport:
        nonlocal preflight_calls
        preflight_calls += 1
        if preflight_calls == 1:
            return RuntimePreflightReport(
                checks=(
                    PreflightCheck(
                        "runtime_config",
                        PreflightState.FAIL,
                        "database_url_missing:DOCWEAVE_DATABASE_URL",
                    ),
                )
            )
        return ready_runtime_preflight_report()

    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=True,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        ),
        classification_function=fake_classification,
        runtime_preflight_function=changing_preflight,
    )
    window.set_authorized_root(corpus)
    window.left.set_documents(
        [
            Document(
                name=first_pdf.name,
                category="PDF",
                pages="-",
                status="READY",
                path=first_pdf,
            )
        ]
    )
    window._selected_document_row = 0
    window._set_busy(False)

    assert window.console.buttons[3].isEnabled()

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    assert preflight_calls == 2
    assert calls == 1
    assert "Classification batch complete: 1 of 1" in window.console.log_text.text()

    close_cockpit_window(window)


def test_cockpit_scans_synthetic_pdfs_and_raises_central_preview(
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    classified_paths: list[tuple[Path, Path]] = []

    def fake_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        classified_paths.append((source_path, authorized_root))
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
            document_language="en",
            rationale="The document contains invoice wording and a total.",
            evidence_count=2,
            metadata_count=1,
            metadata_details=(
                ClassificationMetadataDetail(
                    name="supplier",
                    value="ACME SRL",
                    evidence_ids=("ev_1",),
                ),
                ClassificationMetadataDetail(
                    name="invoice_number",
                    value="INV-2026-004",
                    evidence_ids=("ev_1",),
                ),
            ),
            evidence_details=(
                ClassificationEvidenceDetail(
                    evidence_id="ev_1",
                    page_number=1,
                    quote="Invoice heading and total are explicit.",
                ),
                ClassificationEvidenceDetail(
                    evidence_id="ev_2",
                    page_number=1,
                    quote="Supplier name is visible.",
                ),
            ),
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="1.00000",
            retry_attempts=1,
        )

    window = CockpitWindow(
        classification_function=fake_classification,
        runtime_preflight_function=ready_runtime_preflight_report,
    )
    window.set_authorized_root(corpus)

    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    discovered = tuple(
        DiscoveredFile(
            root=corpus,
            absolute_path=path,
            relative_path=path.name,
            comparison_key=path.name.casefold(),
            status=DiscoveryStatus.CANDIDATE,
            byte_size=path.stat().st_size,
        )
        for path in sorted(corpus.glob("*.pdf"))
    )
    records = tuple(
        IntakeRecord(
            discovered_file=file,
            status=IntakeStatus.READY,
            reason=None,
            signature=None,
            fingerprint=None,
        )
        for file in discovered
    )
    result = DesktopScanResult(
        root=corpus,
        discovery=DiscoveryResult(
            files=discovered,
            scanned_roots=(corpus,),
            limit_reached=False,
        ),
        intake=IntakeResult(records=records),
    )

    window._workspace.start_scan()
    window._handle_scan_completed(result)

    assert window.left.table.rowCount() == 30
    discovered_metric = cast(Any, window.right.metric_frames[0]).number
    ready_metric = cast(Any, window.right.metric_frames[1]).number
    assert discovered_metric.text() == "30"
    assert ready_metric.text() == "30"

    opened_paths: list[Path] = []

    def record_opened_path(path: Path) -> None:
        opened_paths.append(path)
        window.center.filename.setText(path.name)

    monkeypatch.setattr(window.center, "open_document", record_opened_path)
    window._open_document_row(0)

    assert window.center.filename.text().endswith(".pdf")
    assert opened_paths == [first_pdf]
    assert "No files were changed" in window.console.log_text.text()
    assert window.console.buttons[3].isEnabled()

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    expected_paths = sorted(corpus.glob("*.pdf"))
    assert classified_paths == [(path, corpus) for path in expected_paths]
    assert window.left.count_status("REVIEW") == 30
    assert_visible_classification_proposal(window)

    close_cockpit_window(window)


def test_cockpit_records_local_review_decision_without_file_mutation(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    window = CockpitWindow(runtime_preflight_function=ready_runtime_preflight_report)
    window.set_authorized_root(corpus)
    window.left.set_documents(
        [
            Document(
                name=first_pdf.name,
                category="invoice",
                pages="2",
                status="REVIEW",
                path=first_pdf,
                proposed_destination="DocWeave Organized/Invoices/invoice.pdf",
                proposal_fingerprint="a" * 64,
            )
        ]
    )

    window._open_document_row(0)

    assert window.console.buttons[4].isEnabled()
    assert window.console.buttons[5].isEnabled()

    window._approve_selected_review()

    document = window.left.document_at(0)
    assert document is not None
    assert document.status == "APPROVED"
    assert document.review_decision_id is not None
    assert window.left.count_status("REVIEW") == 0
    assert len(window._review_ledger.all_decisions()) == 1
    assert "approved" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "Local review ledger"
    )
    assert cast(Any, window.right.event_rows[4]).event_text.text() == (
        "No copy or move executed"
    )

    close_cockpit_window(window)


def test_cockpit_records_durable_review_decision_when_proposal_id_is_available(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    proposal_id = UUID("44444444-4444-4444-8444-444444444444")
    calls: list[ReviewDecisionCommandInput] = []

    def fake_review_decision_function(
        command_input: ReviewDecisionCommandInput,
    ) -> ReviewDecisionCommandResult:
        calls.append(command_input)
        assert command_input.proposal_id == proposal_id
        assert command_input.proposal_fingerprint == "a" * 64
        assert command_input.review_decision_id is not None
        return ReviewDecisionCommandResult(
            action=command_input.action.value,
            proposal_id=command_input.proposal_id,
            review_decision_id=command_input.review_decision_id,
            disposition=PersistenceDisposition.APPLIED,
        )

    window = CockpitWindow(
        runtime_preflight_function=ready_runtime_preflight_report,
        review_decision_function=fake_review_decision_function,
    )
    window.set_authorized_root(corpus)
    window.left.set_documents(
        [
            Document(
                name=first_pdf.name,
                category="invoice",
                pages="2",
                status="REVIEW",
                path=first_pdf,
                proposed_destination="DocWeave Organized/Invoices/invoice.pdf",
                proposal_id=str(proposal_id),
                proposal_fingerprint="a" * 64,
            )
        ]
    )

    window._open_document_row(0)
    window._approve_selected_review()

    document = window.left.document_at(0)
    assert document is not None
    assert document.status == "APPROVED"
    assert len(calls) == 1
    assert len(window._review_ledger.all_decisions()) == 1
    assert window._review_ledger.all_decisions()[0].proposal_id == str(proposal_id)
    assert "durably" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "CockroachDB applied"
    )

    close_cockpit_window(window)


def test_cockpit_blocks_review_decision_without_proposal_fingerprint(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    window = CockpitWindow(runtime_preflight_function=ready_runtime_preflight_report)
    window.set_authorized_root(corpus)
    window.left.set_documents(
        [
            Document(
                name=first_pdf.name,
                category="invoice",
                pages="2",
                status="REVIEW",
                path=first_pdf,
                proposed_destination="DocWeave Organized/Invoices/invoice.pdf",
            )
        ]
    )
    window._selected_document_row = 0

    window._approve_selected_review()

    document = window.left.document_at(0)
    assert document is not None
    assert document.status == "REVIEW"
    assert len(window._review_ledger.all_decisions()) == 0
    assert "no retained fingerprint" in window.console.log_text.text()

    close_cockpit_window(window)


def test_cockpit_analysis_batch_preserves_progress_after_failure(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    batch_paths = tuple(sorted(corpus.glob("*.pdf"))[:3])
    calls: list[Path] = []
    fail_on_third_attempt = True

    def fake_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        nonlocal fail_on_third_attempt
        assert authorized_root == corpus
        calls.append(source_path)
        if fail_on_third_attempt and source_path == batch_paths[2]:
            raise RuntimeError("synthetic failure")
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
            document_language="en",
            rationale="The document contains invoice wording and a total.",
            evidence_count=1,
            metadata_count=1,
            metadata_details=(
                ClassificationMetadataDetail(
                    name="supplier",
                    value="ACME SRL",
                    evidence_ids=("ev_1",),
                ),
                ClassificationMetadataDetail(
                    name="invoice_number",
                    value="INV-2026-004",
                    evidence_ids=("ev_1",),
                ),
            ),
            evidence_details=(
                ClassificationEvidenceDetail(
                    evidence_id="ev_1",
                    page_number=1,
                    quote="Invoice heading and total are explicit.",
                ),
            ),
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="1.00000",
            retry_attempts=0,
        )

    window = CockpitWindow(
        classification_function=fake_classification,
        runtime_preflight_function=ready_runtime_preflight_report,
    )
    window.set_authorized_root(corpus)
    discovered = tuple(
        DiscoveredFile(
            root=corpus,
            absolute_path=path,
            relative_path=path.name,
            comparison_key=path.name.casefold(),
            status=DiscoveryStatus.CANDIDATE,
            byte_size=path.stat().st_size,
        )
        for path in batch_paths
    )
    records = tuple(
        IntakeRecord(
            discovered_file=file,
            status=IntakeStatus.READY,
            reason=None,
            signature=None,
            fingerprint=None,
        )
        for file in discovered
    )
    result = DesktopScanResult(
        root=corpus,
        discovery=DiscoveryResult(
            files=discovered,
            scanned_roots=(corpus,),
            limit_reached=False,
        ),
        intake=IntakeResult(records=records),
    )
    window._workspace.start_scan()
    window._handle_scan_completed(result)
    window._set_busy(False)

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    assert calls == list(batch_paths)
    assert window.left.count_status("REVIEW") == 2
    assert window.left.count_status("READY") == 1
    assert "Classification batch complete: 2 of 3 proposal(s) persisted" in (
        window.console.log_text.text()
    )
    assert "Failed item(s): 1" in window.console.log_text.text()
    assert window.console.buttons[3].isEnabled()

    close_cockpit_window(window)


def test_cockpit_analysis_retry_queues_only_ready_documents(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    batch_paths = tuple(sorted(corpus.glob("*.pdf"))[:3])
    calls: list[Path] = []

    def fake_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        assert authorized_root == corpus
        calls.append(source_path)
        return ClassificationCommandResult(
            proposed_class="invoice",
            document_disposition="applied",
            taxonomy_disposition="applied",
            proposal_disposition="applied",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
            document_language="en",
            rationale="The document contains invoice wording and a total.",
            evidence_count=1,
            metadata_count=1,
            metadata_details=(
                ClassificationMetadataDetail(
                    name="supplier",
                    value="ACME SRL",
                    evidence_ids=("ev_1",),
                ),
            ),
            evidence_details=(
                ClassificationEvidenceDetail(
                    evidence_id="ev_1",
                    page_number=1,
                    quote="Invoice heading and total are explicit.",
                ),
            ),
            raw_confidence="0.80000",
            classification_confidence="0.80000",
            metadata_confidence="1.00000",
            retry_attempts=0,
        )

    window = CockpitWindow(
        classification_function=fake_classification,
        runtime_preflight_function=ready_runtime_preflight_report,
    )
    window.set_authorized_root(corpus)
    discovered = tuple(
        DiscoveredFile(
            root=corpus,
            absolute_path=path,
            relative_path=path.name,
            comparison_key=path.name.casefold(),
            status=DiscoveryStatus.CANDIDATE,
            byte_size=path.stat().st_size,
        )
        for path in batch_paths
    )
    records = tuple(
        IntakeRecord(
            discovered_file=file,
            status=IntakeStatus.READY,
            reason=None,
            signature=None,
            fingerprint=None,
        )
        for file in discovered
    )
    result = DesktopScanResult(
        root=corpus,
        discovery=DiscoveryResult(
            files=discovered,
            scanned_roots=(corpus,),
            limit_reached=False,
        ),
        intake=IntakeResult(records=records),
    )
    window._workspace.start_scan()
    window._handle_scan_completed(result)
    window._set_busy(False)
    window.left.mark_document_for_review(
        0,
        proposed_class="invoice",
        proposed_destination=None,
    )
    window.left.mark_document_for_review(
        1,
        proposed_class="invoice",
        proposed_destination=None,
    )

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    assert calls == [batch_paths[2]]
    assert window.left.count_status("REVIEW") == 3
    assert window.left.count_status("READY") == 0
    assert "Classification batch complete: 1 of 1" in window.console.log_text.text()

    close_cockpit_window(window)
