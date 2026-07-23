"""Deterministic local filesystem discovery for authorized roots."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from docweave.core.paths import (
    path_comparison_key,
    relative_posix_path,
    resolve_existing_path,
)


class DiscoveryStatus(StrEnum):
    """Discovery result state before content inspection or database matching."""

    BLOCKED = "blocked"
    CANDIDATE = "candidate"
    UNSUPPORTED = "unsupported"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    """Configuration for a bounded local discovery run."""

    supported_extensions: frozenset[str] = frozenset({".pdf"})
    max_files: int = 10_000
    include_unsupported: bool = True
    case_sensitive_paths: bool = False

    def __post_init__(self) -> None:
        if self.max_files < 1:
            msg = "max_files must be at least 1"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """A file observed within an authorized root."""

    root: Path
    absolute_path: Path
    relative_path: str
    comparison_key: str
    status: DiscoveryStatus
    byte_size: int | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Summary of a bounded discovery run."""

    files: tuple[DiscoveredFile, ...]
    scanned_roots: tuple[Path, ...]
    limit_reached: bool

    @property
    def candidate_count(self) -> int:
        return self.count_status(DiscoveryStatus.CANDIDATE)

    @property
    def blocked_count(self) -> int:
        return self.count_status(DiscoveryStatus.BLOCKED)

    @property
    def unsupported_count(self) -> int:
        return self.count_status(DiscoveryStatus.UNSUPPORTED)

    @property
    def unreadable_count(self) -> int:
        return self.count_status(DiscoveryStatus.UNREADABLE)

    def count_status(self, status: DiscoveryStatus) -> int:
        return sum(1 for file in self.files if file.status is status)


def discover_files(
    roots: Iterable[Path],
    *,
    config: DiscoveryConfig | None = None,
) -> DiscoveryResult:
    """Discover files recursively within already-authorized local roots."""
    active_config = config or DiscoveryConfig()
    resolved_roots = tuple(resolve_existing_path(root) for root in roots)
    discovered: list[DiscoveredFile] = []
    limit_reached = False

    for root in resolved_roots:
        if not root.is_dir():
            msg = f"authorized root is not a directory: {root}"
            raise NotADirectoryError(msg)

        for path in _iter_files(root):
            if len(discovered) >= active_config.max_files:
                limit_reached = True
                break

            discovered_file = _inspect_file(path, root, active_config)
            if discovered_file.status is DiscoveryStatus.UNSUPPORTED:
                if active_config.include_unsupported:
                    discovered.append(discovered_file)
                continue

            discovered.append(discovered_file)

        if limit_reached:
            break

    return DiscoveryResult(
        files=tuple(discovered),
        scanned_roots=resolved_roots,
        limit_reached=limit_reached,
    )


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if path.is_symlink() or path.is_file():
            yield path


def _inspect_file(
    path: Path,
    root: Path,
    config: DiscoveryConfig,
) -> DiscoveredFile:
    relative_path = relative_posix_path(path, root)
    comparison_key = path_comparison_key(
        relative_path,
        case_sensitive=config.case_sensitive_paths,
    )

    if path.is_symlink():
        return DiscoveredFile(
            root=root,
            absolute_path=path,
            relative_path=relative_path,
            comparison_key=comparison_key,
            status=DiscoveryStatus.BLOCKED,
            byte_size=None,
            error="SymbolicLink",
        )

    if path.suffix.casefold() not in config.supported_extensions:
        return DiscoveredFile(
            root=root,
            absolute_path=path,
            relative_path=relative_path,
            comparison_key=comparison_key,
            status=DiscoveryStatus.UNSUPPORTED,
            byte_size=None,
        )

    try:
        stat = path.stat()
    except OSError as exc:
        return DiscoveredFile(
            root=root,
            absolute_path=path,
            relative_path=relative_path,
            comparison_key=comparison_key,
            status=DiscoveryStatus.UNREADABLE,
            byte_size=None,
            error=exc.__class__.__name__,
        )

    return DiscoveredFile(
        root=root,
        absolute_path=path,
        relative_path=relative_path,
        comparison_key=comparison_key,
        status=DiscoveryStatus.CANDIDATE,
        byte_size=stat.st_size,
    )
