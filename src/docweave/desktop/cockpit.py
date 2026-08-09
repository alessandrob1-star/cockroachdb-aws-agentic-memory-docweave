# v31 glossy black bezel
"""
DocWeave cockpit UI — absolute positioning rewrite.

Features:
- frameless transparent window
- no outer rectangular shell
- two fixed side screens with outward-leaning silhouettes
- dominant central PDF preview
- high cockpit console
- absolute positioning via resizeEvent()
- click on a PDF row to open the central screen
- close/minimize controls embedded in the left screen

Run:
    py docweave_cockpit_absolute.py

Requires:
    py -m pip install PySide6
"""
# mypy: ignore-errors
# ruff: noqa: PLR0915, PLR2004, RUF001, B905, I001, F401

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QThread,
    Qt,
    QUrl,
    Signal,
    Slot,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QLinearGradient,
    QRadialGradient,
    QBrush,
    QCloseEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QTransform,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeIntegrationSnapshot,
    runtime_integration_snapshot,
)
from docweave.analysis import BedrockGatewayError
from docweave.classification_cli import (
    ClassificationCommandResult,
    classify_pdf_once,
)
from docweave.desktop.link_security import (
    ExternalLinkOutcome,
    request_external_pdf_link,
)
from docweave.desktop.folder_memory import FolderMemory, QtFolderMemory
from docweave.desktop.opening import PdfOpenValidationError, validate_pdf_for_open
from docweave.desktop.preview import SecurePdfView
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
)
from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.core.paths import path_comparison_key
from docweave.intake import IntakeStatus
from docweave.memory_evidence_report import (
    MemoryEvidenceReport,
    collect_memory_evidence,
)
from docweave.classification_cli import ClassificationPipelineError
from docweave.review_cli import (
    ReviewDecisionCommandInput,
    ReviewDecisionCommandResult,
    persist_review_decision,
)
from docweave.operations import (
    AppendOnlyAuditTrail,
    InMemoryReviewDecisionLedger,
    MassOperationCandidate,
    MassOperationMode,
    MassOperationPreviewItem,
    ProposalReviewDecisionRequest,
    RestoreAuditContext,
    ResultDisposition,
    ReviewDecisionAction,
    RestoreExecutionStatus,
    build_mass_operation_preview,
    append_restore_approval_audit_event,
    append_restore_execution_audit_event,
    approve_restore_plan,
    create_proposal_review_decision_from_fingerprint,
    execute_restore_operation,
    plan_restore_operation,
    validate_proposal_review_decision_fingerprint,
)
from docweave.operations.results import OperationResultRecord
from docweave.operations.approval import approve_operation_plan
from docweave.operations.execution import (
    ExecutionReason,
    ExecutionStatus,
    execute_file_operation,
)
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationReason,
    FileOperationRequest,
    FileOperationStatus,
    plan_file_operation,
)
from docweave.runtime_preflight import (
    PreflightCheck,
    PreflightState,
    RuntimePreflightReport,
    run_preflight,
)


SURFACE = QColor("#081E19")
SURFACE_ALT = QColor("#0C2A23")
EDGE = QColor("#59C6A2")
EDGE_SOFT = QColor(89, 198, 162, 72)
TEXT = QColor("#EAF5F1")
MUTED = QColor("#8FAAA1")
ACCENT = QColor("#67D8B0")
WARNING = QColor("#E1AB4D")
DEFAULT_DEMO_DOCUMENT_FOLDER = Path(__file__).parents[3] / "pdf_sintetici"


@dataclass(frozen=True)
class CockpitLineagePreview:
    """Human-visible file lineage state prepared before any file mutation."""

    action: str
    original_relative_path: str
    previous_relative_path: str
    next_relative_path: str
    original_directory: str
    original_filename: str
    next_directory: str
    next_filename: str
    plan_fingerprint: str


@dataclass(frozen=True)
class Document:
    name: str
    category: str
    pages: str
    status: str
    path: Path | None = None
    proposed_destination: str | None = None
    proposed_operation_action: str | None = None
    document_id: str | None = None
    proposal_id: str | None = None
    proposal_fingerprint: str | None = None
    review_decision_id: str | None = None
    lineage_preview: CockpitLineagePreview | None = None


@dataclass(frozen=True)
class ClassificationBatchItem:
    """One ready PDF scheduled for user-initiated classification."""

    row: int
    source_path: Path


@dataclass(frozen=True)
class ClassificationBatchProgress:
    """One completed classification item from a cockpit batch."""

    row: int
    source_path: Path
    result: ClassificationCommandResult
    completed: int
    total: int


@dataclass(frozen=True)
class ClassificationBatchFailure:
    """One failed classification item from a cockpit batch."""

    row: int
    source_path: Path
    error_category: str
    attempted: int
    completed: int
    failed: int
    total: int


@dataclass(frozen=True)
class ClassificationBatchSummary:
    """Terminal state for a cockpit classification batch."""

    completed: int
    failed: int
    total: int
    last_error_category: str | None = None


DOCUMENTS: list[Document] = []
ClassificationFunction = Callable[[Path, Path], ClassificationCommandResult]
ReviewDecisionFunction = Callable[
    [ReviewDecisionCommandInput],
    ReviewDecisionCommandResult,
]
RuntimePreflightFunction = Callable[[], RuntimePreflightReport]
MemoryEvidenceFunction = Callable[[], MemoryEvidenceReport]
BedrockAuthProbeFunction = Callable[[], bool]
BedrockLoginLauncher = Callable[[], bool]


BEDROCK_LOGIN_HELP_URL = (
    "https://docs.aws.amazon.com/signin/latest/userguide/command-line-sign-in.html"
)


