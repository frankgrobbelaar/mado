"""Many at once, by its rules: when a batch may run (now, after what's in the queue, or tonight,
from 23:00 till 07:00), the pictures See it first makes, what the rest takes by what those found,
whether a drive has room, a batch's steps and the words for them. Pure.

A batch's steps are a list, each its kind of step and its choices (`{"step": "size", ...}`), so
later pieces add kinds of their own. They're made in Mado's order, the subject cut out, the
fixes, the size, the depth tools and then the look, whatever order they're listed in, and saved
as the batch says.
"""

from collections.abc import Sequence
from datetime import datetime, time, timedelta
from pathlib import PureWindowsPath
from typing import Literal

from mado.core.sizes import DPI, Purpose, Size

type Starts = Literal["now", "tonight", "after"]
type Step = dict[str, object]

NIGHT = (time(23, 0), time(7, 0))  # when a batch for tonight runs
MARGIN = 256 * 1024 * 1024  # bytes kept free on a drive, so Windows and other apps have room
ORDER = (
    "cutout",
    "fix",
    "size",
    "depth",
    "paint",
    "look",
)  # the kinds of step Mado makes, in order
_GOLDEN = 0.6180339887498949  # spreads See it first's pictures across a batch, round after round
_SAMPLES = 3
_HELD = (1 / 3, 3.0)  # how far See it first can move the rest's time
# How far it can move their space: bytes a pixel vary far more with what's in a picture than its
# time does, and the three are measured as Save writes them.
SPACE_HELD = (0.1, 3.0)
KEPT_SECONDS = 1.0  # what keeping a picture See it first made takes: copied, checked, put in place


class StepError(ValueError):
    """Steps Mado can't make, with a sentence saying why."""


def at_night(moment: datetime) -> bool:
    """Whether a batch for tonight may start a picture now: from 23:00 till 07:00."""
    start, end = NIGHT
    return moment.time() >= start or moment.time() < end


def morning(moment: datetime) -> datetime:
    """The 07:00 that ends the night a moment is in (by day, the coming night's)."""
    seven = moment.replace(hour=NIGHT[1].hour, minute=0, second=0, microsecond=0)
    return seven if moment.time() < NIGHT[1] else seven + timedelta(days=1)


def may_start(starts: Starts, moment: datetime) -> bool:
    """Whether a batch may start a picture now: one for tonight only at night."""
    return starts != "tonight" or at_night(moment)


def sampled(count: int, round_: int, take: int = _SAMPLES) -> list[int]:
    """The places in a batch of `count` of the pictures See it first makes: spread across it,
    the first from its start, and three others each time "Try three others" is asked (`round_`),
    coming round again once all have been seen."""
    if count <= take:
        return list(range(count))
    spread = list(dict.fromkeys(int((index * _GOLDEN) % 1 * count) for index in range(count * 4)))
    spread += [index for index in range(count) if index not in set(spread)]
    start = (round_ * take) % len(spread)
    return [spread[(start + offset) % len(spread)] for offset in range(take)]


def calibrated(
    guesses: Sequence[float],
    found: Sequence[tuple[float, float]],
    *,
    held: tuple[float, float] = _HELD,
) -> float:
    """The whole batch: each picture's guess, moved by how See it first's pictures went against
    theirs (`found`: each one's guess and what it took), held between `held`'s two (for time, a
    third to three times)."""
    guessed = sum(guess for guess, _took in found)
    ratio = sum(took for _guess, took in found) / guessed if guessed > 0 else 1.0
    return sum(guesses) * min(max(ratio, held[0]), held[1])


def fits(needed: int, free: int) -> bool:
    """Whether a drive with `free` bytes has room for `needed` more, a margin kept free."""
    return free - needed >= MARGIN


def fitting(needs: Sequence[int], free: int) -> int:
    """How many pictures, in turn, fit in `free` bytes: the first that doesn't waits, and so do
    those after it."""
    made = 0
    for need in needs:
        if not fits(need, free):
            break
        free -= need
        made += 1
    return made


def steps_in_order(steps: Sequence[Step]) -> list[Step]:
    """The steps in the order Mado makes them; a kind it doesn't know goes last."""
    rank = {kind: at for at, kind in enumerate(ORDER)}
    return sorted(steps, key=lambda step: rank.get(str(step.get("step")), len(ORDER)))


