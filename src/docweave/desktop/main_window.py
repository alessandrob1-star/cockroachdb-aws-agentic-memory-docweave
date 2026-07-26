"""Primary DocWeave desktop discovery window."""

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from docweave.desktop.models import DocumentTableModel
from docweave.desktop.scan import (
    DesktopScanResult,
    ScanFunction,
    ScanWorker,
    scan_authorized_root,
)

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
QPushButton#secondaryButton {
    background: #ffffff;
    border: 1px solid #8da0ba;
    color: #243b5a;
}
QPushButton#primaryButton {
    background: #e76f51;
    border: 1px solid #e76f51;
    color: #ffffff;
}
QPushButton#primaryButton:disabled, QPushButton#secondaryButton:disabled {
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
"""


class DocWeaveMainWindow(QMainWindow):
    """Responsive, read-only first desktop surface."""

    scan_finished = Signal()

    def __init__(
        self,
        *,
        scan_function: ScanFunction = scan_authorized_root,
    ) -> None:
        super().__init__()
        self._scan_function = scan_function
        self._authorized_root: Path | None = None
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._table_model = DocumentTableModel()
        self._build_window()

    @property
    def authorized_root(self) -> Path | None:
        """Return the currently authorized local root."""
        return self._authorized_root

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
        self._authorized_root = resolved
        self._root_field.setText(str(resolved))
        self._scan_button.setEnabled(True)
        self._set_status(
            "Folder authorized for read-only discovery. No files will be changed."
        )

    @Slot()
    def start_scan(self) -> None:
        """Start one non-blocking scan of the explicitly authorized root."""
        if self._authorized_root is None:
            self._set_status("Choose a folder before starting a scan.")
            return
        if self.scan_in_progress:
            return

        self._table_model.clear()
        self._update_metrics(discovered=0, ready=0, attention=0)
        self._set_busy(True)
        self._set_status("Scanning in the background… You can keep using the window.")

        thread = QThread(self)
        worker = ScanWorker(self._authorized_root, self._scan_function)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._handle_scan_completed)
        worker.failed.connect(self._handle_scan_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._handle_thread_finished)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

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

    @Slot(str)
    def _handle_scan_failed(self, error_category: str) -> None:
        self._set_status(
            f"Scan failed safely ({error_category}). No files were changed."
        )

    @Slot()
    def _handle_thread_finished(self) -> None:
        self._scan_thread = None
        self._scan_worker = None
        self._set_busy(False)
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
        controls.addWidget(self._root_field, stretch=1)
        controls.addWidget(self._choose_button)
        controls.addWidget(self._scan_button)
        layout.addLayout(controls)

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
        layout.addWidget(title)
        layout.addWidget(subtitle)

        table = QTableView()
        table.setObjectName("documentTable")
        table.setModel(self._table_model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)
        table.setWordWrap(False)
        table.setAccessibleName("Discovered documents")
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 190)
        table.setColumnWidth(1, 340)
        table.setColumnWidth(2, 140)
        table.setColumnWidth(3, 100)
        table.setFont(QFont("Segoe UI", 9))
        layout.addWidget(table, stretch=1)
        return card

    def _set_busy(self, busy: bool) -> None:
        self._scan_button.setEnabled(not busy and self._authorized_root is not None)
        self._choose_button.setEnabled(not busy)
        self._root_field.setEnabled(not busy)

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
