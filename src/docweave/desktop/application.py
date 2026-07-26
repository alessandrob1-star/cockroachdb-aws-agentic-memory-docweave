"""Desktop application bootstrap."""

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from docweave.desktop.main_window import DocWeaveMainWindow


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Create the configured Qt application without showing a window."""
    existing = QApplication.instance()
    application = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(list(arguments or ()))
    )
    application.setApplicationName("DocWeave")
    application.setOrganizationName("DocWeave")
    application.setApplicationDisplayName("DocWeave")
    return application


def main() -> int:
    """Launch the DocWeave desktop shell."""
    application = create_application(sys.argv)
    window = DocWeaveMainWindow()
    window.show()
    return application.exec()
