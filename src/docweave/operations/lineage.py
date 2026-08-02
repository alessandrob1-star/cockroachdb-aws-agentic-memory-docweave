"""File lineage and mass operation preview contracts.

The objects in this module make the planned and observed file-name history
explicit before DocWeave executes any filesystem mutation. A rename is modeled
as a move whose parent directory does not change, because that is the safe
cross-platform filesystem primitive already supported by the operation core.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from docweave.core.paths import relative_posix_path
from docweave.operations.approval import operation_plan_fingerprint
from docweave.operations.batch import MAX_OPERATION_BATCH_ITEMS
from docweave.operations.execution import ExecutionStatus
from docweave.operations.organization import propose_safe_organization_copy
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    FileOperationStatus,
    plan_file_operation,
)
from docweave.operations.results import OperationResultRecord


class MassOperationMode(StrEnum):
    """Supported non-mutating mass organization preview modes."""

    COPY_TO_ORGANIZED = "copy_to_organized"
    MOVE_TO_ORGANIZED = "move_to_organized"
    RENAME_IN_PLACE = "rename_in_place"


class FileLineageAction(StrEnum):
    """User-facing file-history action derived from a filesystem primitive."""

    COPY = "copy"
    MOVE = "move"
    RENAME = "rename"
    RENAME_AND_MOVE = "rename_and_move"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MassOperationCandidate:
    """One classified document eligible for a mass organization preview."""

    source_path: Path
    proposed_class: str
    metadata: Mapping[str, str]
    proposal_id: str | None = None
    proposal_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class MassOperationPreviewItem:
    """One row in the human-reviewable mass operation preview table."""

    item_id: str
    proposal_id: str | None
    proposal_fingerprint: str | None
    source_relative_path: str
    original_directory: str
    original_filename: str
    proposed_directory: str
    proposed_filename: str
    action: FileLineageAction
    plan: FileOperationPlan
    plan_fingerprint: str
    batch_conflict_reason: str | None = None

    @property
    def status(self) -> FileOperationStatus:
        """Return deterministic pre-execution safety status."""
        if self.batch_conflict_reason is not None:
            return FileOperationStatus.COLLISION
        return self.plan.status

    @property
    def is_ready(self) -> bool:
        """Return whether the item can be submitted for human approval."""
        return self.plan.is_ready and self.batch_conflict_reason is None


@dataclass(frozen=True, slots=True)
class MassOperationPreview:
    """Bounded batch preview for copy, rename, and move operations."""

    mode: MassOperationMode
    authorized_root: Path
    items: tuple[MassOperationPreviewItem, ...]

    @property
    def total(self) -> int:
        """Return number of preview rows."""
        return len(self.items)

    @property
    def ready_count(self) -> int:
        """Return rows ready for explicit human approval."""
        return sum(1 for item in self.items if item.is_ready)

    @property
    def blocked_count(self) -> int:
        """Return rows blocked by deterministic safety checks."""
        return self.total - self.ready_count


@dataclass(frozen=True, slots=True)
class FileLineageEntry:
    """Append-only projected file-name and directory history row."""

    logical_document_key: str
    sequence: int
    action: FileLineageAction
    operation_batch_id: str | None
    batch_item_id: str | None
    proposal_id: str | None
    original_relative_path: str
    previous_relative_path: str
    next_relative_path: str
    original_directory: str
    original_filename: str
    previous_directory: str
    previous_filename: str
    next_directory: str
    next_filename: str
    status: str
    occurred_at_utc: datetime | None
    plan_fingerprint: str
    source_digest_before: str | None = None
    destination_digest_after: str | None = None


def build_mass_operation_preview(
    *,
    authorized_root: Path,
    candidates: Sequence[MassOperationCandidate],
    mode: MassOperationMode,
) -> MassOperationPreview:
    """Build a bounded mass operation preview without mutating files."""
    if not candidates:
        raise ValueError("mass operation preview must contain at least one item")
    if len(candidates) > MAX_OPERATION_BATCH_ITEMS:
        raise ValueError(
            f"mass operation preview cannot exceed {MAX_OPERATION_BATCH_ITEMS} items"
        )
    root = authorized_root.expanduser().resolve(strict=True)
    items = tuple(
        _preview_item(
            root=root,
            candidate=candidate,
            mode=mode,
            index=index,
        )
        for index, candidate in enumerate(candidates, start=1)
    )
    items = _mark_internal_destination_collisions(items)
    return MassOperationPreview(mode=mode, authorized_root=root, items=items)


def lineage_entry_from_preview_result(
    *,
    logical_document_key: str,
    original_relative_path: str,
    sequence: int,
    preview_item: MassOperationPreviewItem,
    result: OperationResultRecord,
) -> FileLineageEntry:
    """Project one operation preview and terminal result into file history."""
    if sequence < 1:
        raise ValueError("lineage sequence must be positive")
    action = (
        preview_item.action
        if result.status is ExecutionStatus.SUCCEEDED
        else FileLineageAction.BLOCKED
    )
    next_relative_path = (
        preview_item.plan.destination_relative_path
        if result.status is ExecutionStatus.SUCCEEDED
        else preview_item.plan.source_relative_path
    )
    occurred_at = result.completed_at_utc
    original_directory, original_filename = _split_relative_path(original_relative_path)
    previous_directory, previous_filename = _split_relative_path(
        preview_item.plan.source_relative_path
    )
    next_directory, next_filename = _split_relative_path(next_relative_path)
    return FileLineageEntry(
        logical_document_key=logical_document_key,
        sequence=sequence,
        action=action,
        operation_batch_id=result.batch_id,
        batch_item_id=result.batch_item_id,
        proposal_id=preview_item.proposal_id,
        original_relative_path=original_relative_path,
        previous_relative_path=preview_item.plan.source_relative_path,
        next_relative_path=next_relative_path,
        original_directory=original_directory,
        original_filename=original_filename,
        previous_directory=previous_directory,
        previous_filename=previous_filename,
        next_directory=next_directory,
        next_filename=next_filename,
        status=result.status.value,
        occurred_at_utc=occurred_at,
        plan_fingerprint=preview_item.plan_fingerprint,
        source_digest_before=result.source_digest_before,
        destination_digest_after=result.destination_digest_after,
    )


def _preview_item(
    *,
    root: Path,
    candidate: MassOperationCandidate,
    mode: MassOperationMode,
    index: int,
) -> MassOperationPreviewItem:
    source = candidate.source_path.expanduser().resolve(strict=True)
    source_relative_path = relative_posix_path(source, root)
    organization = propose_safe_organization_copy(
        source_path=source,
        authorized_root=root,
        proposed_class=candidate.proposed_class,
        metadata=candidate.metadata,
    )
    destination_relative_path = _destination_for_mode(
        mode=mode,
        source_relative_path=source_relative_path,
        organized_destination=organization.destination_relative_path,
    )
    operation = (
        FileOperation.COPY
        if mode is MassOperationMode.COPY_TO_ORGANIZED
        else FileOperation.MOVE
    )
    plan = plan_file_operation(
        FileOperationRequest(
            operation=operation,
            source_root=root,
            source_relative_path=source_relative_path,
            destination_root=root,
            destination_relative_path=destination_relative_path,
        )
    )
    original_directory, original_filename = _split_relative_path(source_relative_path)
    proposed_directory, proposed_filename = _split_relative_path(
        plan.destination_relative_path
    )
    return MassOperationPreviewItem(
        item_id=f"item-{index:04d}",
        proposal_id=candidate.proposal_id,
        proposal_fingerprint=candidate.proposal_fingerprint,
        source_relative_path=source_relative_path,
        original_directory=original_directory,
        original_filename=original_filename,
        proposed_directory=proposed_directory,
        proposed_filename=proposed_filename,
        action=_lineage_action(
            operation=operation,
            source_relative_path=source_relative_path,
            destination_relative_path=plan.destination_relative_path,
        ),
        plan=plan,
        plan_fingerprint=operation_plan_fingerprint(plan),
    )


def _destination_for_mode(
    *,
    mode: MassOperationMode,
    source_relative_path: str,
    organized_destination: str,
) -> str:
    if mode in {
        MassOperationMode.COPY_TO_ORGANIZED,
        MassOperationMode.MOVE_TO_ORGANIZED,
    }:
        return organized_destination
    source_directory, _source_filename = _split_relative_path(source_relative_path)
    _organized_directory, organized_filename = _split_relative_path(
        organized_destination
    )
    if source_directory == "":
        return organized_filename
    return f"{source_directory}/{organized_filename}"


def _lineage_action(
    *,
    operation: FileOperation,
    source_relative_path: str,
    destination_relative_path: str,
) -> FileLineageAction:
    if operation is FileOperation.COPY:
        return FileLineageAction.COPY
    source_directory, source_filename = _split_relative_path(source_relative_path)
    destination_directory, destination_filename = _split_relative_path(
        destination_relative_path
    )
    directory_changed = source_directory != destination_directory
    filename_changed = source_filename != destination_filename
    if directory_changed and filename_changed:
        return FileLineageAction.RENAME_AND_MOVE
    if directory_changed:
        return FileLineageAction.MOVE
    return FileLineageAction.RENAME


def _split_relative_path(relative_path: str) -> tuple[str, str]:
    path = Path(relative_path)
    filename = path.name
    directory = path.parent.as_posix()
    if directory == ".":
        directory = ""
    return directory, filename


def _mark_internal_destination_collisions(
    items: tuple[MassOperationPreviewItem, ...],
) -> tuple[MassOperationPreviewItem, ...]:
    destination_counts: dict[str, int] = {}
    for item in items:
        destination_counts[item.plan.destination_comparison_key] = (
            destination_counts.get(item.plan.destination_comparison_key, 0) + 1
        )
    return tuple(
        replace(item, batch_conflict_reason="duplicate_destination_in_batch")
        if destination_counts[item.plan.destination_comparison_key] > 1
        else item
        for item in items
    )
