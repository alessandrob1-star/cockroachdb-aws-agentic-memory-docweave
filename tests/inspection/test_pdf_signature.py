from pathlib import Path

from docweave.inspection import PDF_SIGNATURE, PdfSignatureStatus, inspect_pdf_signature


def test_accepts_pdf_signature_prefix(tmp_path: Path) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(PDF_SIGNATURE + b"1.7\ncontent")

    result = inspect_pdf_signature(path)

    assert result.is_valid is True
    assert result.status is PdfSignatureStatus.VALID_PDF
    assert result.bytes_read == len(PDF_SIGNATURE)
    assert result.error is None


def test_rejects_non_pdf_prefix(tmp_path: Path) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"not a pdf")

    result = inspect_pdf_signature(path)

    assert result.is_valid is False
    assert result.status is PdfSignatureStatus.NOT_PDF
    assert result.bytes_read == len(PDF_SIGNATURE)


def test_marks_short_non_matching_file_as_not_pdf(tmp_path: Path) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PD")

    result = inspect_pdf_signature(path)

    assert result.status is PdfSignatureStatus.NOT_PDF
    assert result.bytes_read == 3


def test_marks_empty_file_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    result = inspect_pdf_signature(path)

    assert result.status is PdfSignatureStatus.EMPTY
    assert result.bytes_read == 0


def test_marks_missing_file_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "missing.pdf"

    result = inspect_pdf_signature(path)

    assert result.status is PdfSignatureStatus.UNREADABLE
    assert result.bytes_read == 0
    assert result.error == "FileNotFoundError"
