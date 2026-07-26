from pathlib import Path

import pytest

from docweave.desktop.scan import ScanPhase, ScanProgress, scan_authorized_root
from docweave.desktop.workspace import (
    DesktopWorkspaceSession,
    WorkspacePhase,
    WorkspaceSnapshot,
)


def test_workspace_tracks_scan_result_and_validated_selection(tmp_path: Path) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    root = tmp_path.resolve()
    result = scan_authorized_root(root)
    session = DesktopWorkspaceSession()

    session.authorize(root)
    session.start_scan()
    session.record_progress(ScanProgress(ScanPhase.DISCOVERY, 1, None))
    session.record_progress(ScanProgress(ScanPhase.INTAKE, 1, 1))
    session.complete(result)
    session.select_documents(frozenset({"invoice.pdf"}))

    assert session.snapshot.phase is WorkspacePhase.COMPLETE
    assert session.snapshot.result is result
    assert session.snapshot.selected_document_keys == frozenset({"invoice.pdf"})


def test_workspace_rejects_invalid_transitions_and_results(tmp_path: Path) -> None:
    session = DesktopWorkspaceSession()

    with pytest.raises(RuntimeError, match="not authorized"):
        session.start_scan()

    session.authorize(tmp_path.resolve())
    session.start_scan()
    session.record_progress(ScanProgress(ScanPhase.DISCOVERY, 2, None))
    with pytest.raises(ValueError, match="monotonic"):
        session.record_progress(ScanProgress(ScanPhase.DISCOVERY, 1, None))

    other_root = tmp_path / "other"
    other_root.mkdir()
    with pytest.raises(ValueError, match="does not match"):
        session.complete(scan_authorized_root(other_root))

    session.fail("SafeError")
    assert session.snapshot.phase is WorkspacePhase.FAILED
    assert session.snapshot.error_category == "SafeError"


def test_workspace_cancellation_discards_partial_state(tmp_path: Path) -> None:
    session = DesktopWorkspaceSession()
    session.authorize(tmp_path.resolve())
    session.start_scan()
    session.record_progress(ScanProgress(ScanPhase.DISCOVERY, 1, None))

    session.request_cancellation()
    session.cancel()

    assert session.snapshot.phase is WorkspacePhase.CANCELLED
    assert session.snapshot.result is None
    assert session.snapshot.selected_document_keys == frozenset()


def test_workspace_rejects_active_reauthorization_and_unknown_selection(
    tmp_path: Path,
) -> None:
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    root = tmp_path.resolve()
    result = scan_authorized_root(root)
    session = DesktopWorkspaceSession()
    session.authorize(root)
    session.start_scan()

    with pytest.raises(RuntimeError, match="active"):
        session.authorize(root)
    with pytest.raises(RuntimeError, match="active"):
        session.start_scan()

    session.complete(result)
    with pytest.raises(ValueError, match="unknown key"):
        session.select_documents(frozenset({"not-observed.pdf"}))


def test_workspace_requires_active_scan_for_terminal_transitions(
    tmp_path: Path,
) -> None:
    session = DesktopWorkspaceSession()
    session.authorize(tmp_path.resolve())
    session.select_documents(frozenset())
    session.request_cancellation()

    with pytest.raises(RuntimeError, match="active scan"):
        session.record_progress(ScanProgress(ScanPhase.DISCOVERY, 1, None))
    with pytest.raises(RuntimeError, match="not active"):
        session.cancel()
    with pytest.raises(RuntimeError, match="not active"):
        session.fail("SafeError")
    with pytest.raises(RuntimeError, match="completed scan"):
        session.select_documents(frozenset({"invoice.pdf"}))

    session._snapshot = WorkspaceSnapshot(
        authorized_root=tmp_path.resolve(),
        phase=WorkspacePhase.COMPLETE,
    )
    with pytest.raises(RuntimeError, match="no scan result"):
        session.select_documents(frozenset({"invoice.pdf"}))
