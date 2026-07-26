from pathlib import Path

from docweave.desktop.scan import DesktopScanResult, ScanWorker, scan_authorized_root


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


def test_worker_emits_complete_snapshot(tmp_path: Path) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    completed: list[object] = []
    failures: list[str] = []
    worker = ScanWorker(tmp_path, scan_authorized_root)
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)

    worker.run()

    assert len(completed) == 1
    assert isinstance(completed[0], DesktopScanResult)
    assert failures == []


def test_worker_emits_minimized_error_category(tmp_path: Path) -> None:
    def fail_scan(root: Path) -> DesktopScanResult:
        raise PermissionError(f"private path must not leak: {root}")

    completed: list[object] = []
    failures: list[str] = []
    worker = ScanWorker(tmp_path, fail_scan)
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)

    worker.run()

    assert completed == []
    assert failures == ["PermissionError"]
