from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QEventLoop, QItemSelectionModel, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QWidget,
)

from docweave.core.cancellation import CancellationCheck, CancellationRequestedError
from docweave.desktop.main_window import DocWeaveMainWindow
from docweave.desktop.scan import (
    DesktopScanResult,
    ScanPhase,
    ScanProgress,
    ScanProgressCallback,
    scan_authorized_root,
)
from docweave.desktop.workspace import WorkspacePhase


def wait_for_scan(window: DocWeaveMainWindow) -> None:
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


def test_window_runs_scan_without_blocking_and_updates_evidence(
    tmp_path: Path,
    qt_application: object,
) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    window = DocWeaveMainWindow()
    window.set_authorized_root(tmp_path)
    scan_button = window.findChild(QPushButton, "primaryButton")
    root_field = window.findChild(QLineEdit, "authorizedRoot")

    assert scan_button is not None
    assert scan_button.isEnabled()
    assert root_field is not None
    assert root_field.text() == str(tmp_path.resolve())

    wait_for_scan(window)

    table = window.findChild(QTableView, "documentTable")
    status = window.findChild(QLabel, "status")
    assert table is not None
    assert table.model().rowCount() == 2
    assert status is not None
    assert "Scan complete: 2 files" in status.text()
    assert "No files were changed" in status.text()
    assert not window.scan_in_progress
    window.close()


