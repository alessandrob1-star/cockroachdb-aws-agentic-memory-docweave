"""Deterministic pre-execution planning for local file operations."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from docweave.core.paths import path_comparison_key, relative_posix_path

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    },
)


class FileOperation(StrEnum):
    """Supported local file operation kinds."""

    COPY = "copy"
    MOVE = "move"


class FileOperationStatus(StrEnum):
    """Pre-execution operation planning status."""

    READY = "ready"
    BLOCKED = "blocked"
    COLLISION = "collision"
    NO_OP = "no_op"


class FileOperationReason(StrEnum):
    """Machine-readable reason for a file operation planning outcome."""

    READY = "ready"
    DESTINATION_COLLISION = "destination_collision"
    DESTINATION_PARENT_MISSING = "destination_parent_missing"
    DESTINATION_PARENT_NOT_DIRECTORY = "destination_parent_not_directory"
    DESTINATION_PARENT_UNREADABLE = "destination_parent_unreadable"
    INVALID_DESTINATION_PATH = "invalid_destination_path"
    INVALID_SOURCE_PATH = "invalid_source_path"
    RESERVED_DESTINATION_NAME = "reserved_destination_name"
    SAME_SOURCE_AND_DESTINATION = "same_source_and_destination"
    SOURCE_BLOCKED_SYMLINK = "source_blocked_symlink"
    SOURCE_MISSING = "source_missing"
    SOURCE_NOT_FILE = "source_not_file"
    SOURCE_UNREADABLE = "source_unreadable"


@dataclass(frozen=True, slots=True)
class FileOperationRequest:
    """Requested file operation before deterministic safety planning."""

    operation: FileOperation
    source_root: Path
    source_relative_path: str
    destination_root: Path
    destination_relative_path: str
    allow_missing_parent_directories: bool = True
    case_sensitive_paths: bool = False


@dataclass(frozen=True, slots=True)
class FileOperationPlan:
    """Immutable preview of a file operation before human approval."""

    request: FileOperationRequest
    status: FileOperationStatus
    reason: FileOperationReason
    source_root: Path
    source_path: Path | None
    source_relative_path: str
    destination_root: Path
    destination_path: Path | None
    destination_relative_path: str
    destination_comparison_key: str
    planned_parent_directories: tuple[Path, ...] = ()
    error: str | None = None

    @property
    def operation(self) -> FileOperation:
        return self.request.operation

    @property
    def is_ready(self) -> bool:
        return self.status is FileOperationStatus.READY


def plan_file_operation(request: FileOperationRequest) -> FileOperationPlan:
    """Plan a local copy or move without mutating the filesystem."""
    source_root = request.source_root.expanduser().resolve(strict=True)
    destination_root = request.destination_root.expanduser().resolve(strict=True)
    source_path: Path | None = None
    destination_path: Path | None = None
    source_relative_path = request.source_relative_path
    destination_relative_path = request.destination_relative_path
    destination_comparison_key = path_comparison_key(
        destination_relative_path,
        case_sensitive=request.case_sensitive_paths,
    )
    planned_parent_directories: tuple[Path, ...] = ()
    status = FileOperationStatus.READY
    reason = FileOperationReason.READY

    invalid_reason = _invalid_path_reason(
        source_relative_path=request.source_relative_path,
        destination_relative_path=request.destination_relative_path,
    )
    if invalid_reason is not None:
        status = FileOperationStatus.BLOCKED
        reason = invalid_reason
    else:
        source_path = _safe_relative_path(source_root, request.source_relative_path)
        destination_path = _safe_relative_path(
            destination_root,
            request.destination_relative_path,
        )
        source_relative_path = relative_posix_path(source_path, source_root)
        destination_relative_path = relative_posix_path(
            destination_path,
            destination_root,
        )
        destination_comparison_key = path_comparison_key(
            destination_relative_path,
            case_sensitive=request.case_sensitive_paths,
        )
        status, reason, planned_parent_directories = _evaluate_valid_request(
            request,
            source_path,
            destination_path,
            destination_root,
            destination_comparison_key,
        )

    return FileOperationPlan(
        request=request,
        status=status,
        reason=reason,
        source_root=source_root,
        source_path=source_path,
        source_relative_path=source_relative_path,
        destination_root=destination_root,
        destination_path=destination_path,
        destination_relative_path=destination_relative_path,
        destination_comparison_key=destination_comparison_key,
        planned_parent_directories=planned_parent_directories,
    )


def _evaluate_valid_request(
    request: FileOperationRequest,
    source_path: Path,
    destination_path: Path,
    destination_root: Path,
    destination_comparison_key: str,
) -> tuple[FileOperationStatus, FileOperationReason, tuple[Path, ...]]:
    planned_parent_directories: tuple[Path, ...] = ()
    status = FileOperationStatus.READY
    reason = FileOperationReason.READY
    if _has_reserved_windows_name(destination_path, destination_root):
        status = FileOperationStatus.BLOCKED
        reason = FileOperationReason.RESERVED_DESTINATION_NAME
    elif (source_reason := _source_blocker(source_path)) is not None:
        status = FileOperationStatus.BLOCKED
        reason = source_reason
    elif source_path == destination_path:
        status = FileOperationStatus.NO_OP
        reason = FileOperationReason.SAME_SOURCE_AND_DESTINATION
    else:
        status, reason, planned_parent_directories = _evaluate_destination(
            request,
            destination_path,
            destination_root,
            destination_comparison_key,
        )

    return status, reason, planned_parent_directories


def _evaluate_destination(
    request: FileOperationRequest,
    destination_path: Path,
    destination_root: Path,
    destination_comparison_key: str,
) -> tuple[FileOperationStatus, FileOperationReason, tuple[Path, ...]]:
    parent_result = _planned_parent_directories(destination_path, destination_root)
    status = FileOperationStatus.READY
    reason = FileOperationReason.READY
    planned_parent_directories: tuple[Path, ...] = ()

    if isinstance(parent_result, FileOperationReason):
        status = FileOperationStatus.BLOCKED
        reason = parent_result
    elif parent_result and not request.allow_missing_parent_directories:
        status = FileOperationStatus.BLOCKED
        reason = FileOperationReason.DESTINATION_PARENT_MISSING
    elif (
        collision_reason := _destination_collision(
            destination_path,
            destination_root,
            destination_comparison_key,
            case_sensitive_paths=request.case_sensitive_paths,
        )
    ) is not None:
        status = FileOperationStatus.COLLISION
        reason = collision_reason
    else:
        planned_parent_directories = parent_result

    return status, reason, planned_parent_directories


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    destination = (root / path).resolve(strict=False)
    destination.relative_to(root)
    return destination


def _invalid_path_reason(
    *,
    source_relative_path: str,
    destination_relative_path: str,
) -> FileOperationReason | None:
    if _is_invalid_relative_path(source_relative_path):
        return FileOperationReason.INVALID_SOURCE_PATH
    if _is_invalid_relative_path(destination_relative_path):
        return FileOperationReason.INVALID_DESTINATION_PATH
    return None


def _is_invalid_relative_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return (
        relative_path.strip() == ""
        or path.is_absolute()
        or any(part in {"..", ""} for part in path.parts)
    )


def _has_reserved_windows_name(path: Path, root: Path) -> bool:
    for part in path.relative_to(root).parts:
        if part.endswith((" ", ".")):
            return True
        stem = part.split(".", maxsplit=1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            return True
    return False


def _source_blocker(source_path: Path) -> FileOperationReason | None:
    try:
        if source_path.is_symlink():
            return FileOperationReason.SOURCE_BLOCKED_SYMLINK
        if not source_path.exists():
            return FileOperationReason.SOURCE_MISSING
        if not source_path.is_file():
            return FileOperationReason.SOURCE_NOT_FILE
    except OSError:
        return FileOperationReason.SOURCE_UNREADABLE
    return None


def _planned_parent_directories(
    destination_path: Path,
    destination_root: Path,
) -> tuple[Path, ...] | FileOperationReason:
    missing: list[Path] = []
    parent = destination_path.parent

    while parent != destination_root:
        try:
            if parent.exists():
                if parent.is_dir():
                    return tuple(reversed(missing))
                return FileOperationReason.DESTINATION_PARENT_NOT_DIRECTORY
        except OSError:
            return FileOperationReason.DESTINATION_PARENT_UNREADABLE

        missing.append(parent)
        parent = parent.parent

    return tuple(reversed(missing))


def _destination_collision(
    destination_path: Path,
    destination_root: Path,
    destination_comparison_key: str,
    *,
    case_sensitive_paths: bool,
) -> FileOperationReason | None:
    try:
        if destination_path.exists():
            return FileOperationReason.DESTINATION_COLLISION
        if case_sensitive_paths or not destination_path.parent.exists():
            return None

        for sibling in destination_path.parent.iterdir():
            sibling_relative_path = relative_posix_path(sibling, destination_root)
            sibling_key = path_comparison_key(
                sibling_relative_path,
                case_sensitive=case_sensitive_paths,
            )
            if sibling_key == destination_comparison_key:
                return FileOperationReason.DESTINATION_COLLISION
    except OSError:
        return FileOperationReason.DESTINATION_PARENT_UNREADABLE
    return None
