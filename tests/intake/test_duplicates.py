from pathlib import Path

from docweave.discovery import discover_files
from docweave.intake import IntakeStatus, build_intake_records


def write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_groups_ready_records_with_identical_fingerprints(tmp_path: Path) -> None:
    content = b"%PDF-1.7\nsame content"
    write_file(tmp_path / "a.pdf", content)
    write_file(tmp_path / "nested" / "b.pdf", content)
    write_file(tmp_path / "different.pdf", b"%PDF-1.7\ndifferent")

    discovery = discover_files([tmp_path])
    result = build_intake_records(discovery.files)

    assert result.ready_count == 3
    assert result.duplicate_count == 2
    assert len(result.duplicate_groups) == 1
    group = result.duplicate_groups[0]
    assert group.count == 2
    assert group.hex_digest == group.digest.hex()
    assert [record.relative_path for record in group.records] == [
        "a.pdf",
        "nested/b.pdf",
    ]
    assert result.duplicate_group_for_digest(group.digest) == group


def test_groups_multiple_duplicate_digests_deterministically(tmp_path: Path) -> None:
    write_file(tmp_path / "a1.pdf", b"%PDF-1.7\na")
    write_file(tmp_path / "a2.pdf", b"%PDF-1.7\na")
    write_file(tmp_path / "b1.pdf", b"%PDF-1.7\nb")
    write_file(tmp_path / "b2.pdf", b"%PDF-1.7\nb")

    discovery = discover_files([tmp_path])
    result = build_intake_records(discovery.files)

    assert result.duplicate_count == 4
    assert len(result.duplicate_groups) == 2
    assert [group.count for group in result.duplicate_groups] == [2, 2]
    second_group = result.duplicate_groups[1]
    assert result.duplicate_group_for_digest(second_group.digest) == second_group


def test_ignores_invalid_and_unsupported_records_for_duplicates(
    tmp_path: Path,
) -> None:
    content = b"%PDF-1.7\nsame content"
    write_file(tmp_path / "a.pdf", content)
    write_file(tmp_path / "b.pdf", b"not a pdf")
    write_file(tmp_path / "notes.txt", content)

    discovery = discover_files([tmp_path])
    result = build_intake_records(discovery.files)

    assert result.count_status(IntakeStatus.READY) == 1
    assert result.count_status(IntakeStatus.INVALID_SIGNATURE) == 1
    assert result.count_status(IntakeStatus.UNSUPPORTED) == 1
    assert result.duplicate_groups == ()
    assert result.duplicate_count == 0


def test_returns_none_for_unknown_duplicate_digest(tmp_path: Path) -> None:
    write_file(tmp_path / "a.pdf", b"%PDF-1.7\ncontent")
    discovery = discover_files([tmp_path])
    result = build_intake_records(discovery.files)

    assert result.duplicate_group_for_digest(b"x" * 32) is None
