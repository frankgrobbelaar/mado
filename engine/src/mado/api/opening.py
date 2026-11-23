"""Pictures from anywhere: what's dropped on the window, picked, pasted, or opened from File
Explorer, Open with or the command line (the shell hands over the paths), and a picture pasted
from the clipboard. One picture opens its page; several, or a folder, open Many at once
(mado/outside.py, mado/pasting.py, mado/core/opening.py)."""

import sqlite3
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from mado import batches, outside, pasting
from mado.api.batches import LeftOut, Picked, picked_out
from mado.api.common import ApiModel, Copies, Database, Paths, SetAside
from mado.api.pictures import PictureDetails, details
from mado.core.opening import Entry, nothing_to_open, what_opens
from mado.outside import OpenError
from mado.pasting import MOST_BYTES, PasteError

router = APIRouter()

type OpenHow = Literal["dropped", "picked", "pasted", "opened"]


class OpenIn(ApiModel):
    """Paths to open: dropped, picked, pasted (files copied in File Explorer, or a path copied
    as words), or opened from File Explorer, Open with or the command line."""

    paths: Annotated[list[str], Field(min_length=1, max_length=batches.MOST)]
    how: OpenHow = "opened"


class Opened(ApiModel):
    picture: PictureDetails | None  # one picture: its page
    picked: Picked | None  # several pictures, or a folder: Many at once, with them chosen
    left_out: list[LeftOut]  # beside one picture, what wasn't taken, and why


@router.post("/open")
def open_paths(
    body: OpenIn, conn: Database, aside: SetAside, copies: Copies, paths: Paths
) -> Opened:
    """Opens what's given: one picture as Mado knows it (the library's, or one outside the
    library, read now), with what else was given and left out; several, or a folder, as Many at
    once would take them. 404 or 422, with why, when none of it is a picture."""
    given = [outside.reachable(each) for each in body.paths if each.strip()]
    entries = [Entry(str(path), outside.found(path)) for path in given]
    match what_opens(entries):
        case "many":
            found = batches.from_paths(conn, [str(path) for path in given], body.how)
            return Opened(picture=None, picked=picked_out(found), left_out=[])
        case "page":
            one = next(
                path for path, entry in zip(given, entries, strict=True) if entry.found == "picture"
            )
            left = [
                LeftOut(name=path.name or str(path), why=outside.why_not(path))
                for path, entry in zip(given, entries, strict=True)
                if entry.found != "picture"
            ]
            try:
                picture_id = outside.open_picture(
                    conn, one, now=_now(), forget=copies.forget, data=paths
                )
            except OpenError as error:
                raise HTTPException(error.status, str(error)) from None
            return Opened(picture=_details(conn, picture_id, aside), picked=None, left_out=left)
        case "nothing":
            left = [(path.name or str(path), outside.why_not(path)) for path in given]
            missing = all(entry.found == "missing" for entry in entries)
            unplugged = {
                PureWindowsPath(path).drive
                for path, entry in zip(given, entries, strict=True)
                if entry.found == "missing" and not outside.drive_there(path)
            }
            raise HTTPException(
                status.HTTP_404_NOT_FOUND if missing else status.HTTP_422_UNPROCESSABLE_CONTENT,
                nothing_to_open(left, entries, unplugged_drives=unplugged)
                if left
                else "There was nothing to open.",
            )


_PASTED: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post("/pasted", openapi_extra=_PASTED)
async def pasted(request: Request, conn: Database, paths: Paths, aside: SetAside) -> PictureDetails:
    """Keeps a picture pasted from the clipboard (its bytes, as the window has them: PNG) in
    Mado's data folder, never the owner's, and says it as a picture outside the library; the
    same picture pasted again is the one kept already. 413 for one too big, 422 for what isn't a
    picture."""
    told = request.headers.get("content-length", "")
    if told.isdigit() and int(told) > MOST_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(PasteError(_TOO_BIG, 413)))
    data = await request.body()

    def keep() -> PictureDetails:
        try:
            picture_id = pasting.keep_pasted(conn, paths.pasted, data, now=_now())
        except PasteError as error:
            raise HTTPException(error.status, str(error)) from None
        return _details(conn, picture_id, aside)

    return await run_in_threadpool(keep)


_TOO_BIG = (
    f"That picture is too big to paste: Mado takes pictures up to "
    f"{round(pasting.MOST_PIXELS / 1_000_000)} megapixels from the clipboard. Save it as a file, "
    "then open that."
)


def _details(conn: sqlite3.Connection, picture_id: int, aside: SetAside) -> PictureDetails:
    row = conn.execute("SELECT * FROM pictures WHERE id = ?", (picture_id,)).fetchone()
    return details(conn, row, aside)


def _now() -> datetime:
    return datetime.now().astimezone()
