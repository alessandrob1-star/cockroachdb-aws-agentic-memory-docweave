"""PySide6 desktop surface for the DocWeave production core."""

from docweave.desktop.application import create_application, main
from docweave.desktop.main_window import DocWeaveMainWindow
from docweave.desktop.scan import DesktopScanResult, scan_authorized_root

__all__ = [
    "DesktopScanResult",
    "DocWeaveMainWindow",
    "create_application",
    "main",
    "scan_authorized_root",
]
