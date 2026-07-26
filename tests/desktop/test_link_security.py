import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget

from docweave.desktop.link_security import (
    ExternalLinkOutcome,
    ExternalLinkRejection,
    ValidatedExternalLink,
    assess_external_pdf_link,
    request_external_pdf_link,
)


@pytest.mark.parametrize("scheme", ["https", "http"])
def test_allows_only_explicit_web_destinations(scheme: str) -> None:
    assessment = assess_external_pdf_link(QUrl(f"{scheme}://Example.COM/invoice?id=42"))

    assert assessment.rejection is None
    assert assessment.link is not None
    assert assessment.link.host == "example.com"
    assert assessment.link.url.scheme() == scheme
    assert assessment.link.uses_encrypted_transport is (scheme == "https")


@pytest.mark.parametrize(
    ("value", "rejection"),
    [
        (
            "file:///C:/Windows/System32/calc.exe",
            ExternalLinkRejection.UNSUPPORTED_SCHEME,
        ),
        ("javascript:alert(1)", ExternalLinkRejection.UNSUPPORTED_SCHEME),
        ("data:text/html,payload", ExternalLinkRejection.UNSUPPORTED_SCHEME),
        ("ftp://example.com/file", ExternalLinkRejection.UNSUPPORTED_SCHEME),
        ("https:///missing-host", ExternalLinkRejection.MISSING_HOST),
        ("https://user:secret@example.com", ExternalLinkRejection.CREDENTIALS),
        ("https://localhost/admin", ExternalLinkRejection.LOCAL_DESTINATION),
        ("http://127.0.0.1:8080", ExternalLinkRejection.LOCAL_DESTINATION),
        (
            "http://169.254.169.254/latest/meta-data",
            ExternalLinkRejection.LOCAL_DESTINATION,
        ),
        ("https://[::1]/", ExternalLinkRejection.LOCAL_DESTINATION),
    ],
)
def test_blocks_dangerous_or_local_destinations(
    value: str,
    rejection: ExternalLinkRejection,
) -> None:
    assessment = assess_external_pdf_link(QUrl(value))

    assert assessment.link is None
    assert assessment.rejection is rejection


def test_blocks_oversized_destination() -> None:
    assessment = assess_external_pdf_link(QUrl("https://example.com/" + ("a" * 2_100)))

    assert assessment.rejection is ExternalLinkRejection.TOO_LONG


def test_requires_confirmation_before_opening(
    qt_application: object,
) -> None:
    parent = QWidget()
    calls: list[str] = []

    def confirm(unused_parent: QWidget, link: ValidatedExternalLink) -> bool:
        del unused_parent
        calls.append(f"confirm:{link.host}")
        return True

    def open_url(url: QUrl) -> bool:
        calls.append(f"open:{url.toString()}")
        return True

    outcome = request_external_pdf_link(
        QUrl("https://example.com/document"),
        parent,
        confirm=confirm,
        opener=open_url,
    )

    assert outcome is ExternalLinkOutcome.OPENED
    assert calls == [
        "confirm:example.com",
        "open:https://example.com/document",
    ]
    parent.close()


@pytest.mark.parametrize(
    ("confirmation", "expected"),
    [
        (False, ExternalLinkOutcome.CANCELLED),
        (True, ExternalLinkOutcome.FAILED),
    ],
)
def test_reports_cancelled_or_failed_open(
    confirmation: bool,
    expected: ExternalLinkOutcome,
    qt_application: object,
) -> None:
    parent = QWidget()

    def opener(unused_url: QUrl) -> bool:
        del unused_url
        return False

    outcome = request_external_pdf_link(
        QUrl("https://example.com"),
        parent,
        confirm=lambda unused_parent, unused_link: confirmation,
        opener=opener,
    )

    assert outcome is expected
    parent.close()


def test_blocked_link_never_prompts_or_opens(qt_application: object) -> None:
    parent = QWidget()

    def unexpected(*unused_arguments: object) -> bool:
        raise AssertionError("blocked link crossed the external boundary")

    outcome = request_external_pdf_link(
        QUrl("file:///private/document"),
        parent,
        confirm=unexpected,
        opener=unexpected,
    )

    assert outcome is ExternalLinkOutcome.BLOCKED
    parent.close()
