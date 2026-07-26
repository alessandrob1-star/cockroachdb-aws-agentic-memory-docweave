"""Explicit in-memory state for one desktop workspace session."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docweave.desktop.scan import DesktopScanResult, ScanProgress


class WorkspacePhase(StrEnum):
    """Truthful lifecycle phases for the local desktop session."""

    EMPTY = "empty"
    READY = "ready"
    SCANNING = "scanning"
    CANCELLING = "cancelling"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """Immutable state exposed to the user-interface layer."""

    authorized_root: Path | None = None
    phase: WorkspacePhase = WorkspacePhase.EMPTY
    progress: ScanProgress | None = None
    result: DesktopScanResult | None = None
    selected_document_keys: frozenset[str] = frozenset()
    error_category: str | None = None


class DesktopWorkspaceSession:
    """Validate local session transitions without claiming persistence."""

    def __init__(self) -> None:
        self._snapshot = WorkspaceSnapshot()

    @property
    def snapshot(self) -> WorkspaceSnapshot:
        """Return the current immutable session snapshot."""
        return self._snapshot

    def authorize(self, root: Path) -> None:
        """Replace the authorized root and clear all prior scan state."""
        self._require_not_active()
        self._snapshot = WorkspaceSnapshot(
            authorized_root=root,
            phase=WorkspacePhase.READY,
        )

    def start_scan(self) -> None:
        """Enter scanning only when a root is explicitly authorized."""
        self._require_not_active()
        if self._snapshot.authorized_root is None:
            raise RuntimeError("workspace root is not authorized")
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=WorkspacePhase.SCANNING,
        )

    def record_progress(self, progress: ScanProgress) -> None:
        """Record monotonic progress for the active scan."""
        if self._snapshot.phase not in {
            WorkspacePhase.SCANNING,
            WorkspacePhase.CANCELLING,
        }:
            raise RuntimeError("scan progress requires an active scan")
        previous = self._snapshot.progress
        if (
            previous is not None
            and previous.phase is progress.phase
            and progress.completed < previous.completed
        ):
            raise ValueError("scan progress must be monotonic")
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=self._snapshot.phase,
            progress=progress,
        )

    def request_cancellation(self) -> None:
        """Record a user cancellation request for the active scan."""
        if self._snapshot.phase is not WorkspacePhase.SCANNING:
            return
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=WorkspacePhase.CANCELLING,
            progress=self._snapshot.progress,
        )

    def complete(self, result: DesktopScanResult) -> None:
        """Publish one complete scan snapshot after root validation."""
        self._require_active()
        if result.root != self._snapshot.authorized_root:
            raise ValueError("scan result root does not match the authorized root")
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=WorkspacePhase.COMPLETE,
            progress=self._snapshot.progress,
            result=result,
        )

    def cancel(self) -> None:
        """Finish an active scan without publishing partial results."""
        self._require_active()
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=WorkspacePhase.CANCELLED,
            progress=self._snapshot.progress,
        )

    def fail(self, error_category: str) -> None:
        """Record a minimized failure category and no partial result."""
        self._require_active()
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=WorkspacePhase.FAILED,
            progress=self._snapshot.progress,
            error_category=error_category,
        )

    def select_documents(self, comparison_keys: frozenset[str]) -> None:
        """Store a selection only from the current completed result."""
        if not comparison_keys and self._snapshot.phase is not WorkspacePhase.COMPLETE:
            return
        if self._snapshot.phase is not WorkspacePhase.COMPLETE:
            raise RuntimeError("document selection requires a completed scan")
        result = self._snapshot.result
        if result is None:
            raise RuntimeError("completed workspace has no scan result")
        available_keys = {
            record.discovered_file.comparison_key for record in result.intake.records
        }
        if not comparison_keys.issubset(available_keys):
            raise ValueError("document selection contains an unknown key")
        self._snapshot = WorkspaceSnapshot(
            authorized_root=self._snapshot.authorized_root,
            phase=self._snapshot.phase,
            progress=self._snapshot.progress,
            result=result,
            selected_document_keys=comparison_keys,
        )

    def _require_active(self) -> None:
        if self._snapshot.phase not in {
            WorkspacePhase.SCANNING,
            WorkspacePhase.CANCELLING,
        }:
            raise RuntimeError("workspace scan is not active")

    def _require_not_active(self) -> None:
        if self._snapshot.phase in {
            WorkspacePhase.SCANNING,
            WorkspacePhase.CANCELLING,
        }:
            raise RuntimeError("workspace scan is active")
