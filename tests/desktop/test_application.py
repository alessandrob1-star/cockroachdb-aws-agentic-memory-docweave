import pytest
from PySide6.QtWidgets import QApplication

import docweave.desktop.application as application_module
from docweave.desktop.application import create_application


def test_create_application_configures_existing_qt_instance(
    qt_application: QApplication,
) -> None:
    application = create_application(["docweave-desktop"])

    assert application is qt_application
    assert application.applicationName() == "DocWeave"
    assert application.organizationName() == "DocWeave"
    assert application.applicationDisplayName() == "DocWeave"


def test_main_shows_window_and_returns_event_loop_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeApplication:
        def exec(self) -> int:
            return 17

    class FakeWindow:
        shown = False

        def show(self) -> None:
            self.shown = True

    fake_application = FakeApplication()
    fake_window = FakeWindow()
    monkeypatch.setattr(
        application_module,
        "create_application",
        lambda arguments: fake_application,
    )
    monkeypatch.setattr(
        application_module,
        "CockpitWindow",
        lambda: fake_window,
    )

    result = application_module.main()

    assert result == 17
    assert fake_window.shown