def test_window_reports_background_failure_without_private_details(
    tmp_path: Path,
    qt_application: object,
) -> None:
    def fail_scan(
        root: Path,
        *,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> DesktopScanResult:
        del progress_callback, cancellation_check
        raise PermissionError(f"must not be displayed: {root}")

    window = DocWeaveMainWindow(scan_function=fail_scan)
    window.set_authorized_root(tmp_path)

    wait_for_scan(window)

    status = window.findChild(QLabel, "status")
    assert status is not None
    assert status.text() == (
        "Scan failed safely (PermissionError). No files were changed."
    )
    assert str(tmp_path) not in status.text()
    window.close()


def test_window_rejects_non_directory_authorization(
    tmp_path: Path,
    qt_application: object,
) -> None:
    file_path = tmp_path / "invoice.pdf"
    file_path.write_bytes(b"%PDF-1.7\ninvoice")
    window = DocWeaveMainWindow()

    with pytest.raises(NotADirectoryError, match="must be a directory"):
        window.set_authorized_root(file_path)

    assert window.authorized_root is None
    window.close()


def test_window_blocks_root_change_and_close_during_scan(
    tmp_path: Path,
    qt_application: object,
) -> None:
    started = Event()
    release = Event()

    def controlled_scan(
        root: Path,
        *,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> DesktopScanResult:
        del progress_callback, cancellation_check
        started.set()
        release.wait(timeout=2)
        return scan_authorized_root(root)

    window = DocWeaveMainWindow(scan_function=controlled_scan)
    window.set_authorized_root(tmp_path)
    window.start_scan()
    assert started.wait(timeout=1)
    assert window.scan_in_progress
    choose_button = window.findChild(QPushButton, "secondaryButton")
    assert choose_button is not None
    assert not choose_button.isEnabled()

    window.start_scan()
    with pytest.raises(RuntimeError, match="cannot change"):
        window.set_authorized_root(tmp_path)
    assert not window.close()
    status = window.findChild(QLabel, "status")
    assert status is not None
    assert "Scan still running" in status.text()

    release.set()
    loop = QEventLoop()
    window.scan_finished.connect(loop.quit)
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()
    assert not window.scan_in_progress
    window.close()


def test_window_cancels_scan_and_discards_partial_results(
    tmp_path: Path,
    qt_application: object,
) -> None:
    started = Event()

    def cancellable_scan(
        root: Path,
        *,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> DesktopScanResult:
        del root, progress_callback
        started.set()
        assert cancellation_check is not None
        while not cancellation_check():
            started.wait(timeout=0.01)
        raise CancellationRequestedError

    window = DocWeaveMainWindow(scan_function=cancellable_scan)
    window.set_authorized_root(tmp_path)
    window.start_scan()
    assert started.wait(timeout=1)
    cancel_button = window.findChild(QPushButton, "secondaryButton")
    progress_bar = window.findChild(QProgressBar, "scanProgress")
    assert progress_bar is not None
    assert progress_bar.isVisible() is window.isVisible()

    window.cancel_scan()
    loop = QEventLoop()
    window.scan_finished.connect(loop.quit)
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()

    assert window.workspace_snapshot.phase is WorkspacePhase.CANCELLED
    assert window.workspace_snapshot.result is None
    assert cancel_button is not None
    status = window.findChild(QLabel, "status")
    assert status is not None
    assert "cancelled safely" in status.text()
    window.close()


def test_window_tracks_multiple_document_selection_in_memory(
    tmp_path: Path,
    qt_application: object,
) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    (tmp_path / "payment.pdf").write_bytes(b"%PDF-1.7\npayment")
    window = DocWeaveMainWindow()
    window.set_authorized_root(tmp_path)
    wait_for_scan(window)
    table = window.findChild(QTableView, "documentTable")
    selection_status = window.findChild(QLabel, "selectionStatus")
    assert table is not None
    selection_model = table.selectionModel()
    flags = (
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows
    )

    selection_model.select(table.model().index(0, 0), flags)
    selection_model.select(table.model().index(1, 0), flags)

    assert window.workspace_snapshot.selected_document_keys == frozenset(
        {"invoice.pdf", "payment.pdf"}
    )
    assert selection_status is not None
    assert selection_status.text() == "2 selected"
    window.close()


def test_window_opens_one_ready_pdf_through_injected_preview(
    tmp_path: Path,
    qt_application: object,
) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.7\ninvoice")
    previews: list[tuple[Path, QDialog]] = []

    def create_preview(path: Path, parent: QWidget) -> QDialog:
        dialog = QDialog(parent)
        previews.append((path, dialog))
        return dialog

    window = DocWeaveMainWindow(preview_factory=create_preview)
    window.set_authorized_root(tmp_path)
    wait_for_scan(window)
    table = window.findChild(QTableView, "documentTable")
    open_button = window.findChild(QPushButton, "openPdfButton")
    assert table is not None
    table.selectRow(0)

    window.open_selected_document()

    assert len(previews) == 1
    assert previews[0][0] == path.resolve()
    status = window.findChild(QLabel, "status")
    assert status is not None
    assert "preview opened inside DocWeave" in status.text()
    assert open_button is not None
    assert open_button.isEnabled()
    window.close()


def test_window_blocks_changed_or_non_ready_pdf_and_reports_preview_failure(
    tmp_path: Path,
    qt_application: object,
) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    ready = tmp_path / "ready.pdf"
    ready.write_bytes(b"%PDF-1.7\nready")

    def fail_preview(path: Path, parent: QWidget) -> QDialog:
        del path, parent
        raise RuntimeError("private details")

    window = DocWeaveMainWindow(preview_factory=fail_preview)
    window.set_authorized_root(tmp_path)
    wait_for_scan(window)
    table = window.findChild(QTableView, "documentTable")
    status = window.findChild(QLabel, "status")
    assert table is not None
    assert status is not None

    window._handle_document_activated(table.model().index(0, 0))
    assert "Only a document with Ready status" in status.text()

    ready_row = next(
        row
        for row in range(table.model().rowCount())
        if window._table_model.is_openable_at(row)
    )
    window._open_document_row(ready_row)
    assert "RuntimeError" in status.text()

    ready.write_bytes(b"changed after scan")
    window._open_document_row(ready_row)
    assert "invalid_signature" in status.text()
    window.close()


def test_window_requires_exactly_one_selected_pdf(
    qt_application: object,
) -> None:
    window = DocWeaveMainWindow()

    window.open_selected_document()

    status = window.findChild(QLabel, "status")
    assert status is not None
    assert status.text() == "Select one ready PDF to preview it safely."
    window.close()


def test_window_explains_missing_folder_and_invalid_result(
    qt_application: object,
) -> None:
    window = DocWeaveMainWindow()
    scan_button = window.findChild(QPushButton, "primaryButton")
    assert scan_button is not None
    assert not scan_button.isEnabled()

    window.start_scan()
    status = window.findChild(QLabel, "status")
    assert status is not None
    assert status.text() == "Choose a folder before starting a scan."

    window._handle_scan_completed(object())

    assert status.text() == (
        "Scan failed safely (InvalidScanResult). No files were changed."
    )
    window.close()


def test_window_fails_closed_for_invalid_progress_and_mismatched_result(
    tmp_path: Path,
    qt_application: object,
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    window = DocWeaveMainWindow()
    window.cancel_scan()
    window.set_authorized_root(tmp_path)
    window._workspace.start_scan()
    status = window.findChild(QLabel, "status")
    assert status is not None

    window._handle_scan_progress(object())
    assert "progress was invalid" in status.text()

    window._handle_scan_progress(ScanProgress(ScanPhase.DISCOVERY, 2, None))
    window._handle_scan_progress(ScanProgress(ScanPhase.DISCOVERY, 1, None))
    assert "progress was inconsistent" in status.text()

    window._handle_scan_completed(scan_authorized_root(other))
    assert window.workspace_snapshot.phase is WorkspacePhase.FAILED
    assert "ValueError" in status.text()
    window.close()


def test_folder_picker_authorizes_selected_directory(
    tmp_path: Path,
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = DocWeaveMainWindow()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args: str(tmp_path),
    )

    window._choose_folder()

    assert window.authorized_root == tmp_path.resolve()
    window.close()


def test_folder_picker_reports_invalid_selection_without_path_leak(
    tmp_path: Path,
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "private-missing"
    window = DocWeaveMainWindow()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args: str(missing),
    )

    window._choose_folder()

    status = window.findChild(QLabel, "status")
    assert status is not None
    assert status.text() == (
        "Folder authorization failed safely (FileNotFoundError). No files were changed."
    )
    assert str(missing) not in status.text()
    window.close()