def recipe_of(steps: Sequence[Step]) -> dict[str, object]:
    """Steps as a job keeps its recipe: its edits (the subject cut out), its fixes, its size
    step, its depth step and its look step, any of them None. Raises StepError for none, two of a
    kind, or a kind this Mado doesn't know."""
    found: dict[str, dict[str, object]] = {}
    for step in steps:
        kind = str(step.get("step"))
        if kind not in ORDER:
            raise StepError(
                "This Mado doesn't know one of the steps, so it can't make them: update Mado, "
                "or take that step out."
            )
        if kind in found:
            raise StepError(f"A batch makes one {_SAID.get(kind, kind)} at a time: take one out.")
        found[kind] = {key: value for key, value in step.items() if key != "step"}
    if not found:
        raise StepError(
            "Pick what to do first: cut out the subject, fix them, make them for a screen, give "
            "them depth, paint them in a style, or give them a look."
        )
    fix = found.get("fix")
    if fix is not None and all(fix.get(kind) is None for kind in ("noise", "blur", "jpeg", "dark")):
        raise StepError("The Fix step has no fix turned on: turn one on, or take the step out.")
    depth = found.get("depth")
    if depth is not None and all(depth.get(kind) is None for kind in ("portrait", "fog", "tilt")):
        raise StepError("The Depth step has no tool turned on: turn one on, or take the step out.")
    cut = found.get("cutout")
    edit = (
        {
            "version": None,
            "edits": [
                {
                    "kind": "subject",
                    "quality": cut.get("quality"),
                    "behind": cut.get("behind", "nothing"),
                    "colour": cut.get("colour"),
                }
            ],
        }
        if cut is not None
        else None
    )
    return {
        "edit": edit,
        "fix": found.get("fix"),
        "size": found.get("size"),
        "depth": found.get("depth"),
        "paint": found.get("paint"),
        "look": found.get("look"),
    }


_SAID = {
    "cutout": "cut-out",
    "fix": "set of fixes",
    "size": "size",
    "depth": "set of depth tools",
    "paint": "painting style",
    "look": "look",
}


def paint_detail(name: str, strength: float, colours: bool, setting: tuple[str, int] | None) -> str:
    """A painting style as a batch's steps say it: "After Hokusai at 80%, in each picture's own
    colours", "Oil paint, brush 70"."""
    percent = round(strength * 100)
    said = name if percent >= 100 else f"{name} at {percent}%"
    if setting is not None:
        said = f"{said}, {setting[0].lower()} {setting[1]}"
    return f"{said}, in each picture's own colours" if colours else said


def cutout_detail(quality: str | None, behind: str) -> str:
    """Cutting out the subject as a batch's steps say it: "Fast, with nothing behind it"."""
    model = {"fast": "Fast", "best": "Best"}.get(quality or "", "As this PC suits")
    on = {
        "colour": "on a colour",
        "blurred": "on the rest of the picture blurred",
    }.get(behind, "with nothing behind it")
    return f"{model}, {on}"


def size_chip(size: Size) -> str:
    """A size as a recipe's line says it: "TV 8K", "Phone 1290 × 2796", "A3 at 300 dpi"."""
    if size.purpose == "print":
        return f"{size.name} at {DPI} dpi"
    if size.group == "other" or size.purpose in ("tv", "monitor"):
        return size.name  # its name says its size: "TV 8K", "5000 × 3000"
    return f"{size.name} {size.width} × {size.height}"


def size_detail(size: Size, shape: str, quality: str | None) -> str:
    """The size step as a batch's steps say it: "TV 8K, 7680 × 4320, cropped around the
    subject; the right model for each picture"."""
    if size.purpose == "print":
        named = f"{size.name} at {DPI} dpi, turned to each picture"
    elif size.group == "other":
        named = size.name
    else:
        named = f"{size.name}, {size.width} × {size.height}"
    shaped = "its edges extended" if shape == "extend" else "cropped around the subject"
    model = {"fast": "Fast", "best": "Best"}.get(quality or "", "the right model")
    return f"{named}, {shaped}; {model} for each picture"


