from pathlib import Path

from PySide6.QtCore import QEventLoop, QModelIndex, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtPdf import QPdfDocument, QPdfLink, QPdfLinkModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from docweave.desktop.link_security import ValidatedExternalLink
from docweave.desktop.preview import PdfPreviewDialog


def _write_valid_pdf(path: Path) -> None:
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(100, 100, "Synthetic preview test")
    painter.end()


def _write_pdf_with_external_link(path: Path) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 6 0 R >> >> "
            b"/Contents 4 0 R /Annots [5 0 R] >>"
        ),
        (
            b"<< /Length 46 >>\nstream\n"
            b"BT /F1 12 Tf 72 710 Td (Open example) Tj ET\n"
            b"endstream"
        ),
        (
            b"<< /Type /Annot /Subtype /Link /Rect [72 700 180 730] "
            b"/Border [0 0 1] "
            b"/A << /S /URI /URI (https://example.com/document) >> >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(pdf)


def _wait_until_terminal(dialog: PdfPreviewDialog) -> None:
    if dialog.document.status() in {
        QPdfDocument.Status.Ready,
        QPdfDocument.Status.Error,
    }:
        return
    loop = QEventLoop()
    dialog.document.statusChanged.connect(
        lambda status: (
            loop.quit()
            if status in {QPdfDocument.Status.Ready, QPdfDocument.Status.Error}
            else None
        )
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


def test_clicking_real_pdf_link_requires_confirmation_then_uses_browser(
    tmp_path: Path,
    qt_application: object,
) -> None:
    path = tmp_path / "linked.pdf"
    _write_pdf_with_external_link(path)
    calls: list[str] = []

    def confirm(
        unused_parent: object,
        link: ValidatedExternalLink,
    ) -> bool:
        del unused_parent
        calls.append(f"confirm:{link.host}")
        return True

    def open_url(url: QUrl) -> bool:
        calls.append(f"open:{url.toString()}")
        return True

    dialog = PdfPreviewDialog(
        path,
        link_confirmation=confirm,
        url_opener=open_url,
    )
    dialog.resize(900, 700)
    dialog.show()
    _wait_until_terminal(dialog)
    QTest.qWait(50)

    link_model = QPdfLinkModel(document=dialog.document, page=0)
    assert link_model.rowCount(QModelIndex()) == 1
    link = link_model.data(
        link_model.index(0),
        QPdfLinkModel.Role.Link.value,
    )
    assert isinstance(link, QPdfLink)
    assert link.url() == QUrl("https://example.com/document")
    link_rectangle = link.rectangles()[0]
    page, page_rectangle, points_scale = dialog.view._page_layout()[0]
    assert page == 0
    click_x = page_rectangle.x() + link_rectangle.center().x() * points_scale
    click_y = page_rectangle.y() + link_rectangle.center().y() * points_scale
    viewport_point = QPoint(
        round(click_x - dialog.view.horizontalScrollBar().value()),
        round(click_y - dialog.view.verticalScrollBar().value()),
    )
    detected_link = dialog.view.link_at_viewport_position(viewport_point)
    assert detected_link.url() == QUrl("https://example.com/document")

    QTest.mouseClick(
        dialog.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=viewport_point,
    )

    assert calls == [
        "confirm:example.com",
        "open:https://example.com/document",
    ]
    status = dialog.findChild(QLabel, "previewStatus")
    assert status is not None
    assert status.text() == "External link opened in the default browser."
    dialog.close()
