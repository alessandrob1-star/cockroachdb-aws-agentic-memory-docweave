"""Typed contracts for bounded Portable Document Format text extraction."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractionLimits:
    """Resource budgets applied before and during one extraction attempt."""

    maximum_file_bytes: int = 100 * 1024 * 1024
    maximum_pages: int = 500
    maximum_characters: int = 5_000_000
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        values = (
            self.maximum_file_bytes,
            self.maximum_pages,
            self.maximum_characters,
            self.timeout_seconds,
        )
        if any(value <= 0 for value in values):
            raise ValueError("Extraction limits must be positive.")


class ExtractionStatus(StrEnum):
    """Explicit terminal state for one extraction attempt."""

    CHARACTER_LIMIT_EXCEEDED = "character_limit_exceeded"
    COMPLETED = "completed"
    ENCRYPTED = "encrypted"
    FILE_LIMIT_EXCEEDED = "file_limit_exceeded"
    MALFORMED = "malformed"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    PAGE_LIMIT_EXCEEDED = "page_limit_exceeded"
    SOURCE_CHANGED = "source_changed"
    SOURCE_REJECTED = "source_rejected"
    TIMED_OUT = "timed_out"
    UNSUPPORTED_SECURITY = "unsupported_security"
    WORKER_FAILED = "worker_failed"


@dataclass(frozen=True, slots=True)
class PdfExtractionRequest:
    """Authorized source and budgets for a local extraction attempt."""

    source_path: Path
    authorized_root: Path
    limits: ExtractionLimits = ExtractionLimits()


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Text evidence retained with its zero-based source page."""

    page_index: int
    page_label: str
    text: str

    @property
    def character_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    """Path-free extraction outcome safe to expose outside the worker."""

    status: ExtractionStatus
    pages: tuple[ExtractedPage, ...] = ()
    source_sha256: str | None = None
    source_bytes: int | None = None
    document_page_count: int | None = None
    extractor: str | None = None
    error_code: str | None = None

    @property
    def total_characters(self) -> int:
        return sum(page.character_count for page in self.pages)

    @property
    def is_successful(self) -> bool:
        return self.status in {
            ExtractionStatus.COMPLETED,
            ExtractionStatus.NO_EXTRACTABLE_TEXT,
        }
