"""Fail-closed policy for external hyperlinks embedded in untrusted PDFs."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

_MAXIMUM_URL_LENGTH = 2_048
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class ExternalLinkRejection(StrEnum):
    """Safe categories for links that must not reach an external application."""

    CREDENTIALS = "credentials"
    INVALID = "invalid"
    LOCAL_DESTINATION = "local_destination"
    MISSING_HOST = "missing_host"
    TOO_LONG = "too_long"
    UNSUPPORTED_SCHEME = "unsupported_scheme"


class ExternalLinkOutcome(StrEnum):
    """Observable result of a user-initiated external-link request."""

    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"
    OPENED = "opened"


@dataclass(frozen=True, slots=True)
class ValidatedExternalLink:
    """A normalized HTTP(S) destination safe to present for confirmation."""

    url: QUrl
    display_url: str
    host: str
    uses_encrypted_transport: bool


@dataclass(frozen=True, slots=True)
class ExternalLinkAssessment:
    """Fail-closed result of validating one PDF-provided destination."""

    link: ValidatedExternalLink | None
    rejection: ExternalLinkRejection | None

    @property
    def is_allowed(self) -> bool:
        return self.link is not None


LinkConfirmation = Callable[[QWidget, ValidatedExternalLink], bool]
UrlOpener = Callable[[QUrl], bool]


def assess_external_pdf_link(url: QUrl) -> ExternalLinkAssessment:
    """Validate a PDF-provided URL without resolving or opening it."""
    encoded = bytes(url.toEncoded().data()).decode("ascii", errors="strict")
    rejection: ExternalLinkRejection | None = None
    if len(encoded) > _MAXIMUM_URL_LENGTH:
        rejection = ExternalLinkRejection.TOO_LONG
    elif not url.isValid() or url.isRelative() or "\x00" in encoded:
        rejection = ExternalLinkRejection.INVALID

    scheme = url.scheme().casefold()
    host = url.host().casefold().rstrip(".")
    if rejection is None:
        if scheme not in _ALLOWED_SCHEMES:
            rejection = ExternalLinkRejection.UNSUPPORTED_SCHEME
        elif url.userName() or url.password():
            rejection = ExternalLinkRejection.CREDENTIALS
        elif not host:
            rejection = ExternalLinkRejection.MISSING_HOST
        elif _is_local_destination(host):
            rejection = ExternalLinkRejection.LOCAL_DESTINATION
    if rejection is not None:
        return _blocked(rejection)

    normalized = QUrl(url)
    normalized.setScheme(scheme)
    normalized.setHost(host)
    return ExternalLinkAssessment(
        link=ValidatedExternalLink(
            url=normalized,
            display_url=normalized.toDisplayString(
                QUrl.ComponentFormattingOption.FullyEncoded
            ),
            host=host,
            uses_encrypted_transport=scheme == "https",
        ),
        rejection=None,
    )


def request_external_pdf_link(
    url: QUrl,
    parent: QWidget,
    *,
    confirm: LinkConfirmation | None = None,
    opener: UrlOpener | None = None,
) -> ExternalLinkOutcome:
    """Confirm and open one allowed destination in the user's default browser."""
    assessment = assess_external_pdf_link(url)
    if assessment.link is None:
        return ExternalLinkOutcome.BLOCKED

    confirmation = confirm or confirm_external_pdf_link
    if not confirmation(parent, assessment.link):
        return ExternalLinkOutcome.CANCELLED

    open_url = opener or QDesktopServices.openUrl
    if not open_url(assessment.link.url):
        return ExternalLinkOutcome.FAILED
    return ExternalLinkOutcome.OPENED


def confirm_external_pdf_link(
    parent: QWidget,
    link: ValidatedExternalLink,
) -> bool:
    """Show a plain-text warning before leaving DocWeave."""
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("Open external link?")
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(f"The PDF links to {link.host}.")
    transport_warning = (
        "This HTTP link is not encrypted. " if not link.uses_encrypted_transport else ""
    )
    dialog.setInformativeText(
        f"{transport_warning}PDF content is untrusted. Verify the address before "
        f"opening it in your default browser.\n\n{link.display_url}"
    )
    dialog.setStandardButtons(
        QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel
    )
    dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
    dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
    return dialog.exec() == QMessageBox.StandardButton.Open


def _blocked(rejection: ExternalLinkRejection) -> ExternalLinkAssessment:
    return ExternalLinkAssessment(link=None, rejection=rejection)


def _is_local_destination(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ip_address(host.removeprefix("[").removesuffix("]"))
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
