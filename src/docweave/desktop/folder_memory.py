"""Local desktop folder preference storage."""

from pathlib import Path
from typing import Protocol, cast

from PySide6.QtCore import QSettings

_LAST_AUTHORIZED_FOLDER_KEY = "desktop/lastAuthorizedFolder"


class FolderMemory(Protocol):
    """Store and retrieve the last successful authorized folder selection."""

    def last_authorized_folder(self) -> Path | None:
        """Return the last valid authorized folder, if it is still available."""

    def remember_authorized_folder(self, folder: Path) -> None:
        """Persist one successfully authorized folder path."""


class QtFolderMemory:
    """Persist desktop folder preference through the local Qt settings store."""

    def __init__(
        self,
        *,
        organization: str = "DocWeave",
        application: str = "DocWeave",
        key: str = _LAST_AUTHORIZED_FOLDER_KEY,
    ) -> None:
        self._organization = organization
        self._application = application
        self._key = key

    def last_authorized_folder(self) -> Path | None:
        """Return the remembered folder only when it still exists."""
        raw_value = cast(
            str,
            QSettings(self._organization, self._application).value(
                self._key,
                "",
                str,
            ),
        )
        if not raw_value:
            return None
        try:
            resolved = Path(raw_value).resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_dir():
            return None
        return resolved

    def remember_authorized_folder(self, folder: Path) -> None:
        """Persist a valid folder without storing any runtime configuration."""
        resolved = folder.resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError("authorized folder must be a directory")
        settings = QSettings(self._organization, self._application)
        settings.setValue(self._key, str(resolved))
        settings.sync()
