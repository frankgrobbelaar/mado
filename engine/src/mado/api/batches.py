"""Many at once: the pictures a batch is made of, what it takes, See it first's three, putting it
in the queue, and the batches done that Home tells of (mado/batches.py, mado/samples.py)."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import Field

from mado import batches
from mado.api.common import (
    ApiModel,
    Copies,
    Database,
    FirstLook,
    Models,
    Searching,
    Toolbox,
    Working,
)
from mado.api.fixes import FixStepIn
from mado.api.looks import LookIn
from mado.api.making import Need, SizeIn
from mado.api.pictures import Shown
from mado.api.search import found_ids
from mado.api.styles import PaintIn
from mado.batches import BatchError, Picture
from mado.core.batch import Starts, sampled, steps_in_order
from mado.core.files import kind_of
from mado.core.models import Quality
from mado.core.quality import Format
from mado.making import NO_RAW_REPLACE, saving_from
from mado.previews import version
from mado.samples import SampleSet

router = APIRouter()

type How = Literal[
    "ticked", "folder", "search", "favourites", "dropped", "picked", "pasted", "opened"
]
_DONE_DAYS = 7  # how long Home tells of a batch done


class SizeStep(SizeIn):
    """Make it for a screen: the Size tab's choices, each picture's own subject and model."""

    step: Literal["size"] = "size"


class LookStep(LookIn):
    """A look, with its strength and touches: the Looks tab's choices."""

    step: Literal["look"] = "look"


class CutoutStep(ApiModel):
    """Cut out the subject, found without a click: Fast, Best, or as this PC suits; with nothing,
    a colour or the rest of the picture blurred behind it."""

    step: Literal["cutout"] = "cutout"
    quality: Quality | None = None
    behind: Literal["nothing", "colour", "blurred"] = "nothing"
    colour: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class FixStep(FixStepIn):
    """The fixes: noise, blur, JPEG blocks and a dark photo, each off or at its setting: the Fix
    tab's choices."""

    step: Literal["fix"] = "fix"


class PaintStep(PaintIn):
    """A painting style, at its strength, in each picture's own colours or the style's: the Looks
    tab's painting styles. A picture's own style goes in a batch once it's kept as a style."""

    step: Literal["paint"] = "paint"


type Step = Annotated[
    CutoutStep | FixStep | SizeStep | PaintStep | LookStep, Field(discriminator="step")
]


class BatchSaving(ApiModel):
    """How a batch saves: new pictures (beside the originals, into a folder by name beside each,
    or into a folder of their own), or in the originals' places, each original to quarantine."""

    how: Literal["new", "replace"] = "new"
    format: Format = "JPEG"
    quality: int | None = Field(default=None, ge=1, le=100)
    folder: str | None = None
    keep_camera: bool = True
    keep_colours: bool = True
    keep_location: bool = False


class PickIn(ApiModel):
    """Which pictures: ticked (`ids`), a folder (`folder`, `dir`), what a search found (`search`,
    with `q`), the favourites (with `q`, those a search found among them), or files and folders
    dropped, picked, pasted, or opened from File Explorer (`paths`)."""

    how: How
    ids: Annotated[list[int], Field(default_factory=list[int], max_length=batches.MOST)]
    paths: Annotated[list[str], Field(default_factory=list[str], max_length=batches.MOST)]
    folder: int | None = None
    dir: str = ""
    q: str = ""
    like: int | None = None  # a search: the pictures More like this found, most like it first


class BatchPicture(ApiModel):
    id: int | None  # in the library; None for one outside it
    path: str
    name: str
    size: int  # bytes
    width: int
    height: int
    version: str
    raw: bool = False  # a camera RAW: its batch saves new pictures, as Mado can't write RAW


class BatchLeftOut(ApiModel):
    name: str
    why: str
    waiting: bool = False  # a camera RAW, left out only till Mado's RAW reader has read it


class Picked(ApiModel):
    pictures: list[BatchPicture]
    bytes: int
    source: str  # where they're from: "Holiday"
    shared: str | None  # the folder they share
    words: str  # "ticked in Holiday", "found by “beach”", "dropped from Desktop"
    left_out: list[BatchLeftOut]


class Words(ApiModel):
    """A step, or a batch's save, as the steps and a recipe's line say it."""

    kind: str  # "size", "look", "save"; a step a later Mado makes says its own
    title: str  # "Make it for a screen"
    detail: str  # "TV 8K, 7680 × 4320, cropped around the subject; the right model for each…"
    chip: str  # "TV 8K"
    amount: str | None  # a look's strength, "60"


