"""Read-only PDF preview with guarded hyperlink handling."""

from pathlib import Path

from PySide6.QtCore import (
    QPoint,
    QPointF,
    QRectF,
    QSize,
    QSizeF,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtPdf import QPdfDocument, QPdfLink, QPdfLinkModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from docweave.desktop.link_security import (
    ExternalLinkOutcome,
    LinkConfirmation,
    UrlOpener,
    request_external_pdf_link,
)

_MINIMUM_ZOOM = 0.25
_MAXIMUM_ZOOM = 4.0
_ZOOM_STEP = 1.2


class SecurePdfView(QPdfView):
    """Expose PDF links without allowing Qt to launch external URLs directly."""

    external_link_activated = Signal(QUrl)

    def __init__(self, parent: QWidget | None = None) -> None:
        if parent is None:
            super().__init__()
        else:
            super().__init__(parent)
        screen = QGuiApplication.primaryScreen()
        self._screen_points_scale = (
            screen.logicalDotsPerInch() / 72.0 if screen is not None else 1.0
        )
        self._link_model = QPdfLinkModel(self)

    def setDocument(self, document: QPdfDocument) -> None:
        """Keep the public view and hyperlink model on the same document."""
        super().setDocument(document)
        self._link_model.setDocument(document)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Route an explicit left-click to internal or guarded external navigation."""
        if event.button() is Qt.MouseButton.LeftButton:
            link = self._link_at_viewport_position(event.position())
            if not link.url().isEmpty():
                self.external_link_activated.emit(link.url())
                event.accept()
                return
            if link.isValid() and link.page() >= 0:
                self.pageNavigator().jump(
                    link.page(),
                    link.location(),
                    link.zoom(),
                )
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def link_at_viewport_position(self, position: QPoint | QPointF) -> QPdfLink:
        """Return the PDF link at a viewport point for tested UI integration."""
        return self._link_at_viewport_position(position)

    def _link_at_viewport_position(self, position: QPoint | QPointF) -> QPdfLink:
        document = self.document()
        if document is None or document.status() is not QPdfDocument.Status.Ready:
            return QPdfLink()

        document_position = QPointF(
            position.x() + self.horizontalScrollBar().value(),
            position.y() + self.verticalScrollBar().value(),
        )
        for page, page_rectangle, points_scale in self._page_layout():
            if not page_rectangle.contains(document_position):
                continue
            point_on_page = QPointF(
                (document_position.x() - page_rectangle.x()) / points_scale,
                (document_position.y() - page_rectangle.y()) / points_scale,
            )
            self._link_model.setPage(page)
            return self._link_model.linkAt(point_on_page)
        return QPdfLink()

    def _page_layout(self) -> list[tuple[int, QRectF, float]]:
        document = self.document()
        if document is None:
            return []

        margins = self.documentMargins()
        viewport_size = self.viewport().size()
        page_data: list[tuple[int, QSize, float]] = []
        start_page = (
            self.pageNavigator().currentPage()
            if self.pageMode() is QPdfView.PageMode.SinglePage
            else 0
        )
        end_page = (
            start_page + 1
            if self.pageMode() is QPdfView.PageMode.SinglePage
            else document.pageCount()
        )
        for page in range(start_page, end_page):
            point_size = document.pagePointSize(page)
            natural_size = QSizeF(
                point_size.width() * self._screen_points_scale,
                point_size.height() * self._screen_points_scale,
            ).toSize()
            page_size, points_scale = self._scaled_page(
                point_size,
                natural_size,
                viewport_size,
            )
            page_data.append((page, page_size, points_scale))

        maximum_page_width = max((item[1].width() for item in page_data), default=0)
        document_width = maximum_page_width + margins.left() + margins.right()
        layout: list[tuple[int, QRectF, float]] = []
        page_y = margins.top()
        for page, page_size, points_scale in page_data:
            available_document_width = max(document_width, viewport_size.width())
            page_x = (available_document_width - page_size.width()) // 2
            layout.append(
                (
                    page,
                    QRectF(page_x, page_y, page_size.width(), page_size.height()),
                    points_scale,
                )
            )
            page_y += page_size.height() + self.pageSpacing()
        return layout

    def _scaled_page(
        self,
        point_size: QSizeF,
        natural_size: QSize,
        viewport_size: QSize,
    ) -> tuple[QSize, float]:
        margins = self.documentMargins()
        if self.zoomMode() is QPdfView.ZoomMode.Custom:
            scale = self._screen_points_scale * self.zoomFactor()
            scaled_size = QSizeF(
                point_size.width() * scale,
                point_size.height() * scale,
            ).toSize()
            return (
                scaled_size,
                scale,
            )
        if self.zoomMode() is QPdfView.ZoomMode.FitToWidth:
            available_width = max(
                1,
                viewport_size.width() - margins.left() - margins.right(),
            )
            layout_scale = available_width / max(1, natural_size.width())
            return natural_size * layout_scale, self._screen_points_scale * layout_scale

        available = QSize(
            max(1, viewport_size.width() - margins.left() - margins.right()),
            max(1, viewport_size.height() - self.pageSpacing()),
        )
        scaled = natural_size.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        layout_scale = scaled.width() / max(1, natural_size.width())
        return scaled, self._screen_points_scale * layout_scale


class PdfPreviewDialog(QDialog):
    """Display one validated local PDF without editing capabilities."""

    def __init__(
        self,
        path: Path,
        parent: QWidget | None = None,
        *,
        link_confirmation: LinkConfirmation | None = None,
        url_opener: UrlOpener | None = None,
    ) -> None:
        super().__init__(parent)
        self._link_confirmation = link_confirmation
        self._url_opener = url_opener
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"DocWeave PDF preview - {path.name}")
        self.setMinimumSize(720, 560)
        self.resize(960, 760)

        self._document = QPdfDocument(self)
        self._view = SecurePdfView(self)
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
        self._view.external_link_activated.connect(self._open_external_link)
        load_error = self._document.load(str(path))
        if load_error is not QPdfDocument.Error.None_:
            self._show_load_error(load_error)

    @property
    def document(self) -> QPdfDocument:
        """Return the owned Qt PDF document for state inspection."""
        return self._document

    @property
    def view(self) -> SecurePdfView:
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

    @Slot(QUrl)
    def _open_external_link(self, url: QUrl) -> None:
        outcome = request_external_pdf_link(
            url,
            self,
            confirm=self._link_confirmation,
            opener=self._url_opener,
        )
        messages = {
            ExternalLinkOutcome.BLOCKED: (
                "External link blocked by DocWeave safety policy."
            ),
            ExternalLinkOutcome.CANCELLED: "External link cancelled.",
            ExternalLinkOutcome.FAILED: (
                "The default browser could not open the external link."
            ),
            ExternalLinkOutcome.OPENED: "External link opened in the default browser.",
        }
        self._status_label.setText(messages[outcome])

    def _show_load_error(self, error: QPdfDocument.Error) -> None:
        self._status_label.setText(
            f"PDF preview failed safely ({error.name}). No files were changed."
        )


def create_pdf_preview(path: Path, parent: QWidget) -> QDialog:
    """Create the default internal PDF preview window."""
    return PdfPreviewDialog(path, parent)
