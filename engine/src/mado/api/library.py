"""The library: its folders (adding and forgetting them, each as a tree of the folders inside it),
what it holds in numbers, the pictures that won't open, and the room on the drives it's on, for
Home."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, HTTPException, Response, status

from mado.api.common import ApiModel, Copies, Database, Finding, Scans, Watching
from mado.jobs import drive_of, needed_on
from mado.library import FolderError, add_folder, folders, remove_folder
from mado.previews import version
from mado.quarantine import by_drive

router = APIRouter()

_LISTED = "gone_at IS NULL AND read_at IS NOT NULL"  # in the grid: read, RAW, or won't open


class FolderNode(ApiModel):
    """A folder inside a library folder."""

    name: str
    dir: str  # where it is in its library folder: "2026/Trip"
    pictures: int  # in it and the folders inside it
    children: list[FolderNode]  # the newest pictures' first


class LibraryFolder(ApiModel):
    id: int
    path: str
    name: str  # its own name: "Phone"
    added_at: str
    available: bool  # False while its drive is unplugged
    looked: bool  # a scan has looked all through it since it was added
    pictures: int  # listed in the grid: read, camera RAW, or won't open
    reading: int  # found and still to read
    raw: int
    broken: int  # won't open
    children: list[FolderNode]


class NewFolder(ApiModel):
    path: str


class LibraryPart(ApiModel):
    folder_id: int
    name: str
    pictures: int


class Library(ApiModel):
    """The whole library in numbers, for Home."""

    folders: int
    pictures: int  # listed in the grid
    size: int  # bytes, every picture found
    reading: int  # found and still to read
    raw: int
    broken: int  # won't open
    damaged: int  # of those, marked as damaged by the owner: not asked about again
    parts: list[LibraryPart]  # each library folder's pictures, in the order they were added


class Unopened(ApiModel):
    """A picture that won't open."""

    id: int
    name: str
    path: str
    folder: str  # the folder it's in
    format: str | None
    size: int
    problem: str  # why, in a sentence
    version: str


class WontOpen(ApiModel):
    pictures: list[Unopened]  # those not marked as damaged, newest file first
    damaged: int  # marked as damaged, so not listed


class DriveSpace(ApiModel):
    """Room on a drive the library uses."""

    drive: str  # "D:"
    connected: bool
    free: int | None  # bytes; None while it isn't connected
    total: int | None
    pictures: int  # bytes of the library's pictures on it
    quarantine: int  # bytes waiting in its quarantine
    queue: int  # bytes the pictures waiting in the queue want there


@router.get("/folders")
def list_folders(conn: Database) -> list[LibraryFolder]:
    """The library's folders, in the order they were added, each with the folders inside it."""
    counts = {
        row["folder_id"]: row
        for row in conn.execute(
            f"""SELECT folder_id,
                       COUNT(*) FILTER (WHERE {_LISTED}) AS pictures,
                       COUNT(*) FILTER (WHERE read_at IS NULL) AS reading,
                       COUNT(*) FILTER (WHERE {_LISTED} AND raw = 1) AS raw,
                       COUNT(*) FILTER (WHERE {_LISTED} AND problem IS NOT NULL) AS broken
                FROM pictures WHERE gone_at IS NULL GROUP BY folder_id"""  # noqa: S608 - fixed
        )
    }
    trees = _trees(conn)
    found: list[LibraryFolder] = []
    for folder in folders(conn):
        count = counts.get(folder.id)
        found.append(
            LibraryFolder(
                id=folder.id,
                path=str(folder.path),
                name=folder.path.name or str(folder.path),
                added_at=folder.added_at,
                available=folder.path.is_dir(),
                looked=folder.walked_at is not None,
                pictures=count["pictures"] if count else 0,
                reading=count["reading"] if count else 0,
                raw=count["raw"] if count else 0,
                broken=count["broken"] if count else 0,
                children=trees.get(folder.id, []),
            )
        )
    return found


@router.post("/folders", status_code=status.HTTP_201_CREATED)
def new_folder(body: NewFolder, conn: Database, scanner: Scans, watcher: Watching) -> LibraryFolder:
    """Adds a folder to the library, reads it and watches it. Nothing in it changes."""
    if not body.path.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a folder to add.")
    try:
        folder = add_folder(conn, Path(body.path.strip()), now=datetime.now().astimezone())
    except FolderError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    scanner.request()
    if watcher is not None:
        watcher.follow()
    return next(each for each in list_folders(conn) if each.id == folder.id)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_folder(
    folder_id: int, conn: Database, copies: Copies, watcher: Watching, finder: Finding
) -> Response:
    """Takes a folder out of the library, with Mado's copies of its pictures. The pictures
    themselves stay exactly where they are."""
    forgotten = remove_folder(conn, folder_id)
    if forgotten is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That folder isn't in your library.")
    copies.forget(forgotten)
    if watcher is not None:
        watcher.follow()
    finder.regroup(conn)  # its pictures leave their groups
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/library")
def library(conn: Database) -> Library:
    """The library in numbers, for Home."""
    totals = conn.execute(
        f"""SELECT COUNT(*) FILTER (WHERE {_LISTED}) AS pictures,
                   COALESCE(SUM(size), 0) AS size,
                   COUNT(*) FILTER (WHERE read_at IS NULL) AS reading,
                   COUNT(*) FILTER (WHERE {_LISTED} AND raw = 1) AS raw,
                   COUNT(*) FILTER (WHERE {_LISTED} AND problem IS NOT NULL) AS broken,
                   COUNT(*) FILTER (WHERE {_LISTED} AND problem IS NOT NULL AND damaged = 1)
                       AS damaged
            FROM pictures WHERE gone_at IS NULL"""  # noqa: S608 - a fixed fragment
    ).fetchone()
    listed = {
        row["folder_id"]: row["pictures"]
        for row in conn.execute(
            f"""SELECT folder_id, COUNT(*) AS pictures FROM pictures
                WHERE {_LISTED} GROUP BY folder_id"""  # noqa: S608 - a fixed fragment
        )
    }
    found = folders(conn)
    return Library(
        folders=len(found),
        pictures=totals["pictures"],
        size=totals["size"],
        reading=totals["reading"],
        raw=totals["raw"],
        broken=totals["broken"],
        damaged=totals["damaged"],
        parts=[
            LibraryPart(
                folder_id=folder.id,
                name=folder.path.name or str(folder.path),
                pictures=listed.get(folder.id, 0),
            )
            for folder in found
        ],
    )


