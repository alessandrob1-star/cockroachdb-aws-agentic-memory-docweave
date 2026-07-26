"""Virtualized desktop table models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)

from docweave.intake import IntakeRecord

_INVALID_INDEX = QModelIndex()
_SIZE_COLUMN = 3
_KIBIBYTE = 1_024


@dataclass(frozen=True, slots=True)
class DocumentTableRow:
    """Minimized presentation data for one locally inspected file."""

    name: str
    relative_path: str
    comparison_key: str
    status: str
    byte_size: int | None
    reason: str | None

    @classmethod
    def from_intake_record(cls, record: IntakeRecord) -> DocumentTableRow:
        """Map deterministic intake evidence without exposing file contents."""
        return cls(
            name=record.absolute_path.name,
            relative_path=record.relative_path,
            comparison_key=record.discovered_file.comparison_key,
            status=record.status.value,
            byte_size=record.discovered_file.byte_size,
            reason=record.reason,
        )


class DocumentTableModel(QAbstractTableModel):
    """Read-only table model suitable for thousands of discovered files."""

    _HEADERS = ("Document", "Relative path", "Status", "Size", "Details")

    def __init__(self) -> None:
        super().__init__()
        self._rows: tuple[DocumentTableRow, ...] = ()

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX,
    ) -> int:
        """Return the visible row count."""
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX,
    ) -> int:
        """Return the fixed presentation column count."""
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        """Return display or accessibility text for one cell."""
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        if not 0 <= index.column() < len(self._HEADERS):
            return None
        row = self._rows[index.row()]
        values = (
            row.name,
            row.relative_path,
            _status_label(row.status),
            _format_byte_size(row.byte_size),
            row.reason or "",
        )
        if role in {
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.AccessibleTextRole,
        }:
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.relative_path
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == _SIZE_COLUMN:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        """Return accessible horizontal headers."""
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return cast(object | None, super().headerData(section, orientation, role))

    def replace_records(self, records: tuple[IntakeRecord, ...]) -> None:
        """Replace the snapshot atomically for the view."""
        rows = tuple(DocumentTableRow.from_intake_record(record) for record in records)
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def clear(self) -> None:
        """Clear prior scan results."""
        self.beginResetModel()
        self._rows = ()
        self.endResetModel()

    def comparison_key_at(self, row: int) -> str | None:
        """Return the stable, root-relative identity for one visible row."""
        if not 0 <= row < len(self._rows):
            return None
        return self._rows[row].comparison_key


def _status_label(status: str) -> str:
    return status.replace("_", " ").title()


def _format_byte_size(byte_size: int | None) -> str:
    if byte_size is None:
        return "—"
    if byte_size < _KIBIBYTE:
        return f"{byte_size} B"
    if byte_size < _KIBIBYTE * _KIBIBYTE:
        return f"{byte_size / _KIBIBYTE:.1f} KB"
    return f"{byte_size / (_KIBIBYTE * _KIBIBYTE):.1f} MB"
