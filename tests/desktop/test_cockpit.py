from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

import docweave.desktop.cockpit as cockpit_module
from docweave.analysis import BedrockGatewayError, BedrockGatewayErrorCode
from docweave.application_runtime import RuntimeIntegrationSnapshot
from docweave.classification_cli import (
    ClassificationCommandResult,
    ClassificationEvidenceDetail,
    ClassificationMetadataDetail,
)
from docweave.desktop.cockpit import CockpitLineagePreview, CockpitWindow, Document
from docweave.desktop.scan import DesktopScanResult
from docweave.discovery import DiscoveredFile, DiscoveryResult, DiscoveryStatus
from docweave.intake import IntakeRecord, IntakeResult, IntakeStatus
from docweave.live_memory_validation import EXPECTED_HEAD
from docweave.memory_evidence_report import MemoryEvidenceReport, MemoryTableCount
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


class _InMemoryFolderMemory:
    def __init__(self, remembered: Path | None = None) -> None:
        self.remembered = remembered
        self.saved: list[Path] = []

    def last_authorized_folder(self) -> Path | None:
        return self.remembered

    def remember_authorized_folder(self, folder: Path) -> None:
        self.saved.append(folder)
        self.remembered = folder


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


def reachable_runtime_preflight_report() -> RuntimePreflightReport:
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
                PreflightState.OK,
                "reachable",
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
    assert not window.center.memory_panel.isHidden()
    assert "Bedrock proposal persisted as applied" in (
        window.center.memory_summary.text()
    )
    assert "Fingerprint" in window.center.memory_detail.text()
    assert "rename_and_move" in window.center.memory_detail.text()

    log_text = window.console.log_text.text()
    assert "Classification batch complete: 30 of 30" in log_text

    proposed_class_item = window.left.table.item(0, 1)
    assert proposed_class_item is not None
    assert window.left.table.columnCount() == 2
    assert proposed_class_item.text() == "invoice"
    assert "Proposed rename_and_move target: DocWeave Organized/Invoices/" in (
        proposed_class_item.toolTip()
    )
    assert "invoice_acme-srl_inv-2026-004.pdf" in proposed_class_item.toolTip()
    assert "Lineage preview:" in proposed_class_item.toolTip()

    document = window.left.document_at(0)
    assert document is not None
    assert document.lineage_preview is not None
    assert document.lineage_preview.action == "rename_and_move"
    assert document.lineage_preview.original_relative_path.endswith(".pdf")
    assert document.lineage_preview.previous_relative_path.endswith(".pdf")
    assert document.lineage_preview.next_relative_path.startswith(
        "DocWeave Organized/Invoices/"
    )
    assert document.lineage_preview.next_filename == "invoice_acme-srl_inv-2026-004.pdf"
    assert len(document.lineage_preview.plan_fingerprint) == 64

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
        "Mass rename/move previews ready"
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
    assert window.left.table.font().pointSize() >= 11
    assert window.left.table.horizontalHeader().font().pointSize() >= 11
    assert window.console.bedrock_button is window.console.buttons[6]
    assert window.console.lateral_screens_button.text() == "S-SCREENS"
    assert not window.console.lateral_screens_button.isHidden()
    assert cast(Any, window.right.event_rows[0]).event_text.wordWrap()
    assert "CockroachDB      Configured" in window.console.status_text.text()
    assert window.console.bedrock_button.text() == "BEDROCK"
    assert "Read-only CockroachDB restore history reader is available" in (
        window.right.restore_text.text()
    )

    close_cockpit_window(window)


def test_cockpit_places_bedrock_button_beside_reject(
    qt_application: object,
) -> None:
    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=True,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        )
    )
    window.resize(1760, 1080)
    window.show()
    cast(QApplication, qt_application).processEvents()

    reject = window.console.buttons[5].geometry()
    bedrock = window.console.bedrock_button.geometry()

    assert bedrock.left() > reject.left()
    assert bedrock.top() == reject.top()
    assert bedrock.height() == reject.height()
    assert bedrock.width() == reject.width()

    close_cockpit_window(window)


