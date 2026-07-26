"""Background-safe local discovery and intake orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event
from typing import Protocol

from PySide6.QtCore import QObject, Signal, Slot

from docweave.core.cancellation import (
    CancellationCheck,
    CancellationRequestedError,
    raise_if_cancelled,
)
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


class ScanPhase(StrEnum):
    """Observable phases of deterministic local scanning."""

    DISCOVERY = "discovery"
    INTAKE = "intake"


@dataclass(frozen=True, slots=True)
class ScanProgress:
    """Minimized progress evidence safe for presentation."""

    phase: ScanPhase
    completed: int
    total: int | None

    def __post_init__(self) -> None:
        if self.completed < 0:
            raise ValueError("completed must not be negative")
        if self.total is not None and (self.total < 0 or self.completed > self.total):
            raise ValueError("total must not be below completed")


ScanProgressCallback = Callable[[ScanProgress], None]


class ScanFunction(Protocol):
    """Injectable progressive scan contract."""

    def __call__(
        self,
        root: Path,
        *,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> DesktopScanResult: ...


def scan_authorized_root(
    root: Path,
    *,
    progress_callback: ScanProgressCallback | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> DesktopScanResult:
    """Discover and inspect files strictly inside one authorized root."""

    def report_discovery(completed: int) -> None:
        if progress_callback is not None:
            progress_callback(
                ScanProgress(
                    phase=ScanPhase.DISCOVERY,
                    completed=completed,
                    total=None,
                )
            )

    def report_intake(completed: int, total: int) -> None:
        if progress_callback is not None:
            progress_callback(
                ScanProgress(
                    phase=ScanPhase.INTAKE,
                    completed=completed,
                    total=total,
                )
            )

    discovery = discover_files(
        (root,),
        progress_callback=report_discovery,
        cancellation_check=cancellation_check,
    )
    intake = build_intake_records(
        discovery.files,
        progress_callback=report_intake,
        cancellation_check=cancellation_check,
    )
    raise_if_cancelled(cancellation_check)
    return DesktopScanResult(
        root=discovery.scanned_roots[0],
        discovery=discovery,
        intake=intake,
    )


class ScanWorker(QObject):
    """Run deterministic scanning outside the Qt user-interface thread."""

    completed = Signal(object)
    progressed = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, root: Path, scan_function: ScanFunction) -> None:
        super().__init__()
        self._root = root
        self._scan_function = scan_function
        self._cancellation_requested = Event()

    def request_cancellation(self) -> None:
        """Request a thread-safe cooperative stop."""
        self._cancellation_requested.set()

    @Slot()
    def run(self) -> None:
        """Emit a complete snapshot or a minimized safe error category."""
        try:
            result = self._scan_function(
                self._root,
                progress_callback=self._report_progress,
                cancellation_check=self._cancellation_requested.is_set,
            )
            raise_if_cancelled(self._cancellation_requested.is_set)
        except CancellationRequestedError:
            self.cancelled.emit()
            return
        except Exception as error:
            self.failed.emit(error.__class__.__name__)
            return
        self.completed.emit(result)

    def _report_progress(self, progress: ScanProgress) -> None:
        if (
            progress.completed <= 1
            or progress.completed % 25 == 0
            or progress.total == progress.completed
        ):
            self.progressed.emit(progress)
