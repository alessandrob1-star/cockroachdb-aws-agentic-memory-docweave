"""Background-safe local discovery and intake orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from docweave.discovery import DiscoveryResult, discover_files
from docweave.intake import IntakeResult, build_intake_records


@dataclass(frozen=True, slots=True)
class DesktopScanResult:
    """Deterministic discovery evidence presented by the desktop shell."""

    root: Path
    discovery: DiscoveryResult
    intake: IntakeResult

    @property
    def attention_count(self) -> int:
        """Count records that are not ready for later extraction."""
        return len(self.intake.records) - self.intake.ready_count


ScanFunction = Callable[[Path], DesktopScanResult]


def scan_authorized_root(root: Path) -> DesktopScanResult:
    """Discover and inspect files strictly inside one authorized root."""
    discovery = discover_files((root,))
    intake = build_intake_records(discovery.files)
    return DesktopScanResult(
        root=discovery.scanned_roots[0],
        discovery=discovery,
        intake=intake,
    )


class ScanWorker(QObject):
    """Run deterministic scanning outside the Qt user-interface thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, root: Path, scan_function: ScanFunction) -> None:
        super().__init__()
        self._root = root
        self._scan_function = scan_function

    @Slot()
    def run(self) -> None:
        """Emit a complete snapshot or a minimized safe error category."""
        try:
            result = self._scan_function(self._root)
        except Exception as error:
            self.failed.emit(error.__class__.__name__)
            return
        self.completed.emit(result)