class TakesIn(ApiModel):
    pictures: Annotated[list[BatchPicture], Field(min_length=1, max_length=batches.MOST)]
    steps: list[Step]
    saving: BatchSaving
    shared: str | None = None
    sample: str | None = None  # See it first's three, to reckon by


class Takes(ApiModel):
    words: list[Words]  # the steps, then the save
    seconds: float
    bytes: int
    free: int | None  # bytes free where most are saved
    drive: str | None  # "D:"
    fits: bool
    measured: bool  # timed on this PC, not a guess
    reckoned: bool  # by See it first
    place: Literal["card", "processor"]
    needs: list[Need]
    example: str  # "Name (TV 8K).jpg"
    into: str  # "Holiday › Edited", "beside the originals"
    made_for: str | None
    look: str | None


class SamplesIn(ApiModel):
    pictures: Annotated[list[BatchPicture], Field(min_length=1, max_length=batches.MOST)]
    steps: list[Step]
    saving: BatchSaving
    round: int = Field(default=0, ge=0)


class SampleOut(ApiModel):
    index: int  # its place in the batch
    name: str
    picture: int | None
    state: Literal["waiting", "making", "done", "failed"]
    progress: float
    seconds: float | None
    bytes: int
    made_bytes: int | None
    width: int | None
    height: int | None
    problem: str | None


class SamplesOut(ApiModel):
    id: str
    round: int
    samples: list[SampleOut]
    seconds: float | None  # all of them, once made


class BatchIn(ApiModel):
    name: str | None = Field(default=None, max_length=80)  # None: its recipe's, or its source
    source: str = Field(max_length=200)
    shared: str | None = None
    pictures: Annotated[list[BatchPicture], Field(min_length=1, max_length=batches.MOST)]
    steps: list[Step]
    saving: BatchSaving
    starts: Starts = "now"
    recipe: int | None = None
    sample: str | None = None  # See it first's three, kept rather than made again


class BatchOut(ApiModel):
    id: int
    name: str
    source: str
    shared: str | None
    recipe: int | None
    watch: str | None  # the watch folder that made it
    starts: Starts
    added_at: str
    started_at: str | None
    finished_at: str | None
    total: int  # its pictures, but those cancelled
    done: int
    failed: int
    waiting: int
    cancelled: int
    progress: float  # with the picture being made's share
    seconds_left: float | None
    seen_first: bool
    how: Literal["new", "replace"]
    into: str  # where its pictures go: "Holiday › Edited"
    folder: str | None  # the folder to open, when they share one
    made_for: str | None
    look: str | None
    purpose: str | None
    words: list[Words]  # its steps, then its save
    before: int  # bytes of its pictures made, as they were
    after: int  # and as made


@router.post("/batches/pictures")
def pictures(body: PickIn, conn: Database, copies: Copies, finding: Searching) -> Picked:
    """The pictures a batch would be made of: those ticked, a folder's, what a search found, or
    the pictures in files and folders dropped or picked, with those left out and why."""
    match body.how:
        case "ticked":
            found = batches.from_ids(conn, body.ids)
        case "folder":
            if body.folder is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick a folder.")
            found = batches.from_folder(conn, body.folder, body.dir)
        case "search":
            shown = Shown(body.folder, body.dir.strip("/"), body.q, "newest", like=body.like)
            ids = found_ids(conn, finding, shown)
            found = batches.from_search(conn, body.folder, body.dir, body.q, ids)
        case "favourites":
            searched = Shown(None, "", body.q, "newest", favourites=True)
            ids = found_ids(conn, finding, searched) if body.q.strip() else None
            found = batches.from_favourites(conn, body.q, ids)
        case "dropped" | "picked" | "pasted" | "opened":
            found = batches.from_paths(conn, body.paths, body.how, copies.reader)
    return picked_out(found, reader_here=copies.reader is not None and copies.reader.ready())


def picked_out(found: batches.Picked, *, reader_here: bool = False) -> Picked:
    """The pictures a batch would be made of, as the API says them. A camera RAW left out for
    its reader, once that's here, is left out only till the scan has read it."""

    def left(name: str, why: str) -> BatchLeftOut:
        if why == batches.WAITS_FOR_READER and reader_here:
            why = batches.BEING_READ
        waiting = why in (batches.WAITS_FOR_READER, batches.BEING_READ)
        return BatchLeftOut(name=name, why=why, waiting=waiting)

    return Picked(
        pictures=[_out(each) for each in found.pictures],
        bytes=sum(each.size for each in found.pictures),
        source=found.source,
        shared=found.shared,
        words=found.words,
        left_out=[left(name, why) for name, why in found.left_out],
    )


