from datetime import UTC, datetime
from pathlib import Path

import pytest

from docweave.operations import (
    ExecutionReason,
    ExecutionStatus,
    FileLineageAction,
    FileOperation,
    FileOperationStatus,
    MassOperationCandidate,
    MassOperationMode,
    OperationResultRecord,
    ResultDisposition,
    build_mass_operation_preview,
    lineage_entry_from_preview_result,
)


def _pdf(path: Path, content: bytes = b"%PDF-1.7\n%%EOF\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _candidate(path: Path) -> MassOperationCandidate:
    return MassOperationCandidate(
        source_path=path,
        proposed_class="invoice",
        metadata={
            "supplier": "ACME SRL",
            "invoice_number": "INV-2026-004",
        },
        proposal_id="proposal-001",
        proposal_fingerprint="f" * 64,
    )


def _result(
    *,
    status: ExecutionStatus,
    batch_id: str = "batch-001",
    item_id: str = "item-0001",
) -> OperationResultRecord:
    return OperationResultRecord(
        batch_id=batch_id,
        batch_item_id=item_id,
        execution_key=f"{batch_id}:{item_id}",
        execution_id=f"{batch_id}:{item_id}:execution",
        status=status,
        reason=(
            ExecutionReason.SUCCEEDED
            if status is ExecutionStatus.SUCCEEDED
            else ExecutionReason.DESTINATION_COLLISION
        ),
        disposition=ResultDisposition.EXECUTED,
        attempted_at_utc=datetime(2026, 8, 2, 8, 0, tzinfo=UTC),
        completed_at_utc=datetime(2026, 8, 2, 8, 1, tzinfo=UTC),
        approval_id="approval-001",
        source_exists_after=status is not ExecutionStatus.SUCCEEDED,
        destination_exists_after=status is ExecutionStatus.SUCCEEDED,
        source_digest_before="a" * 64,
        destination_digest_after="a" * 64
        if status is ExecutionStatus.SUCCEEDED
        else None,
    )


def test_builds_mass_rename_preview_without_mutating_file(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")

    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(source),),
        mode=MassOperationMode.RENAME_IN_PLACE,
    )

    item = preview.items[0]
    assert preview.total == 1
    assert preview.ready_count == 1
    assert item.action is FileLineageAction.RENAME
    assert item.plan.request.operation is FileOperation.MOVE
    assert item.original_directory == "incoming"
    assert item.original_filename == "scan_001.pdf"
    assert item.proposed_directory == "incoming"
    assert item.proposed_filename == "invoice_acme-srl_inv-2026-004.pdf"
    assert source.exists()
    assert not (tmp_path / item.plan.destination_relative_path).exists()


def test_builds_mass_move_preview_with_original_and_target_columns(
    tmp_path: Path,
) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")

    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(source),),
        mode=MassOperationMode.MOVE_TO_ORGANIZED,
    )

    item = preview.items[0]
    assert item.action is FileLineageAction.RENAME_AND_MOVE
    assert item.plan.request.operation is FileOperation.MOVE
    assert item.original_directory == "incoming"
    assert item.proposed_directory == "DocWeave Organized/Invoices"
    assert item.proposed_filename == "invoice_acme-srl_inv-2026-004.pdf"
    assert len(item.plan_fingerprint) == 64


def test_mass_preview_surfaces_destination_collisions(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")
    _pdf(tmp_path / "incoming" / "invoice_acme-srl_inv-2026-004.pdf")

    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(source),),
        mode=MassOperationMode.RENAME_IN_PLACE,
    )

    item = preview.items[0]
    assert preview.ready_count == 0
    assert preview.blocked_count == 1
    assert item.status is FileOperationStatus.COLLISION
    assert item.plan.reason.value == "destination_collision"


def test_mass_preview_blocks_duplicate_destinations_inside_same_batch(
    tmp_path: Path,
) -> None:
    first = _pdf(tmp_path / "incoming" / "scan_001.pdf", b"%PDF-1.7\none\n%%EOF\n")
    second = _pdf(tmp_path / "incoming" / "scan_002.pdf", b"%PDF-1.7\ntwo\n%%EOF\n")

    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(first), _candidate(second)),
        mode=MassOperationMode.MOVE_TO_ORGANIZED,
    )

    assert preview.ready_count == 0
    assert preview.blocked_count == 2
    assert {item.status for item in preview.items} == {FileOperationStatus.COLLISION}
    assert {item.batch_conflict_reason for item in preview.items} == {
        "duplicate_destination_in_batch"
    }


def test_mass_preview_enforces_batch_limit(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")
    candidates = tuple(_candidate(source) for _index in range(1_001))

    with pytest.raises(ValueError, match="cannot exceed 1000"):
        build_mass_operation_preview(
            authorized_root=tmp_path,
            candidates=candidates,
            mode=MassOperationMode.RENAME_IN_PLACE,
        )


def test_lineage_entry_records_original_previous_and_next_paths(
    tmp_path: Path,
) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")
    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(source),),
        mode=MassOperationMode.MOVE_TO_ORGANIZED,
    )

    entry = lineage_entry_from_preview_result(
        logical_document_key="workspace-001:document-001",
        original_relative_path="incoming/scan_001.pdf",
        sequence=1,
        preview_item=preview.items[0],
        result=_result(status=ExecutionStatus.SUCCEEDED),
    )

    assert entry.action is FileLineageAction.RENAME_AND_MOVE
    assert entry.original_relative_path == "incoming/scan_001.pdf"
    assert entry.previous_relative_path == "incoming/scan_001.pdf"
    assert entry.next_relative_path == (
        "DocWeave Organized/Invoices/invoice_acme-srl_inv-2026-004.pdf"
    )
    assert entry.original_filename == "scan_001.pdf"
    assert entry.next_filename == "invoice_acme-srl_inv-2026-004.pdf"
    assert entry.status == "succeeded"
    assert entry.proposal_id == "proposal-001"
    assert entry.source_digest_before == "a" * 64


def test_lineage_entry_keeps_blocked_operation_at_previous_location(
    tmp_path: Path,
) -> None:
    source = _pdf(tmp_path / "incoming" / "scan_001.pdf")
    preview = build_mass_operation_preview(
        authorized_root=tmp_path,
        candidates=(_candidate(source),),
        mode=MassOperationMode.MOVE_TO_ORGANIZED,
    )

    entry = lineage_entry_from_preview_result(
        logical_document_key="workspace-001:document-001",
        original_relative_path="incoming/scan_001.pdf",
        sequence=2,
        preview_item=preview.items[0],
        result=_result(status=ExecutionStatus.BLOCKED),
    )

    assert entry.action is FileLineageAction.BLOCKED
    assert entry.previous_relative_path == "incoming/scan_001.pdf"
    assert entry.next_relative_path == "incoming/scan_001.pdf"
    assert entry.status == "blocked"