def probe_bedrock_aws_session() -> bool:
    """Return whether local AWS credentials are usable without exposing identity."""
    aws_executable = shutil.which("aws")
    if aws_executable is None:
        return False
    try:
        completed = subprocess.run(  # noqa: S603
            [aws_executable, "sts", "get-caller-identity", "--output", "json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def launch_aws_login() -> bool:
    """Start AWS CLI browser login as an explicit user action."""
    aws_executable = shutil.which("aws")
    if aws_executable is None:
        QDesktopServices.openUrl(QUrl(BEDROCK_LOGIN_HELP_URL))
        return False
    creation_flags = 0
    if sys.platform.startswith("win"):
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(  # noqa: S603
            [aws_executable, "login"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except (FileNotFoundError, OSError):
        QDesktopServices.openUrl(QUrl(BEDROCK_LOGIN_HELP_URL))
        return False
    return True


def classify_pdf_for_cockpit(
    source_path: Path,
    authorized_root: Path,
) -> ClassificationCommandResult:
    """Run the configured classification command with positional UI inputs."""
    return classify_pdf_once(source_path, authorized_root=authorized_root)


class ClassificationWorker(QObject):
    """Run a configured classification batch outside the Qt user-interface thread."""

    progressed = Signal(object)
    item_failed = Signal(object)
    completed = Signal(object)

    def __init__(
        self,
        items: tuple[ClassificationBatchItem, ...],
        authorized_root: Path,
        classification_function: ClassificationFunction,
    ) -> None:
        super().__init__()
        self._items = items
        self._authorized_root = authorized_root
        self._classification_function = classification_function

    @Slot()
    def run(self) -> None:
        """Emit sanitized per-item progress and one terminal summary."""
        total = len(self._items)
        completed = 0
        failed = 0
        last_error_category: str | None = None
        for attempted, item in enumerate(self._items, start=1):
            try:
                result = self._classification_function(
                    item.source_path,
                    self._authorized_root,
                )
            except RuntimeConfigurationError as error:
                failed += 1
                last_error_category = f"configuration:{error.code.value}"
                self.item_failed.emit(
                    ClassificationBatchFailure(
                        row=item.row,
                        source_path=item.source_path,
                        error_category=last_error_category,
                        attempted=attempted,
                        completed=completed,
                        failed=failed,
                        total=total,
                    )
                )
                continue
            except ClassificationPipelineError as error:
                failed += 1
                last_error_category = (
                    f"classification:{error.code.value}:{error.extraction_status.value}"
                )
                self.item_failed.emit(
                    ClassificationBatchFailure(
                        row=item.row,
                        source_path=item.source_path,
                        error_category=last_error_category,
                        attempted=attempted,
                        completed=completed,
                        failed=failed,
                        total=total,
                    )
                )
                continue
            except BedrockGatewayError as error:
                failed += 1
                last_error_category = f"bedrock:{error.code.value}"
                self.item_failed.emit(
                    ClassificationBatchFailure(
                        row=item.row,
                        source_path=item.source_path,
                        error_category=last_error_category,
                        attempted=attempted,
                        completed=completed,
                        failed=failed,
                        total=total,
                    )
                )
                continue
            except Exception as error:
                failed += 1
                last_error_category = error.__class__.__name__
                self.item_failed.emit(
                    ClassificationBatchFailure(
                        row=item.row,
                        source_path=item.source_path,
                        error_category=last_error_category,
                        attempted=attempted,
                        completed=completed,
                        failed=failed,
                        total=total,
                    )
                )
                continue
            completed += 1
            self.progressed.emit(
                ClassificationBatchProgress(
                    row=item.row,
                    source_path=item.source_path,
                    result=result,
                    completed=completed,
                    total=total,
                )
            )
        self.completed.emit(
            ClassificationBatchSummary(
                completed=completed,
                failed=failed,
                total=total,
                last_error_category=last_error_category,
            )
        )


class ShapeWidget(QWidget):
    """Base class for clipped, independently positioned cockpit parts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(70)
        self._pulse_timer.timeout.connect(self._advance_pulse)
        self._pulse_timer.start()

    def _advance_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 1) % 40
        self.update()

    def shape_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        return path

    def update_mask(self) -> None:
        polygon = self.shape_path().toFillPolygon().toPolygon()
        self.setMask(QRegion(polygon))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_mask()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = self.shape_path()
        bounds = path.boundingRect()

        # Rear chassis depth.
        chassis_transform = QTransform()
        chassis_transform.translate(8.0, 10.0)
        chassis_path = chassis_transform.map(path)

        painter.setPen(QPen(QColor(0, 0, 0, 125), 18))
        painter.drawPath(chassis_path)

        # Outer glass frame.
        glass = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        glass.setColorAt(0.00, QColor(100, 225, 185, 52))
        glass.setColorAt(0.22, QColor(62, 175, 140, 38))
        glass.setColorAt(0.62, QColor(24, 92, 73, 28))
        glass.setColorAt(1.00, QColor(8, 36, 29, 24))
        painter.fillPath(path, QBrush(glass))

        # Inner carbon panel: exact scaled copy of the outer silhouette.
        # This preserves every cut corner and angled edge.
        inner_transform = QTransform()
        inner_transform.translate(bounds.center().x(), bounds.center().y())
        inner_transform.scale(0.89, 0.87)
        inner_transform.translate(-bounds.center().x(), -bounds.center().y())
        inner_path = inner_transform.map(path)
        inner = inner_path.boundingRect()

        carbon_base = QLinearGradient(inner.topLeft(), inner.bottomRight())
        carbon_base.setColorAt(0.00, QColor(30, 34, 33, 255))
        carbon_base.setColorAt(0.45, QColor(18, 22, 21, 255))
        carbon_base.setColorAt(1.00, QColor(7, 10, 10, 255))
        painter.fillPath(inner_path, QBrush(carbon_base))

        # Carbon-fiber weave texture.
        painter.save()
        painter.setClipPath(inner_path)

        tile = 9
        for y in range(int(inner.top()), int(inner.bottom()) + tile, tile):
            for x in range(int(inner.left()), int(inner.right()) + tile, tile):
                alt = ((x // tile) + (y // tile)) % 2

                if alt == 0:
                    c1 = QColor(58, 64, 62, 48)
                    c2 = QColor(8, 12, 11, 58)
                else:
                    c1 = QColor(18, 24, 22, 46)
                    c2 = QColor(70, 78, 75, 36)

                painter.setPen(QPen(c1, 1.0))
                painter.drawLine(x, y + tile, x + tile, y)

                painter.setPen(QPen(c2, 0.55))
                painter.drawLine(x - tile * 0.35, y + tile, x + tile * 0.65, y)

        # Subtle diagonal sheen on carbon.
        sheen = QLinearGradient(
            inner.left(),
            inner.top(),
            inner.right(),
            inner.bottom(),
        )
        sheen.setColorAt(0.00, QColor(255, 255, 255, 8))
        sheen.setColorAt(0.35, QColor(120, 255, 210, 8))
        sheen.setColorAt(0.65, QColor(0, 0, 0, 0))
        sheen.setColorAt(1.00, QColor(0, 0, 0, 22))
        painter.fillPath(inner_path, QBrush(sheen))

        painter.restore()

        # Recessed bevel between glass and carbon.
        # Light catches the upper/left edge, while lower/right edges fall into shadow.
        bevel_outer = inner_path

        inner_bevel_transform = QTransform()
        inner_bevel_transform.translate(inner.center().x(), inner.center().y())
        inner_bevel_transform.scale(0.975, 0.970)
        inner_bevel_transform.translate(-inner.center().x(), -inner.center().y())
        bevel_inner = inner_bevel_transform.map(inner_path)

        bevel_ring = bevel_outer.subtracted(bevel_inner)

        bevel_black = QColor(8, 8, 10, 255)
        painter.fillPath(bevel_ring, QBrush(bevel_black))
        painter.setPen(QPen(QColor(42, 42, 46, 210), 0.8))
        painter.drawPath(bevel_outer)
        painter.setPen(QPen(QColor(0, 0, 0, 245), 1.2))
        painter.drawPath(bevel_inner)

        # Top bevel / glass reflection.
        top_face = QPainterPath()
        top_face.moveTo(bounds.left() + bounds.width() * 0.06, bounds.top() + 4)
        top_face.lineTo(bounds.right() - bounds.width() * 0.06, bounds.top() + 4)
        top_face.lineTo(
            bounds.right() - bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.12,
        )
        top_face.lineTo(
            bounds.left() + bounds.width() * 0.10, bounds.top() + bounds.height() * 0.12
        )
        top_face.closeSubpath()

        top_grad = QLinearGradient(
            0,
            bounds.top(),
            0,
            bounds.top() + bounds.height() * 0.15,
        )
        top_grad.setColorAt(0.00, QColor(235, 255, 248, 72))
        top_grad.setColorAt(0.40, QColor(130, 245, 205, 26))
        top_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.fillPath(top_face, QBrush(top_grad))

        # Directional depth faces.
        left_face = QPainterPath()
        left_face.moveTo(bounds.left() + 3, bounds.top() + bounds.height() * 0.08)
        left_face.lineTo(
            bounds.left() + bounds.width() * 0.10, bounds.top() + bounds.height() * 0.12
        )
        left_face.lineTo(
            bounds.left() + bounds.width() * 0.10,
            bounds.bottom() - bounds.height() * 0.10,
        )
        left_face.lineTo(bounds.left() + 3, bounds.bottom() - bounds.height() * 0.06)
        left_face.closeSubpath()

        left_grad = QLinearGradient(
            bounds.left(),
            bounds.top(),
            bounds.left() + bounds.width() * 0.14,
            bounds.top(),
        )
        left_grad.setColorAt(0.00, QColor(175, 255, 226, 78))
        left_grad.setColorAt(0.55, QColor(70, 210, 168, 22))
        left_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.fillPath(left_face, QBrush(left_grad))

        right_face = QPainterPath()
        right_face.moveTo(bounds.right() - 3, bounds.top() + bounds.height() * 0.08)
        right_face.lineTo(
            bounds.right() - bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.12,
        )
        right_face.lineTo(
            bounds.right() - bounds.width() * 0.10,
            bounds.bottom() - bounds.height() * 0.10,
        )
        right_face.lineTo(bounds.right() - 3, bounds.bottom() - bounds.height() * 0.06)
        right_face.closeSubpath()

        right_grad = QLinearGradient(
            bounds.right() - bounds.width() * 0.14,
            bounds.top(),
            bounds.right(),
            bounds.top(),
        )
        right_grad.setColorAt(0.00, QColor(0, 0, 0, 0))
        right_grad.setColorAt(0.55, QColor(0, 8, 7, 55))
        right_grad.setColorAt(1.00, QColor(0, 2, 2, 165))
        painter.fillPath(right_face, QBrush(right_grad))

        bottom_face = QPainterPath()
        bottom_face.moveTo(
            bounds.left() + bounds.width() * 0.10,
            bounds.bottom() - bounds.height() * 0.10,
        )
        bottom_face.lineTo(
            bounds.right() - bounds.width() * 0.10,
            bounds.bottom() - bounds.height() * 0.10,
        )
        bottom_face.lineTo(bounds.right() - bounds.width() * 0.06, bounds.bottom() - 3)
        bottom_face.lineTo(bounds.left() + bounds.width() * 0.06, bounds.bottom() - 3)
        bottom_face.closeSubpath()

        bottom_grad = QLinearGradient(
            0,
            bounds.bottom() - bounds.height() * 0.15,
            0,
            bounds.bottom(),
        )
        bottom_grad.setColorAt(0.00, QColor(0, 0, 0, 0))
        bottom_grad.setColorAt(0.45, QColor(0, 6, 5, 50))
        bottom_grad.setColorAt(1.00, QColor(0, 2, 2, 190))
        painter.fillPath(bottom_face, QBrush(bottom_grad))

        # Directional edge lighting.
        painter.setPen(QPen(QColor(185, 255, 230, 190), 1.5))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.08),
            int(bounds.top() + 4),
            int(bounds.right() - bounds.width() * 0.08),
            int(bounds.top() + 4),
        )

        painter.setPen(QPen(QColor(115, 235, 195, 110), 1.0))
        painter.drawLine(
            int(bounds.left() + 4),
            int(bounds.top() + bounds.height() * 0.08),
            int(bounds.left() + 4),
            int(bounds.bottom() - bounds.height() * 0.08),
        )

        painter.setPen(QPen(QColor(0, 6, 5, 180), 2.4))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.08),
            int(bounds.bottom() - 4),
            int(bounds.right() - bounds.width() * 0.08),
            int(bounds.bottom() - 4),
        )

        painter.setPen(QPen(QColor(0, 7, 6, 145), 1.8))
        painter.drawLine(
            int(bounds.right() - 4),
            int(bounds.top() + bounds.height() * 0.08),
            int(bounds.right() - 4),
            int(bounds.bottom() - bounds.height() * 0.08),
        )

        # Soft asymmetric reflection: stronger near top-left, fading inward.
        reflection = QLinearGradient(
            bounds.left(),
            bounds.top(),
            bounds.right(),
            bounds.bottom(),
        )
        reflection.setColorAt(0.00, QColor(255, 255, 255, 34))
        reflection.setColorAt(0.18, QColor(205, 255, 238, 18))
        reflection.setColorAt(0.42, QColor(120, 230, 195, 7))
        reflection.setColorAt(0.72, QColor(0, 0, 0, 0))
        reflection.setColorAt(1.00, QColor(0, 0, 0, 10))

        reflection_path = QPainterPath()
        reflection_path.moveTo(
            bounds.left() + bounds.width() * 0.06,
            bounds.top() + bounds.height() * 0.05,
        )
        reflection_path.lineTo(
            bounds.right() - bounds.width() * 0.20,
            bounds.top() + bounds.height() * 0.05,
        )
        reflection_path.lineTo(
            bounds.right() - bounds.width() * 0.30,
            bounds.top() + bounds.height() * 0.15,
        )
        reflection_path.lineTo(
            bounds.left() + bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.18,
        )
        reflection_path.closeSubpath()
        painter.fillPath(reflection_path, QBrush(reflection))

        # Mechanical details.
        screw_points = (
            QPointF(bounds.left() + 14, bounds.top() + 14),
            QPointF(bounds.right() - 14, bounds.top() + 14),
            QPointF(bounds.left() + 14, bounds.bottom() - 14),
            QPointF(bounds.right() - 14, bounds.bottom() - 14),
        )
        for point in screw_points:
            painter.setPen(QPen(QColor(0, 5, 4, 180), 1))
            painter.setBrush(QColor(12, 30, 26, 230))
            painter.drawEllipse(point, 3.4, 3.4)
            painter.setPen(QPen(QColor(130, 235, 200, 80), 0.8))
            painter.drawLine(
                QPointF(point.x() - 1.8, point.y()),
                QPointF(point.x() + 1.8, point.y()),
            )


class LeftScreen(ShapeWidget):
    document_selected = Signal(int)

    def __init__(self, window: QMainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.window = window
        self._dragging = False
        self._drag_offset = QPoint()

        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("windowButton")
        self.close_button.clicked.connect(window.close)

        self.min_button = QPushButton("—", self)
        self.min_button.setObjectName("windowButton")
        self.min_button.clicked.connect(window.showMinimized)

        self.local = QLabel("● LOCAL", self)
        self.local.setObjectName("online")

        self.section = QLabel("LOCAL DOCUMENTS", self)
        self.section.setObjectName("sectionLabel")

        self._documents: list[Document] = list(DOCUMENTS)
        self.table = QTableWidget(0, 2, self)
        self.table.setObjectName("documentTable")
        self.table.setHorizontalHeaderLabels(["DOCUMENT", "TYPE"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))

        header = self.table.horizontalHeader()
        header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)

        self.set_documents(self._documents)

        self.table.cellClicked.connect(
            lambda row, _column: self.document_selected.emit(row)
        )

        self.hint = QLabel("Choose a folder, scan, then select a ready PDF.", self)
        self.hint.setObjectName("muted")

        for label in (self.local, self.section, self.hint):
            glow = QGraphicsDropShadowEffect(label)
            glow.setBlurRadius(14)
            glow.setOffset(0, 0)
            glow.setColor(QColor(255, 30, 30, 180))
            label.setGraphicsEffect(glow)

    def document_at(self, row: int) -> Document | None:
        if not 0 <= row < len(self._documents):
            return None
        return self._documents[row]

    def set_documents(self, documents: list[Document]) -> None:
        self._documents = list(documents)
        self.table.setRowCount(len(self._documents))
        for row, doc in enumerate(self._documents):
            self._set_document_row(row, doc)

    def mark_document_for_review(  # noqa: PLR0913
        self,
        row: int,
        *,
        proposed_class: str,
        proposed_destination: str | None = None,
        proposal_id: str | None = None,
        document_id: str | None = None,
        proposal_fingerprint: str | None = None,
        lineage_preview: CockpitLineagePreview | None = None,
    ) -> None:
        """Update one discovered PDF with a non-authoritative proposal."""
        if not 0 <= row < len(self._documents):
            return
        current = self._documents[row]
        updated = Document(
            name=current.name,
            category=proposed_class,
            pages=current.pages,
            status="REVIEW",
            path=current.path,
            proposed_destination=proposed_destination,
            proposed_operation_action=(
                "rename_and_move" if proposed_destination is not None else None
            ),
            document_id=document_id,
            proposal_id=proposal_id,
            proposal_fingerprint=proposal_fingerprint,
            review_decision_id=None,
            lineage_preview=lineage_preview,
        )
        self._documents[row] = updated
        self._set_document_row(row, updated)

    def record_review_decision(
        self,
        row: int,
        *,
        status: str,
        review_decision_id: str,
        path: Path | None = None,
        name: str | None = None,
    ) -> None:
        """Update one proposal row after an append-only local review decision."""
        if not 0 <= row < len(self._documents):
            return
        current = self._documents[row]
        updated = Document(
            name=current.name if name is None else name,
            category=current.category,
            pages=current.pages,
            status=status,
            path=current.path if path is None else path,
            proposed_destination=current.proposed_destination,
            proposed_operation_action=current.proposed_operation_action,
            document_id=current.document_id,
            proposal_id=current.proposal_id,
            proposal_fingerprint=current.proposal_fingerprint,
            review_decision_id=review_decision_id,
            lineage_preview=current.lineage_preview,
        )
        self._documents[row] = updated
        self._set_document_row(row, updated)

    def _set_document_row(self, row: int, doc: Document) -> None:
        for column, value in enumerate((doc.name, doc.category)):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setToolTip(doc.name)
            if doc.proposed_destination is not None:
                action = doc.proposed_operation_action or "operation"
                tooltip = f"Proposed {action} target: {doc.proposed_destination}"
                if doc.lineage_preview is not None:
                    tooltip = (
                        f"{tooltip}\n"
                        "Lineage preview: "
                        f"{doc.lineage_preview.original_relative_path} -> "
                        f"{doc.lineage_preview.next_relative_path}\n"
                        "Plan fingerprint: "
                        f"{doc.lineage_preview.plan_fingerprint[:12]}"
                    )
                item.setToolTip(tooltip)
            if doc.review_decision_id is not None:
                item.setToolTip(
                    f"{item.toolTip()}\nReview decision: {doc.review_decision_id}"
                )
            self.table.setItem(row, column, item)
        self.table.setRowHeight(row, 42)

    def count_status(self, status: str) -> int:
        """Count current visible document states."""
        return sum(1 for document in self._documents if document.status == status)

    @property
    def document_count(self) -> int:
        """Return the current visible document count."""
        return len(self._documents)

    def shape_path(self) -> QPainterPath:
        r = self.rect().adjusted(3, 3, -3, -3)
        x, y, w, h = map(float, (r.x(), r.y(), r.width(), r.height()))

        path = QPainterPath()
        path.moveTo(x + w * 0.08, y)
        path.lineTo(x + w * 0.92, y)
        path.lineTo(x + w, y + h * 0.08)
        path.lineTo(x + w * 0.97, y + h * 0.92)
        path.lineTo(x + w * 0.88, y + h)
        path.lineTo(x + w * 0.12, y + h)
        path.lineTo(x, y + h * 0.92)
        path.lineTo(x + w * 0.03, y + h * 0.08)
        path.closeSubpath()
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        self.close_button.setGeometry(34, 18, 31, 29)
        self.min_button.setGeometry(71, 18, 31, 29)
        self.local.setGeometry(w - 94, 20, 72, 24)

        # Carbon content area: extra lower/side clearance keeps the table
        # entirely inside the scaled carbon silhouette.
        content_left = int(w * 0.105)
        content_right = int(w * 0.105)
        content_top = int(h * 0.145)
        content_width = w - content_left - content_right

        self.section.setGeometry(
            40,
            61,
            w - 80,
            24,
        )

        table_top = content_top
        hint_height = 22
        hint_y = h - 46
        self.table.setGeometry(
            content_left,
            table_top,
            content_width,
            hint_y - table_top - 30,
        )
        self.table.setColumnWidth(1, max(78, int(content_width * 0.24)))
        self.hint.setGeometry(
            46,
            hint_y,
            w - 92,
            hint_height,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 58:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        event.accept()


class RightScreen(ShapeWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.title = QLabel("SYSTEM INTELLIGENCE", self)
        self.title.setObjectName("screenTitle")

        self.online = QLabel("● ONLINE", self)
        self.online.setObjectName("online")

        self.section = QLabel("MEMORY / AGENT STATUS", self)
        self.section.setObjectName("sectionLabel")

        self.metric_frames: list[QFrame] = []
        for value, caption in (("0", "DISCOVERED"), ("0", "READY"), ("0", "REVIEW")):
            frame = QFrame(self)
            frame.setObjectName("metric")
            number = QLabel(value, frame)
            number.setObjectName("metricValue")
            label = QLabel(caption, frame)
            label.setObjectName("metricLabel")
            frame.number = number
            frame.caption = label
            self.metric_frames.append(frame)

        self.stream_label = QLabel("AGENT EVENT STREAM", self)
        self.stream_label.setObjectName("sectionLabel")

        self.restore_label = QLabel("RESTORE HISTORY", self)
        self.restore_label.setObjectName("sectionLabel")

        self.memory_label = QLabel("DATABASE EVIDENCE", self)
        self.memory_label.setObjectName("sectionLabel")

        self.memory_text = QLabel("Memory evidence waiting for runtime preflight", self)
        self.memory_text.setObjectName("eventText")
        self.memory_text.setAccessibleName("CockroachDB memory evidence status")
        self.memory_text.setWordWrap(True)

        self.memory_table = QTableWidget(0, 2, self)
        self.memory_table.setObjectName("memoryTable")
        self.memory_table.setAccessibleName("CockroachDB memory table evidence")
        self.memory_table.setHorizontalHeaderLabels(["TABLE", "ROWS"])
        self.memory_table.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        self.memory_table.verticalHeader().hide()
        self.memory_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.memory_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.memory_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.memory_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.memory_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.memory_table.setAlternatingRowColors(True)

        self.restore_text = QLabel("Read-only history waiting for runtime", self)
        self.restore_text.setObjectName("eventText")
        self.restore_text.setAccessibleName("Restore history status")
        self.restore_text.setWordWrap(True)

        for label in (
            self.title,
            self.online,
            self.section,
            self.stream_label,
            self.memory_label,
            self.restore_label,
        ):
            glow = QGraphicsDropShadowEffect(label)
            glow.setBlurRadius(14)
            glow.setOffset(0, 0)
            glow.setColor(QColor(255, 30, 30, 180))
            label.setGraphicsEffect(glow)

        self.event_rows: list[QFrame] = []
        events = [
            ("DISCOVERY", "Choose a folder to begin"),
            ("PREVIEW", "Embedded PDF viewer ready"),
            ("MEMORY", "CockroachDB not connected"),
            ("BEDROCK", "Classification not active"),
            ("SECURITY", "Read-only local boundary"),
        ]
        for name, text in events:
            frame = QFrame(self)
            frame.setObjectName("eventRow")
            a = QLabel(name, frame)
            a.setObjectName("eventName")
            b = QLabel(text, frame)
            b.setObjectName("eventText")
            b.setWordWrap(True)
            frame.event_name = a
            frame.event_text = b
            self.event_rows.append(frame)

    def set_metrics(self, discovered: int, ready: int, review: int) -> None:
        for frame, value in zip(
            self.metric_frames,
            (discovered, ready, review),
            strict=True,
        ):
            frame.number.setText(str(value))

    def set_events(self, events: list[tuple[str, str]]) -> None:
        for frame, event in zip(self.event_rows, events, strict=False):
            name, text = event
            frame.event_name.setText(name)
            frame.event_text.setText(text)

    def set_restore_history_status(self, text: str) -> None:
        self.restore_text.setText(text)

    def set_memory_evidence_status(self, text: str) -> None:
        self.memory_text.setText(text)

    def set_memory_table_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        self.memory_table.setRowCount(len(rows))
        for row_index, (table_name, row_count) in enumerate(rows):
            table_item = QTableWidgetItem(table_name)
            count_item = QTableWidgetItem(row_count)
            table_item.setToolTip(table_name)
            count_item.setToolTip(f"{table_name}: {row_count}")
            self.memory_table.setItem(row_index, 0, table_item)
            self.memory_table.setItem(row_index, 1, count_item)
            self.memory_table.setRowHeight(row_index, 32)

    def shape_path(self) -> QPainterPath:
        r = self.rect().adjusted(3, 3, -3, -3)
        x, y, w, h = map(float, (r.x(), r.y(), r.width(), r.height()))

        path = QPainterPath()
        path.moveTo(x + w * 0.08, y)
        path.lineTo(x + w * 0.92, y)
        path.lineTo(x + w, y + h * 0.08)
        path.lineTo(x + w * 0.97, y + h * 0.92)
        path.lineTo(x + w * 0.88, y + h)
        path.lineTo(x + w * 0.12, y + h)
        path.lineTo(x, y + h * 0.92)
        path.lineTo(x + w * 0.03, y + h * 0.08)
        path.closeSubpath()
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        # Title and status remain on the glass frame.
        self.title.setGeometry(44, 18, w - 150, 28)
        self.online.setGeometry(w - 96, 20, 74, 22)
        self.section.setGeometry(44, 58, w - 88, 22)

        # Carbon content area.
        content_left = int(w * 0.085)
        content_right = int(w * 0.085)
        content_top = int(h * 0.135)
        content_width = w - content_left - content_right

        metric_gap = 10
        metric_top = content_top
        metric_w = int((content_width - metric_gap * 2) / 3)
        x = content_left
        for frame in self.metric_frames:
            frame.setGeometry(x, metric_top, metric_w, 84)
            frame.number.setGeometry(11, 8, metric_w - 22, 36)
            frame.caption.setGeometry(11, 48, metric_w - 22, 24)
            x += metric_w + metric_gap

        memory_y = metric_top + 98
        self.memory_label.setGeometry(content_left, memory_y, content_width, 24)
        self.memory_text.setGeometry(
            content_left + 12,
            memory_y + 28,
            content_width - 24,
            48,
        )
        self.memory_table.setGeometry(
            content_left,
            memory_y + 82,
            content_width,
            128,
        )

        stream_top = memory_y + 210
        self.stream_label.setGeometry(
            content_left,
            stream_top,
            content_width,
            21,
        )

        row_y = stream_top + 30
        row_height = 42
        row_gap = 5
        for frame in self.event_rows:
            frame.setGeometry(
                content_left,
                row_y,
                content_width,
                row_height,
            )
            frame.event_name.setGeometry(12, 6, content_width - 24, 18)
            frame.event_text.setGeometry(12, 24, content_width - 24, 18)
            row_y += row_height + row_gap

        self.restore_label.hide()
        self.restore_text.hide()
        self.restore_label.setGeometry(content_left, h + 12, content_width, 1)
        self.restore_text.setGeometry(content_left, h + 16, content_width, 1)


class PdfPageMock(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document_name = "Contract_Master_v3.pdf"

    def set_document(self, name: str) -> None:
        self.document_name = name
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        available = self.rect().adjusted(25, 8, -25, -12)
        ratio = 0.707

        page_h = min(available.height(), int(available.width() / ratio))
        page_w = int(page_h * ratio)

        page = QRectF(
            available.center().x() - page_w / 2,
            available.top(),
            page_w,
            page_h,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 85))
        painter.drawRoundedRect(page.translated(9, 10), 5, 5)

        painter.setBrush(QColor(248, 250, 249, 255))
        painter.setPen(QPen(QColor("#AAB8B2"), 1.2))
        painter.drawRoundedRect(page, 5, 5)

        painter.setPen(QColor("#13211C"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.drawText(
            page.adjusted(28, 24, -28, -20),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            self.document_name.replace("_", " "),
        )

        y = page.top() + 74
        painter.setPen(QPen(QColor("#51615B"), 1.8))

        widths = (0.84, 0.92, 0.72, 0.88, 0.64, 0.90, 0.77, 0.86, 0.61)
        for index, factor in enumerate(widths):
            x1 = page.left() + 32
            x2 = x1 + (page.width() - 64) * factor
            painter.drawLine(x1, y, x2, y)
            y += 18 if index not in (2, 5) else 31


class CenterPreview(ShapeWidget):
    review_approve_requested = Signal(int)
    review_reject_requested = Signal(int)
    review_preview_requested = Signal(int)
    review_approve_all_requested = Signal()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = self.shape_path()
        bounds = path.boundingRect()

        # Transparent green glass frame only. No carbon on the central screen.
        glass = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        glass.setColorAt(0.00, QColor(110, 230, 190, 48))
        glass.setColorAt(0.25, QColor(65, 175, 140, 30))
        glass.setColorAt(0.70, QColor(18, 80, 64, 18))
        glass.setColorAt(1.00, QColor(5, 28, 23, 14))
        painter.fillPath(path, QBrush(glass))

        # Dark depth behind the frame only.
        painter.setPen(QPen(QColor(0, 0, 0, 125), 16))
        painter.drawPath(path)

        # Directional highlights.
        painter.setPen(QPen(QColor(205, 255, 238, 210), 1.8))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.05),
            int(bounds.top() + 4),
            int(bounds.right() - bounds.width() * 0.05),
            int(bounds.top() + 4),
        )

        painter.setPen(QPen(QColor(115, 235, 195, 110), 1.1))
        painter.drawLine(
            int(bounds.left() + 4),
            int(bounds.top() + bounds.height() * 0.06),
            int(bounds.left() + 4),
            int(bounds.bottom() - bounds.height() * 0.06),
        )

        painter.setPen(QPen(QColor(0, 7, 6, 165), 2.0))
        painter.drawLine(
            int(bounds.right() - 4),
            int(bounds.top() + bounds.height() * 0.06),
            int(bounds.right() - 4),
            int(bounds.bottom() - bounds.height() * 0.06),
        )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._target_rect = QRect()
        self._geometry_animation = QPropertyAnimation(self, b"geometry", self)
        self._geometry_animation.setDuration(360)
        self._geometry_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.opacity_animation = QPropertyAnimation(
            self.opacity_effect,
            b"opacity",
            self,
        )
        self.opacity_animation.setDuration(260)
        self.opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.title = QLabel("PDF PREVIEW", self)
        self.title.setObjectName("screenTitle")

        self.filename = QLabel("No document selected", self)
        self.filename.setObjectName("muted")

        self.review_title = QLabel("BATCH REVIEW", self)
        self.review_title.setObjectName("screenTitle")
        self.review_title.hide()

        for label in (self.title, self.filename, self.review_title):
            glow = QGraphicsDropShadowEffect(label)
            glow.setBlurRadius(14)
            glow.setOffset(0, 0)
            glow.setColor(QColor(255, 30, 30, 180))
            label.setGraphicsEffect(glow)

        self.lower_button = QPushButton("LOWER", self)
        self.lower_button.setObjectName("smallButton")
        self.lower_button.clicked.connect(self.close_preview)

        self.zoom_out = QPushButton("−", self)
        self.zoom_value = QPushButton("100%", self)
        self.zoom_in = QPushButton("+", self)
        self.fit = QPushButton("FIT", self)

        for button in (self.zoom_out, self.zoom_value, self.zoom_in, self.fit):
            button.setObjectName("smallButton")

        self.counter = QLabel("1 / 1", self)
        self.counter.setObjectName("muted")

        self.analysis_panel = QFrame(self)
        self.analysis_panel.setObjectName("eventRow")
        self.analysis_panel.hide()
        self.analysis_title = QLabel("AI PROPOSAL", self.analysis_panel)
        self.analysis_title.setObjectName("eventName")
        self.analysis_summary = QLabel(
            "No classification proposal yet.", self.analysis_panel
        )
        self.analysis_summary.setObjectName("eventText")
        self.analysis_summary.setWordWrap(True)
        self.analysis_rationale = QLabel("", self.analysis_panel)
        self.analysis_rationale.setObjectName("muted")
        self.analysis_rationale.setWordWrap(True)
        self.analysis_evidence = QLabel("", self.analysis_panel)
        self.analysis_evidence.setObjectName("eventText")
        self.analysis_evidence.setWordWrap(True)

        self.memory_panel = QFrame(self)
        self.memory_panel.setObjectName("eventRow")
        self.memory_panel.hide()
        self.memory_title = QLabel("MEMORY TRACE", self.memory_panel)
        self.memory_title.setObjectName("eventName")
        self.memory_summary = QLabel("No memory trace selected.", self.memory_panel)
        self.memory_summary.setObjectName("eventText")
        self.memory_summary.setWordWrap(True)
        self.memory_detail = QLabel("", self.memory_panel)
        self.memory_detail.setObjectName("muted")
        self.memory_detail.setWordWrap(True)

        self.review_approve_all = QPushButton("APPROVE ALL", self)
        self.review_approve_all.setObjectName("smallButton")
        self.review_approve_all.hide()
        self.review_approve_all.clicked.connect(self.review_approve_all_requested)

        self.review_table = QTableWidget(0, 4, self)
        self.review_table.setObjectName("reviewTable")
        self.review_table.setHorizontalHeaderLabels(
            ["PDF NAME", "PROPOSED NAME", "SUGGESTED DIRECTORY", ""]
        )
        self.review_table.verticalHeader().setVisible(False)
        self.review_table.setShowGrid(False)
        self.review_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.review_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.review_table.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        review_header = self.review_table.horizontalHeader()
        review_header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        review_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        review_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        review_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        review_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.review_table.hide()

        self._document = QPdfDocument(self)
        self.page = SecurePdfView(self)
        self.page.setObjectName("centralPdfView")
        self.page.setStyleSheet(
            """
            QPdfView#centralPdfView {
                background: rgba(2, 8, 7, 235);
                border: 1px solid rgba(103, 216, 176, 120);
            }

            QPdfView#centralPdfView QScrollBar:vertical {
                background: rgba(4, 18, 15, 215);
                border-left: 1px solid rgba(103, 216, 176, 85);
                width: 18px;
                margin: 2px;
            }

            QPdfView#centralPdfView QScrollBar:horizontal {
                background: rgba(4, 18, 15, 215);
                border-top: 1px solid rgba(103, 216, 176, 85);
                height: 18px;
                margin: 2px;
            }

            QPdfView#centralPdfView QScrollBar::handle:vertical,
            QPdfView#centralPdfView QScrollBar::handle:horizontal {
                background: rgba(103, 255, 200, 185);
                border: 1px solid rgba(205, 255, 238, 210);
                border-radius: 8px;
                min-height: 42px;
                min-width: 42px;
            }

            QPdfView#centralPdfView QScrollBar::handle:vertical:hover,
            QPdfView#centralPdfView QScrollBar::handle:horizontal:hover {
                background: rgba(150, 255, 220, 230);
                border-color: rgba(235, 255, 248, 245);
            }

            QPdfView#centralPdfView QScrollBar::add-line,
            QPdfView#centralPdfView QScrollBar::sub-line {
                width: 0;
                height: 0;
            }

            QPdfView#centralPdfView QScrollBar::add-page,
            QPdfView#centralPdfView QScrollBar::sub-page {
                background: transparent;
            }
            """
        )
        self.page.setDocument(self._document)
        self.page.setPageMode(QPdfView.PageMode.MultiPage)
        self.page.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.page.external_link_activated.connect(self._open_external_link)
        self._document.statusChanged.connect(self._handle_document_status)
        self._document.pageCountChanged.connect(self._update_page_counter)
        self.page.pageNavigator().currentPageChanged.connect(self._update_page_counter)

        self.zoom_out.clicked.connect(self.zoom_out_pdf)
        self.zoom_in.clicked.connect(self.zoom_in_pdf)
        self.fit.clicked.connect(self.fit_pdf_width)

    def _review_action_widget(self, row: int) -> QWidget:
        box = QWidget(self.review_table)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(7, 3, 7, 3)
        layout.setSpacing(9)
        approve = QPushButton("⚑", box)
        reject = QPushButton("×", box)
        preview = QPushButton("PDF", box)
        approve.setObjectName("reviewApproveButton")
        reject.setObjectName("reviewRejectButton")
        preview.setObjectName("reviewPreviewButton")
        approve.setFont(QFont("Segoe UI Symbol", 24, QFont.Weight.Black))
        reject.setFont(QFont("Segoe UI", 23, QFont.Weight.Black))
        for button in (approve, reject):
            button.setFixedSize(60, 34)
        preview.setFixedSize(64, 34)
        approve_glow = QGraphicsDropShadowEffect(approve)
        approve_glow.setBlurRadius(18)
        approve_glow.setOffset(0, 0)
        approve_glow.setColor(QColor(90, 255, 185, 190))
        approve.setGraphicsEffect(approve_glow)
        reject_glow = QGraphicsDropShadowEffect(reject)
        reject_glow.setBlurRadius(18)
        reject_glow.setOffset(0, 0)
        reject_glow.setColor(QColor(255, 70, 70, 190))
        reject.setGraphicsEffect(reject_glow)
        approve.setToolTip("Approve this proposed rename.")
        reject.setToolTip("Reject this proposed rename.")
        preview.setToolTip("Open the PDF preview for this row.")
        approve.clicked.connect(
            lambda _checked=False, row=row: self.review_approve_requested.emit(row)
        )
        reject.clicked.connect(
            lambda _checked=False, row=row: self.review_reject_requested.emit(row)
        )
        preview.clicked.connect(
            lambda _checked=False, row=row: self.review_preview_requested.emit(row)
        )
        layout.addWidget(approve)
        layout.addWidget(reject)
        layout.addWidget(preview)
        return box

    def shape_path(self) -> QPainterPath:
        r = self.rect().adjusted(3, 3, -3, -3)
        x, y, w, h = map(float, (r.x(), r.y(), r.width(), r.height()))

        path = QPainterPath()
        path.moveTo(x + w * 0.04, y)
        path.lineTo(x + w * 0.96, y)
        path.lineTo(x + w, y + h * 0.05)
        path.lineTo(x + w * 0.985, y + h * 0.96)
        path.lineTo(x + w * 0.96, y + h)
        path.lineTo(x + w * 0.04, y + h)
        path.lineTo(x + w * 0.015, y + h * 0.96)
        path.lineTo(x, y + h * 0.05)
        path.closeSubpath()
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        # Header remains on the glass.
        self.title.setGeometry(28, 16, 180, 27)
        self.filename.setGeometry(28, 43, w - 200, 22)
        self.lower_button.setGeometry(w - 96, 16, 68, 29)

        self.zoom_out.setGeometry(28, 72, 62, 30)
        self.zoom_value.setGeometry(98, 72, 72, 30)
        self.zoom_in.setGeometry(178, 72, 62, 30)
        self.fit.setGeometry(248, 72, 62, 30)
        self.counter.setGeometry(w - 98, 75, 70, 25)
        self.review_title.setGeometry(28, 112, 210, 27)
        self.review_approve_all.setGeometry(w - 148, 112, 120, 30)
        self.review_table.setGeometry(18, 150, w - 36, h - 166)
        self.review_table.setColumnWidth(0, 230)
        self.review_table.setColumnWidth(3, 250)

        top = 112
        if self.analysis_panel.isVisible():
            self.analysis_panel.setGeometry(18, 112, w - 36, 132)
            self.analysis_title.setGeometry(16, 8, 120, 20)
            self.analysis_summary.setGeometry(16, 28, w - 68, 24)
            self.analysis_rationale.setGeometry(16, 52, w - 68, 28)
            self.analysis_evidence.setGeometry(16, 84, w - 68, 40)
            top = 254

        if self.memory_panel.isVisible():
            self.memory_panel.setGeometry(18, top, w - 36, 92)
            self.memory_title.setGeometry(16, 7, 135, 20)
            self.memory_summary.setGeometry(16, 28, w - 68, 24)
            self.memory_detail.setGeometry(16, 53, w - 68, 31)
            top += 102

        self.page.setGeometry(18, top, w - 36, h - top - 16)

    def set_target_rect(self, rect: QRect) -> None:
        self._target_rect = QRect(rect)

    def open_document(self, path: Path) -> None:
        self.review_title.hide()
        self.review_approve_all.hide()
        self.review_table.hide()
        self.page.show()
        self.title.show()
        self.filename.show()
        self.zoom_out.show()
        self.zoom_value.show()
        self.zoom_in.show()
        self.fit.show()
        self.counter.show()
        self.filename.setText(path.name)
        self.counter.setText("Loading")
        self._document.close()
        self.page.setDocument(self._document)
        load_error = self._document.load(str(path))
        if load_error is not QPdfDocument.Error.None_:
            self.counter.setText("Blocked")

        collapsed = QRect(
            self._target_rect.center().x(),
            self._target_rect.bottom() - 12,
            0,
            12,
        )

        if self.width() <= 10 or self.height() <= 20:
            self.setGeometry(collapsed)

        self.analysis_panel.hide()
        self.memory_panel.hide()
        self.resizeEvent(None)
        self.show()

        self._geometry_animation.stop()
        self.opacity_animation.stop()

        self._geometry_animation.setStartValue(self.geometry())
        self._geometry_animation.setEndValue(self._target_rect)

        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(1.0)

        self._geometry_animation.start()
        self.opacity_animation.start()

    def show_review_table(self, rows: list[tuple[int, str, str, str]]) -> None:
        """Replace the PDF preview with a batch decision table."""
        self._geometry_animation.stop()
        self.opacity_animation.stop()
        self.opacity_effect.setOpacity(1.0)
        self.setGeometry(self._target_rect)
        self.show()
        self._document.close()
        self.page.hide()
        self.title.hide()
        self.filename.hide()
        self.zoom_out.hide()
        self.zoom_value.hide()
        self.zoom_in.hide()
        self.fit.hide()
        self.counter.hide()
        self.analysis_panel.hide()
        self.memory_panel.hide()
        self.review_title.show()
        self.review_approve_all.show()
        self.review_table.show()
        self.review_table.setRowCount(len(rows))
        for table_row, (document_row, original, proposed_name, directory) in enumerate(
            rows
        ):
            original_item = QTableWidgetItem(original)
            proposed_item = QTableWidgetItem(proposed_name)
            directory_item = QTableWidgetItem(directory)
            original_item.setToolTip(original)
            proposed_item.setToolTip(proposed_name)
            directory_item.setToolTip(directory)
            self.review_table.setItem(table_row, 0, original_item)
            self.review_table.setItem(table_row, 1, proposed_item)
            self.review_table.setItem(table_row, 2, directory_item)
            self.review_table.setCellWidget(
                table_row,
                3,
                self._review_action_widget(document_row),
            )
            self.review_table.setRowHeight(table_row, 48)
        self.resizeEvent(None)

    def show_classification_result(self, result: ClassificationCommandResult) -> None:
        """Surface validated model proposal details without replacing the preview."""
        confidence = "n/a" if result.raw_confidence is None else result.raw_confidence
        retry_label = (
            "no validation retry"
            if result.retry_attempts == 0
            else f"{result.retry_attempts} validation retry"
        )
        self.analysis_summary.setText(
            f"{result.proposed_class} · confidence {confidence} · "
            f"{result.evidence_count} evidence · {result.metadata_count} metadata · "
            f"{retry_label}"
        )
        self.analysis_rationale.setText(
            _compact_console_text(result.rationale, maximum=150)
        )
        self.analysis_evidence.setText(_classification_evidence_summary(result))
        self.analysis_panel.show()
        self.analysis_panel.raise_()
        self.resizeEvent(None)

    def show_memory_trace(self, *, summary: str, detail: str) -> None:
        """Surface the current CockroachDB-backed memory chain."""
        self.memory_summary.setText(_compact_console_text(summary, maximum=140))
        self.memory_detail.setText(_compact_console_text(detail, maximum=190))
        self.memory_panel.show()
        self.memory_panel.raise_()
        self.resizeEvent(None)

    @Slot()
    def zoom_in_pdf(self) -> None:
        self.page.setZoomMode(QPdfView.ZoomMode.Custom)
        self.page.setZoomFactor(min(4.0, self.page.zoomFactor() * 1.2))
        self._update_zoom_label()

    @Slot()
    def zoom_out_pdf(self) -> None:
        self.page.setZoomMode(QPdfView.ZoomMode.Custom)
        self.page.setZoomFactor(max(0.25, self.page.zoomFactor() / 1.2))
        self._update_zoom_label()

    @Slot()
    def fit_pdf_width(self) -> None:
        self.page.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.zoom_value.setText("FIT")

    @Slot(QPdfDocument.Status)
    def _handle_document_status(self, status: QPdfDocument.Status) -> None:
        if status is QPdfDocument.Status.Ready:
            self.fit_pdf_width()
            self._update_page_counter()
            return
        if status is QPdfDocument.Status.Error:
            self.counter.setText("Load error")

    @Slot()
    @Slot(int)
    def _update_page_counter(self, unused_value: int | None = None) -> None:
        del unused_value
        page_count = self._document.pageCount()
        if page_count < 1:
            self.counter.setText("Page -")
            return
        current_page = self.page.pageNavigator().currentPage() + 1
        self.counter.setText(f"{current_page} / {page_count}")

    def _update_zoom_label(self) -> None:
        self.zoom_value.setText(f"{int(self.page.zoomFactor() * 100)}%")

    @Slot(QUrl)
    def _open_external_link(self, url: QUrl) -> None:
        outcome = request_external_pdf_link(url, self)
        if outcome is ExternalLinkOutcome.OPENED:
            self.counter.setText("Link opened")
        elif outcome is ExternalLinkOutcome.BLOCKED:
            self.counter.setText("Link blocked")
        elif outcome is ExternalLinkOutcome.CANCELLED:
            self.counter.setText("Link cancelled")
        else:
            self.counter.setText("Link failed")

    def close_preview(self) -> None:
        collapsed = QRect(
            self._target_rect.center().x(),
            self._target_rect.bottom() - 12,
            0,
            12,
        )

        self._geometry_animation.stop()
        self.opacity_animation.stop()

        self._geometry_animation.setStartValue(self.geometry())
        self._geometry_animation.setEndValue(collapsed)

        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(0.0)

        self._geometry_animation.start()
        self.opacity_animation.start()

    def release_document_handle(self) -> None:
        """Release the previewed PDF before an approved local move."""
        old_document = self._document
        self.page.setDocument(None)
        old_document.close()
        try:
            old_document.statusChanged.disconnect(self._handle_document_status)
            old_document.pageCountChanged.disconnect(self._update_page_counter)
        except RuntimeError:
            pass
        old_document.deleteLater()
        QApplication.sendPostedEvents(old_document, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        self._document = QPdfDocument(self)
        self._document.statusChanged.connect(self._handle_document_status)
        self._document.pageCountChanged.connect(self._update_page_counter)
        self.page.setDocument(self._document)
        self.counter.setText("Closed")


class CurvedConsoleButton(QPushButton):
    """Curved trapezoidal control that can rotate along the console arc."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
        *,
        angle: float = 0.0,
    ) -> None:
        super().__init__(text, parent)
        self.angle = angle
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def base_path(self) -> QPainterPath:
        # Draw inside a smaller central box so rotation does not clip the shape.
        margin_x = self.width() * 0.10
        margin_y = self.height() * 0.18

        x = margin_x
        y = margin_y
        w = self.width() - margin_x * 2
        h = self.height() - margin_y * 2

        path = QPainterPath()
        path.moveTo(x + w * 0.10, y + h * 0.20)
        path.quadTo(x + w * 0.50, y - h * 0.10, x + w * 0.90, y + h * 0.20)
        path.lineTo(x + w * 0.96, y + h * 0.68)
        path.quadTo(x + w * 0.50, y + h * 1.06, x + w * 0.04, y + h * 0.68)
        path.closeSubpath()
        return path

    def button_path(self) -> QPainterPath:
        path = self.base_path()

        transform = QTransform()
        transform.translate(self.width() / 2, self.height() / 2)
        transform.rotate(self.angle)
        transform.translate(-self.width() / 2, -self.height() / 2)

        return transform.map(path)

    def update_mask(self) -> None:
        polygon = self.button_path().toFillPolygon().toPolygon()
        self.setMask(QRegion(polygon))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_mask()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        painter.translate(-self.width() / 2, -self.height() / 2)

        path = self.base_path()
        bounds = path.boundingRect()

        pressed = self.isDown()
        hovered = self.underMouse() and self.isEnabled()
        enabled = self.isEnabled()
        role = self.text().casefold()

        if not enabled:
            top = QColor(18, 24, 23, 125)
            bottom = QColor(8, 12, 12, 155)
            edge_color = QColor(100, 118, 112, 90)
            text_color = QColor(142, 158, 152, 170)
        elif role == "approve":
            top = QColor(30, 126, 82, 235)
            bottom = QColor(7, 54, 34, 245)
            edge_color = QColor(126, 255, 183, 235)
            text_color = QColor("#F4FFF8")
        elif role == "reject":
            top = QColor(126, 42, 42, 235)
            bottom = QColor(58, 11, 17, 245)
            edge_color = QColor(255, 135, 135, 230)
            text_color = QColor("#FFF6F6")
        elif pressed:
            top = QColor(8, 38, 31, 235)
            bottom = QColor(3, 20, 17, 245)
            edge_color = QColor(185, 255, 230, 220)
            text_color = QColor("#EAF5F1")
        elif hovered:
            top = QColor(37, 118, 94, 220)
            bottom = QColor(10, 54, 43, 235)
            edge_color = QColor(185, 255, 230, 215)
            text_color = QColor("#EAF5F1")
        else:
            top = QColor(24, 82, 66, 220)
            bottom = QColor(7, 38, 31, 238)
            edge_color = QColor(185, 255, 230, 175)
            text_color = QColor("#EAF5F1")

        fill = QLinearGradient(0, bounds.top(), 0, bounds.bottom())
        fill.setColorAt(0.00, top)
        fill.setColorAt(0.42, QColor(top.red(), top.green(), top.blue(), 190))
        fill.setColorAt(1.00, bottom)
        painter.fillPath(path, QBrush(fill))

        if enabled and role in {"approve", "reject"}:
            glow_color = QColor(edge_color)
            glow_color.setAlpha(95)
            painter.setPen(QPen(glow_color, 4.8))
            painter.drawPath(path)

        # Upper illuminated edge.
        top_edge = QPainterPath()
        top_edge.moveTo(
            bounds.left() + bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.20,
        )
        top_edge.quadTo(
            bounds.center().x(),
            bounds.top() - bounds.height() * 0.10,
            bounds.right() - bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.20,
        )
        painter.setPen(
            QPen(
                edge_color,
                1.9 if enabled and role in {"approve", "reject"} else 1.2,
            )
        )
        painter.drawPath(top_edge)

        # Dark lower edge.
        bottom_edge = QPainterPath()
        bottom_edge.moveTo(
            bounds.left() + bounds.width() * 0.04,
            bounds.top() + bounds.height() * 0.68,
        )
        bottom_edge.quadTo(
            bounds.center().x(),
            bounds.bottom() + bounds.height() * 0.06,
            bounds.right() - bounds.width() * 0.04,
            bounds.top() + bounds.height() * 0.68,
        )
        painter.setPen(QPen(QColor(0, 8, 6, 95 if not enabled else 190), 2.4))
        painter.drawPath(bottom_edge)

        painter.setPen(QPen(edge_color if enabled else QColor(90, 104, 99, 90), 1.0))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.10),
            int(bounds.top() + bounds.height() * 0.20),
            int(bounds.left() + bounds.width() * 0.04),
            int(bounds.top() + bounds.height() * 0.68),
        )

        painter.setPen(QPen(QColor(0, 10, 8, 70 if not enabled else 150), 1.3))
        painter.drawLine(
            int(bounds.right() - bounds.width() * 0.10),
            int(bounds.top() + bounds.height() * 0.20),
            int(bounds.right() - bounds.width() * 0.04),
            int(bounds.top() + bounds.height() * 0.68),
        )

        painter.setPen(text_color)
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        painter.setFont(font)
        painter.drawText(
            QRectF(bounds),
            Qt.AlignmentFlag.AlignCenter,
            self.text(),
        )


