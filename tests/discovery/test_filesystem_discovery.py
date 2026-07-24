from pathlib import Path

import pytest

from docweave.discovery import DiscoveryConfig, DiscoveryStatus, discover_files


def write_file(path: Path, content: bytes = b"content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_discovers_supported_pdfs_recursively(tmp_path: Path) -> None:
    write_file(tmp_path / "invoice.pdf", b"%PDF-1.7")
    write_file(tmp_path / "nested" / "contract.PDF", b"%PDF-1.7")
    write_file(tmp_path / "notes.txt", b"not a pdf")

    result = discover_files([tmp_path])

    assert result.limit_reached is False
    assert result.candidate_count == 2
    assert result.blocked_count == 0
    assert result.unsupported_count == 1
    assert result.unreadable_count == 0
    assert [file.relative_path for file in result.files] == [
        "invoice.pdf",
        "nested/contract.PDF",
        "notes.txt",
    ]
    assert {file.relative_path: file.status for file in result.files} == {
        "invoice.pdf": DiscoveryStatus.CANDIDATE,
        "nested/contract.PDF": DiscoveryStatus.CANDIDATE,
        "notes.txt": DiscoveryStatus.UNSUPPORTED,
    }


def test_can_exclude_unsupported_files(tmp_path: Path) -> None:
    write_file(tmp_path / "invoice.pdf")
    write_file(tmp_path / "notes.txt")

    result = discover_files(
        [tmp_path],
        config=DiscoveryConfig(include_unsupported=False),
    )

    assert [file.relative_path for file in result.files] == ["invoice.pdf"]
    assert result.unsupported_count == 0


def test_enforces_max_file_limit(tmp_path: Path) -> None:
    write_file(tmp_path / "a.pdf")
    write_file(tmp_path / "b.pdf")
    write_file(tmp_path / "c.pdf")

    result = discover_files([tmp_path], config=DiscoveryConfig(max_files=2))

    assert result.limit_reached is True
    assert len(result.files) == 2


def test_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "invoice.pdf"
    write_file(file_path)

    with pytest.raises(NotADirectoryError):
        discover_files([file_path])


def test_rejects_invalid_max_files() -> None:
    with pytest.raises(ValueError, match="max_files"):
        DiscoveryConfig(max_files=0)


def test_marks_supported_file_unreadable_when_metadata_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreadable = tmp_path / "blocked.pdf"
    write_file(unreadable)
    original_stat = Path.stat

    def fake_stat(path: Path, *, follow_symlinks: bool = True) -> object:
        if path == unreadable:
            raise PermissionError
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = discover_files([tmp_path])

    assert result.unreadable_count == 1
    assert result.files[0].relative_path == "blocked.pdf"
    assert result.files[0].status is DiscoveryStatus.UNREADABLE
    assert result.files[0].error == "PermissionError"


def test_marks_supported_file_unreadable_when_symlink_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreadable = tmp_path / "blocked.pdf"
    write_file(unreadable)
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == unreadable:
            raise PermissionError
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    result = discover_files([tmp_path])

    assert result.unreadable_count == 1
    assert result.files[0].relative_path == "blocked.pdf"
    assert result.files[0].status is DiscoveryStatus.UNREADABLE
    assert result.files[0].error == "PermissionError"


def test_comparison_key_is_case_insensitive_by_default(tmp_path: Path) -> None:
    write_file(tmp_path / "Folder" / "Invoice.PDF")

    result = discover_files([tmp_path])

    assert result.files[0].relative_path == "Folder/Invoice.PDF"
    assert result.files[0].comparison_key == "folder/invoice.pdf"


def test_can_preserve_case_sensitive_comparison_key(tmp_path: Path) -> None:
    write_file(tmp_path / "Folder" / "Invoice.PDF")

    result = discover_files(
        [tmp_path],
        config=DiscoveryConfig(case_sensitive_paths=True),
    )

    assert result.files[0].comparison_key == "Folder/Invoice.PDF"


def test_blocks_symbolic_link_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = tmp_path / "linked.pdf"
    write_file(link)

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == link:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    result = discover_files([tmp_path])

    assert result.blocked_count == 1
    assert {file.relative_path: file.status for file in result.files} == {
        "linked.pdf": DiscoveryStatus.BLOCKED,
    }
