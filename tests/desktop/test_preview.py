from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QLabel

from docweave.desktop.preview import PdfPreviewDialog


def _write_valid_pdf(path: Path) -> None:
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(100, 100, "Synthetic preview test")
    painter.end()


def _wait_until_terminal(dialog: PdfPreviewDialog) -> None:
    if dialog.document.status() in {
        QPdfDocument.Status.Ready,
        QPdfDocument.Status.Error,
    }:
        return
    loop = QEventLoop()
    dialog.document.statusChanged.connect(
        lambda status: loop.quit()
        if status in {QPdfDocument.Status.Ready, QPdfDocument.Status.Error}
        else None
    )
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()


def test_preview_loads_valid_pdf_with_multi_page_scroll_and_zoom(
    tmp_path: Path,
    qt_application: object,
) -> None:
    path = tmp_path / "invoice.pdf"
    _write_valid_pdf(path)
    dialog = PdfPreviewDialog(path)
    _wait_until_terminal(dialog)

    assert dialog.document.status() is QPdfDocument.Status.Ready
    assert dialog.document.pageCount() == 1
    assert dialog.view.pageMode() is QPdfView.PageMode.MultiPage
    assert dialog.view.zoomMode() is QPdfView.ZoomMode.FitToWidth
    page_status = dialog.findChild(QLabel, "pageStatus")
    assert page_status is not None
    assert page_status.text() == "Page 1 of 1"

    dialog.zoom_in()
    assert dialog.view.zoomMode() is QPdfView.ZoomMode.Custom
    zoomed = dialog.view.zoomFactor()
    dialog.zoom_out()
    assert dialog.view.zoomFactor() < zoomed
    dialog.fit_width()
    assert dialog.view.zoomMode() is QPdfView.ZoomMode.FitToWidth
    dialog.close()


def test_preview_reports_malformed_pdf_without_private_path(
    tmp_path: Path,
    qt_application: object,
) -> None:
    path = tmp_path / "private-name.pdf"
    path.write_bytes(b"%PDF-not-a-complete-document")
    dialog = PdfPreviewDialog(path)
    _wait_until_terminal(dialog)

    status = dialog.findChild(QLabel, "previewStatus")
    assert status is not None
    assert "failed safely" in status.text()
    assert str(tmp_path) not in status.text()
    dialog.close()
