from pathlib import Path

import pytest

from docweave.desktop.opening import (
    PdfOpenFailure,
    PdfOpenValidationError,
    validate_pdf_for_open,
)


def test_validates_current_pdf_inside_authorized_root(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.7\ninvoice")

    assert validate_pdf_for_open(path, tmp_path) == path.resolve()


@pytest.mark.parametrize(
    ("name", "content", "category"),
    [
        ("notes.txt", b"%PDF-1.7\n", PdfOpenFailure.NOT_PDF),
        ("invalid.pdf", b"not a pdf", PdfOpenFailure.INVALID_SIGNATURE),
    ],
)
def test_rejects_non_pdf_or_invalid_content(
    tmp_path: Path,
    name: str,
    content: bytes,
    category: PdfOpenFailure,
) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    with pytest.raises(PdfOpenValidationError) as captured:
        validate_pdf_for_open(path, tmp_path)

    assert captured.value.category is category


def test_rejects_missing_directory_and_outside_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(PdfOpenValidationError) as captured:
        validate_pdf_for_open(missing, tmp_path)
    assert captured.value.category is PdfOpenFailure.UNAVAILABLE

    root = tmp_path / "authorized"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.7\n")
    with pytest.raises(PdfOpenValidationError) as captured:
        validate_pdf_for_open(outside, root)
    assert captured.value.category is PdfOpenFailure.OUTSIDE_AUTHORIZED_ROOT


def test_rejects_directory_and_symbolic_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "folder.pdf"
    directory.mkdir()
    with pytest.raises(PdfOpenValidationError) as captured:
        validate_pdf_for_open(directory, tmp_path)
    assert captured.value.category is PdfOpenFailure.NOT_A_FILE

    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.7\n")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(candidate: Path) -> bool:
        return candidate == path or original_is_symlink(candidate)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(PdfOpenValidationError) as captured:
        validate_pdf_for_open(path, tmp_path)
    assert captured.value.category is PdfOpenFailure.SYMBOLIC_LINK
