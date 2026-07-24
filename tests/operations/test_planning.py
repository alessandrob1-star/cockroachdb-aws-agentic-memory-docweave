from collections.abc import Iterator
from pathlib import Path

import pytest

from docweave.operations import (
    FileOperation,
    FileOperationReason,
    FileOperationRequest,
    FileOperationStatus,
    plan_file_operation,
)


def write_file(path: Path, content: bytes = b"content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_plans_copy_without_creating_missing_parent_directories(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source = source_root / "incoming" / "invoice.pdf"
    destination_root.mkdir()
    write_file(source)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="incoming/invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="Invoices/2026/invoice.pdf",
        ),
    )

    assert plan.is_ready is True
    assert plan.operation is FileOperation.COPY
    assert plan.status is FileOperationStatus.READY
    assert plan.reason is FileOperationReason.READY
    assert plan.source_path == source.resolve()
    assert plan.destination_relative_path == "Invoices/2026/invoice.pdf"
    assert plan.destination_comparison_key == "invoices/2026/invoice.pdf"
    assert [
        path.relative_to(destination_root) for path in plan.planned_parent_directories
    ] == [
        Path("Invoices"),
        Path("Invoices/2026"),
    ]
    assert not (destination_root / "Invoices").exists()


def test_blocks_destination_path_traversal(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.MOVE,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="../outside.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.INVALID_DESTINATION_PATH


def test_blocks_reserved_windows_destination_names(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="archive/CON.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.RESERVED_DESTINATION_NAME


def test_reports_existing_destination_collision(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "invoice.pdf", b"unrelated")

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.COLLISION
    assert plan.reason is FileOperationReason.DESTINATION_COLLISION


def test_reports_case_insensitive_destination_collision(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "Invoice.PDF", b"unrelated")

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.COLLISION
    assert plan.reason is FileOperationReason.DESTINATION_COLLISION


def test_preserves_case_sensitive_destination_key(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
            case_sensitive_paths=True,
        ),
    )

    assert plan.status is FileOperationStatus.READY
    assert plan.reason is FileOperationReason.READY
    assert plan.destination_comparison_key == "invoice.pdf"


def test_reports_no_op_for_same_source_and_destination(tmp_path: Path) -> None:
    write_file(tmp_path / "invoice.pdf")

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.MOVE,
            source_root=tmp_path,
            source_relative_path="invoice.pdf",
            destination_root=tmp_path,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.NO_OP
    assert plan.reason is FileOperationReason.SAME_SOURCE_AND_DESTINATION


def test_blocks_missing_source(tmp_path: Path) -> None:
    destination_root = tmp_path / "organized"
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=tmp_path,
            source_relative_path="missing.pdf",
            destination_root=destination_root,
            destination_relative_path="missing.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.SOURCE_MISSING


def test_blocks_invalid_source_path(tmp_path: Path) -> None:
    destination_root = tmp_path / "organized"
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=tmp_path,
            source_relative_path="",
            destination_root=destination_root,
            destination_relative_path="missing.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.INVALID_SOURCE_PATH
    assert plan.source_path is None
    assert plan.destination_path is None


def test_blocks_source_directory(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    (source_root / "folder.pdf").mkdir(parents=True)
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="folder.pdf",
            destination_root=destination_root,
            destination_relative_path="folder.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.SOURCE_NOT_FILE


def test_blocks_source_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source = source_root / "invoice.pdf"
    write_file(source)
    destination_root.mkdir()
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == source.resolve():
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.SOURCE_BLOCKED_SYMLINK


def test_blocks_unreadable_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source = source_root / "invoice.pdf"
    write_file(source)
    destination_root.mkdir()
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == source.resolve():
            raise PermissionError
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.SOURCE_UNREADABLE


def test_blocks_missing_parent_when_creation_is_not_allowed(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="missing/invoice.pdf",
            allow_missing_parent_directories=False,
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.DESTINATION_PARENT_MISSING
    assert plan.planned_parent_directories == ()


def test_plans_only_missing_nested_parent_directories(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    (destination_root / "existing").mkdir(parents=True)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="existing/missing/invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.READY
    assert [
        path.relative_to(destination_root) for path in plan.planned_parent_directories
    ] == [
        Path("existing/missing"),
    ]


def test_blocks_destination_parent_that_is_a_file(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "blocked")

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="blocked/invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.DESTINATION_PARENT_NOT_DIRECTORY


def test_blocks_unreadable_destination_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    destination_parent = destination_root / "blocked"
    write_file(source_root / "invoice.pdf")
    destination_parent.mkdir(parents=True)
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == destination_parent.resolve():
            raise PermissionError
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="blocked/invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.DESTINATION_PARENT_UNREADABLE


def test_allows_distinct_sibling_after_case_insensitive_scan(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "receipt.pdf", b"unrelated")

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.READY
    assert plan.reason is FileOperationReason.READY


def test_blocks_unreadable_destination_sibling_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()
    original_iterdir = Path.iterdir

    def fake_iterdir(path: Path) -> Iterator[Path]:
        if path == destination_root.resolve():
            raise PermissionError
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.COLLISION
    assert plan.reason is FileOperationReason.DESTINATION_PARENT_UNREADABLE


def test_blocks_destination_name_with_trailing_dot(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    write_file(source_root / "invoice.pdf")
    destination_root.mkdir()

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="bad./invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.BLOCKED
    assert plan.reason is FileOperationReason.RESERVED_DESTINATION_NAME


def test_reports_case_insensitive_collision_from_sibling_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    destination = destination_root / "invoice.pdf"
    write_file(source_root / "invoice.pdf")
    write_file(destination_root / "Invoice.PDF", b"unrelated")
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == destination.resolve(strict=False):
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source_root,
            source_relative_path="invoice.pdf",
            destination_root=destination_root,
            destination_relative_path="invoice.pdf",
        ),
    )

    assert plan.status is FileOperationStatus.COLLISION
    assert plan.reason is FileOperationReason.DESTINATION_COLLISION
