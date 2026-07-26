from pathlib import Path

import pytest

from docweave.core.cancellation import CancellationCheck
from docweave.desktop.scan import (
    DesktopScanResult,
    ScanPhase,
    ScanProgress,
    ScanProgressCallback,
    ScanWorker,
    scan_authorized_root,
)


def test_scans_only_the_authorized_root_and_reports_attention(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    (tmp_path / "invalid.pdf").write_bytes(b"not a pdf")

    result = scan_authorized_root(tmp_path)

    assert result.root == tmp_path.resolve()
    assert len(result.discovery.files) == 2
    assert result.intake.ready_count == 1
    assert result.attention_count == 1
    assert {record.relative_path for record in result.intake.records} == {
        "invalid.pdf",
        "nested/invoice.pdf",
    }


def test_scan_reports_discovery_and_intake_progress(tmp_path: Path) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    progress: list[ScanProgress] = []

    scan_authorized_root(tmp_path, progress_callback=progress.append)

    assert progress == [
        ScanProgress(ScanPhase.DISCOVERY, 1, None),
        ScanProgress(ScanPhase.INTAKE, 1, 1),
    ]


def test_progress_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError, match="negative"):
        ScanProgress(ScanPhase.DISCOVERY, -1, None)
    with pytest.raises(ValueError, match="below completed"):
        ScanProgress(ScanPhase.INTAKE, 2, 1)
    with pytest.raises(ValueError, match="below completed"):
        ScanProgress(ScanPhase.INTAKE, 0, -1)


def test_worker_emits_complete_snapshot(tmp_path: Path) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    completed: list[object] = []
    failures: list[str] = []
    progress: list[object] = []
    worker = ScanWorker(tmp_path, scan_authorized_root)
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)
    worker.progressed.connect(progress.append)

    worker.run()

    assert len(completed) == 1
    assert isinstance(completed[0], DesktopScanResult)
    assert failures == []
    assert progress == [
        ScanProgress(ScanPhase.DISCOVERY, 1, None),
        ScanProgress(ScanPhase.INTAKE, 1, 1),
    ]


def test_worker_emits_minimized_error_category(tmp_path: Path) -> None:
    def fail_scan(
        root: Path,
        *,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> DesktopScanResult:
        del progress_callback, cancellation_check
        raise PermissionError(f"private path must not leak: {root}")

    completed: list[object] = []
    failures: list[str] = []
    worker = ScanWorker(tmp_path, fail_scan)
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)

    worker.run()

    assert completed == []
    assert failures == ["PermissionError"]


def test_worker_emits_expected_cancellation_without_failure(tmp_path: Path) -> None:
    completed: list[object] = []
    failures: list[str] = []
    cancellations: list[bool] = []
    worker = ScanWorker(tmp_path, scan_authorized_root)
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)
    worker.cancelled.connect(lambda: cancellations.append(True))
    worker.request_cancellation()

    worker.run()

    assert completed == []
    assert failures == []
    assert cancellations == [True]
