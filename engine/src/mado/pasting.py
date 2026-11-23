"""A picture pasted from the clipboard (a screenshot, or one copied from a browser or another
app), which has no file of its own: kept in Mado's data folder, in `pasted`, never in the owner's
folders, as a PNG named by when it was pasted ("Pasted 2026-11-23 14.05.png"). It's a picture
outside the library (mado/outside.py) that Save writes out, as a new picture into a folder the
owner picks; unsaved, it's forgotten after a month unopened, as any picture from outside is.
The same picture pasted again opens the one already kept.
"""

import hashlib
import io
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from mado.core.opening import pasted_name
from mado.library import record, save_facts
from mado.pictures import read_facts

# The biggest picture Mado takes from the clipboard: 2^26 pixels, about 67 megapixels, as that's
# all the window's own clipboard hands a page (256 MiB of pixels: past it, an empty picture).
# Measured on the owner's PC (docs/stack/tauri.md, "Paste"): the window hands over a 66-megapixel
# picture in 1.2 s, and Mado keeps a 100-megapixel one in 0.7 s and makes its view in 1.6 s.
MOST_PIXELS = 1 << 26
# Most a PNG of that many pixels takes: 4 bytes a pixel, uncompressed, and room for its header.
MOST_BYTES = MOST_PIXELS * 4 + (1 << 20)


class PasteError(Exception):
    """A paste Mado couldn't keep, with a sentence saying why, and the answer it makes."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def keep_pasted(conn: sqlite3.Connection, folder: Path, data: bytes, *, now: datetime) -> int:
    """Keeps a pasted picture in `folder` and says its number; the same picture pasted before
    is that one, opened again. Raises PasteError."""
    if len(data) > MOST_BYTES:
        raise PasteError(_too_big(None), 413)
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            format_ = image.format
            if width * height > MOST_PIXELS:
                raise PasteError(_too_big((width, height)), 413)
            if format_ != "PNG":  # kept as PNG whatever the clipboard gave
                image.load()
                written = io.BytesIO()
                image.save(written, format="PNG")
                data = written.getvalue()
    except PasteError:
        raise
    except UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError:
        raise PasteError(
            "What's on the clipboard isn't a picture Mado can read. Copy the picture again, "
            "then paste it.",
            422,
        ) from None
    stamp = now.isoformat()
    again = _pasted_before(conn, data)
    if again is not None:
        with conn:
            conn.execute("UPDATE pictures SET opened_at = ? WHERE id = ?", (stamp, again))
        return again
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / pasted_name(now, lambda name: (folder / name).exists())
        writing = path.with_name(f"{path.name}.{secrets.token_hex(4)}.part")
        writing.write_bytes(data)
        writing.replace(path)
    except OSError as error:
        raise PasteError(
            f"Mado couldn't keep the pasted picture in its data folder: "
            f"{error.strerror or error}. Nothing of yours changed.",
            507,
        ) from None
    stat = path.stat()
    with conn:
        _, picture_id = record(
            conn, None, path, "", "picture", stat.st_size, stat.st_mtime_ns, stamp
        )
        conn.execute(
            "UPDATE pictures SET pasted = 1, opened_at = ? WHERE id = ?", (stamp, picture_id)
        )
    save_facts(conn, picture_id, read_facts(path, "picture"), now=now)
    return picture_id


def _pasted_before(conn: sqlite3.Connection, data: bytes) -> int | None:
    """The pasted picture kept already with these very bytes, if there is one."""
    rows = conn.execute(
        "SELECT id, path FROM pictures WHERE pasted = 1 AND gone_at IS NULL AND size = ?",
        (len(data),),
    ).fetchall()
    if not rows:
        return None
    digest = hashlib.blake2b(data).digest()
    for row in rows:
        try:
            same = hashlib.blake2b(Path(row["path"]).read_bytes()).digest() == digest
        except OSError:
            continue
        if same:
            return int(row["id"])
    return None


def _too_big(size: tuple[int, int] | None) -> str:
    said = f" ({size[0]:,} × {size[1]:,})" if size else ""
    return (
        f"That picture is too big to paste{said}: Mado takes pictures up to "
        f"{round(MOST_PIXELS / 1_000_000)} megapixels from the clipboard. Save it as a file, then "
        "open that."
    )