def test_cockpit_bedrock_button_launches_login_when_disconnected(
    qt_application: object,
) -> None:
    launches = 0

    def fake_login() -> bool:
        nonlocal launches
        launches += 1
        return True

    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=True,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        ),
        bedrock_auth_probe_function=lambda: False,
        bedrock_login_launcher=fake_login,
    )
    window._refresh_bedrock_auth_status()

    assert window.console.bedrock_button.text() == "BEDROCK LOGIN"
    assert window.console.bedrock_button.property("authState") == "disconnected"

    window.console.bedrock_button.click()

    assert launches == 1
    assert "AWS login opened" in window.console.log_text.text()
    assert window.console.bedrock_button.property("authState") == "checking"

    close_cockpit_window(window)


def test_cockpit_blocks_analyze_when_bedrock_login_is_required(
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
        raise AssertionError("classification should not start")

    window = CockpitWindow(
        classification_function=unexpected_classification,
        runtime_preflight_function=ready_runtime_preflight_report,
        bedrock_auth_probe_function=lambda: False,
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

    window._analyze_selected_document()

    assert calls == 0
    assert "Bedrock login required" in window.console.log_text.text()
    assert window.console.bedrock_button.text() == "BEDROCK LOGIN"
    assert cast(Any, window.right.event_rows[1]).event_text.text() == (
        "AWS login required"
    )

    close_cockpit_window(window)


def test_cockpit_right_screen_visible_text_stays_inside_panel(
    qt_application: object,
) -> None:
    window = CockpitWindow(
        integration_snapshot=RuntimeIntegrationSnapshot(
            cockroachdb_configured=True,
            bedrock_region="eu-central-1",
            bedrock_model_id="eu.amazon.nova-2-lite-v1:0",
        )
    )
    window.resize(1760, 1080)
    window.show()
    window.right.resize(431, 739)
    cast(QApplication, qt_application).processEvents()

    visible_widgets = [
        window.right.title,
        window.right.online,
        window.right.section,
        window.right.memory_label,
        window.right.memory_text,
        window.right.memory_table,
        window.right.stream_label,
        *window.right.metric_frames,
        *window.right.event_rows,
    ]

    panel_rect = window.right.rect()
    for widget in visible_widgets:
        assert panel_rect.contains(widget.geometry()), widget.objectName()

    assert not window.right.restore_label.isVisible()
    assert not window.right.restore_text.isVisible()

    close_cockpit_window(window)


def test_cockpit_surfaces_read_only_memory_evidence(
    qt_application: object,
) -> None:
    report = MemoryEvidenceReport(
        alembic_revision=EXPECTED_HEAD,
        expected_head=EXPECTED_HEAD,
        table_counts=(
            MemoryTableCount("documents", True, 30),
            MemoryTableCount("proposals", True, 12),
            MemoryTableCount("file_history", True, 6),
        ),
    )
    window = CockpitWindow(
        runtime_preflight_function=reachable_runtime_preflight_report,
        memory_evidence_function=lambda: report,
    )

    window._refresh_runtime_preflight_report()
    window._set_status("Runtime checked")

    assert (
        f"CockroachDB memory schema ready: 3/3 tables at {EXPECTED_HEAD}; 48 row(s)."
    ) in window.right.memory_text.text()
    assert window.right.memory_table.rowCount() == 3
    first_table = window.right.memory_table.item(0, 0)
    first_count = window.right.memory_table.item(0, 1)
    last_table = window.right.memory_table.item(2, 0)
    last_count = window.right.memory_table.item(2, 1)
    assert first_table is not None
    assert first_count is not None
    assert last_table is not None
    assert last_count is not None
    assert first_table.text() == "documents"
    assert first_count.text() == "30"
    assert last_table.text() == "proposals"
    assert last_count.text() == "12"
    assert "DOCWEAVE_DATABASE_URL" not in window.right.memory_text.text()

    close_cockpit_window(window)


def test_cockpit_sanitizes_memory_evidence_failures(
    qt_application: object,
) -> None:
    def broken_evidence() -> MemoryEvidenceReport:
        raise RuntimeError("secret connection value")

    window = CockpitWindow(
        runtime_preflight_function=reachable_runtime_preflight_report,
        memory_evidence_function=broken_evidence,
    )

    window._refresh_runtime_preflight_report()
    window._set_status("Runtime checked")

    assert (
        "CockroachDB memory evidence unavailable: RuntimeError."
        in window.right.memory_text.text()
    )
    assert "secret connection value" not in window.right.memory_text.text()

    close_cockpit_window(window)


def test_cockpit_folder_picker_reuses_active_authorized_directory(
    tmp_path: Path,
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = tmp_path / "active"
    selected = tmp_path / "selected"
    active.mkdir()
    selected.mkdir()
    memory = _InMemoryFolderMemory(None)
    dialog_directories: list[str] = []

    def choose_directory(
        _parent: object,
        _caption: str,
        directory: str,
    ) -> str:
        dialog_directories.append(directory)
        return str(selected)

    window = CockpitWindow(folder_memory=memory)
    window.set_authorized_root(active)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_directory)

    window._choose_folder()

    assert dialog_directories == [str(active.resolve())]
    assert window.authorized_root == selected.resolve()
    assert memory.saved == [active.resolve(), selected.resolve()]

    close_cockpit_window(window)


def test_cockpit_folder_picker_defaults_to_synthetic_pdf_directory(
    tmp_path: Path,
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    memory = _InMemoryFolderMemory(None)
    dialog_directories: list[str] = []

    def choose_directory(
        _parent: object,
        _caption: str,
        directory: str,
    ) -> str:
        dialog_directories.append(directory)
        return str(selected)

    window = CockpitWindow(folder_memory=memory)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_directory)

    window._choose_folder()

    assert dialog_directories == [str(Path("pdf_sintetici").resolve(strict=True))]
    assert window.authorized_root == selected.resolve()

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
    assert window.console.bedrock_button.text() == "BEDROCK"
    assert "DOCWEAVE_DATABASE_URL" not in status
    assert "Restore history reader blocked by runtime config" in (
        window.right.restore_text.text()
    )
    assert "DOCWEAVE_DATABASE_URL" not in window.right.restore_text.text()

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


def test_cockpit_checks_database_before_analyze_and_reports_reachable(
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    check_database_calls: list[bool] = []

    def fake_run_preflight(*, check_database: bool) -> RuntimePreflightReport:
        check_database_calls.append(check_database)
        cockroach_state = PreflightState.OK if check_database else PreflightState.SKIP
        cockroach_detail = "reachable" if check_database else "not_requested"
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
                    cockroach_state,
                    cockroach_detail,
                ),
            )
        )

    def fake_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
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
        )

    monkeypatch.setenv(
        "DOCWEAVE_DATABASE_URL",
        "cockroachdb://user:secret@example.test/docweave",
    )
    monkeypatch.setattr(cockpit_module, "run_preflight", fake_run_preflight)

    window = CockpitWindow(
        classification_function=fake_classification,
        bedrock_auth_probe_function=lambda: True,
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

    assert "CockroachDB      Reachable" in window.console.status_text.text()

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    assert check_database_calls == [False, True, True]
    assert "CockroachDB      Reachable" in window.console.status_text.text()

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
    compact_width = window.center.geometry().width()

    window.console.lateral_screens_button.click()

    assert window.side_view.isHidden()
    assert window.center.geometry().width() > window.width() * 0.75

    window.console.lateral_screens_button.click()

    assert not window.side_view.isHidden()
    assert window.center.geometry().width() == compact_width

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    expected_paths = sorted(corpus.glob("*.pdf"))
    assert classified_paths == [(path, corpus) for path in expected_paths]
    assert window.left.count_status("REVIEW") == 30
    assert_visible_classification_proposal(window)

    window._open_document_row(0)

    assert cast(Any, window.right.event_rows[2]).event_name.text() == "LINEAGE"
    assert "rename_and_move:" in cast(Any, window.right.event_rows[2]).event_text.text()
    assert (
        "DocWeave Organized/Invoices/"
        in cast(
            Any,
            window.right.event_rows[2],
        ).event_text.text()
    )

    close_cockpit_window(window)


def test_cockpit_records_local_rejection_without_file_mutation(
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
                proposal_fingerprint="a" * 64,
            )
        ]
    )

    window._open_document_row(0)

    assert window.console.buttons[4].isEnabled()
    assert window.console.buttons[5].isEnabled()
    assert not window.center.memory_panel.isHidden()
    assert "Review memory selected for invoice" in window.center.memory_summary.text()
    assert "fingerprint aaaaaaaaaaaa" in window.center.memory_detail.text()

    window._reject_selected_review()

    document = window.left.document_at(0)
    assert document is not None
    assert document.status == "REJECTED"
    assert document.review_decision_id is not None
    assert window.left.count_status("REVIEW") == 0
    assert len(window._review_ledger.all_decisions()) == 1
    assert "rejected" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "Local review ledger"
    )
    assert cast(Any, window.right.event_rows[4]).event_text.text() == "No move"
    assert "Human review rejected append recorded" in (
        window.center.memory_summary.text()
    )
    assert "Local review ledger" in window.center.memory_detail.text()

    close_cockpit_window(window)