@router.post("/batches/takes")
def takes(body: TakesIn, conn: Database, ai: Models, samples: FirstLook, toolbox: Toolbox) -> Takes:
    """What a batch would take: about how long, how much space, and what's free there, by this
    PC's speeds and what See it first found; its steps in words, and where its pictures go."""
    steps = steps_of(body.steps)
    saving = body.saving.model_dump(by_alias=True)
    try:
        recipe = batches.recipe_from_steps(conn, steps)
        found = batches.takes(
            conn,
            [_picture(each) for each in body.pictures],
            recipe,
            saving,
            ai,
            samples.found(body.sample, _key(steps, saving)),
        )
    except BatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    names = {item.id: item for item, _ in toolbox.status()}
    plan = found.plan
    extension = {"JPEG": ".jpg", "PNG": ".png", "WebP": ".webp", "AVIF": ".avif"}[
        body.saving.format
    ]
    return Takes(
        words=words_of(conn, steps, saving),
        seconds=found.seconds,
        bytes=found.bytes,
        free=found.free,
        drive=found.drive,
        fits=found.fits,
        measured=found.measured,
        reckoned=found.reckoned,
        place=ai.where().place,
        needs=[
            Need(id=each, name=names[each].name, size=names[each].size or 0)
            for each in found.needs
            if each in names
        ],
        example=f"Name ({plan.named}){extension}"
        if body.saving.how == "new"
        else f"Name{extension}",
        into=batches.into_words(saving, body.shared),
        made_for=plan.made_for,
        look=plan.look,
    )


@router.post("/batches/samples", status_code=status.HTTP_202_ACCEPTED)
def see_first(body: SamplesIn, conn: Database, samples: FirstLook) -> SamplesOut:
    """Makes three of a batch's pictures in full, but doesn't save them: timed and sized, to see
    first. `round` asks for three others."""
    steps = steps_of(body.steps)
    saving = body.saving.model_dump(by_alias=True)
    saves_see_through(steps, saving)
    try:
        recipe = batches.recipe_from_steps(conn, steps)
    except BatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    places = sampled(len(body.pictures), body.round)
    shown = samples.ask(
        [(at, _picture(body.pictures[at])) for at in places],
        recipe,
        saving_from(saving),
        _key(steps, saving),
        body.round,
    )
    return _samples(shown)


@router.get("/batches/samples/{set_id}")
def seen_first(set_id: str, samples: FirstLook) -> SamplesOut:
    """How See it first's three are coming on."""
    shown = samples.get(set_id)
    if shown is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Those were let go: ask for three again.")
    return _samples(shown)


@router.delete("/batches/samples/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def let_go(set_id: str, samples: FirstLook) -> Response:
    """Lets See it first's three go: the one being made stops."""
    samples.drop(set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_PICTURES: dict[int | str, dict[str, object]] = {
    200: {"content": {"image/webp": {}, "image/jpeg": {}, "image/png": {}, "image/avif": {}}}
}


@router.get(
    "/batches/samples/{set_id}/{index}/{side}",
    response_class=FileResponse,
    responses=_PICTURES,
)
def sample_picture(
    set_id: str, index: int, side: Literal["before", "after", "full"], samples: FirstLook
) -> FileResponse:
    """One of See it first's pictures: a copy of it before and after (WebP), or as it was made,
    in full, to look at closely."""
    found = samples.file(set_id, index, side)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That one isn't made yet.")
    media = {
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".avif": "image/avif",
    }.get(found.suffix.lower(), "application/octet-stream")
    return FileResponse(found, media_type=media)


@router.post("/batches", status_code=status.HTTP_201_CREATED)
def put_in(
    body: BatchIn, conn: Database, ai: Models, jobs: Working, samples: FirstLook
) -> BatchOut:
    """Puts a batch in the queue: now, after what's in it, or tonight from 23:00. See it first's
    pictures made to the same steps are kept rather than made again."""
    steps = steps_of(body.steps)
    saving = body.saving.model_dump(by_alias=True)
    saves_see_through(steps, saving)
    if body.saving.how == "replace" and any(kind_of(each.name) == "raw" for each in body.pictures):
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RAW_REPLACE)
    folder = Path(body.saving.folder) if body.saving.folder else None
    if body.saving.how == "new" and folder and folder.is_absolute() and not folder.is_dir():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{body.saving.folder} isn't there: its drive may be unplugged. Choose another.",
        )
    recipe_name: str | None = None
    if body.recipe is not None:
        row = conn.execute("SELECT name FROM recipes WHERE id = ?", (body.recipe,)).fetchone()
        recipe_name = row["name"] if row else None
    key = _key(steps, saving)
    pictures_ = [_checked(conn, each) for each in body.pictures]
    try:
        batch_id = batches.put_in(
            conn,
            jobs,
            ai,
            name=(body.name or recipe_name or body.source).strip() or body.source,
            source=body.source,
            shared=body.shared,
            pictures=pictures_,
            steps=steps,
            saving=saving,
            starts=body.starts,
            now=_now(),
            recipe_id=body.recipe if recipe_name else None,
            found=samples.found(body.sample, key),
            made=samples.keep(body.sample, key),
            seen_first=body.sample is not None,
        )
    except BatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if body.sample:
        samples.drop(body.sample)
    return batch_of(conn, jobs, batch_id)


