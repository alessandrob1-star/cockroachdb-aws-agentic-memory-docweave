from pathlib import Path

from PySide6.QtCore import Qt

from docweave.desktop.models import DocumentTableModel
from docweave.desktop.scan import scan_authorized_root


def test_virtualized_model_presents_intake_evidence(
    tmp_path: Path,
    qt_application: object,
) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    (tmp_path / "large.pdf").write_bytes(b"%PDF-" + b"x" * (2 * 1_024 * 1_024))
    (tmp_path / "medium.pdf").write_bytes(b"%PDF-" + b"x" * (2 * 1_024))
    (tmp_path / "invalid.pdf").write_bytes(b"not a pdf")
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    result = scan_authorized_root(tmp_path)
    model = DocumentTableModel()

    model.replace_records(result.intake.records)

    assert model.rowCount() == 5
    assert model.columnCount() == 5
    assert (
        model.headerData(
            0,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.DisplayRole.value,
        )
        == "Document"
    )
    rows = {
        str(model.data(model.index(row, 0))): str(model.data(model.index(row, 2)))
        for row in range(model.rowCount())
    }
    assert rows == {
        "invalid.pdf": "Invalid Signature",
        "invoice.pdf": "Ready",
        "large.pdf": "Ready",
        "medium.pdf": "Ready",
        "notes.txt": "Unsupported",
    }
    paths_and_rows = {
        str(model.data(model.index(row, 0))): row for row in range(model.rowCount())
    }
    large_row = paths_and_rows["large.pdf"]
    medium_row = paths_and_rows["medium.pdf"]
    assert model.data(model.index(large_row, 3)) == "2.0 MB"
    assert model.data(model.index(medium_row, 3)) == "2.0 KB"
    assert (
        model.data(
            model.index(large_row, 1),
            Qt.ItemDataRole.ToolTipRole,
        )
        == "large.pdf"
    )
    assert (
        model.data(
            model.index(large_row, 3),
            Qt.ItemDataRole.TextAlignmentRole,
        )
        is not None
    )
    assert model.data(model.index(-1, -1)) is None
    assert model.data(model.createIndex(0, 99)) is None
    assert (
        model.headerData(
            0,
            Qt.Orientation.Vertical,
            Qt.ItemDataRole.DisplayRole,
        )
        == 1
    )
    assert (
        model.data(
            model.index(large_row, 0),
            Qt.ItemDataRole.DecorationRole,
        )
        is None
    )


def test_model_clear_removes_prior_snapshot(
    tmp_path: Path,
    qt_application: object,
) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    model = DocumentTableModel()
    model.replace_records(scan_authorized_root(tmp_path).intake.records)

    model.clear()

    assert model.rowCount() == 0