def test_cockpit_opens_batch_review_table_from_approve_button(  # noqa: PLR0915
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf, second_pdf = sorted(corpus.glob("*.pdf"))[:2]
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
                proposed_destination="DocWeave Organized/Invoices/first.pdf",
                proposal_fingerprint="a" * 64,
                lineage_preview=CockpitLineagePreview(
                    action="rename_and_move",
                    original_relative_path=first_pdf.name,
                    previous_relative_path=first_pdf.name,
                    next_relative_path="DocWeave Organized/Invoices/first.pdf",
                    original_directory="",
                    original_filename=first_pdf.name,
                    next_directory="DocWeave Organized/Invoices",
                    next_filename="first.pdf",
                    plan_fingerprint="b" * 64,
                ),
            ),
            Document(
                name=second_pdf.name,
                category="supplier_receipt",
                pages="1",
                status="REVIEW",
                path=second_pdf,
                proposed_destination="DocWeave Organized/Receipts/second.pdf",
                proposal_fingerprint="c" * 64,
                lineage_preview=CockpitLineagePreview(
                    action="rename_and_move",
                    original_relative_path=second_pdf.name,
                    previous_relative_path=second_pdf.name,
                    next_relative_path="DocWeave Organized/Receipts/second.pdf",
                    original_directory="",
                    original_filename=second_pdf.name,
                    next_directory="DocWeave Organized/Receipts",
                    next_filename="second.pdf",
                    plan_fingerprint="d" * 64,
                ),
            ),
        ]
    )

    window._selected_document_row = 0
    window._set_busy(False)
    window.show()
    cast(QApplication, qt_application).processEvents()
    window.console.buttons[4].click()

    assert window.center.page.isHidden()
    assert not window.center.review_table.isHidden()
    assert window.side_view.isHidden()
    assert window.center.geometry().width() > window.width() * 0.75
    assert window.center.review_table.rowCount() == 2
    assert not window.console.lateral_screens_button.isHidden()
    assert window.center.review_table.columnCount() == 4
    original_header = window.center.review_table.horizontalHeaderItem(0)
    proposed_header = window.center.review_table.horizontalHeaderItem(1)
    directory_header = window.center.review_table.horizontalHeaderItem(2)
    assert original_header is not None
    assert proposed_header is not None
    assert directory_header is not None
    assert original_header.text() == "PDF NAME"
    assert proposed_header.text() == "PROPOSED NAME"
    assert directory_header.text() == "SUGGESTED DIRECTORY"
    assert window.center.review_table.columnWidth(0) <= 240
    assert window.center.review_table.columnWidth(3) >= 220
    original_item = window.center.review_table.item(0, 0)
    proposed_item = window.center.review_table.item(0, 1)
    directory_item = window.center.review_table.item(0, 2)
    assert original_item is not None
    assert proposed_item is not None
    assert directory_item is not None
    assert original_item.text() == first_pdf.name
    assert proposed_item.text() == "first.pdf"
    assert directory_item.text() == "DocWeave Organized/Invoices"
    action_widget = window.center.review_table.cellWidget(0, 3)
    assert action_widget is not None
    action_buttons = action_widget.findChildren(QPushButton)
    assert [button.objectName() for button in action_buttons] == [
        "reviewApproveButton",
        "reviewRejectButton",
        "reviewPreviewButton",
    ]
    assert action_buttons[0].width() >= 52
    assert action_buttons[1].width() >= 52
    assert action_buttons[2].width() >= 58
    assert "Batch review ready: 2 proposed rename" in window.console.log_text.text()

    window.console.lateral_screens_button.click()

    assert not window.side_view.isHidden()
    assert not window.center.review_table.isHidden()
    assert not window.console.lateral_screens_button.isHidden()
    assert window.center.geometry().width() < window.width() * 0.60

    window.console.lateral_screens_button.click()

    assert window.side_view.isHidden()
    assert not window.center.review_table.isHidden()
    assert window.center.geometry().width() > window.width() * 0.75

    close_cockpit_window(window)


