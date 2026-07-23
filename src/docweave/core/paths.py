"""Path normalization helpers for authorized local filesystem roots."""

from pathlib import Path


def resolve_existing_path(path: Path) -> Path:
    """Resolve an existing path without accepting ambiguous relative state."""
    return path.expanduser().resolve(strict=True)


def relative_posix_path(path: Path, root: Path) -> str:
    """Return a stable slash-separated relative path inside an authorized root."""
    relative = path.relative_to(root)
    return relative.as_posix()


def path_comparison_key(relative_path: str, *, case_sensitive: bool = False) -> str:
    """Return the normalized key used for collision comparison."""
    normalized = relative_path.replace("\\", "/")
    if case_sensitive:
        return normalized
    return normalized.casefold()
