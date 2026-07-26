"""Minimal read-only PDF preview powered by Qt PDF."""

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_MINIMUM_ZOOM = 0.25
_MAXIMUM_ZOOM = 4.0
_ZOOM_STEP = 1.2


class PdfPreviewDialog(QDialog):
    """Display one validated local PDF without editing capabilities."""

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"DocWeave PDF preview - {path.name}")
        self.setMinimumSize(720, 560)
        self.resize(960, 760)

        self._document = QPdfDocument(self)
        self._view = QPdfView(self)
        self._view.setDocument(self._document)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        self._status_label = QLabel("Loading PDF preview…")
        self._status_label.setObjectName("previewStatus")
        self._status_label.setAccessibleName("PDF preview status")
        self._page_label = QLabel("Page — of —")
        self._page_label.setObjectName("pageStatus")
        self._page_label.setAccessibleName("Current PDF page")

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._status_label)
        layout.addWidget(self._view, stretch=1)

        self._document.statusChanged.connect(self._handle_document_status)
        self._document.pageCountChanged.connect(self._update_page_status)
        self._view.pageNavigator().currentPageChanged.connect(self._update_page_status)
        load_error = self._document.load(str(path))
        if load_error is not QPdfDocument.Error.None_:
            self._show_load_error(load_error)

    @property
    def document(self) -> QPdfDocument:
        """Return the owned Qt PDF document for state inspection."""
        return self._document

    @property
    def view(self) -> QPdfView:
        """Return the read-only PDF view for state inspection."""
        return self._view

    @Slot()
    def zoom_in(self) -> None:
        """Increase preview magnification within a bounded range."""
        self._set_custom_zoom(self._view.zoomFactor() * _ZOOM_STEP)

    @Slot()
    def zoom_out(self) -> None:
        """Decrease preview magnification within a bounded range."""
        self._set_custom_zoom(self._view.zoomFactor() / _ZOOM_STEP)

    @Slot()
    def fit_width(self) -> None:
        """Fit each page to the available preview width."""
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        title = QLabel("Read-only preview")
        title.setObjectName("sectionTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(self._page_label)

        zoom_out = QPushButton("-")
        zoom_out.setObjectName("previewZoomOut")
        zoom_out.setAccessibleName("Zoom out")
        zoom_out.clicked.connect(self.zoom_out)
        toolbar.addWidget(zoom_out)

        zoom_in = QPushButton("+")
        zoom_in.setObjectName("previewZoomIn")
        zoom_in.setAccessibleName("Zoom in")
        zoom_in.clicked.connect(self.zoom_in)
        toolbar.addWidget(zoom_in)

        fit_width = QPushButton("Fit width")
        fit_width.setObjectName("previewFitWidth")
        fit_width.clicked.connect(self.fit_width)
        toolbar.addWidget(fit_width)
        return toolbar

    @Slot(QPdfDocument.Status)
    def _handle_document_status(self, status: QPdfDocument.Status) -> None:
        if status is QPdfDocument.Status.Ready:
            self._status_label.setText("PDF ready. Preview is read only.")
            self._update_page_status()
            return
        if status is QPdfDocument.Status.Error:
            self._show_load_error(self._document.error())

    @Slot()
    @Slot(int)
    def _update_page_status(self, unused_value: int | None = None) -> None:
        del unused_value
        page_count = self._document.pageCount()
        if page_count < 1:
            self._page_label.setText("Page — of —")
            return
        current_page = self._view.pageNavigator().currentPage() + 1
        self._page_label.setText(f"Page {current_page} of {page_count}")

    def _set_custom_zoom(self, zoom_factor: float) -> None:
        bounded = max(_MINIMUM_ZOOM, min(_MAXIMUM_ZOOM, zoom_factor))
        self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._view.setZoomFactor(bounded)

    def _show_load_error(self, error: QPdfDocument.Error) -> None:
        self._status_label.setText(
            f"PDF preview failed safely ({error.name}). No files were changed."
        )


def create_pdf_preview(path: Path, parent: QWidget) -> QDialog:
    """Create the default internal PDF preview window."""
    return PdfPreviewDialog(path, parent)
