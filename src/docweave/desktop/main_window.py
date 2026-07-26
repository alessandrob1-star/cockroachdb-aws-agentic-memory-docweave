"""Primary DocWeave desktop discovery window."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QItemSelection, QModelIndex, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from docweave.desktop.models import DocumentTableModel
from docweave.desktop.opening import PdfOpenValidationError, validate_pdf_for_open
from docweave.desktop.preview import create_pdf_preview
from docweave.desktop.scan import (
    DesktopScanResult,
    ScanFunction,
    ScanPhase,
    ScanProgress,
    ScanWorker,
    scan_authorized_root,
)
from docweave.desktop.workspace import (
    DesktopWorkspaceSession,
    WorkspacePhase,
    WorkspaceSnapshot,
)

PreviewFactory = Callable[[Path, QWidget], QDialog]

_WINDOW_STYLESHEET = """
QMainWindow, QWidget#central {
    background: #f4f6f8;
    color: #18212f;
}
QFrame#header {
    background: #14213d;
    border: none;
}
QLabel#brand {
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
}
QLabel#tagline {
    color: #b9c7df;
    font-size: 12px;
}
QFrame#contentCard, QFrame#metricCard {
    background: #ffffff;
    border: 1px solid #dce2ea;
    border-radius: 10px;
}
QLabel#sectionTitle {
    color: #18212f;
    font-size: 17px;
    font-weight: 600;
}
QLabel#muted, QLabel#metricLabel {
    color: #5b6778;
}
QLabel#metricValue {
    color: #14213d;
    font-size: 24px;
    font-weight: 700;
}
QLineEdit {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #18212f;
    padding: 8px;
}
QPushButton {
    border-radius: 6px;
    font-weight: 600;
    padding: 9px 15px;
}
QPushButton#secondaryButton, QPushButton#openPdfButton {
    background: #ffffff;
    border: 1px solid #8da0ba;
    color: #243b5a;
}
QPushButton#primaryButton {
    background: #e76f51;
    border: 1px solid #e76f51;
    color: #ffffff;
}
QPushButton#primaryButton:disabled, QPushButton#secondaryButton:disabled,
QPushButton#openPdfButton:disabled {
    background: #d8dee8;
    border-color: #d8dee8;
    color: #758195;
}
QTableView {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #dce2ea;
    border-radius: 7px;
    color: #18212f;
    gridline-color: #edf0f4;
    selection-background-color: #dbeafe;
    selection-color: #18212f;
}
QHeaderView::section {
    background: #eef2f7;
    border: none;
    border-bottom: 1px solid #d6dde7;
    color: #334155;
    font-weight: 600;
    padding: 8px;
}
QLabel#status {
    background: #e8f0fb;
    border-radius: 6px;
    color: #24466f;
    padding: 9px 12px;
}
QProgressBar {
    background: #e7ebf0;
    border: none;
    border-radius: 4px;
    color: #24466f;
    min-height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background: #2a9d8f;
    border-radius: 4px;
}
QLabel#selectionStatus {
    color: #24466f;
    font-weight: 600;
}
"""


class DocWeaveMainWindow(QMainWindow):
    """Responsive, read-only first desktop surface."""

    scan_finished = Signal()

    def __init__(
        self,
        *,
        scan_function: ScanFunction = scan_authorized_root,
        preview_factory: PreviewFactory = create_pdf_preview,
    ) -> None:
        super().__init__()
        self._scan_function = scan_function
        self._preview_factory = preview_factory
        self._preview_dialogs: set[QDialog] = set()
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._table_model = DocumentTableModel()
        self._workspace = DesktopWorkspaceSession()
        self._build_window()

    @property
    def authorized_root(self) -> Path | None:
        """Return the currently authorized local root."""
        return self._workspace.snapshot.authorized_root

    @property
    def workspace_snapshot(self) -> WorkspaceSnapshot:
        """Return the current non-persistent desktop workspace state."""
        return self._workspace.snapshot

    @property
    def scan_in_progress(self) -> bool:
        """Return whether a background scan thread is active."""
        return self._scan_thread is not None and self._scan_thread.isRunning()

    def set_authorized_root(self, root: Path) -> None:
        """Authorize one existing directory for this local session."""
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError("authorized root must be a directory")
        if self.scan_in_progress:
            raise RuntimeError("authorized root cannot change during a scan")
        self._workspace.authorize(resolved)
        self._table_model.clear()
        self._table.clearSelection()
        self._update_selection_status()
        self._update_metrics(discovered=0, ready=0, attention=0)
        self._root_field.setText(str(resolved))
        self._scan_button.setEnabled(True)
        self._set_status(
            "Folder authorized for read-only discovery. No files will be changed."
        )

    @Slot()
    def start_scan(self) -> None:
        """Start one non-blocking scan of the explicitly authorized root."""
        authorized_root = self.authorized_root
        if authorized_root is None:
            self._set_status("Choose a folder before starting a scan.")
            return
        if self.scan_in_progress:
            return

        self._table_model.clear()
        self._table.clearSelection()
        self._workspace.start_scan()
        self._update_metrics(discovered=0, ready=0, attention=0)
        self._set_busy(True)
        self._set_status("Scanning in the background… You can keep using the window.")

        thread = QThread(self)
        worker = ScanWorker(authorized_root, self._scan_function)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(self._handle_scan_progress)
        worker.completed.connect(self._handle_scan_completed)
        worker.cancelled.connect(self._handle_scan_cancelled)
        worker.failed.connect(self._handle_scan_failed)
        worker.completed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._handle_thread_finished)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    @Slot()
    def cancel_scan(self) -> None:
        """Request cooperative cancellation without publishing partial state."""
        if not self.scan_in_progress or self._scan_worker is None:
            return
        self._workspace.request_cancellation()
        self._scan_worker.request_cancellation()
        self._cancel_button.setEnabled(False)
        self._set_status(
            "Cancelling at the next safe file boundary… No partial result "
            "will be published."
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Prevent unsafe thread destruction during an active scan."""
        if self.scan_in_progress:
            self._set_status(
                "Scan still running. Wait for completion before closing DocWeave."
            )
            event.ignore()
            return
        event.accept()

    @Slot(object)
    def _handle_scan_completed(self, raw_result: object) -> None:
        if not isinstance(raw_result, DesktopScanResult):
            self._handle_scan_failed("InvalidScanResult")
            return
        try:
            self._workspace.complete(raw_result)
        except (RuntimeError, ValueError) as error:
            self._handle_scan_failed(error.__class__.__name__)
            return
        self._table_model.replace_records(raw_result.intake.records)
        self._update_metrics(
            discovered=len(raw_result.discovery.files),
            ready=raw_result.intake.ready_count,
            attention=raw_result.attention_count,
        )
        suffix = (
            " The 10,000-file discovery limit was reached."
            if raw_result.discovery.limit_reached
            else ""
        )
        self._set_status(
            f"Scan complete: {len(raw_result.discovery.files)} files inspected."
            f"{suffix} No files were changed."
        )

    @Slot(object)
    def _handle_scan_progress(self, raw_progress: object) -> None:
        if not isinstance(raw_progress, ScanProgress):
            self.cancel_scan()
            self._set_status(
                "Scan progress was invalid and cancellation was requested safely."
            )
            return
        try:
            self._workspace.record_progress(raw_progress)
        except (RuntimeError, ValueError):
            self.cancel_scan()
            self._set_status(
                "Scan progress was inconsistent and cancellation was requested safely."
            )
            return
        if raw_progress.phase is ScanPhase.DISCOVERY:
            self._progress_bar.setRange(0, 0)
            self._discovered_value.setText(str(raw_progress.completed))
            self._set_status(
                f"Discovering files… {raw_progress.completed} observed. "
                "No files are being changed."
            )
            return
        total = raw_progress.total or 0
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(raw_progress.completed)
        self._discovered_value.setText(str(total))
        self._set_status(
            "Inspecting PDF signatures and fingerprints… "
            f"{raw_progress.completed} of {total}. No files are being changed."
        )

    @Slot()
    def _handle_scan_cancelled(self) -> None:
        self._workspace.cancel()
        self._table_model.clear()
        self._update_metrics(discovered=0, ready=0, attention=0)
        self._set_status(
            "Scan cancelled safely. Partial results were discarded and no files "
            "were changed."
        )

    @Slot(str)
    def _handle_scan_failed(self, error_category: str) -> None:
        if self.workspace_snapshot.phase in {
            WorkspacePhase.SCANNING,
            WorkspacePhase.CANCELLING,
        }:
            self._workspace.fail(error_category)
        self._set_status(
            f"Scan failed safely ({error_category}). No files were changed."
        )

    @Slot()
    def _handle_thread_finished(self) -> None:
        self._scan_thread = None
        self._scan_worker = None
        self._set_busy(False)
        self._progress_bar.setVisible(False)
        self.scan_finished.emit()

    @Slot()
    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose an authorized document folder",
        )
        if selected:
            try:
                self.set_authorized_root(Path(selected))
            except (OSError, RuntimeError) as error:
                self._set_status(
                    "Folder authorization failed safely "
                    f"({error.__class__.__name__}). No files were changed."
                )

    def _build_window(self) -> None:
        self.setWindowTitle("DocWeave — Local document discovery")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)
        self.setStyleSheet(_WINDOW_STYLESHEET)

        central = QWidget()
        central.setObjectName("central")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 24, 28, 26)
        body_layout.setSpacing(18)
        body_layout.addWidget(self._build_workspace_card())
        body_layout.addLayout(self._build_metrics())
        body_layout.addWidget(self._build_documents_card(), stretch=1)
        root_layout.addWidget(body, stretch=1)
        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 16, 28, 16)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        brand = QLabel("DocWeave")
        brand.setObjectName("brand")
        tagline = QLabel("Human-governed document intelligence")
        tagline.setObjectName("tagline")
        title_stack.addWidget(brand)
        title_stack.addWidget(tagline)
        layout.addLayout(title_stack)
        layout.addStretch()
        mode = QLabel("LOCAL DISCOVERY · READ ONLY")
        mode.setObjectName("tagline")
        mode.setAccessibleName("Current mode: local discovery, read only")
        layout.addWidget(mode)
        return header

    def _build_workspace_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("contentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("Authorized workspace folder")
        title.setObjectName("sectionTitle")
        description = QLabel(
            "Choose one folder to discover PDF documents recursively. "
            "This preview never renames, copies, moves, or uploads files."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)

        controls = QHBoxLayout()
        self._root_field = QLineEdit()
        self._root_field.setObjectName("authorizedRoot")
        self._root_field.setReadOnly(True)
        self._root_field.setPlaceholderText("No folder selected")
        self._root_field.setAccessibleName("Authorized workspace folder")
        self._choose_button = QPushButton("Choose folder")
        self._choose_button.setObjectName("secondaryButton")
        self._choose_button.setAccessibleDescription(
            "Select the only local folder DocWeave may scan"
        )
        self._choose_button.clicked.connect(self._choose_folder)
        self._scan_button = QPushButton("Scan documents")
        self._scan_button.setObjectName("primaryButton")
        self._scan_button.setEnabled(False)
        self._scan_button.clicked.connect(self.start_scan)
        self._cancel_button = QPushButton("Cancel scan")
        self._cancel_button.setObjectName("secondaryButton")
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self.cancel_scan)
        controls.addWidget(self._root_field, stretch=1)
        controls.addWidget(self._choose_button)
        controls.addWidget(self._scan_button)
        controls.addWidget(self._cancel_button)
        layout.addLayout(controls)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("scanProgress")
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setAccessibleName("Document scan progress")
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel(
            "Choose a folder to begin. No files will be changed."
        )
        self._status_label.setObjectName("status")
        self._status_label.setWordWrap(True)
        self._status_label.setAccessibleName("Discovery status")
        layout.addWidget(self._status_label)
        return card

    def _build_metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)
        self._discovered_value = self._metric_card(layout, "Discovered")
        self._ready_value = self._metric_card(layout, "Ready")
        self._attention_value = self._metric_card(layout, "Needs attention")
        return layout

    def _metric_card(self, layout: QHBoxLayout, label_text: str) -> QLabel:
        card = QFrame()
        card.setObjectName("metricCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 13, 18, 13)
        label = QLabel(label_text)
        label.setObjectName("metricLabel")
        value = QLabel("0")
        value.setObjectName("metricValue")
        value.setAccessibleName(f"{label_text} document count")
        card_layout.addWidget(label)
        card_layout.addWidget(value)
        layout.addWidget(card)
        return value

    def _build_documents_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("contentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)
        title = QLabel("Documents")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Deterministic discovery and PDF signature checks only. "
            "Content analysis is not active yet."
        )
        subtitle.setObjectName("muted")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        self._selection_status = QLabel("0 selected")
        self._selection_status.setObjectName("selectionStatus")
        self._selection_status.setAccessibleName("Selected document count")
        title_row.addWidget(self._selection_status)
        self._open_button = QPushButton("Preview PDF")
        self._open_button.setObjectName("openPdfButton")
        self._open_button.setEnabled(False)
        self._open_button.setAccessibleDescription(
            "Preview the selected ready PDF inside DocWeave"
        )
        self._open_button.clicked.connect(self.open_selected_document)
        title_row.addWidget(self._open_button)
        layout.addLayout(title_row)
        layout.addWidget(subtitle)

        self._table = QTableView()
        self._table.setObjectName("documentTable")
        self._table.setModel(self._table_model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)
        self._table.setWordWrap(False)
        self._table.setAccessibleName("Discovered documents")
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 190)
        self._table.setColumnWidth(1, 340)
        self._table.setColumnWidth(2, 140)
        self._table.setColumnWidth(3, 100)
        self._table.setFont(QFont("Segoe UI", 9))
        self._table.selectionModel().selectionChanged.connect(
            self._handle_selection_changed
        )
        self._table.doubleClicked.connect(self._handle_document_activated)
        layout.addWidget(self._table, stretch=1)
        return card

    def _set_busy(self, busy: bool) -> None:
        self._scan_button.setEnabled(not busy and self.authorized_root is not None)
        self._choose_button.setEnabled(not busy)
        self._root_field.setEnabled(not busy)
        self._cancel_button.setVisible(busy)
        self._cancel_button.setEnabled(busy)
        self._progress_bar.setVisible(busy)
        if busy:
            self._progress_bar.setRange(0, 0)

    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setToolTip(message)

    def _update_metrics(
        self,
        *,
        discovered: int,
        ready: int,
        attention: int,
    ) -> None:
        self._discovered_value.setText(str(discovered))
        self._ready_value.setText(str(ready))
        self._attention_value.setText(str(attention))

    @Slot(QItemSelection, QItemSelection)
    def _handle_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        del selected, deselected
        selected_rows = self._table.selectionModel().selectedRows()
        keys = frozenset(
            key
            for index in selected_rows
            if (key := self._table_model.comparison_key_at(index.row())) is not None
        )
        self._workspace.select_documents(keys)
        self._update_selection_status()

    def _update_selection_status(self) -> None:
        count = len(self.workspace_snapshot.selected_document_keys)
        self._selection_status.setText(f"{count} selected")
        selected_rows = self._table.selectionModel().selectedRows()
        self._open_button.setEnabled(
            len(selected_rows) == 1
            and self._table_model.is_openable_at(selected_rows[0].row())
        )

    @Slot()
    def open_selected_document(self) -> None:
        """Preview one selected ready PDF after current-state validation."""
        selected_rows = self._table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            self._set_status("Select one ready PDF to preview it safely.")
            return
        self._open_document_row(selected_rows[0].row())

    @Slot(QModelIndex)
    def _handle_document_activated(self, index: QModelIndex) -> None:
        self._open_document_row(index.row())

    def _open_document_row(self, row: int) -> None:
        if not self._table_model.is_openable_at(row):
            self._set_status(
                "Only a document with Ready status can be previewed safely."
            )
            return
        path = self._table_model.absolute_path_at(row)
        root = self.authorized_root
        if path is None or root is None:
            self._set_status("The document is no longer available to preview safely.")
            return
        try:
            validated_path = validate_pdf_for_open(path, root)
        except PdfOpenValidationError as error:
            self._set_status(
                "PDF preview was blocked safely "
                f"({error.category.value}). No files were changed."
            )
            return
        try:
            dialog = self._preview_factory(validated_path, self)
        except Exception as error:
            self._set_status(
                "PDF preview failed safely "
                f"({error.__class__.__name__}). No files were changed."
            )
            return
        self._preview_dialogs.add(dialog)
        dialog.finished.connect(
            lambda unused_result, active_dialog=dialog: self._preview_dialogs.discard(
                active_dialog
            )
        )
        dialog.show()
        self._set_status("PDF preview opened inside DocWeave. No files were changed.")
