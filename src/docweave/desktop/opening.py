"""Fail-closed validation before opening a local PDF externally."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from docweave.inspection import inspect_pdf_signature


class PdfOpenFailure(StrEnum):
    """Safe categories for a rejected local open request."""

    INVALID_SIGNATURE = "invalid_signature"
    NOT_A_FILE = "not_a_file"
    NOT_PDF = "not_pdf"
    OUTSIDE_AUTHORIZED_ROOT = "outside_authorized_root"
    SYMBOLIC_LINK = "symbolic_link"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class PdfOpenValidationError(RuntimeError):
    """Reject an unsafe open request without including a private path."""

    category: PdfOpenFailure


def validate_pdf_for_open(path: Path, authorized_root: Path) -> Path:
    """Return a current safe path or reject the external open request."""
    try:
        if path.is_symlink():
            raise PdfOpenValidationError(PdfOpenFailure.SYMBOLIC_LINK)
        resolved_root = authorized_root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
    except PdfOpenValidationError:
        raise
    except OSError as error:
        raise PdfOpenValidationError(PdfOpenFailure.UNAVAILABLE) from error

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise PdfOpenValidationError(PdfOpenFailure.OUTSIDE_AUTHORIZED_ROOT) from error

    if not resolved_path.is_file():
        raise PdfOpenValidationError(PdfOpenFailure.NOT_A_FILE)
    if resolved_path.suffix.casefold() != ".pdf":
        raise PdfOpenValidationError(PdfOpenFailure.NOT_PDF)
    if not inspect_pdf_signature(resolved_path).is_valid:
        raise PdfOpenValidationError(PdfOpenFailure.INVALID_SIGNATURE)
    return resolved_path