class ConsolePanel(ShapeWidget):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = self.shape_path()
        bounds = path.boundingRect()

        # Rear depth.
        rear_transform = QTransform()
        rear_transform.translate(9.0, 12.0)
        rear = rear_transform.map(path)

        painter.setPen(QPen(QColor(0, 0, 0, 190), 22))
        painter.drawPath(rear)

        # Outer glass shell.
        glass = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        glass.setColorAt(0.00, QColor(100, 225, 185, 52))
        glass.setColorAt(0.24, QColor(62, 175, 140, 38))
        glass.setColorAt(0.64, QColor(18, 70, 56, 70))
        glass.setColorAt(0.86, QColor(10, 42, 34, 115))
        glass.setColorAt(1.00, QColor(4, 18, 15, 165))
        painter.fillPath(path, QBrush(glass))

        # Inner carbon panel built from an explicit inset silhouette.
        # Every carbon edge is parallel to the corresponding glass edge.
        inner_path = self.carbon_path()
        inner = inner_path.boundingRect()

        carbon_base = QLinearGradient(inner.topLeft(), inner.bottomRight())
        carbon_base.setColorAt(0.00, QColor(32, 36, 35, 255))
        carbon_base.setColorAt(0.48, QColor(18, 22, 21, 255))
        carbon_base.setColorAt(1.00, QColor(7, 10, 10, 255))
        painter.fillPath(inner_path, QBrush(carbon_base))

        painter.save()
        painter.setClipPath(inner_path)

        tile = 8
        for y in range(int(inner.top()), int(inner.bottom()) + tile, tile):
            for x in range(int(inner.left()), int(inner.right()) + tile, tile):
                alt = ((x // tile) + (y // tile)) % 2

                if alt == 0:
                    c1 = QColor(62, 68, 66, 46)
                    c2 = QColor(8, 12, 11, 58)
                else:
                    c1 = QColor(18, 24, 22, 46)
                    c2 = QColor(74, 82, 78, 34)

                painter.setPen(QPen(c1, 0.9))
                painter.drawLine(x, y + tile, x + tile, y)

                painter.setPen(QPen(c2, 0.5))
                painter.drawLine(x - tile * 0.35, y + tile, x + tile * 0.65, y)

        sheen = QLinearGradient(
            inner.left(),
            inner.top(),
            inner.right(),
            inner.bottom(),
        )
        sheen.setColorAt(0.00, QColor(255, 255, 255, 8))
        sheen.setColorAt(0.35, QColor(120, 255, 210, 5))
        sheen.setColorAt(0.65, QColor(0, 0, 0, 0))
        sheen.setColorAt(1.00, QColor(0, 0, 0, 24))
        painter.fillPath(inner_path, QBrush(sheen))

        painter.restore()

        # Deep inset bevel between glass and carbon.
        inset_transform = QTransform()
        inset_transform.translate(inner.center().x(), inner.center().y())
        inset_transform.scale(0.978, 0.955)
        inset_transform.translate(-inner.center().x(), -inner.center().y())
        inset_inner_path = inset_transform.map(inner_path)

        inset_ring = inner_path.subtracted(inset_inner_path)

        inset_black = QColor(8, 8, 10, 255)
        painter.fillPath(inset_ring, QBrush(inset_black))
        painter.setPen(QPen(QColor(42, 42, 46, 210), 0.8))
        painter.drawPath(inner_path)
        painter.setPen(QPen(QColor(0, 0, 0, 245), 1.2))
        painter.drawPath(inset_inner_path)

        # Raised upper glass deck.
        upper_face = QPainterPath()
        upper_face.moveTo(
            bounds.left() + bounds.width() * 0.08, bounds.top() + bounds.height() * 0.18
        )
        upper_face.lineTo(
            bounds.left() + bounds.width() * 0.22, bounds.top() + bounds.height() * 0.04
        )
        upper_face.lineTo(
            bounds.right() - bounds.width() * 0.22,
            bounds.top() + bounds.height() * 0.04,
        )
        upper_face.lineTo(
            bounds.right() - bounds.width() * 0.08,
            bounds.top() + bounds.height() * 0.18,
        )
        upper_face.lineTo(
            bounds.right() - bounds.width() * 0.12,
            bounds.top() + bounds.height() * 0.34,
        )
        upper_face.lineTo(
            bounds.left() + bounds.width() * 0.12, bounds.top() + bounds.height() * 0.34
        )
        upper_face.closeSubpath()

        top_grad = QLinearGradient(
            0,
            bounds.top(),
            0,
            bounds.top() + bounds.height() * 0.36,
        )
        top_grad.setColorAt(0.00, QColor(235, 255, 248, 70))
        top_grad.setColorAt(0.35, QColor(110, 235, 190, 28))
        top_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.fillPath(upper_face, QBrush(top_grad))

        # Deep central recess in carbon area.
        recess = QPainterPath()
        recess.moveTo(
            bounds.left() + bounds.width() * 0.31,
            bounds.bottom() - bounds.height() * 0.04,
        )
        recess.lineTo(
            bounds.left() + bounds.width() * 0.40,
            bounds.bottom() - bounds.height() * 0.28,
        )
        recess.lineTo(
            bounds.left() + bounds.width() * 0.60,
            bounds.bottom() - bounds.height() * 0.28,
        )
        recess.lineTo(
            bounds.left() + bounds.width() * 0.69,
            bounds.bottom() - bounds.height() * 0.04,
        )
        recess.closeSubpath()

        recess_grad = QLinearGradient(
            0,
            bounds.bottom() - bounds.height() * 0.30,
            0,
            bounds.bottom(),
        )
        recess_grad.setColorAt(0.00, QColor(0, 0, 0, 20))
        recess_grad.setColorAt(0.45, QColor(0, 5, 4, 90))
        recess_grad.setColorAt(1.00, QColor(0, 2, 2, 215))
        painter.fillPath(recess, QBrush(recess_grad))

        # Directional edges.
        painter.setPen(QPen(QColor(185, 255, 230, 185), 1.5))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.22),
            int(bounds.top() + bounds.height() * 0.04),
            int(bounds.right() - bounds.width() * 0.22),
            int(bounds.top() + bounds.height() * 0.04),
        )

        painter.setPen(QPen(QColor(120, 240, 198, 110), 1.1))
        painter.drawLine(
            int(bounds.left() + bounds.width() * 0.08),
            int(bounds.top() + bounds.height() * 0.18),
            int(bounds.left() + bounds.width() * 0.02),
            int(bounds.top() + bounds.height() * 0.60),
        )

        painter.setPen(QPen(QColor(0, 7, 6, 185), 2.2))
        painter.drawLine(
            int(bounds.right() - bounds.width() * 0.08),
            int(bounds.top() + bounds.height() * 0.18),
            int(bounds.right() - bounds.width() * 0.02),
            int(bounds.top() + bounds.height() * 0.60),
        )

        # Broad but subtle glass reflection across the console crown.
        crown_reflection = QLinearGradient(
            bounds.left(),
            bounds.top(),
            bounds.right(),
            bounds.top(),
        )
        crown_reflection.setColorAt(0.00, QColor(255, 255, 255, 20))
        crown_reflection.setColorAt(0.28, QColor(190, 255, 230, 13))
        crown_reflection.setColorAt(0.62, QColor(80, 180, 150, 5))
        crown_reflection.setColorAt(1.00, QColor(0, 0, 0, 0))

        crown_path = QPainterPath()
        crown_path.moveTo(
            bounds.left() + bounds.width() * 0.09,
            bounds.top() + bounds.height() * 0.18,
        )
        crown_path.lineTo(
            bounds.left() + bounds.width() * 0.22,
            bounds.top() + bounds.height() * 0.045,
        )
        crown_path.lineTo(
            bounds.right() - bounds.width() * 0.22,
            bounds.top() + bounds.height() * 0.045,
        )
        crown_path.lineTo(
            bounds.right() - bounds.width() * 0.10,
            bounds.top() + bounds.height() * 0.18,
        )
        crown_path.lineTo(
            bounds.right() - bounds.width() * 0.14,
            bounds.top() + bounds.height() * 0.25,
        )
        crown_path.lineTo(
            bounds.left() + bounds.width() * 0.14,
            bounds.top() + bounds.height() * 0.25,
        )
        crown_path.closeSubpath()
        painter.fillPath(crown_path, QBrush(crown_reflection))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.buttons: list[CurvedConsoleButton] = []

        button_specs = (
            ("CHOOSE", -13.0),
            ("SCAN", 0.0),
            ("CANCEL", 0.0),
            ("ANALYZE", 0.0),
            ("APPROVE", 0.0),
            ("RESTORE", 0.0),
            ("BEDROCK", 0.0),
        )

        for text, angle in button_specs:
            button = CurvedConsoleButton(text, self, angle=angle)
            self.buttons.append(button)

        self.status_title = QLabel("SYSTEM STATUS", self)
        self.status_title.setObjectName("sectionLabel")

        self.log_title = QLabel("ACTIVITY LOG", self)
        self.log_title.setObjectName("sectionLabel")

        self.action_title = QLabel("QUICK ACTIONS", self)
        self.action_title.setObjectName("sectionLabel")

        self.status_text = QLabel(
            "● Local scan       Ready\n"
            "● PDF preview      Ready\n"
            "● CockroachDB      Not connected",
            self,
        )
        self.status_text.setObjectName("consoleText")

        self.bedrock_button = self.buttons[6]
        self.bedrock_button.setObjectName("bedrockButton")
        self.bedrock_button.setProperty("authState", "unknown")
        self.bedrock_button.setToolTip("Bedrock AWS session status.")
        self.lateral_screens_button = CurvedConsoleButton("S-SCREENS", self)
        self.lateral_screens_button.setObjectName("lateralScreensButton")
        self.lateral_screens_button.setToolTip(
            "Toggle side screens and single central screen mode."
        )

        self.log_text = QLabel(
            "Session started\n"
            "Read-only desktop cockpit loaded\n"
            "No files changed\n"
            "Awaiting authorized folder\n"
            "Human approval required for actions",
            self,
        )
        self.log_text.setObjectName("consoleText")

        self.quick_text = QLabel(
            "+ Choose folder\n◉ Scan PDFs\n▣ Preview selected PDF\nSettings planned",
            self,
        )
        self.quick_text.setObjectName("consoleText")

    def set_bedrock_auth_state(self, state: str) -> None:
        labels = {
            "connected": "BEDROCK ON",
            "disconnected": "BEDROCK LOGIN",
            "checking": "BEDROCK...",
            "unknown": "BEDROCK",
        }
        tooltips = {
            "connected": "AWS session is active for Bedrock calls.",
            "disconnected": "AWS login required. Click to open browser login.",
            "checking": "Checking or opening AWS login.",
            "unknown": "Bedrock client configured; AWS session not checked yet.",
        }
        clean_state = state if state in labels else "unknown"
        self.bedrock_button.setText(labels[clean_state])
        self.bedrock_button.setToolTip(tooltips[clean_state])
        self.bedrock_button.setProperty("authState", clean_state)
        self.bedrock_button.style().unpolish(self.bedrock_button)
        self.bedrock_button.style().polish(self.bedrock_button)
        self.bedrock_button.update()

    def carbon_path(self) -> QPainterPath:
        """Inset carbon silhouette aligned with every outer console face."""
        r = self.rect().adjusted(3, 3, -3, -3)
        x, y, w, h = map(float, (r.x(), r.y(), r.width(), r.height()))

        path = QPainterPath()
        path.moveTo(x + w * 0.105, y + h * 0.215)
        path.lineTo(x + w * 0.235, y + h * 0.075)
        path.lineTo(x + w * 0.765, y + h * 0.075)
        path.lineTo(x + w * 0.895, y + h * 0.215)
        path.lineTo(x + w * 0.945, y + h * 0.595)
        path.lineTo(x + w * 0.845, y + h * 0.890)
        path.lineTo(x + w * 0.705, y + h * 0.910)
        path.lineTo(x + w * 0.615, y + h * 0.690)
        path.lineTo(x + w * 0.385, y + h * 0.690)
        path.lineTo(x + w * 0.295, y + h * 0.910)
        path.lineTo(x + w * 0.155, y + h * 0.890)
        path.lineTo(x + w * 0.055, y + h * 0.595)
        path.closeSubpath()
        return path

    def upper_carbon_surface(self, x_center: float) -> tuple[float, float]:
        """Return y coordinate and tangent angle of the upper carbon face."""
        w = float(self.width())
        h = float(self.height())
        t = x_center / w

        left_x1, left_y1 = 0.105, 0.215
        left_x2, left_y2 = 0.235, 0.075
        right_x1, right_y1 = 0.765, 0.075
        right_x2, right_y2 = 0.895, 0.215

        if t < left_x2:
            local = (t - left_x1) / (left_x2 - left_x1)
            local = max(0.0, min(1.0, local))
            y_ratio = left_y1 + (left_y2 - left_y1) * local
            angle = math.degrees(
                math.atan2(
                    (left_y2 - left_y1) * h,
                    (left_x2 - left_x1) * w,
                )
            )
            return h * y_ratio, angle

        if t <= right_x1:
            return h * left_y2, 0.0

        local = (t - right_x1) / (right_x2 - right_x1)
        local = max(0.0, min(1.0, local))
        y_ratio = right_y1 + (right_y2 - right_y1) * local
        angle = math.degrees(
            math.atan2(
                (right_y2 - right_y1) * h,
                (right_x2 - right_x1) * w,
            )
        )
        return h * y_ratio, angle

    def shape_path(self) -> QPainterPath:
        r = self.rect().adjusted(3, 3, -3, -3)
        x, y, w, h = map(float, (r.x(), r.y(), r.width(), r.height()))

        path = QPainterPath()
        path.moveTo(x + w * 0.08, y + h * 0.18)
        path.lineTo(x + w * 0.22, y + h * 0.03)
        path.lineTo(x + w * 0.78, y + h * 0.03)
        path.lineTo(x + w * 0.92, y + h * 0.18)
        path.lineTo(x + w * 0.98, y + h * 0.60)
        path.lineTo(x + w * 0.87, y + h * 0.94)
        path.lineTo(x + w * 0.69, y + h * 0.96)
        path.lineTo(x + w * 0.60, y + h * 0.73)
        path.lineTo(x + w * 0.40, y + h * 0.73)
        path.lineTo(x + w * 0.31, y + h * 0.96)
        path.lineTo(x + w * 0.13, y + h * 0.94)
        path.lineTo(x + w * 0.02, y + h * 0.60)
        path.closeSubpath()
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        # CHOOSE and S-SCREENS follow the angled side faces.
        # SCAN through BEDROCK sit on the long flat axis.
        button_w = 118
        button_h = 62

        first_x = int(w * 0.165)
        first_surface_y, _ = self.upper_carbon_surface(first_x + button_w / 2)
        first_y = int(first_surface_y - button_h * 0.14 + h * 0.060)

        self.buttons[0].angle = -13.0
        self.buttons[0].setGeometry(
            first_x,
            first_y,
            button_w,
            button_h,
        )
        self.buttons[0].update_mask()
        self.buttons[0].update()

        flat_y = int(h * 0.108)
        flat_xs = (
            int(w * 0.248),
            int(w * 0.328),
            int(w * 0.408),
            int(w * 0.488),
            int(w * 0.568),
            int(w * 0.648),
        )

        for button, x_pos in zip(self.buttons[1:], flat_xs):
            button.angle = 0.0
            button.setGeometry(
                x_pos,
                flat_y,
                button_w,
                button_h,
            )
            button.update_mask()
            button.update()

        last_x = w - first_x - button_w
        last_surface_y, _ = self.upper_carbon_surface(last_x + button_w / 2)
        last_y = int(last_surface_y - button_h * 0.14 + h * 0.060)

        self.lateral_screens_button.setGeometry(
            last_x,
            last_y,
            button_w,
            button_h,
        )
        self.lateral_screens_button.angle = 13.0
        self.lateral_screens_button.update_mask()
        self.lateral_screens_button.update()

        # Keep all text blocks clear of the lower recess.
        title_y = int(h * 0.455)
        text_y = int(h * 0.525)
        text_h = int(h * 0.205)

        self.status_title.setGeometry(int(w * 0.17), title_y, 170, 22)
        log_title_y = title_y - int(h * 0.135)
        log_text_y = text_y - int(h * 0.155)

        self.log_title.setGeometry(int(w * 0.39), log_title_y, 170, 22)
        self.action_title.setGeometry(int(w * 0.715), title_y, 170, 22)

        self.status_text.setGeometry(int(w * 0.17), text_y, 270, text_h)
        self.log_text.setGeometry(
            int(w * 0.39),
            log_text_y,
            450,
            int(h * 0.215),
        )
        self.quick_text.setGeometry(int(w * 0.715), text_y, 250, text_h)