@router.get("/batches/done")
def done(conn: Database, jobs: Working) -> list[BatchOut]:
    """Batches done that Home tells of: made in the last week, not cancelled, not yet seen. A
    watch folder's aren't: they come as pictures arrive, and History and Made today have them."""
    since = (_now() - timedelta(days=_DONE_DAYS)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT b.id FROM batches AS b
           WHERE b.finished_at IS NOT NULL AND b.finished_at >= ? AND b.seen_at IS NULL
             AND b.watch_id IS NULL
             AND EXISTS (SELECT 1 FROM jobs WHERE batch_id = b.id AND state = 'done')
           ORDER BY b.finished_at DESC LIMIT 5""",
        (since,),
    ).fetchall()
    return [batch_of(conn, jobs, row["id"]) for row in rows]


@router.post("/batches/{batch_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
def seen(batch_id: int, conn: Database) -> Response:
    """Home's card for a batch done was seen: it goes."""
    with conn:
        conn.execute(
            "UPDATE batches SET seen_at = COALESCE(seen_at, ?) WHERE id = ?",
            (_now().isoformat(timespec="seconds"), batch_id),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def batch_of(conn: sqlite3.Connection, jobs: Working, batch_id: int) -> BatchOut:
    """A batch as the window shows it."""
    row = conn.execute(
        """SELECT b.*, w.path AS watch_path FROM batches AS b
           LEFT JOIN watch_folders AS w ON w.id = b.watch_id WHERE b.id = ?""",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mado has no such batch.")
    counts = conn.execute(
        """SELECT COUNT(*) FILTER (WHERE state = 'done') AS done,
                  COUNT(*) FILTER (WHERE state = 'failed') AS failed,
                  COUNT(*) FILTER (WHERE state IN ('queued', 'running')) AS waiting,
                  COUNT(*) FILTER (WHERE state = 'cancelled') AS cancelled,
                  COALESCE(SUM(bytes) FILTER (WHERE state = 'done'), 0) AS before,
                  COALESCE(SUM(made_bytes) FILTER (WHERE state = 'done'), 0) AS after
           FROM jobs WHERE batch_id = ?""",
        (batch_id,),
    ).fetchone()
    steps, saving = batches.kept_steps(row["steps"])
    total = counts["done"] + counts["failed"] + counts["waiting"]
    running = conn.execute(
        "SELECT id, recipe FROM jobs WHERE batch_id = ? AND state = 'running'", (batch_id,)
    ).fetchone()
    share = 0.0
    left: float | None = 0.0
    if running is not None:
        live = jobs.live(running["id"])
        share = live.progress if live else 0.0
        left = live.seconds_left if live and live.seconds_left is not None else None
    waiting: float = conn.execute(
        """SELECT COALESCE(SUM(json_extract(recipe, '$.seconds')), 0.0) FROM jobs
           WHERE batch_id = ? AND state = 'queued' AND json_valid(recipe)""",
        (batch_id,),
    ).fetchone()[0]
    if left is not None:
        left += float(waiting)
    order = batches.first_order(conn, batch_id)
    made_for, look = order.get("label"), order.get("look")
    return BatchOut(
        id=row["id"],
        name=row["name"],
        source=row["source"],
        shared=row["shared"],
        recipe=row["recipe_id"],
        watch=row["watch_path"],
        starts=row["starts"],
        added_at=row["added_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        total=total,
        done=counts["done"],
        failed=counts["failed"],
        waiting=counts["waiting"],
        cancelled=counts["cancelled"],
        progress=(counts["done"] + counts["failed"] + share) / total if total else 1.0,
        seconds_left=left if counts["waiting"] else None,
        seen_first=bool(row["seen_first"]),
        how="replace" if saving.get("how") == "replace" else "new",
        into=batches.into_words(saving, row["shared"]),
        folder=batches.folder_of(saving, row["shared"]),
        made_for=made_for if isinstance(made_for, str) else None,
        look=look if isinstance(look, str) else None,
        purpose=batches.purpose_of(conn, steps),
        words=words_of(conn, steps, saving),
        before=counts["before"],
        after=counts["after"],
    )


def words_of(
    conn: sqlite3.Connection, steps: list[dict[str, object]], saving: dict[str, object]
) -> list[Words]:
    """Steps, then their save, as the steps and a recipe's line say them."""
    return [
        Words(kind=kind, title=title, detail=detail, chip=chip, amount=amount)
        for kind, title, detail, chip, amount in batches.words_for(conn, steps, saving)
    ]


def steps_of(body: list[Step]) -> list[dict[str, object]]:
    """Steps as the engine keeps them, in the order Mado makes them; a size step's own point to
    crop around goes, as each picture has its own subject."""
    found: list[dict[str, object]] = []
    for step in body:
        kept = step.model_dump(by_alias=True)
        if kept.get("step") == "size":
            kept.pop("focus", None)
        found.append(kept)
    return steps_in_order(found)


def saves_see_through(steps: list[dict[str, object]], saving: dict[str, object]) -> None:
    """Refuses a save that would lose a cut-out's see-through parts: only PNG and WebP keep
    them."""
    nothing = any(
        each.get("step") == "cutout" and each.get("behind", "nothing") == "nothing"
        for each in steps
    )
    if nothing and saving.get("format") not in ("PNG", "WebP"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A cut-out with nothing behind it keeps its see-through parts only as PNG or WebP: "
            "pick one of those.",
        )


_MAKES = ("format", "quality", "keepCamera", "keepColours", "keepLocation")


def _key(steps: list[dict[str, object]], saving: dict[str, object]) -> str:
    """What See it first's pictures were made to, so a batch knows they're its own: its steps
    and what of its saving changes the picture written (not where it goes, nor whether it
    replaces)."""
    written = {name: saving.get(name) for name in _MAKES}
    return json.dumps({"steps": steps, "saving": written}, sort_keys=True)


def _samples(shown: SampleSet) -> SamplesOut:
    return SamplesOut(
        id=shown.id,
        round=shown.round,
        samples=[
            SampleOut(
                index=each.index,
                name=each.picture.name,
                picture=each.picture.id,
                state=each.state,
                progress=each.progress,
                seconds=each.seconds,
                bytes=each.picture.size,
                made_bytes=each.made_bytes,
                width=each.width,
                height=each.height,
                problem=each.problem,
            )
            for each in shown.samples
        ],
        seconds=shown.seconds,
    )


def _out(picture: Picture) -> BatchPicture:
    return BatchPicture(
        id=picture.id,
        path=str(picture.path),
        name=picture.name,
        size=picture.size,
        width=picture.width,
        height=picture.height,
        version=picture.version,
        raw=kind_of(picture.name) == "raw",
    )


def _picture(each: BatchPicture) -> Picture:
    return Picture(
        each.id, Path(each.path), each.name, each.size, each.width, each.height, each.version
    )


def _checked(conn: sqlite3.Connection, each: BatchPicture) -> Picture:
    """A batch's picture as it is now: one in the library as the library knows it."""
    if each.id is not None:
        row = conn.execute(
            """SELECT id, path, name, size, width, height, modified FROM pictures
               WHERE id = ? AND gone_at IS NULL AND read_at IS NOT NULL AND problem IS NULL""",
            (each.id,),
        ).fetchone()
        if row is None or not row["width"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{each.name} isn't in your library any more: pick the pictures again.",
            )
        return Picture(
            row["id"],
            Path(row["path"]),
            row["name"],
            row["size"],
            row["width"],
            row["height"],
            version(row["modified"], row["size"]),
        )
    path = Path(each.path)
    if not path.is_file():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{each.name} isn't there any more: pick the pictures again.",
        )
    return _picture(each)


def _now() -> datetime:
    return datetime.now().astimezone()
