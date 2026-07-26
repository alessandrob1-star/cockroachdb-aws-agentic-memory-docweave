"""PySide6 desktop surface for the DocWeave production core."""

from docweave.desktop.application import create_application, main
from docweave.desktop.main_window import DocWeaveMainWindow
from docweave.desktop.opening import (
    PdfOpenFailure,
    PdfOpenValidationError,
    validate_pdf_for_open,
)
from docweave.desktop.preview import PdfPreviewDialog, create_pdf_preview
from docweave.desktop.scan import (
    DesktopScanResult,
    ScanPhase,
    ScanProgress,
    scan_authorized_root,
)
from docweave.desktop.workspace import WorkspacePhase, WorkspaceSnapshot

__all__ = [
    "DesktopScanResult",
    "DocWeaveMainWindow",
    "PdfOpenFailure",
    "PdfOpenValidationError",
    "PdfPreviewDialog",
    "ScanPhase",
    "ScanProgress",
    "WorkspacePhase",
    "WorkspaceSnapshot",
    "create_application",
    "create_pdf_preview",
    "main",
    "scan_authorized_root",
    "validate_pdf_for_open",
]