@router.get("/library/wont-open")
def wont_open(conn: Database) -> WontOpen:
    """The pictures that won't open, but those the owner marked as damaged: each with why. They
    were left exactly as they are."""
    rows = conn.execute(
        f"""SELECT id, name, path, format, size, modified, problem FROM pictures
            WHERE {_LISTED} AND problem IS NOT NULL AND damaged = 0
            ORDER BY modified DESC, id"""  # noqa: S608 - a fixed fragment
    ).fetchall()
    marked: int = conn.execute(
        f"""SELECT COUNT(*) FROM pictures
            WHERE {_LISTED} AND problem IS NOT NULL AND damaged = 1"""  # noqa: S608 - fixed
    ).fetchone()[0]
    return WontOpen(
        pictures=[
            Unopened(
                id=row["id"],
                name=row["name"],
                path=row["path"],
                folder=str(PureWindowsPath(row["path"]).parent),
                format=row["format"],
                size=row["size"],
                problem=row["problem"],
                version=version(row["modified"], row["size"]),
            )
            for row in rows
        ],
        damaged=marked,
    )


@router.get("/space")
def space(conn: Database) -> list[DriveSpace]:
    """The drives the library's folders are on, the one with the most of its pictures first:
    what's free, what the pictures use, what waits in quarantine and what the queue wants."""
    used: dict[str, int] = {}
    for folder in folders(conn):
        used.setdefault(drive_of(folder.path), 0)
    for row in conn.execute(
        "SELECT f.path, COALESCE(SUM(p.size), 0) AS size FROM folders AS f"
        " LEFT JOIN pictures AS p ON p.folder_id = f.id AND p.gone_at IS NULL GROUP BY f.id"
    ):
        drive = drive_of(Path(row["path"]))
        used[drive] = used.get(drive, 0) + row["size"]
    aside = {drive.casefold(): size for drive, size in by_drive(conn).items()}
    found: list[DriveSpace] = []
    for drive, size in sorted(used.items(), key=lambda each: (-each[1], each[0])):
        connected, free, total = _room(drive)
        found.append(
            DriveSpace(
                drive=drive,
                connected=connected,
                free=free,
                total=total,
                pictures=size,
                quarantine=aside.get(drive.casefold(), 0),
                queue=needed_on(conn, drive),
            )
        )
    return found


def _room(drive: str) -> tuple[bool, int | None, int | None]:
    """Whether a drive is connected, and its free and whole bytes."""
    root = Path(f"{drive}\\")
    if not root.exists():
        return False, None, None
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return True, None, None
    return True, usage.free, usage.total


class _Node:
    """A folder of the tree as it's put together: its pictures, the newest, and its folders."""

    def __init__(self, name: str, place: str) -> None:
        self.name, self.place = name, place
        self.pictures = 0
        self.newest = ""
        self.children: dict[str, _Node] = {}

    def answer(self) -> FolderNode:
        inside = sorted(self.children.values(), key=lambda node: node.name.casefold())
        inside.sort(key=lambda node: node.newest, reverse=True)
        return FolderNode(
            name=self.name,
            dir=self.place,
            pictures=self.pictures,
            children=[node.answer() for node in inside],
        )


def _trees(conn: sqlite3.Connection) -> dict[int, list[FolderNode]]:
    """The folders inside each library folder that hold listed pictures, each counting the
    pictures in it and in the folders inside it, the folder with the newest pictures first."""
    roots: dict[int, _Node] = {}
    for row in conn.execute(
        f"""SELECT folder_id, dir, COUNT(*) AS pictures, MAX(taken_at) AS newest
            FROM pictures WHERE {_LISTED} AND dir <> ''
            GROUP BY folder_id, dir"""  # noqa: S608 - a fixed fragment
    ):
        node = roots.setdefault(row["folder_id"], _Node("", ""))
        names = str(row["dir"]).split("/")
        for depth, name in enumerate(names):
            node = node.children.setdefault(name, _Node(name, "/".join(names[: depth + 1])))
            node.pictures += row["pictures"]
            node.newest = max(node.newest, row["newest"])
    return {folder_id: root.answer().children for folder_id, root in roots.items()}
