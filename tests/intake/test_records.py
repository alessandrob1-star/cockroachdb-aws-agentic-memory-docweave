from pathlib import Path

import pytest

from docweave.core.fingerprints import ContentFingerprint, compute_sha256_fingerprint
from docweave.discovery import (
    DiscoveredFile,
    DiscoveryConfig,
    DiscoveryStatus,
    discover_files,
)
from docweave.inspection import PdfSignatureInspection, PdfSignatureStatus
from docweave.intake import IntakeStatus, build_intake_records
from docweave.intake import records as intake_records


def write_file(path: Path, content: bytes = b"content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_builds_ready_record_for_valid_pdf(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    content = b"%PDF-1.7\nbody"
    write_file(path, content)
    discovery = discover_files([tmp_path])

    result = build_intake_records(discovery.files)

    assert result.ready_count == 1
    record = result.records[0]
    assert record.status is IntakeStatus.READY
    assert record.reason is None
    assert record.is_ready_for_extraction is True
    assert record.absolute_path == path
    assert record.relative_path == "invoice.pdf"
    assert record.signature is not None
    assert record.signature.is_valid is True
    assert record.fingerprint == compute_sha256_fingerprint(path)


def test_preserves_unsupported_discovery_state_without_file_reads(
    tmp_path: Path,
) -> None:
    write_file(tmp_path / "notes.txt", b"not a pdf")
    discovery = discover_files([tmp_path])

    result = build_intake_records(discovery.files)

    assert result.count_status(IntakeStatus.UNSUPPORTED) == 1
    record = result.records[0]
    assert record.status is IntakeStatus.UNSUPPORTED
    assert record.is_ready_for_extraction is False
    assert record.signature is None
    assert record.fingerprint is None


def test_preserves_unreadable_discovery_state(tmp_path: Path) -> None:
    path = tmp_path / "blocked.pdf"
    write_file(path, b"%PDF-1.7\n")
    discovery = discover_files([tmp_path])
    unreadable_file = DiscoveredFile(
        root=discovery.files[0].root,
        absolute_path=discovery.files[0].absolute_path,
        relative_path=discovery.files[0].relative_path,
        comparison_key=discovery.files[0].comparison_key,
        status=DiscoveryStatus.UNREADABLE,
        byte_size=None,
        error="PermissionError",
    )

    result = build_intake_records([unreadable_file])

    record = result.records[0]
    assert record.status is IntakeStatus.UNREADABLE
    assert record.reason == "PermissionError"
    assert record.signature is None
    assert record.fingerprint is None


def test_marks_invalid_pdf_signature(tmp_path: Path) -> None:
    write_file(tmp_path / "invoice.pdf", b"not a pdf")
    discovery = discover_files([tmp_path])

    result = build_intake_records(discovery.files)

    record = result.records[0]
    assert record.status is IntakeStatus.INVALID_SIGNATURE
    assert record.reason == "not_pdf"
    assert record.signature is not None
    assert record.fingerprint is None


def test_marks_empty_pdf_candidate(tmp_path: Path) -> None:
    write_file(tmp_path / "empty.pdf", b"")
    discovery = discover_files([tmp_path])

    result = build_intake_records(discovery.files)

    record = result.records[0]
    assert record.status is IntakeStatus.EMPTY
    assert record.reason == "empty"
    assert record.fingerprint is None


def test_preserves_blocked_symlink_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = tmp_path / "linked.pdf"
    write_file(link, b"%PDF-1.7\n")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == link:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    discovery = discover_files([tmp_path])

    result = build_intake_records(discovery.files)

    record = result.records[0]
    assert record.status is IntakeStatus.BLOCKED
    assert record.reason == "SymbolicLink"
    assert record.signature is None
    assert record.fingerprint is None


def test_marks_signature_read_failure_as_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "blocked.pdf"
    write_file(path, b"%PDF-1.7\n")
    discovery = discover_files([tmp_path])

    def fail_signature(candidate: Path) -> PdfSignatureInspection:
        assert candidate == path
        return PdfSignatureInspection(
            path=candidate,
            status=PdfSignatureStatus.UNREADABLE,
            bytes_read=0,
            error="PermissionError",
        )

    monkeypatch.setattr(intake_records, "inspect_pdf_signature", fail_signature)

    result = build_intake_records(discovery.files)

    record = result.records[0]
    assert record.status is IntakeStatus.UNREADABLE
    assert record.reason == "PermissionError"
    assert record.signature is not None
    assert record.fingerprint is None


def test_marks_fingerprint_read_failure_as_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "blocked.pdf"
    write_file(path, b"%PDF-1.7\n")
    discovery = discover_files([tmp_path])

    def fail_fingerprint(
        candidate: Path,
        *,
        cancellation_check: object = None,
    ) -> ContentFingerprint:
        del cancellation_check
        assert candidate == path
        raise PermissionError

    monkeypatch.setattr(intake_records, "compute_sha256_fingerprint", fail_fingerprint)

    result = build_intake_records(discovery.files)

    record = result.records[0]
    assert record.status is IntakeStatus.UNREADABLE
    assert record.reason == "PermissionError"
    assert record.signature is not None
    assert record.signature.is_valid is True
    assert record.fingerprint is None


def test_can_omit_unsupported_files_before_intake(tmp_path: Path) -> None:
    write_file(tmp_path / "invoice.pdf", b"%PDF-1.7\n")
    write_file(tmp_path / "notes.txt", b"not a pdf")
    discovery = discover_files(
        [tmp_path],
        config=DiscoveryConfig(include_unsupported=False),
    )

    result = build_intake_records(discovery.files)

    assert len(result.records) == 1
    assert result.records[0].status is IntakeStatus.READY