def test_cockpit_records_durable_review_decision_when_proposal_id_is_available(
    qt_application: object,
    tmp_path: Path,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    working_pdf = authorized / first_pdf.name
    working_pdf.write_bytes(first_pdf.read_bytes())
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
    window.set_authorized_root(authorized)
    window.left.set_documents(
        [
            Document(
                name=working_pdf.name,
                category="invoice",
                pages="2",
                status="REVIEW",
                path=working_pdf,
                proposed_destination="DocWeave Organized/Invoices/invoice.pdf",
                document_id="66666666-6666-4666-8666-666666666666",
                proposal_id=str(proposal_id),
                proposal_fingerprint="a" * 64,
                lineage_preview=CockpitLineagePreview(
                    action="rename_and_move",
                    original_relative_path=working_pdf.name,
                    previous_relative_path=working_pdf.name,
                    next_relative_path="DocWeave Organized/Invoices/invoice.pdf",
                    original_directory="",
                    original_filename=working_pdf.name,
                    next_directory="DocWeave Organized/Invoices",
                    next_filename="invoice.pdf",
                    plan_fingerprint="b" * 64,
                ),
            )
        ]
    )

    window._open_document_row(0)
    window._approve_selected_review()

    document = window.left.document_at(0)
    assert document is not None
    assert document.status == "MOVED"
    assert document.path == (
        authorized / "DocWeave Organized" / "Invoices" / "invoice.pdf"
    )
    assert document.path.exists()
    assert not working_pdf.exists()
    assert len(calls) == 1
    assert calls[0].previous_filename == first_pdf.name
    assert calls[0].next_filename == "invoice.pdf"
    assert len(window._review_ledger.all_decisions()) == 1
    assert window._review_ledger.all_decisions()[0].proposal_id == str(proposal_id)
    assert "durably" in window.console.log_text.text()
    assert cast(Any, window.right.event_rows[3]).event_text.text() == (
        "CockroachDB applied"
    )
    assert "Human review approved append recorded" in (
        window.center.memory_summary.text()
    )
    assert "CockroachDB applied" in window.center.memory_detail.text()

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


def test_cockpit_reports_sanitized_bedrock_gateway_error(
    qt_application: object,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    first_pdf = sorted(corpus.glob("*.pdf"))[0]

    def fail_classification(
        source_path: Path,
        authorized_root: Path,
    ) -> ClassificationCommandResult:
        raise BedrockGatewayError(BedrockGatewayErrorCode.AUTHENTICATION_FAILED)

    window = CockpitWindow(
        classification_function=fail_classification,
        runtime_preflight_function=ready_runtime_preflight_report,
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

    window._analyze_selected_document()
    wait_for_cockpit_classification(window)

    assert "bedrock:authentication_failed" in window.console.log_text.text()
    assert (
        "bedrock:authentication_failed"
        in cast(
            Any,
            window.right.event_rows[1],
        ).event_text.text()
    )
    assert "DOCWEAVE_DATABASE_URL" not in window.console.log_text.text()

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
