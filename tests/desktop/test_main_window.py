from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QFileDialog, QLabel, QLineEdit, QPushButton, QTableView

from docweave.desktop.main_window import DocWeaveMainWindow
from docweave.desktop.scan import DesktopScanResult, scan_authorized_root


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
    def fail_scan(root: Path) -> DesktopScanResult:
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

    def controlled_scan(root: Path) -> DesktopScanResult:
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
