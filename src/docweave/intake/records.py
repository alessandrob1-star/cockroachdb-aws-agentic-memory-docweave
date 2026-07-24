"""Deterministic intake records for discovered local files."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from docweave.core.fingerprints import ContentFingerprint, compute_sha256_fingerprint
from docweave.discovery import DiscoveredFile, DiscoveryStatus
from docweave.inspection import (
    PdfSignatureInspection,
    PdfSignatureStatus,
    inspect_pdf_signature,
)


class IntakeStatus(StrEnum):
    """State after discovery, signature inspection, and fingerprinting."""

    BLOCKED = "blocked"
    EMPTY = "empty"
    INVALID_SIGNATURE = "invalid_signature"
    READY = "ready"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class IntakeRecord:
    """A deterministic pre-extraction record for one discovered file."""

    discovered_file: DiscoveredFile
    status: IntakeStatus
    reason: str | None
    signature: PdfSignatureInspection | None
    fingerprint: ContentFingerprint | None

    @property
    def absolute_path(self) -> Path:
        return self.discovered_file.absolute_path

    @property
    def relative_path(self) -> str:
        return self.discovered_file.relative_path

    @property
    def is_ready_for_extraction(self) -> bool:
        return self.status is IntakeStatus.READY


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """Summary of deterministic intake records."""

    records: tuple[IntakeRecord, ...]

    @property
    def ready_count(self) -> int:
        return self.count_status(IntakeStatus.READY)

    def count_status(self, status: IntakeStatus) -> int:
        return sum(1 for record in self.records if record.status is status)


def build_intake_records(files: Iterable[DiscoveredFile]) -> IntakeResult:
    """Build deterministic intake records for discovered files."""
    records = tuple(_build_intake_record(file) for file in files)
    return IntakeResult(records=records)


def _build_intake_record(file: DiscoveredFile) -> IntakeRecord:
    terminal_record = _discovery_terminal_record(file)
    if terminal_record is not None:
        return terminal_record

    signature = inspect_pdf_signature(file.absolute_path)
    signature_record = _signature_terminal_record(file, signature)
    if signature_record is not None:
        return signature_record

    try:
        fingerprint = compute_sha256_fingerprint(file.absolute_path)
    except OSError as exc:
        return IntakeRecord(
            discovered_file=file,
            status=IntakeStatus.UNREADABLE,
            reason=exc.__class__.__name__,
            signature=signature,
            fingerprint=None,
        )

    return IntakeRecord(
        discovered_file=file,
        status=IntakeStatus.READY,
        reason=None,
        signature=signature,
        fingerprint=fingerprint,
    )


def _discovery_terminal_record(file: DiscoveredFile) -> IntakeRecord | None:
    if file.status is DiscoveryStatus.BLOCKED:
        return _terminal_record(file, IntakeStatus.BLOCKED, file.error)

    if file.status is DiscoveryStatus.UNSUPPORTED:
        return _terminal_record(file, IntakeStatus.UNSUPPORTED, None)

    if file.status is DiscoveryStatus.UNREADABLE:
        return _terminal_record(file, IntakeStatus.UNREADABLE, file.error)

    return None


def _signature_terminal_record(
    file: DiscoveredFile,
    signature: PdfSignatureInspection,
) -> IntakeRecord | None:
    status_map = {
        PdfSignatureStatus.UNREADABLE: IntakeStatus.UNREADABLE,
        PdfSignatureStatus.EMPTY: IntakeStatus.EMPTY,
        PdfSignatureStatus.NOT_PDF: IntakeStatus.INVALID_SIGNATURE,
    }
    intake_status = status_map.get(signature.status)
    if intake_status is None:
        return None

    reason = signature.error
    if reason is None:
        reason = signature.status.value

    return IntakeRecord(
        discovered_file=file,
        status=intake_status,
        reason=reason,
        signature=signature,
        fingerprint=None,
    )


def _terminal_record(
    file: DiscoveredFile,
    status: IntakeStatus,
    reason: str | None,
) -> IntakeRecord:
    return IntakeRecord(
        discovered_file=file,
        status=status,
        reason=reason,
        signature=None,
        fingerprint=None,
    )
