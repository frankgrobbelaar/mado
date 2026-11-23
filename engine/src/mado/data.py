"""Where Mado keeps its data, and how big each part is, for Settings > Your data: the database,
the cache, logs, backups, the tools and the pictures pasted in the data folder."""

import os
from dataclasses import dataclass
from pathlib import Path

from mado.config import DataPaths


@dataclass(frozen=True)
class DataSizes:
    folder: Path
    database: int  # mado.db with its write-ahead log
    cache: int  # what Mado can always make again
    logs: int
    backups: int
    tools: int  # ffmpeg
    pasted: int  # pictures pasted from the clipboard, kept till they're saved


def sizes(paths: DataPaths) -> DataSizes:
    """How big each part of Mado's data is now."""
    database = sum(
        _size(paths.database.with_name(paths.database.name + end)) for end in ("", "-wal", "-shm")
    )
    return DataSizes(
        folder=paths.root,
        database=database,
        cache=_tree(paths.cache),
        logs=_tree(paths.logs),
        backups=_tree(paths.backups),
        tools=_tree(paths.tools),
        pasted=_tree(paths.pasted),
    )


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _tree(folder: Path) -> int:
    """The bytes under a folder, nothing when it isn't there."""
    return sum(_size(Path(parent) / name) for parent, _, names in os.walk(folder) for name in names)
