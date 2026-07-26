import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_application() -> QApplication:
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    application.setApplicationName("DocWeave Tests")
    return application
