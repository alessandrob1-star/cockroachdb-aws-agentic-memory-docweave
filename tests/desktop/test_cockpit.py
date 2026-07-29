from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from docweave.application_runtime import RuntimeIntegrationSnapshot
from docweave.classification_cli import ClassificationCommandResult
from docweave.desktop.cockpit import CockpitWindow, Document
from docweave.desktop.scan import DesktopScanResult
from docweave.discovery import DiscoveredFile, DiscoveryResult, DiscoveryStatus
from docweave.intake import IntakeRecord, IntakeResult, IntakeStatus
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

    def poll() -> None:
        if not window.classification_in_progress:
            loop.quit()
            return
        QTimer.singleShot(10, poll)

    QTimer.singleShot(10, poll)
    QTimer.singleShot(3_000, mark_timeout)
    loop.exec()
    assert not timed_out


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

    log_text = window.console.log_text.text()
    assert "Classification proposal persisted" in log_text
    assert "Class: invoice" in log_text
    assert "Confidence: 0.80000" in log_text
    assert "Evidence items: 2; metadata fields: 1" in log_text
    assert "Rationale: The document contains invoice wording" in log_text

    proposed_class_item = window.left.table.item(0, 1)
    review_status_item = window.left.table.item(0, 3)
    assert proposed_class_item is not None
    assert review_status_item is not None
    assert proposed_class_item.text() == "invoice"
    assert review_status_item.text() == "REVIEW"

    ready_metric = cast(Any, window.right.metric_frames[1]).number
    review_metric = cast(Any, window.right.metric_frames[2]).number
    assert ready_metric.text() == "29"
    assert review_metric.text() == "1"
    assert cast(Any, window.right.event_rows[0]).event_text.text() == (
        "Proposed invoice"
    )
    assert cast(Any, window.right.event_rows[1]).event_text.text() == "2 cited spans"
    assert cast(Any, window.right.event_rows[2]).event_text.text() == "Raw 0.80000"
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "Proposal applied"
    )
    assert (
        "Validation retries 1"
        in cast(Any, window.right.event_rows[4]).event_text.text()
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

    window.close()


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

    window.close()


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

    assert not window.console.buttons[3].isEnabled()
    assert "preflight" in window.console.buttons[3].toolTip().lower()

    window._analyze_selected_document()

    assert calls == 0
    assert not window.classification_in_progress
    assert "Runtime is not ready for classification" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[0]).event_text.text() == "Not started"
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "No model invocation"
    )

    window.close()


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

    assert classified_paths == [(first_pdf, corpus)]
    assert_visible_classification_proposal(window)

    window.close()
