from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from docweave.desktop.cockpit import CockpitWindow
from docweave.desktop.scan import DesktopScanResult
from docweave.discovery import DiscoveredFile, DiscoveryResult, DiscoveryStatus
from docweave.intake import IntakeRecord, IntakeResult, IntakeStatus


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


def test_cockpit_starts_with_definitive_local_surface(
    qt_application: object,
) -> None:
    window = CockpitWindow()

    assert window.windowTitle() == "DocWeave Cockpit"
    assert window.left.table.rowCount() == 0
    assert "CockroachDB      Not connected" in window.console.status_text.text()
    assert "Bedrock          Not connected" in window.console.status_text.text()

    window.close()


def test_cockpit_scans_synthetic_pdfs_and_raises_central_preview(
    qt_application: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = Path("pdf_sintetici").resolve(strict=True)
    window = CockpitWindow()
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

    window.close()
