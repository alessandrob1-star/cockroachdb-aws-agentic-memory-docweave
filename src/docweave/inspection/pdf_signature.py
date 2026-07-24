"""Deterministic Portable Document Format signature inspection."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PDF_SIGNATURE = b"%PDF-"


class PdfSignatureStatus(StrEnum):
    """Result of checking the leading Portable Document Format bytes."""

    EMPTY = "empty"
    NOT_PDF = "not_pdf"
    UNREADABLE = "unreadable"
    VALID_PDF = "valid_pdf"


@dataclass(frozen=True, slots=True)
class PdfSignatureInspection:
    """Outcome of a bounded signature read."""

    path: Path
    status: PdfSignatureStatus
    bytes_read: int
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status is PdfSignatureStatus.VALID_PDF


def inspect_pdf_signature(path: Path) -> PdfSignatureInspection:
    """Inspect only the fixed PDF signature prefix before extraction."""
    try:
        with path.open("rb") as file:
            prefix = file.read(len(PDF_SIGNATURE))
    except OSError as exc:
        return PdfSignatureInspection(
            path=path,
            status=PdfSignatureStatus.UNREADABLE,
            bytes_read=0,
            error=exc.__class__.__name__,
        )

    if len(prefix) == 0:
        return PdfSignatureInspection(
            path=path,
            status=PdfSignatureStatus.EMPTY,
            bytes_read=0,
        )

    if prefix != PDF_SIGNATURE:
        return PdfSignatureInspection(
            path=path,
            status=PdfSignatureStatus.NOT_PDF,
            bytes_read=len(prefix),
        )

    return PdfSignatureInspection(
        path=path,
        status=PdfSignatureStatus.VALID_PDF,
        bytes_read=len(prefix),
    )