class CockpitWindow(QMainWindow):
    scan_finished = Signal()
    classification_finished = Signal()

    def __init__(  # noqa: PLR0913
        self,
        *,
        scan_function: ScanFunction = scan_authorized_root,
        integration_snapshot: RuntimeIntegrationSnapshot | None = None,
        classification_function: ClassificationFunction = classify_pdf_for_cockpit,
        review_decision_function: ReviewDecisionFunction = persist_review_decision,
        runtime_preflight_function: RuntimePreflightFunction | None = None,
        memory_evidence_function: MemoryEvidenceFunction = collect_memory_evidence,
        folder_memory: FolderMemory | None = None,
        bedrock_auth_probe_function: BedrockAuthProbeFunction = (
            probe_bedrock_aws_session
        ),
        bedrock_login_launcher: BedrockLoginLauncher = launch_aws_login,
    ) -> None:
        super().__init__()
        self._scan_function = scan_function
        self._classification_function = classification_function
        self._review_decision_function = review_decision_function
        self._runtime_preflight_function = runtime_preflight_function
        self._memory_evidence_function = memory_evidence_function
        self._bedrock_auth_probe_function = bedrock_auth_probe_function
        self._bedrock_login_launcher = bedrock_login_launcher
        self._bedrock_auth_probe_explicit = (
            bedrock_auth_probe_function is not probe_bedrock_aws_session
        )
        self._folder_memory = (
            folder_memory if folder_memory is not None else QtFolderMemory()
        )
        self._integration_snapshot = (
            integration_snapshot
            if integration_snapshot is not None
            else runtime_integration_snapshot()
        )
        self._runtime_preflight_report = _initial_runtime_preflight_report(
            runtime_preflight_function,
            integration_snapshot,
        )
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._classification_thread: QThread | None = None
        self._classification_worker: ClassificationWorker | None = None
        self._classification_batch_completed = 0
        self._classification_batch_failed = 0
        self._classification_batch_total = 0
        self._memory_evidence_report: MemoryEvidenceReport | None = None
        self._memory_evidence_error: str | None = None
        self._bedrock_auth_state = "unknown"
        self._bedrock_login_poll_attempts = 0
        self._review_expanded = False
        self._center_expanded = False
        self._selected_document_row: int | None = None
        self._review_ledger = InMemoryReviewDecisionLedger()
        self._restore_audit_trail = AppendOnlyAuditTrail()
        self._workspace = DesktopWorkspaceSession()

        self.setWindowTitle("DocWeave Cockpit")
        self.resize(1760, 1080)
        self.setMinimumSize(1460, 900)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.root = QWidget()
        self.root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCentralWidget(self.root)

        # Side screens are hosted in a QGraphicsScene so the complete widgets
        # can be rotated: frame, table, text and controls all tilt together.
        self.side_view = QGraphicsView(self.root)
        self.side_view.setFrameShape(QFrame.Shape.NoFrame)
        self.side_view.setStyleSheet("background: transparent; border: none;")
        self.side_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.side_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.side_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.side_view.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.side_view.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.side_view.setInteractive(True)

        self.side_scene = QGraphicsScene(self.side_view)
        self.side_scene.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.side_view.setScene(self.side_scene)

        self.left = LeftScreen(self)
        self.right = RightScreen()

        self.left_proxy = self.side_scene.addWidget(self.left)
        self.right_proxy = self.side_scene.addWidget(self.right)

        # Strong, visible outward inclination.
        self.left_proxy.setRotation(-6.0)
        self.right_proxy.setRotation(6.0)

        self.center = CenterPreview(self.root)
        self.console = ConsolePanel(self.root)

        self.left.document_selected.connect(self._open_document_row)
        self.console.buttons[0].clicked.connect(self._choose_folder)
        self.console.buttons[1].clicked.connect(self.start_scan)
        self.console.buttons[2].clicked.connect(self.cancel_scan)
        self.console.buttons[3].clicked.connect(self._analyze_selected_document)
        self.console.buttons[4].clicked.connect(self._open_batch_review)
        self.console.buttons[5].clicked.connect(self._open_restore_for_selected)
        self.console.bedrock_button.clicked.connect(self._handle_bedrock_button_clicked)
        self.console.lateral_screens_button.clicked.connect(
            self._toggle_lateral_screens
        )
        self.center.review_approve_requested.connect(self._approve_review_row)
        self.center.review_reject_requested.connect(self._reject_review_row)
        self.center.review_preview_requested.connect(self._preview_review_row)
        self.center.review_approve_all_requested.connect(self._approve_all_review_rows)
        self.console.buttons[3].setEnabled(False)
        self.console.buttons[3].setToolTip(
            "Run configured classification for ready PDFs."
        )
        self.console.buttons[4].setEnabled(False)
        self.console.buttons[4].setToolTip(
            "Open the batch review table for proposed renames."
        )
        self.console.buttons[5].setEnabled(False)
        self.console.buttons[5].setToolTip(
            "Reject the selected review proposal without moving files."
        )

        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: transparent;
                color: #EAF5F1;
                font-family: "Segoe UI";
            }

            QLabel#brand {
                color: #FF3B3B;
                font-size: 20px;
                font-weight: 800;
                letter-spacing: 0.7px;
                background: transparent;
            }

            QLabel#screenTitle {
                color: #FF3B3B;
                font-size: 19px;
                font-weight: 800;
                letter-spacing: 0.4px;
                background: transparent;
            }

            QLabel#sectionLabel {
                color: #FF4C4C;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.5px;
                background: transparent;
            }

            QLabel#online {
                color: #FF3B3B;
                font-size: 13px;
                font-weight: 800;
                background: transparent;
            }

            QLabel#muted {
                color: #FF6A6A;
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }

            QLabel#consoleText {
                color: #F4FFFB;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0;
            }

            QTableWidget#documentTable {
                background: rgba(4, 8, 8, 235);
                border: 1px solid rgba(170, 255, 225, 132);
                border-radius: 8px;
                color: #F1FBF7;
                outline: none;
                selection-background-color: rgba(73, 179, 144, 75);
                selection-color: #FFFFFF;
                font-size: 13px;
            }

            QTableWidget#documentTable::item {
                border-bottom: 1px solid rgba(89, 198, 162, 28);
                padding: 7px;
            }

            QHeaderView::section {
                background: rgba(20, 26, 24, 230);
                border: none;
                border-bottom: 1px solid rgba(89, 198, 162, 80);
                color: #D7F4EA;
                font-size: 13px;
                font-weight: 800;
                padding: 8px;
            }

            QFrame#metric {
                background: rgba(16, 22, 21, 210);
                border: 1px solid rgba(155, 250, 218, 95);
                border-radius: 9px;
            }

            QLabel#metricValue {
                color: #EAF5F1;
                font-size: 27px;
                font-weight: 800;
            }

            QLabel#metricLabel {
                color: #BDE7D8;
                font-size: 12px;
                font-weight: 800;
            }

            QFrame#eventRow {
                background: rgba(5, 10, 9, 228);
                border-left: 2px solid rgba(125, 240, 200, 165);
                border-radius: 5px;
            }

            QLabel#eventName {
                color: #67D8B0;
                font-size: 13px;
                font-weight: 800;
            }

            QLabel#eventText {
                color: #EDF7F3;
                font-size: 13px;
                font-weight: 700;
            }

            QTableWidget#memoryTable {
                background: rgba(4, 8, 8, 238);
                border: 1px solid rgba(125, 240, 200, 120);
                border-radius: 6px;
                color: #F3FFF9;
                gridline-color: rgba(103, 216, 176, 60);
                alternate-background-color: rgba(22, 36, 32, 180);
                font-size: 13px;
                font-weight: 700;
                outline: none;
            }

            QTableWidget#memoryTable::item {
                padding-left: 6px;
            }

            QTableWidget#memoryTable QHeaderView::section {
                background: rgba(20, 26, 24, 240);
                border: none;
                border-bottom: 1px solid rgba(103, 216, 176, 125);
                color: #67D8B0;
                font-size: 12px;
                font-weight: 900;
                padding: 4px;
            }

            QTableWidget#reviewTable {
                background: rgba(4, 8, 8, 238);
                border: 1px solid rgba(125, 240, 200, 120);
                border-radius: 6px;
                color: #F3FFF9;
                gridline-color: rgba(103, 216, 176, 60);
                alternate-background-color: rgba(22, 36, 32, 180);
                font-size: 12px;
                font-weight: 700;
                outline: none;
            }

            QTableWidget#reviewTable::item {
                border-bottom: 1px solid rgba(89, 198, 162, 30);
                padding: 7px;
            }

            QTableWidget#reviewTable QHeaderView::section {
                background: rgba(20, 26, 24, 240);
                border: none;
                border-bottom: 1px solid rgba(103, 216, 176, 125);
                color: #67D8B0;
                font-size: 12px;
                font-weight: 900;
                padding: 5px;
            }

            QPushButton {
                color: #E6F6F0;
                background: rgba(14, 20, 19, 215);
                border: 1px solid rgba(145, 245, 210, 100);
                border-radius: 8px;
                padding: 6px 11px;
                font-weight: 700;
            }

            QPushButton:hover {
                background: rgba(38, 132, 104, 165);
                border-color: #9CFFE0;
            }

            QPushButton:pressed {
                background: #091F1A;
            }

            QPushButton#windowButton {
                background: rgba(10, 35, 29, 190);
                border: 1px solid rgba(103, 216, 176, 72);
                border-radius: 7px;
                padding: 0;
                font-size: 14px;
            }

            QPushButton#smallButton {
                font-size: 9px;
                min-width: 44px;
            }

            QPushButton#reviewApproveButton {
                color: #66FFB8;
                background: rgba(2, 38, 23, 245);
                border: 2px solid rgba(104, 255, 184, 255);
                border-radius: 9px;
                font-weight: 900;
                padding: 0;
            }

            QPushButton#reviewApproveButton:hover {
                color: #FFFFFF;
                background: rgba(9, 126, 74, 255);
                border: 2px solid rgba(185, 255, 222, 255);
            }

            QPushButton#reviewRejectButton {
                color: #FF4F5F;
                background: rgba(48, 8, 10, 238);
                border: 2px solid rgba(255, 80, 92, 255);
                border-radius: 9px;
                font-weight: 900;
                padding: 0;
            }

            QPushButton#reviewRejectButton:hover {
                color: #FFFFFF;
                background: rgba(132, 22, 24, 245);
                border: 2px solid rgba(255, 142, 142, 255);
            }

            QPushButton#reviewPreviewButton {
                color: #E6F6F0;
                background: rgba(10, 42, 34, 225);
                border: 1px solid rgba(145, 245, 210, 125);
                border-radius: 9px;
                font-size: 10px;
                font-weight: 900;
                padding: 0;
            }

            QPushButton#consoleButton {
                background: rgba(10, 42, 34, 225);
                border: 1px solid rgba(145, 245, 210, 125);
                border-bottom: 3px solid rgba(0, 10, 8, 185);
                border-radius: 13px;
                letter-spacing: 0;
                font-size: 12px;
                padding-top: 2px;
            }

            QPushButton#consoleButton:hover {
                background: rgba(30, 105, 84, 210);
                border-color: rgba(175, 255, 228, 190);
            }

            QPushButton#consoleButton:pressed {
                background: rgba(5, 28, 23, 235);
                border-bottom: 1px solid rgba(0, 8, 6, 210);
                padding-top: 4px;
            }

            QPushButton#bedrockButton {
                border-radius: 13px;
                border-bottom: 3px solid rgba(0, 10, 8, 185);
                font-size: 10px;
                font-weight: 900;
                letter-spacing: 0;
                padding-top: 2px;
            }

            QPushButton#bedrockButton[authState="connected"] {
                color: #061411;
                background: rgba(103, 216, 176, 235);
                border: 1px solid rgba(202, 255, 235, 235);
                border-bottom: 3px solid rgba(0, 10, 8, 185);
            }

            QPushButton#bedrockButton[authState="disconnected"] {
                color: #FFFFFF;
                background: rgba(178, 34, 34, 235);
                border: 1px solid rgba(255, 114, 114, 235);
                border-bottom: 3px solid rgba(0, 10, 8, 185);
            }

            QPushButton#bedrockButton[authState="checking"] {
                color: #1B1202;
                background: rgba(225, 171, 77, 230);
                border: 1px solid rgba(255, 222, 150, 235);
                border-bottom: 3px solid rgba(0, 10, 8, 185);
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: rgba(103, 216, 176, 90);
                border-radius: 4px;
                min-height: 24px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        self._set_status(
            "Ready. Choose an authorized folder; no files will be changed."
        )
        if runtime_preflight_function is None and integration_snapshot is None:
            self._refresh_runtime_preflight_report()
            self._refresh_bedrock_auth_status()
            self._set_status(
                "Ready. Runtime integrations checked; choose an authorized folder."
            )

    @property
    def authorized_root(self) -> Path | None:
        return self._workspace.snapshot.authorized_root

    @property
    def scan_in_progress(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.isRunning()

    @property
    def classification_in_progress(self) -> bool:
        return (
            self._classification_thread is not None
            and self._classification_thread.isRunning()
        )

    def set_authorized_root(self, root: Path) -> None:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError("authorized root must be a directory")
        if self.scan_in_progress or self.classification_in_progress:
            raise RuntimeError("authorized root cannot change during active work")
        self._workspace.authorize(resolved)
        self._selected_document_row = None
        self.left.set_documents([])
        self.right.set_metrics(0, 0, 0)
        self._remember_authorized_root(resolved)
        self._set_status(f"Authorized folder: {resolved}")

    @Slot()
    def start_scan(self) -> None:
        authorized_root = self.authorized_root
        if authorized_root is None:
            self._set_status("Choose a folder before starting a scan.")
            return
        if self.scan_in_progress:
            return

        self._selected_document_row = None
        self.left.set_documents([])
        self._workspace.start_scan()
        self.right.set_metrics(0, 0, 0)
        self._set_busy(True)
        self._set_status("Scanning PDFs in the background. No files are changed.")

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
        if not self.scan_in_progress or self._scan_worker is None:
            return
        self._workspace.request_cancellation()
        self._scan_worker.request_cancellation()
        self.console.buttons[2].setEnabled(False)
        self._set_status("Cancelling at the next safe file boundary.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.scan_in_progress:
            self._set_status("Scan still running. Wait before closing DocWeave.")
            event.ignore()
            return
        if self.classification_in_progress:
            self._set_status(
                "Classification still running. Wait before closing DocWeave."
            )
            event.ignore()
            return
        event.accept()

    @Slot(object)
    def _handle_scan_progress(self, raw_progress: object) -> None:
        if not isinstance(raw_progress, ScanProgress):
            self.cancel_scan()
            self._set_status("Invalid scan progress. Cancellation requested safely.")
            return
        try:
            self._workspace.record_progress(raw_progress)
        except (RuntimeError, ValueError):
            self.cancel_scan()
            self._set_status(
                "Inconsistent scan progress. Cancellation requested safely."
            )
            return
        if raw_progress.phase is ScanPhase.DISCOVERY:
            self.right.set_metrics(raw_progress.completed, 0, 0)
            self._set_status(f"Discovering files: {raw_progress.completed} observed.")
            return
        total = raw_progress.total or 0
        self.right.set_metrics(total, 0, 0)
        self._set_status(f"Inspecting PDFs: {raw_progress.completed} of {total}.")

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
        documents = [
            Document(
                name=record.absolute_path.name,
                category=(
                    "PDF" if record.status is IntakeStatus.READY else "Needs check"
                ),
                pages="-",
                status="READY" if record.status is IntakeStatus.READY else "ATTENTION",
                path=record.absolute_path,
            )
            for record in raw_result.intake.records
        ]
        self.left.set_documents(documents)
        self.right.set_metrics(
            len(raw_result.discovery.files),
            raw_result.intake.ready_count,
            raw_result.attention_count,
        )
        self._set_status(
            f"Scan complete: {len(raw_result.discovery.files)} files inspected. "
            "No files were changed."
        )

    @Slot()
    def _handle_scan_cancelled(self) -> None:
        self._workspace.cancel()
        self.left.set_documents([])
        self.right.set_metrics(0, 0, 0)
        self._set_status("Scan cancelled safely. Partial results were discarded.")

    @Slot(str)
    def _handle_scan_failed(self, error_category: str) -> None:
        if self._workspace.snapshot.phase in {
            WorkspacePhase.SCANNING,
            WorkspacePhase.CANCELLING,
        }:
            self._workspace.fail(error_category)
        self._set_status(f"Scan failed safely ({error_category}). No files changed.")

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
            self._folder_dialog_start_directory(),
        )
        if not selected:
            return
        try:
            self.set_authorized_root(Path(selected))
        except (OSError, RuntimeError) as error:
            self._set_status(
                f"Folder authorization failed safely ({error.__class__.__name__})."
            )

    def _folder_dialog_start_directory(self) -> str:
        authorized_root = self.authorized_root
        if authorized_root is not None:
            return str(authorized_root)
        if DEFAULT_DEMO_DOCUMENT_FOLDER.is_dir():
            return str(DEFAULT_DEMO_DOCUMENT_FOLDER)
        remembered = self._folder_memory.last_authorized_folder()
        if remembered is None:
            return ""
        return str(remembered)

    def _remember_authorized_root(self, root: Path) -> None:
        try:
            self._folder_memory.remember_authorized_folder(root)
        except OSError:
            return

    @Slot(int)
    def _open_document_row(self, row: int) -> None:  # noqa: PLR0911
        self._set_review_expanded(False, keep_center_expanded=True)
        document = self.left.document_at(row)
        root = self.authorized_root
        if document is None or document.path is None or root is None:
            self._set_status("No ready PDF is available for preview.")
            return
        self._selected_document_row = row
        if document.status == "REVIEW":
            try:
                validated_path = validate_pdf_for_open(document.path, root)
            except PdfOpenValidationError as error:
                self._set_status(
                    f"PDF preview blocked safely ({error.category.value})."
                )
                return
            self.center.open_document(validated_path)
            self.center.show_memory_trace(
                summary=_review_memory_trace_summary(document),
                detail=_review_memory_trace_detail(document),
            )
            self._set_busy(False)
            lineage_label = _lineage_preview_label(document.lineage_preview)
            self._set_status(
                "Review proposal selected. Approve or reject without changing files."
            )
            self.right.set_events(
                [
                    ("REVIEW", f"Proposal for {document.category}"),
                    (
                        "TARGET",
                        document.proposed_destination
                        or "No rename/move target available",
                    ),
                    ("LINEAGE", lineage_label),
                    ("APPROVAL", "Human decision required"),
                    ("MEMORY", "CockroachDB lineage row prepared"),
                    ("SECURITY", "No file mutation performed"),
                ]
            )
            return
        if document.status in {"APPROVED", "MOVED"}:
            try:
                validated_path = validate_pdf_for_open(document.path, root)
            except PdfOpenValidationError as error:
                self._set_status(
                    f"PDF preview blocked safely ({error.category.value})."
                )
                return
            self.center.open_document(validated_path)
            self.center.show_memory_trace(
                summary=_review_memory_trace_summary(document),
                detail=_review_memory_trace_detail(document),
            )
            self._set_busy(False)
            self._set_status("Approved PDF selected; original path history is visible.")
            self.right.set_events(
                [
                    ("CURRENT", document.path.name if document.path else document.name),
                    ("ORIGINAL", _original_path_label(document.lineage_preview)),
                    ("CURRENT DIR", _current_path_label(document)),
                    ("MEMORY", "CockroachDB file_history recorded"),
                    ("SECURITY", "Original path remains traceable"),
                ]
            )
            return
        if document.status != "READY":
            self._set_status("Only ready or approved PDFs can be previewed safely.")
            return
        try:
            validated_path = validate_pdf_for_open(document.path, root)
        except PdfOpenValidationError as error:
            self._set_status(f"PDF preview blocked safely ({error.category.value}).")
            return
        self.center.open_document(validated_path)
        self._set_busy(False)
        self._set_status("PDF preview raised inside DocWeave. No files were changed.")

    @Slot()
    def _analyze_selected_document(self) -> None:
        root = self.authorized_root
        if root is None:
            self._set_status(
                "Choose and scan an authorized folder before classification."
            )
            return
        if self.left.document_count == 0:
            self._set_status("Scan ready PDFs before classification.")
            return
        if self.scan_in_progress or self.classification_in_progress:
            return
        self._refresh_runtime_preflight_report()
        if self._should_probe_bedrock_auth():
            self._refresh_bedrock_auth_status()
        runtime_block = _classification_preflight_block(self._runtime_preflight_report)
        if runtime_block is not None:
            self._set_status(
                f"Runtime is not ready for classification ({runtime_block})."
            )
            self.right.set_events(
                [
                    ("CLASSIFIER", "Not started"),
                    ("CONFIG", f"Blocked {runtime_block}"),
                    ("MEMORY", "No proposal attempted"),
                    ("BEDROCK", "No model invocation"),
                    ("SECURITY", "No file mutation performed"),
                ]
            )
            return
        if self._bedrock_auth_state == "disconnected":
            self._set_status("Bedrock login required before classification.")
            self.right.set_events(
                [
                    ("CLASSIFIER", "Not started"),
                    ("BEDROCK", "AWS login required"),
                    ("ACTION", "Press red Bedrock button"),
                    ("MEMORY", "No proposal attempted"),
                    ("SECURITY", "No file mutation performed"),
                ]
            )
            return

        batch_items = self._classification_batch_items(root)
        if not batch_items:
            self._set_status("No ready PDFs are available for classification.")
            return

        thread = QThread(self)
        worker = ClassificationWorker(
            batch_items,
            root,
            self._classification_function,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(self._handle_classification_progress)
        worker.item_failed.connect(self._handle_classification_item_failed)
        worker.completed.connect(self._handle_classification_completed)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._handle_classification_thread_finished)
        self._classification_thread = thread
        self._classification_worker = worker
        self._classification_batch_completed = 0
        self._classification_batch_failed = 0
        self._classification_batch_total = len(batch_items)
        self._set_busy(True)
        self._set_status(
            f"Classifying {len(batch_items)} ready PDF(s) through configured runtime."
        )
        thread.start()

    @Slot(object)
    def _handle_classification_progress(self, raw_progress: object) -> None:
        if not isinstance(raw_progress, ClassificationBatchProgress):
            self._handle_classification_failed("InvalidClassificationResult")
            return
        self._classification_batch_completed = raw_progress.completed
        self._classification_batch_total = raw_progress.total
        result = raw_progress.result
        (
            proposed_destination,
            proposed_action,
            lineage_preview,
        ) = self._organization_preview_for(
            raw_progress.source_path,
            result,
        )
        self.left.mark_document_for_review(
            raw_progress.row,
            proposed_class=result.proposed_class,
            proposed_destination=proposed_destination,
            document_id=None if result.document_id is None else str(result.document_id),
            proposal_id=None if result.proposal_id is None else str(result.proposal_id),
            proposal_fingerprint=result.proposal_fingerprint,
            lineage_preview=lineage_preview,
        )
        self.right.set_metrics(
            self.left.document_count,
            self.left.count_status("READY"),
            self.left.count_status("REVIEW"),
        )
        self.center.show_classification_result(result)
        self.center.show_memory_trace(
            summary=_classification_memory_trace_summary(result),
            detail=_classification_memory_trace_detail(
                result,
                proposed_action=proposed_action,
                proposed_destination=proposed_destination,
                lineage_preview=lineage_preview,
            ),
        )
        self._set_status(
            f"Classification {raw_progress.completed}/{raw_progress.total} persisted "
            f"with {self._classification_batch_failed} failed: "
            f"{result.proposed_class}; "
            f"tokens {result.total_tokens}."
        )
        confidence_label = (
            "n/a" if result.raw_confidence is None else result.raw_confidence
        )
        retry_label = (
            "No validation retry"
            if result.retry_attempts == 0
            else f"Validation retries {result.retry_attempts}"
        )
        rationale = _compact_console_text(result.rationale, maximum=96)
        self.console.log_text.setText(
            f"Classification batch {raw_progress.completed}/{raw_progress.total}\n"
            f"Failed so far: {self._classification_batch_failed}\n"
            f"Document: {raw_progress.source_path.name}\n"
            f"Class: {result.proposed_class}\n"
            f"Confidence: {confidence_label}\n"
            f"Mass operation preview: {proposed_action or 'unavailable'}\n"
            f"Proposed target: {proposed_destination or 'unavailable'}\n"
            f"Lineage preview: {_lineage_preview_label(lineage_preview)}\n"
            f"Evidence items: {result.evidence_count}; "
            f"metadata fields: {result.metadata_count}\n"
            f"Rationale: {rationale}"
        )
        self.right.set_events(
            [
                (
                    "CLASSIFIER",
                    f"{raw_progress.completed}/{raw_progress.total} persisted",
                ),
                ("PROPOSAL", f"Proposed {result.proposed_class}"),
                ("EVIDENCE", f"{result.evidence_count} cited spans"),
                ("CONFIDENCE", f"Raw {confidence_label}"),
                ("MEMORY", f"Proposal {result.proposal_disposition}"),
                (
                    "OPERATION",
                    f"{proposed_action} preview ready"
                    if proposed_destination is not None
                    else "Operation preview unavailable",
                ),
                ("LINEAGE", _lineage_preview_label(lineage_preview)),
                ("BEDROCK", f"{result.total_tokens} tokens; {retry_label}"),
                ("SECURITY", "No file mutation performed"),
            ]
        )

    @Slot(object)
    def _handle_classification_item_failed(self, raw_failure: object) -> None:
        if not isinstance(raw_failure, ClassificationBatchFailure):
            self._handle_classification_failed("InvalidClassificationFailure")
            return
        if raw_failure.error_category == "bedrock:authentication_failed":
            self._bedrock_auth_state = "disconnected"
            self.console.set_bedrock_auth_state("disconnected")
        self._classification_batch_completed = raw_failure.completed
        self._classification_batch_failed = raw_failure.failed
        self._classification_batch_total = raw_failure.total
        self._set_status(
            f"Classification item failed safely ({raw_failure.error_category}). "
            f"{raw_failure.completed} persisted, {raw_failure.failed} failed, "
            f"{raw_failure.total - raw_failure.attempted} queued."
        )
        self.console.log_text.setText(
            "Classification item failed safely.\n"
            f"Document: {raw_failure.source_path.name}\n"
            f"Error: {raw_failure.error_category}\n"
            f"Persisted: {raw_failure.completed}/{raw_failure.total}; "
            f"failed: {raw_failure.failed}\n"
            "The failed document remains READY for a later Analyze retry."
        )
        self.right.set_events(
            [
                (
                    "CLASSIFIER",
                    f"{raw_failure.completed} persisted; {raw_failure.failed} failed",
                ),
                ("ERROR", raw_failure.error_category[:42]),
                ("RETRY", "Failed item remains ready"),
                ("READY", f"{self.left.count_status('READY')} ready remaining"),
                ("SECURITY", "No file mutation performed"),
            ]
        )

    @Slot(object)
    def _handle_classification_completed(self, raw_summary: object) -> None:
        if not isinstance(raw_summary, ClassificationBatchSummary):
            self._handle_classification_failed("InvalidClassificationSummary")
            return
        self._classification_batch_completed = raw_summary.completed
        self._classification_batch_failed = raw_summary.failed
        self._classification_batch_total = raw_summary.total
        self._refresh_memory_evidence()
        self.console.log_text.setText(
            f"Classification batch complete: {raw_summary.completed} of "
            f"{raw_summary.total} proposal(s) persisted for human review.\n"
            f"Failed item(s): {raw_summary.failed}; "
            "ready documents remain eligible for retry."
            + (
                f"\nLast error: {raw_summary.last_error_category}"
                if raw_summary.last_error_category is not None
                else ""
            )
        )
        self.right.set_events(
            [
                (
                    "CLASSIFIER",
                    f"{raw_summary.completed}/{raw_summary.total} persisted",
                ),
                (
                    "FAILED",
                    (f"{raw_summary.failed} item(s); {raw_summary.last_error_category}")
                    if raw_summary.last_error_category is not None
                    else f"{raw_summary.failed} item(s)",
                ),
                ("REVIEW", f"{self.left.count_status('REVIEW')} awaiting human review"),
                ("READY", f"{self.left.count_status('READY')} ready remaining"),
                ("OPERATION", "Mass rename/move previews ready"),
                (
                    "MEMORY",
                    _memory_evidence_status(
                        self._memory_evidence_report,
                        self._memory_evidence_error,
                        self._runtime_preflight_report,
                        self._integration_snapshot,
                    ),
                ),
                ("SECURITY", "No file mutation performed"),
            ]
        )

    @Slot(str)
    def _handle_classification_failed(self, error_category: str) -> None:
        if error_category == "bedrock:authentication_failed":
            self._bedrock_auth_state = "disconnected"
            self.console.set_bedrock_auth_state("disconnected")
        batch_total = self._classification_batch_total
        batch_completed = self._classification_batch_completed
        progress_label = (
            "No proposal persisted"
            if batch_total == 0
            else f"{batch_completed}/{batch_total} proposal(s) persisted"
        )
        self.console.log_text.setText(
            f"Classification batch failed safely ({error_category}).\n"
            f"{progress_label} before the failure.\n"
            "Ready documents remain eligible for a later Analyze retry."
        )
        self.right.set_events(
            [
                ("CLASSIFIER", "Failed closed"),
                ("ERROR", error_category[:42]),
                ("MEMORY", progress_label),
                ("REVIEW", f"{self.left.count_status('REVIEW')} awaiting review"),
                ("READY", f"{self.left.count_status('READY')} ready to retry"),
                ("SECURITY", "No file mutation performed"),
            ]
        )

    @Slot()
    def _handle_classification_thread_finished(self) -> None:
        self._classification_thread = None
        self._classification_worker = None
        self._set_busy(False)
        self.classification_finished.emit()

    @Slot()
    def _approve_selected_review(self) -> None:
        self._record_selected_review_decision(ReviewDecisionAction.APPROVE)

    @Slot()
    def _open_batch_review(self) -> None:
        rows = self._batch_review_rows()
        if not rows:
            self._set_status("No review proposals are ready for batch approval.")
            return
        self._set_review_expanded(True)
        self.center.show_review_table(rows)
        self._set_status(
            f"Batch review ready: {len(rows)} proposed rename(s) awaiting decision."
        )
        self.right.set_events(
            [
                ("REVIEW", f"{len(rows)} pending proposals"),
                ("ACTION", "Approve, reject, or preview per row"),
                ("MEMORY", "Decisions remain append-only"),
            ]
        )

    def _batch_review_rows(self) -> list[tuple[int, str, str, str]]:
        rows: list[tuple[int, str, str, str]] = []
        for row in range(self.left.document_count):
            document = self.left.document_at(row)
            if document is None or document.status != "REVIEW":
                continue
            original = _review_original_name_label(document.lineage_preview)
            proposed_name = _review_proposed_name_label(document.lineage_preview)
            directory = _review_proposed_directory_label(document.lineage_preview)
            if original == "Original name unavailable":
                original = document.name
            if proposed_name == "Proposed name unavailable":
                proposed_name = _filename_from_destination(
                    document.proposed_destination,
                    fallback=document.name,
                )
            if directory == "Suggested directory unavailable":
                directory = _directory_from_destination(document.proposed_destination)
            rows.append((row, original, proposed_name, directory))
        return rows

    @Slot(int)
    def _approve_review_row(self, row: int) -> None:
        self._selected_document_row = row
        self._record_selected_review_decision(ReviewDecisionAction.APPROVE)
        self._open_batch_review()

    @Slot(int)
    def _reject_review_row(self, row: int) -> None:
        self._selected_document_row = row
        self._record_selected_review_decision(
            ReviewDecisionAction.REJECT,
            reason="Reviewer rejected the local proposal.",
        )
        self._open_batch_review()

    @Slot(int)
    def _preview_review_row(self, row: int) -> None:
        self._close_batch_review(preview_row=row)

    @Slot()
    def _toggle_lateral_screens(self) -> None:
        self._set_center_expanded(not self._center_expanded)
        if self._center_expanded:
            self._set_status("Single central screen mode enabled.")
            return
        self._set_status("Side screens restored.")

    def _set_review_expanded(
        self,
        expanded: bool,
        *,
        keep_center_expanded: bool = False,
    ) -> None:
        if self._review_expanded == expanded:
            return
        self._review_expanded = expanded
        self._set_center_expanded(expanded, keep_expanded=keep_center_expanded)

    def _set_center_expanded(
        self,
        expanded: bool,
        *,
        keep_expanded: bool = False,
    ) -> None:
        if keep_expanded and self._center_expanded:
            expanded = True
        if self._center_expanded != expanded:
            self._center_expanded = expanded
        self.side_view.setVisible(not self._center_expanded)
        self.resizeEvent(None)

    @Slot()
    def _close_batch_review(self, *, preview_row: int | None = None) -> None:
        self._set_review_expanded(False, keep_center_expanded=preview_row is not None)
        self.center.review_title.hide()
        self.center.review_approve_all.hide()
        self.center.review_table.hide()
        row = self._selected_document_row if preview_row is None else preview_row
        if row is None:
            self._set_status("Batch review closed. Side screens restored.")
            return
        document = self.left.document_at(row)
        root = self.authorized_root
        if document is None or document.path is None or root is None:
            self._set_status("Batch review closed. Side screens restored.")
            return
        try:
            validated_path = validate_pdf_for_open(document.path, root)
        except PdfOpenValidationError as error:
            self._set_status(f"PDF preview blocked safely ({error.category.value}).")
            return
        self._selected_document_row = row
        self.center.open_document(validated_path)
        self._set_status("Batch review closed. Side screens restored.")

    @Slot()
    def _approve_all_review_rows(self) -> None:
        rows = [
            row
            for row, _original, _proposed_name, _directory in self._batch_review_rows()
        ]
        if not rows:
            self._set_status("No review proposals remain to approve.")
            return
        approved = 0
        for row in rows:
            document = self.left.document_at(row)
            if document is None or document.status != "REVIEW":
                continue
            self._selected_document_row = row
            self._record_selected_review_decision(ReviewDecisionAction.APPROVE)
            approved += 1
        self._open_batch_review()
        self._set_status(f"Batch approval completed: {approved} proposal(s) approved.")

    @Slot()
    def _reject_selected_review(self) -> None:
        self._record_selected_review_decision(
            ReviewDecisionAction.REJECT,
            reason="Reviewer rejected the local proposal.",
        )

    @Slot()
    def _open_restore_for_selected(self) -> None:
        document = self._selected_restorable_document()
        if document is None or document.lineage_preview is None:
            self._set_status(
                "Select a moved document with retained file history before restore."
            )
            return
        row = self._selected_document_row
        root = self.authorized_root
        if row is None or root is None:
            self._set_status("Restore blocked: no authorized root is active.")
            return
        try:
            original_plan, original_result = self._restore_original_operation_for(
                document,
                root,
            )
            restore_plan = plan_restore_operation(original_plan, original_result)
        except (OSError, ValueError) as error:
            self._set_status(
                f"Restore blocked before preview ({error.__class__.__name__})."
            )
            return
        if not restore_plan.is_ready:
            self._set_status(f"Restore blocked safely: {restore_plan.reason.value}.")
            self.center.show_memory_trace(
                summary="Restore blocked by deterministic file-history checks.",
                detail=(
                    f"Current: {document.lineage_preview.next_relative_path}; "
                    f"original: {document.lineage_preview.original_relative_path}; "
                    f"reason: {restore_plan.reason.value}."
                ),
            )
            return
        restore_id = str(uuid4())
        approved_at = datetime.now(UTC)
        approval = approve_restore_plan(
            restore_plan,
            approval_id=restore_id,
            approved_by_user_id="local-cockpit-reviewer",
            approved_at_utc=approved_at,
            expires_at_utc=approved_at + timedelta(minutes=15),
        )
        audit_context = RestoreAuditContext(
            workspace_id="local-cockpit",
            batch_id="single-restore",
            batch_item_id=restore_id,
            actor_id="local-cockpit-reviewer",
            correlation_id=restore_id,
            occurred_at_utc=approved_at,
        )
        append_restore_approval_audit_event(
            self._restore_audit_trail,
            restore_plan,
            approval,
            audit_context,
        )
        self.center.release_document_handle()
        result = execute_restore_operation(
            restore_plan,
            approval,
            restore_id=restore_id,
            now_utc=approved_at,
        )
        append_restore_execution_audit_event(
            self._restore_audit_trail,
            restore_plan,
            result,
            audit_context,
        )
        if result.status is not RestoreExecutionStatus.SUCCEEDED:
            self._set_status(f"Restore failed safely: {result.reason.value}.")
            self.center.show_memory_trace(
                summary="Restore execution did not mutate to the requested state.",
                detail=(
                    f"Restore id {restore_id[:8]}; reason {result.reason.value}; "
                    f"current {document.lineage_preview.next_relative_path}; "
                    f"original {document.lineage_preview.original_relative_path}."
                ),
            )
            return
        restored_path = root / document.lineage_preview.original_relative_path
        self.left.record_review_decision(
            row,
            status="RESTORED",
            review_decision_id=restore_id,
            path=restored_path,
            name=document.lineage_preview.original_filename,
        )
        self.right.set_metrics(
            self.left.document_count,
            self.left.count_status("READY"),
            self.left.count_status("REVIEW"),
        )
        self._set_status("Restore completed: file moved back to its original path.")
        self.center.show_memory_trace(
            summary="Restore approved and executed from persistent file history.",
            detail=(
                f"Restore {restore_id[:8]}; "
                f"{document.lineage_preview.next_relative_path} -> "
                f"{document.lineage_preview.original_relative_path}; "
                "append-only restore approval and execution audit recorded."
            ),
        )
        self.right.set_events(
            [
                ("RESTORE", "Succeeded"),
                ("CURRENT", document.lineage_preview.original_relative_path),
                ("PREVIOUS", document.lineage_preview.next_relative_path),
                ("MEMORY", "file_history lineage drove restore"),
                ("AUDIT", f"{len(self._restore_audit_trail.events)} restore events"),
            ]
        )

    def _record_selected_review_decision(  # noqa: PLR0911
        self,
        action: ReviewDecisionAction,
        *,
        reason: str | None = None,
    ) -> None:
        row = self._selected_document_row
        if row is None:
            self._set_status("Select one review proposal before recording a decision.")
            return
        document = self.left.document_at(row)
        if document is None or document.status != "REVIEW":
            self._set_status("Only a document in REVIEW can receive a decision.")
            return
        if document.proposal_fingerprint is None:
            self._set_status(
                "Review blocked safely: selected proposal has no retained fingerprint."
            )
            return
        review_decision_id = str(uuid4())
        proposal_id = (
            document.proposal_id or f"cockpit:{document.proposal_fingerprint[:16]}"
        )
        decision = create_proposal_review_decision_from_fingerprint(
            document.proposal_fingerprint,
            request=ProposalReviewDecisionRequest(
                review_decision_id=review_decision_id,
                proposal_id=proposal_id,
                reviewer_actor_id="local-cockpit-reviewer",
                decided_at_utc=datetime.now(UTC),
                action=action,
                reason=reason,
            ),
        )
        validation = validate_proposal_review_decision_fingerprint(
            document.proposal_fingerprint,
            decision,
        )
        if not validation.is_valid:
            self._set_status(f"Review decision blocked safely ({validation.reason}).")
            return
        moved_path: Path | None = None
        file_history_kwargs: dict[str, object] = {}
        if action is ReviewDecisionAction.APPROVE:
            root = self.authorized_root
            if (
                root is None
                or document.path is None
                or document.lineage_preview is None
                or document.document_id is None
            ):
                self._set_status(
                    "Approve blocked: selected proposal has no complete move history."
                )
                return
            try:
                plan = plan_file_operation(
                    FileOperationRequest(
                        operation=FileOperation.MOVE,
                        source_root=root,
                        source_relative_path=document.lineage_preview.previous_relative_path,
                        destination_root=root,
                        destination_relative_path=document.lineage_preview.next_relative_path,
                    )
                )
                approved_at = datetime.now(UTC)
                approval = approve_operation_plan(
                    plan,
                    approval_id=review_decision_id,
                    approved_by_user_id="local-cockpit-reviewer",
                    approved_at_utc=approved_at,
                    expires_at_utc=approved_at + timedelta(minutes=15),
                )
                self.center.release_document_handle()
                execution = execute_file_operation(
                    plan,
                    approval,
                    execution_id=review_decision_id,
                    now_utc=approved_at,
                )
            except (OSError, ValueError) as error:
                self._set_status(
                    f"Approve blocked before moving file ({error.__class__.__name__})."
                )
                return
            if not execution.succeeded or plan.destination_path is None:
                self._set_status(
                    "Approve blocked: move/rename did not succeed "
                    f"({execution.reason.value})."
                )
                return
            moved_path = plan.destination_path
            file_history_kwargs = {
                "document_id": UUID(document.document_id),
                "operation": "rename_and_move",
                "previous_directory": document.lineage_preview.original_directory,
                "previous_filename": document.lineage_preview.original_filename,
                "next_directory": document.lineage_preview.next_directory,
                "next_filename": document.lineage_preview.next_filename,
                "file_status": "succeeded",
                "note": "Dashboard approval executed local move/rename.",
            }
        durable_result = None
        if document.proposal_id is not None:
            try:
                durable_result = self._review_decision_function(
                    ReviewDecisionCommandInput(
                        proposal_id=UUID(document.proposal_id),
                        action=action,
                        proposal_fingerprint=document.proposal_fingerprint,
                        reason=reason,
                        review_decision_id=UUID(review_decision_id),
                        decided_at_utc=decision.decided_at_utc,
                        **file_history_kwargs,
                    )
                )
            except (RuntimeConfigurationError, ValueError) as error:
                self._set_status(
                    "Review decision blocked safely before durable memory "
                    f"({error.__class__.__name__})."
                )
                return
        self._review_ledger.append(decision)
        next_status = (
            "APPROVED" if action is ReviewDecisionAction.APPROVE else "REJECTED"
        )
        self.left.record_review_decision(
            row,
            status="MOVED" if moved_path is not None else next_status,
            review_decision_id=review_decision_id,
            path=moved_path,
            name=None if moved_path is None else moved_path.name,
        )
        self.right.set_metrics(
            self.left.document_count,
            self.left.count_status("READY"),
            self.left.count_status("REVIEW"),
        )
        decision_count = len(
            self._review_ledger.decisions_for_proposal(decision.proposal_id)
        )
        self._set_busy(False)
        memory_label = (
            "Local review ledger"
            if durable_result is None
            else f"CockroachDB {durable_result.disposition.value}"
        )
        self._set_status(
            "Review decision recorded "
            f"{'locally' if durable_result is None else 'durably'}: "
            f"{next_status.lower()}."
        )
        self.center.show_memory_trace(
            summary=(
                f"Human review {next_status.lower()} append recorded; "
                f"decision {review_decision_id[:8]}"
            ),
            detail=(
                f"{memory_label}; proposal {decision.proposal_id}; "
                f"fingerprint {document.proposal_fingerprint[:12]}; "
                + (
                    f"moved to {moved_path.name} with original path retained."
                    if moved_path is not None
                    else "no file mutation executed."
                )
            ),
        )
        self.right.set_events(
            [
                ("REVIEW", next_status),
                ("DECISION", review_decision_id[:8]),
                ("HISTORY", f"{decision_count} append-only decision(s)"),
                ("MEMORY", memory_label),
                (
                    "OPERATION",
                    "Move/rename executed" if moved_path is not None else "No move",
                ),
                ("LINEAGE", _lineage_preview_label(document.lineage_preview)),
                ("ORIGINAL", _original_path_label(document.lineage_preview)),
            ]
        )

    def _set_busy(self, busy: bool) -> None:
        blocked = busy or self.scan_in_progress or self.classification_in_progress
        analysis_ready = (
            _classification_preflight_block(self._runtime_preflight_report) is None
        )
        batch_review_ready = self.left.count_status("REVIEW") > 0 and not blocked
        selected_restore_ready = (
            self._selected_restorable_document() is not None and not blocked
        )
        self.console.buttons[0].setEnabled(not blocked)
        self.console.buttons[1].setEnabled(
            not blocked and self.authorized_root is not None
        )
        self.console.buttons[2].setEnabled(self.scan_in_progress)
        self.console.buttons[3].setEnabled(
            not blocked and self._ready_document_count() > 0
        )
        if analysis_ready:
            self.console.buttons[3].setToolTip(
                "Run configured classification for all visible ready PDFs."
            )
        else:
            self.console.buttons[3].setToolTip(
                "Retry runtime preflight and analyze when configuration is ready."
            )
        self.console.buttons[4].setEnabled(batch_review_ready)
        self.console.buttons[5].setEnabled(selected_restore_ready)
        self.console.lateral_screens_button.setEnabled(not blocked)
        if batch_review_ready:
            self.console.buttons[4].setToolTip(
                "Open the batch review table for all proposed renames."
            )
        else:
            self.console.buttons[4].setToolTip(
                "Analyze documents before opening batch review."
            )
        if selected_restore_ready:
            self.console.buttons[5].setToolTip(
                "Open restore preview from retained file history."
            )
        else:
            self.console.buttons[5].setToolTip(
                "Select a moved document with retained file history before restore."
            )

    def _set_status(self, message: str) -> None:
        self.console.log_text.setText(message)
        runtime_status = _runtime_config_status(self._runtime_preflight_report)
        cockroachdb_status = _cockroachdb_status(
            self._runtime_preflight_report,
            self._integration_snapshot,
        )
        bedrock_status = self._effective_bedrock_status()
        self.console.status_text.setText(
            "● Local scan       "
            + ("Running" if self.scan_in_progress else "Ready")
            + "\n"
            "● PDF preview      Ready\n"
            f"● Runtime config   {runtime_status}\n"
            f"● CockroachDB      {cockroachdb_status}"
        )
        self.console.set_bedrock_auth_state(self._bedrock_auth_state)
        self.right.set_events(
            [
                ("DISCOVERY", message[:42]),
                ("PREVIEW", "Embedded PDF viewer ready"),
                ("CONFIG", f"Runtime {runtime_status.lower()}"),
                ("MEMORY", f"CockroachDB {cockroachdb_status.lower()}"),
                ("BEDROCK", f"Bedrock {bedrock_status.lower()}"),
                ("SECURITY", "Read-only local boundary"),
            ]
        )
        self.right.set_restore_history_status(
            _restore_history_status(
                self._runtime_preflight_report,
                self._integration_snapshot,
            )
        )
        self.right.set_memory_evidence_status(
            _memory_evidence_status(
                self._memory_evidence_report,
                self._memory_evidence_error,
                self._runtime_preflight_report,
                self._integration_snapshot,
            )
        )
        self.right.set_memory_table_rows(
            _memory_table_rows(self._memory_evidence_report)
        )

    def _effective_bedrock_status(self) -> str:
        if self._bedrock_auth_state == "connected":
            return "Connected"
        if self._bedrock_auth_state == "disconnected":
            return "Login required"
        if self._bedrock_auth_state == "checking":
            return "Checking login"
        return _bedrock_status(self._runtime_preflight_report)

    def _refresh_runtime_preflight_report(self) -> None:
        """Refresh runtime readiness before a user-triggered classification run."""
        try:
            self._runtime_preflight_report = _initial_runtime_preflight_report(
                self._runtime_preflight_function,
                self._integration_snapshot,
                check_database=True,
            )
        except Exception as error:
            self._runtime_preflight_report = RuntimePreflightReport(
                checks=(
                    PreflightCheck(
                        "runtime_config",
                        PreflightState.FAIL,
                        error.__class__.__name__,
                    ),
                )
            )
        self._refresh_memory_evidence()

    def _refresh_bedrock_auth_status(self) -> None:
        """Refresh local AWS credential usability without exposing account details."""
        try:
            connected = self._bedrock_auth_probe_function()
        except Exception:
            connected = False
        self._bedrock_auth_state = "connected" if connected else "disconnected"
        self.console.set_bedrock_auth_state(self._bedrock_auth_state)

    def _should_probe_bedrock_auth(self) -> bool:
        return (
            self._bedrock_auth_probe_explicit
            or self._runtime_preflight_function is None
        )

    @Slot()
    def _handle_bedrock_button_clicked(self) -> None:
        if self._bedrock_auth_state == "connected":
            self._refresh_bedrock_auth_status()
            self._set_status("Bedrock AWS session is active.")
            return
        self._bedrock_auth_state = "checking"
        self.console.set_bedrock_auth_state("checking")
        launched = self._bedrock_login_launcher()
        if launched:
            self._set_status(
                "AWS login opened. Complete the browser flow, then press Analyze."
            )
            self._bedrock_login_poll_attempts = 0
            QTimer.singleShot(4_000, self._poll_bedrock_auth_after_login)
            return
        self._bedrock_auth_state = "disconnected"
        self.console.set_bedrock_auth_state("disconnected")
        self._set_status("AWS login could not start; browser help was opened.")

    @Slot()
    def _poll_bedrock_auth_after_login(self) -> None:
        self._bedrock_login_poll_attempts += 1
        self._refresh_bedrock_auth_status()
        if self._bedrock_auth_state == "connected":
            self._set_status("Bedrock AWS session is active.")
            return
        if self._bedrock_login_poll_attempts < 6:
            QTimer.singleShot(5_000, self._poll_bedrock_auth_after_login)
            return
        self._set_status("Bedrock still needs AWS login. Press the red button again.")

    def _refresh_memory_evidence(self) -> None:
        """Refresh read-only CockroachDB memory evidence after database preflight."""
        self._memory_evidence_report = None
        self._memory_evidence_error = None
        cockroachdb_check = _preflight_check(
            self._runtime_preflight_report,
            "cockroachdb_connection",
        )
        if (
            cockroachdb_check is None
            or cockroachdb_check.state is not PreflightState.OK
        ):
            return
        try:
            self._memory_evidence_report = self._memory_evidence_function()
        except Exception as error:
            self._memory_evidence_error = error.__class__.__name__

    def _ready_document_count(self) -> int:
        return self.left.count_status("READY")

    def _selected_review_document(self) -> Document | None:
        row = self._selected_document_row
        if row is None:
            return None
        document = self.left.document_at(row)
        if (
            document is None
            or document.status != "REVIEW"
            or document.proposal_fingerprint is None
        ):
            return None
        return document

    def _selected_restorable_document(self) -> Document | None:
        row = self._selected_document_row
        if row is None:
            return None
        document = self.left.document_at(row)
        if (
            document is None
            or document.status not in {"APPROVED", "MOVED"}
            or document.path is None
            or document.lineage_preview is None
        ):
            return None
        return document

    def _restore_original_operation_for(
        self,
        document: Document,
        root: Path,
    ) -> tuple[FileOperationPlan, OperationResultRecord]:
        lineage = document.lineage_preview
        if lineage is None or document.path is None:
            raise ValueError("restore lineage is incomplete")
        resolved_root = root.resolve(strict=True)
        original_path = (resolved_root / lineage.original_relative_path).resolve(
            strict=False,
        )
        current_path = document.path.resolve(strict=True)
        original_path.relative_to(resolved_root)
        current_path.relative_to(resolved_root)
        original_request = FileOperationRequest(
            operation=FileOperation.MOVE,
            source_root=resolved_root,
            source_relative_path=lineage.original_relative_path,
            destination_root=resolved_root,
            destination_relative_path=lineage.next_relative_path,
        )
        original_plan = FileOperationPlan(
            request=original_request,
            status=FileOperationStatus.READY,
            reason=FileOperationReason.READY,
            source_root=resolved_root,
            source_path=original_path,
            source_relative_path=lineage.original_relative_path,
            destination_root=resolved_root,
            destination_path=current_path,
            destination_relative_path=lineage.next_relative_path,
            destination_comparison_key=path_comparison_key(
                lineage.next_relative_path,
                case_sensitive=original_request.case_sensitive_paths,
            ),
        )
        now = datetime.now(UTC)
        current_digest = compute_sha256_fingerprint(current_path).hex_digest
        return (
            original_plan,
            OperationResultRecord(
                batch_id="local-cockpit-approval",
                batch_item_id=document.review_decision_id or "selected-document",
                execution_key=document.review_decision_id or "selected-document",
                execution_id=document.review_decision_id or "selected-document",
                status=ExecutionStatus.SUCCEEDED,
                reason=ExecutionReason.SUCCEEDED,
                disposition=ResultDisposition.EXECUTED,
                attempted_at_utc=now,
                completed_at_utc=now,
                approval_id=document.review_decision_id,
                source_exists_after=False,
                destination_exists_after=True,
                destination_digest_after=current_digest,
            ),
        )

    def _classification_batch_items(
        self,
        authorized_root: Path,
    ) -> tuple[ClassificationBatchItem, ...]:
        items: list[ClassificationBatchItem] = []
        for row in range(self.left.document_count):
            document = self.left.document_at(row)
            if document is None or document.path is None or document.status != "READY":
                continue
            try:
                validated_path = validate_pdf_for_open(document.path, authorized_root)
            except PdfOpenValidationError:
                continue
            items.append(ClassificationBatchItem(row=row, source_path=validated_path))
            if len(items) >= 1000:
                break
        return tuple(items)

    def _organization_preview_for(
        self,
        source_path: Path,
        result: ClassificationCommandResult,
    ) -> tuple[str | None, str | None, CockpitLineagePreview | None]:
        root = self.authorized_root
        if root is None:
            return None, None, None
        try:
            preview = build_mass_operation_preview(
                authorized_root=root,
                mode=MassOperationMode.MOVE_TO_ORGANIZED,
                candidates=(
                    MassOperationCandidate(
                        source_path=source_path,
                        proposed_class=result.proposed_class,
                        metadata={
                            item.name: item.value for item in result.metadata_details
                        },
                        proposal_id=(
                            None
                            if result.proposal_id is None
                            else str(result.proposal_id)
                        ),
                        proposal_fingerprint=result.proposal_fingerprint,
                    ),
                ),
            )
        except (OSError, ValueError):
            return None, None, None
        item = preview.items[0]
        if not item.is_ready:
            return None, item.action.value, _cockpit_lineage_preview_from_item(item)
        lineage_preview = _cockpit_lineage_preview_from_item(item)
        return item.plan.destination_relative_path, item.action.value, lineage_preview

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        w = self.width()
        h = self.height()

        margin_x = int(w * 0.075)
        top = int(h * 0.085)

        side_w = int(w * 0.245)
        side_h = int(h * 0.685)

        center_w = int(w * 0.43)
        center_h = int(h * 0.61)

        console_w = int(w * 0.84)
        console_h = int(h * 0.29)

        # All three screens are lifted away from the console.
        # The side displays also move outward along their inclined axes,
        # creating more separation across their upper edges.
        side_lift = int(h * 0.055)
        center_lift = int(h * 0.075)

        left_y = top - side_lift
        center_x = (w - center_w) // 2
        center_y = top - center_lift

        console_x = (w - console_w) // 2
        console_y = h - console_h - int(h * 0.005)

        self.side_view.setGeometry(0, 0, w, h)
        self.side_scene.setSceneRect(0, 0, w, h)

        # The widgets themselves remain rectangular; the proxies rotate them.
        self.left.resize(side_w, side_h)
        self.right.resize(side_w, side_h)

        # Rotation pivots around the exact centre of each panel.
        self.left_proxy.setTransformOriginPoint(side_w / 2, side_h / 2)
        self.right_proxy.setTransformOriginPoint(side_w / 2, side_h / 2)

        # Exact mirror symmetry around the vertical centre of the window.
        # Both panels use the same distance from the centre and the same height.
        screen_center_y = left_y + side_h / 2
        horizontal_distance = (w * 0.5) - margin_x - (side_w * 0.5)

        left_center_x = (w * 0.5) - horizontal_distance
        right_center_x = (w * 0.5) + horizontal_distance

        self.left_proxy.setPos(
            left_center_x - side_w / 2,
            screen_center_y - side_h / 2,
        )
        self.right_proxy.setPos(
            right_center_x - side_w / 2,
            screen_center_y - side_h / 2,
        )

        self.console.setGeometry(console_x, console_y, console_w, console_h)

        if self._center_expanded:
            expanded_margin_x = int(w * 0.075)
            expanded_top = max(12, top - center_lift)
            expanded_bottom = console_y - int(h * 0.035)
            target = QRect(
                expanded_margin_x,
                expanded_top,
                w - expanded_margin_x * 2,
                max(int(h * 0.50), expanded_bottom - expanded_top),
            )
        else:
            target = QRect(center_x, center_y, center_w, center_h)
        self.center.set_target_rect(target)

        if self._center_expanded or self.center.opacity_effect.opacity() > 0.01:
            self.center.setGeometry(target)
        else:
            self.center.setGeometry(
                target.center().x(),
                target.bottom() - 12,
                0,
                12,
            )

        if not self._center_expanded:
            self.side_view.raise_()
        self.console.raise_()
        self.center.raise_()


def _initial_runtime_preflight_report(
    runtime_preflight_function: RuntimePreflightFunction | None,
    integration_snapshot: RuntimeIntegrationSnapshot | None,
    *,
    check_database: bool = False,
) -> RuntimePreflightReport:
    if runtime_preflight_function is not None:
        return runtime_preflight_function()
    if integration_snapshot is not None and not check_database:
        return _snapshot_preflight_report(integration_snapshot)
    return run_preflight(check_database=check_database)


def _snapshot_preflight_report(
    integration_snapshot: RuntimeIntegrationSnapshot,
) -> RuntimePreflightReport:
    cockroach_state = (
        PreflightState.SKIP
        if integration_snapshot.cockroachdb_configured
        else PreflightState.FAIL
    )
    cockroach_detail = (
        "configured_not_connected"
        if integration_snapshot.cockroachdb_configured
        else "not_configured"
    )
    return RuntimePreflightReport(
        checks=(
            PreflightCheck("runtime_config", PreflightState.OK, "snapshot"),
            PreflightCheck(
                "bedrock_client",
                PreflightState.OK,
                f"{integration_snapshot.bedrock_region}:configured",
            ),
            PreflightCheck(
                "cockroachdb_connection",
                cockroach_state,
                cockroach_detail,
            ),
        )
    )


def _runtime_config_status(report: RuntimePreflightReport) -> str:
    check = _preflight_check(report, "runtime_config")
    if check is None:
        return "Unknown"
    if check.state is PreflightState.OK:
        return "Ready"
    return f"Blocked ({_compact_preflight_detail(check.detail)})"


def _cockroachdb_status(
    report: RuntimePreflightReport,
    integration_snapshot: RuntimeIntegrationSnapshot,
) -> str:
    check = _preflight_check(report, "cockroachdb_connection")
    if check is None:
        return integration_snapshot.cockroachdb_status
    if check.state is PreflightState.OK:
        return "Reachable"
    if check.state is PreflightState.SKIP:
        if integration_snapshot.cockroachdb_configured:
            return "Configured"
        return "Not configured"
    return f"Blocked ({_compact_preflight_detail(check.detail)})"


def _bedrock_status(report: RuntimePreflightReport) -> str:
    check = _preflight_check(report, "bedrock_client")
    if check is None:
        return "Blocked by config"
    if check.state is PreflightState.OK:
        return "Client configured"
    return f"Blocked ({_compact_preflight_detail(check.detail)})"


def _restore_history_status(
    report: RuntimePreflightReport,
    integration_snapshot: RuntimeIntegrationSnapshot,
) -> str:
    runtime_check = _preflight_check(report, "runtime_config")
    if runtime_check is None:
        return "Restore history reader waiting for runtime configuration."
    if runtime_check.state is PreflightState.FAIL:
        return (
            "Restore history reader blocked by runtime config: "
            f"{_compact_preflight_detail(runtime_check.detail)}."
        )

    cockroachdb_status = _cockroachdb_status(report, integration_snapshot)
    if cockroachdb_status in {"Reachable", "Configured"}:
        return (
            "Read-only CockroachDB restore history reader is available; "
            "no restore action is wired."
        )
    return f"Restore history reader blocked: CockroachDB {cockroachdb_status.lower()}."


def _memory_evidence_status(
    report: MemoryEvidenceReport | None,
    error_category: str | None,
    preflight_report: RuntimePreflightReport,
    integration_snapshot: RuntimeIntegrationSnapshot,
) -> str:
    if report is not None:
        present = sum(1 for row in report.table_counts if row.present)
        total = len(report.table_counts)
        rows = sum(row.row_count or 0 for row in report.table_counts)
        readiness = "ready" if report.schema_ready else "not ready"
        return (
            f"CockroachDB memory schema {readiness}: {present}/{total} "
            f"tables at {report.alembic_revision or 'missing'}; {rows} row(s)."
        )
    if error_category is not None:
        return f"CockroachDB memory evidence unavailable: {error_category}."

    runtime_check = _preflight_check(preflight_report, "runtime_config")
    if runtime_check is None:
        return "CockroachDB memory evidence waiting for runtime configuration."
    if runtime_check.state is PreflightState.FAIL:
        return (
            "CockroachDB memory evidence blocked by runtime config: "
            f"{_compact_preflight_detail(runtime_check.detail)}."
        )

    cockroachdb_status = _cockroachdb_status(preflight_report, integration_snapshot)
    if cockroachdb_status == "Reachable":
        return "CockroachDB memory evidence waiting for the next read-only refresh."
    return f"CockroachDB memory evidence waiting: {cockroachdb_status.lower()}."


def _memory_table_rows(
    report: MemoryEvidenceReport | None,
) -> tuple[tuple[str, str], ...]:
    if report is None:
        return (("schema", "waiting"),)
    return tuple(
        (row.table_name, "missing" if not row.present else str(row.row_count or 0))
        for row in sorted(report.table_counts, key=lambda item: item.table_name)
    )


def _classification_preflight_block(report: RuntimePreflightReport) -> str | None:
    runtime_check = _preflight_check(report, "runtime_config")
    if runtime_check is None:
        return "runtime unknown"
    if runtime_check.state is PreflightState.FAIL:
        return _compact_preflight_detail(runtime_check.detail)

    bedrock_check = _preflight_check(report, "bedrock_client")
    if bedrock_check is None:
        return "bedrock unavailable"
    if bedrock_check.state is PreflightState.FAIL:
        return _compact_preflight_detail(bedrock_check.detail)

    return None


def _compact_console_text(value: str, *, maximum: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= maximum:
        return normalized
    return normalized[: max(0, maximum - 1)].rstrip() + "…"


def _classification_evidence_summary(result: ClassificationCommandResult) -> str:
    if not result.evidence_details:
        return "Evidence details unavailable in this result."
    parts = [
        f"{item.evidence_id} p{item.page_number}: "
        f"{_compact_console_text(item.quote, maximum=58)}"
        for item in result.evidence_details[:3]
    ]
    return " | ".join(parts)


def _classification_memory_trace_summary(result: ClassificationCommandResult) -> str:
    proposal_id = "pending" if result.proposal_id is None else str(result.proposal_id)
    disposition = getattr(
        result.proposal_disposition,
        "value",
        result.proposal_disposition,
    )
    return (
        f"Bedrock proposal persisted as {disposition}; "
        f"class {result.proposed_class}; proposal {proposal_id}."
    )


def _classification_memory_trace_detail(
    result: ClassificationCommandResult,
    *,
    proposed_action: str | None,
    proposed_destination: str | None,
    lineage_preview: CockpitLineagePreview | None,
) -> str:
    action = proposed_action or "no operation preview"
    destination = proposed_destination or "no destination"
    lineage = _lineage_preview_label(lineage_preview)
    fingerprint = (
        "unavailable"
        if result.proposal_fingerprint is None
        else result.proposal_fingerprint[:12]
    )
    return (
        f"Fingerprint {fingerprint}; evidence {result.evidence_count}; "
        f"{action} -> {destination}; {lineage}."
    )


def _review_memory_trace_summary(document: Document) -> str:
    proposal_id = document.proposal_id or "local proposal"
    return (
        f"Review memory selected for {document.category}; proposal {proposal_id}; "
        "human approval required."
    )


def _review_memory_trace_detail(document: Document) -> str:
    destination = document.proposed_destination or "no destination proposed"
    fingerprint = (
        "missing"
        if document.proposal_fingerprint is None
        else document.proposal_fingerprint[:12]
    )
    return (
        f"Target {destination}; fingerprint {fingerprint}; "
        f"{_lineage_preview_label(document.lineage_preview)}."
    )


def _cockpit_lineage_preview_from_item(
    item: MassOperationPreviewItem,
) -> CockpitLineagePreview:
    """Project a mass-operation preview into human-visible lineage state."""
    return CockpitLineagePreview(
        action=item.action.value,
        original_relative_path=item.source_relative_path,
        previous_relative_path=item.plan.source_relative_path,
        next_relative_path=item.plan.destination_relative_path,
        original_directory=item.original_directory,
        original_filename=item.original_filename,
        next_directory=item.proposed_directory,
        next_filename=item.proposed_filename,
        plan_fingerprint=item.plan_fingerprint,
    )


def _lineage_preview_label(preview: CockpitLineagePreview | None) -> str:
    if preview is None:
        return "No lineage preview available"
    return _compact_console_text(
        f"{preview.action}: {preview.previous_relative_path} -> "
        f"{preview.next_relative_path}",
        maximum=76,
    )


def _original_path_label(preview: CockpitLineagePreview | None) -> str:
    if preview is None:
        return "Original path unavailable"
    return _compact_console_text(
        f"{preview.original_directory}/{preview.original_filename}",
        maximum=76,
    )


def _review_original_name_label(preview: CockpitLineagePreview | None) -> str:
    if preview is None or not preview.original_filename:
        return "Original name unavailable"
    return preview.original_filename


def _review_proposed_name_label(preview: CockpitLineagePreview | None) -> str:
    if preview is None or not preview.next_filename:
        return "Proposed name unavailable"
    return preview.next_filename


def _review_proposed_directory_label(preview: CockpitLineagePreview | None) -> str:
    if preview is None or not preview.next_directory:
        return "Suggested directory unavailable"
    return preview.next_directory


def _filename_from_destination(destination: str | None, *, fallback: str) -> str:
    if not destination:
        return fallback
    return PurePosixPath(destination.replace("\\", "/")).name or fallback


def _directory_from_destination(destination: str | None) -> str:
    if not destination:
        return "Suggested directory unavailable"
    directory = PurePosixPath(destination.replace("\\", "/")).parent.as_posix()
    if directory == ".":
        return "Suggested directory unavailable"
    return directory


def _current_path_label(document: Document) -> str:
    if document.path is None:
        return document.proposed_destination or "Current path unavailable"
    return _compact_console_text(str(document.path.parent), maximum=76)


def _preflight_check(
    report: RuntimePreflightReport,
    name: str,
) -> PreflightCheck | None:
    for check in report.checks:
        if check.name == name:
            return check
    return None


def _compact_preflight_detail(detail: str) -> str:
    return detail.split(":", 1)[0].replace("_", " ")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DocWeave Cockpit")

    window = CockpitWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