def look_chip(name: str, strength: float) -> tuple[str, str | None]:
    """A look as a recipe's line says it: its name, and its strength when it isn't all of it
    ("Warm film", "60")."""
    percent = round(strength * 100)
    return name, None if percent >= 100 else str(percent)


def saving_chip(how: str, format_: str, quality: int | None, folder: str | None) -> str:
    """How a batch saves, as a recipe's line says it: "JPEG 95 into Edited"."""
    kind = f"{format_} {quality}" if quality else format_
    if how == "replace":
        return f"{kind} in place of the originals"
    if not folder:
        return f"{kind} beside the originals"
    return f"{kind} into {_last(folder)}"


def folder_words(folder: str | None, shared: str | None) -> str:
    """Where new pictures go, as Saving says it: beside the originals, a folder by name beside
    them ("Holiday › Edited", from the folder they share), or a folder of its own."""
    if not folder:
        return "beside the originals"
    if _absolute(folder):
        inside = _inside(folder, shared) if shared else None
        return " › ".join([_last(shared or folder), *inside]) if inside else folder
    if shared:
        return f"{_last(shared)} › {folder}"
    return f"a folder called {folder} beside each"


def ready_words(source: str, purpose: Purpose | None, look: str | None) -> str:
    """What Home says of a batch done: "Holiday is ready for the TV", "Holiday has Warm film"."""
    if purpose is None:
        return f"{source} has {look}" if look else f"{source} is ready"
    if purpose == "print":
        return f"{source} is ready to print"
    return f"{source} is ready for {_FOR[purpose]}"


def told(
    name: str,
    *,
    made: int,
    failed: int,
    made_for: str | None,
    look: str | None,
    edit: str | None = None,
    fix: str | None = None,
    depth: str | None = None,
) -> tuple[str, str]:
    """A batch done, as its notification says it: "Holiday prints is done", "48 pictures made
    for TV 8K · 1 didn't work", "12 pictures made: cut out the subject"."""
    edit = ", ".join(each for each in (edit, fix) if each) or None
    look = " and ".join(each for each in (depth, look) if each) or None
    if made == 0:
        whole = failed
        return (
            f"{name} didn't work",
            f"None of its {whole} {'picture' if whole == 1 else 'pictures'} could be made. "
            "The queue says why.",
        )
    what = [f"for {made_for}"] if made_for else []
    if look:
        what.append(f"with {look}")
    body = f"{made} {'picture' if made == 1 else 'pictures'} made"
    if edit:
        body += f": {', '.join([edit, *what])}"
    elif what:
        body += f" {', '.join(what)}"
    if failed:
        body += f" · {failed} didn't work"
    return f"{name} is done", body


_FOR: dict[Purpose, str] = {
    "phone": "the phone",
    "tablet": "the tablet",
    "laptop": "the laptop",
    "monitor": "the monitor",
    "ultrawide": "the ultrawide",
    "tv": "the TV",
    "print": "printing",
    "screen": "your screen",
}


def _absolute(folder: str) -> bool:
    return (len(folder) > 2 and folder[1] == ":") or folder.startswith(("\\\\", "/"))


def _inside(folder: str, shared: str) -> list[str] | None:
    """The folders a folder is inside `shared` by ("Done" of "D:\\To TV\\Done" in "D:\\To
    TV"); None when it isn't inside it."""
    within = PureWindowsPath(shared)
    found = PureWindowsPath(folder)
    if found.drive.casefold() != within.drive.casefold():
        return None
    outer = [part.casefold() for part in within.parts]
    if len(found.parts) <= len(outer) or [p.casefold() for p in found.parts[: len(outer)]] != outer:
        return None
    return list(found.parts[len(outer) :])


def _last(folder: str) -> str:
    """A folder's own name: "Prints" of "D:\\Prints"."""
    parts = [part for part in folder.replace("/", "\\").split("\\") if part]
    return parts[-1] if parts else folder


def starts_of(value: object) -> Starts:
    """A batch's When as it's kept, "now" for anything else."""
    match value:
        case "tonight":
            return "tonight"
        case "after":
            return "after"
        case _:
            return "now"
