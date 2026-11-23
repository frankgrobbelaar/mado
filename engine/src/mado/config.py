"""Where Mado keeps its data."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    """Mado's data folder: the database, backups, logs and tools. The owner's pictures never go
    here: only a picture pasted from the clipboard, till Save writes it out."""

    root: Path

    @property
    def database(self) -> Path:
        return self.root / "mado.db"

    @property
    def search(self) -> Path:
        """What SigLIP read each picture into, for search: beside the database, never in a
        backup or the export, read again when it's lost (see mado/search.py)."""
        return self.root / "search.db"

    @property
    def backups(self) -> Path:
        """Copies of the database, one a night (see mado/backups.py)."""
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def cache(self) -> Path:
        """What Mado keeps for a while and can always make again. Anything in it can go."""
        return self.root / "cache"

    @property
    def pasted(self) -> Path:
        """Pictures pasted from the clipboard, kept till they're saved (see mado/pasting.py)."""
        return self.root / "pasted"

    @property
    def wallpapers(self) -> Path:
        """The wallpapers Mado made and set, and its copy of the owner's own (mado/wallpaper.py)."""
        return self.root / "wallpapers"

    @property
    def tools(self) -> Path:
        """What Mado downloads to work with, such as ffmpeg (see downloads.json)."""
        return self.root / "tools"

    @classmethod
    def default(cls) -> DataPaths:
        r"""Mado's data folder: %LOCALAPPDATA%\Mado, or the folder in MADO_DATA_DIR when that is
        set (development uses engine/.dev-data, never the real folder)."""
        if override := os.environ.get("MADO_DATA_DIR"):
            return cls(Path(os.path.normpath(override)))
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return cls(base / "Mado")
