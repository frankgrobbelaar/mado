"""Duplicates and bursts: which of the library's pictures are one picture saved more than once,
or shots of one moment, and which of each group to keep. Pure: the pictures come in as what
Mado knows of them (mado/duplicates.py looks).

- Exact copies have the same bytes (the same digest).
- A picture saved again (another size, quality or format) has a fingerprint within NEAR bits,
  the same shape within SHAPE, and a finer fingerprint within FINE bits: a crop of two per cent
  or more shifts the finer one well past it (docs/stack/duplicates.md has the measurements).
- A burst is the same camera in the same folder, each shot within BURST_GAP of the one before,
  the same size, and fingerprints within the looser BURST bits. Only neighbours in time are
  compared.
- Never grouped: pictures the owner said aren't the same, and two of one family (an original and
  what Mado made from it, or two Mado made from one original). Groups are joined pair by pair,
  the most alike first, and a join that would put two such pictures in one group is left out.
- Which to keep: a burst's sharpest shot, each shot with its copies counted as one (a sharpened
  export never outranks its own original), and that shot's best copy; a duplicate's most pixels,
  then the larger file of its format, then a name that isn't a copy's ("(2)", "Copy", "- Copy"),
  then the older file. Each group says which of these decided.
"""

import itertools
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from typing import Literal

import numpy as np

from mado.core.likeness import apart, fine_apart, near_pairs

type Kind = Literal["duplicates", "burst"]
type Reason = Literal["sharpest", "pixels", "larger", "name", "older"]  # what decided the keep

NEAR = 6  # fingerprint bits apart a picture saved again can be (measured: 4 at most)
FINE = 10  # finer fingerprint bits apart it can be, of 256 (measured: 6; a 2% crop 14 or more)
SHAPE = 0.01  # how far two shapes (width over height) can differ and be the same picture's
BURST = 12  # fingerprint bits apart two shots of a burst can be (measured: 12 at a 2% shift)
BURST_GAP = timedelta(seconds=2)  # each shot of a burst taken within this of the one before


@dataclass(frozen=True)
class Known:
    """A picture as finding duplicates sees it."""

    id: int
    name: str  # its file's name
    folder: str  # the folder it's in, as a path
    width: int
    height: int
    size: int  # bytes
    format: str | None
    modified: int  # its file's time, nanoseconds since 1970
    taken: datetime | None  # by the camera's clock; None when only the file's time says
    camera: str | None
    hash: int | None  # its fingerprint (mado/core/likeness.py)
    fine: bytes | None  # its finer fingerprint
    digest: str | None  # its bytes', when another file shares its size
    sharpness: float | None = None
    family: int | None = None  # an original and the pictures Mado made from it share one
    path: str = ""  # where it is

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class Group:
    kind: Kind
    members: tuple[int, ...]  # in the order they're shown: a burst's in time, else biggest first
    keep: int  # the one Mado suggests keeping
    exact: bool  # every one the same bytes
    reason: Reason = "older"  # what decided which to keep


@dataclass(frozen=True)
class _Join:
    rank: tuple[int, int]  # the most alike first: exact copies, then saved again, then bursts
    first: int  # places in the list of pictures
    second: int
    burst: bool
    exact: bool


def groups(pictures: Sequence[Known], *, not_same: Collection[tuple[int, int]] = ()) -> list[Group]:
    """The groups among `pictures`, each of two or more. `not_same` holds pairs of ids (the
    smaller first) the owner said aren't the same."""
    joins = sorted(
        [*_exact(pictures), *_saved_again(pictures), *_bursts(pictures)],
        key=lambda join: join.rank,
    )
    owner = {(min(a, b), max(a, b)) for a, b in not_same}
    sets = _Sets(pictures, owner)
    for join in joins:
        sets.join(join)
    found: list[Group] = []
    for places, burst, exact in sets.groups():
        members = [pictures[at] for at in places]
        kind: Kind = "burst" if burst else "duplicates"
        units = _units(places, joins, pictures) if burst else None
        keep, reason = _suggested(members, kind, units)
        shown = tuple(each.id for each in _shown(members, kind))
        found.append(Group(kind, shown, keep.id, exact, reason))
    found.sort(key=lambda group: min(group.members))
    return found


def _units(
    places: Sequence[int], joins: Sequence[_Join], pictures: Sequence[Known]
) -> list[list[Known]]:
    """A burst's shots, each with the copies saved of it (its exact and saved-again joins), as
    one unit apiece: a copy's sharpness is the shot's, never a rival to it."""
    inside = set(places)
    parent = {at: at for at in places}

    def root(at: int) -> int:
        while parent[at] != at:
            parent[at] = parent[parent[at]]
            at = parent[at]
        return at

    for join in joins:
        if not join.burst and join.first in inside and join.second in inside:
            parent[root(join.second)] = root(join.first)
    units: dict[int, list[Known]] = {}
    for at in places:
        units.setdefault(root(at), []).append(pictures[at])
    return list(units.values())


def suggested(
    members: Sequence[Known], kind: Kind, units: Sequence[Sequence[Known]] | None = None
) -> Known:
    """Which of a group to keep: a burst's sharpest shot (`units`: each shot with its copies;
    alone, each picture its own), that shot's best copy; else the most pixels, then the larger
    file of its format, then a name that isn't a copy's, then the older file."""
    return _suggested(members, kind, units)[0]


def _suggested(
    members: Sequence[Known], kind: Kind, units: Sequence[Sequence[Known]] | None
) -> tuple[Known, Reason]:
    if not members:
        raise ValueError("A group has pictures.")
    if kind != "burst":
        return _best_copy(members)
    shots = [_best_copy(unit)[0] for unit in (units or [[each] for each in members]) if unit]
    sharpest = max((each.sharpness or 0.0) for each in shots)
    sharp = [each for each in shots if (each.sharpness or 0.0) >= sharpest]
    keep, reason = _best_copy(sharp)
    return keep, "sharpest" if len(sharp) < len(shots) else reason


def _best_copy(members: Sequence[Known]) -> tuple[Known, Reason]:
    """The best of copies of one picture, and what decided it."""
    most = max(each.pixels for each in members)
    biggest = [each for each in members if each.pixels == most]
    if len(biggest) == 1:
        return biggest[0], "pixels"
    largest: dict[str, int] = {}
    for each in biggest:
        key = (each.format or "").casefold()
        largest[key] = max(largest.get(key, 0), each.size)
    kept = [each for each in biggest if each.size == largest[(each.format or "").casefold()]]
    if len(kept) == 1:
        return kept[0], "larger"
    plain = [each for each in kept if not is_copy_name(each.name)]
    if len(plain) == 1:
        return plain[0], "name"
    return min(plain or kept, key=lambda each: (each.modified, each.id)), "older"


def _shown(members: Sequence[Known], kind: Kind) -> list[Known]:
    """A group's pictures in the order they're shown: a burst's in time, else biggest first."""
    if kind == "burst":
        return sorted(members, key=lambda each: (each.taken or datetime.min, each.name, each.id))
    return sorted(members, key=lambda each: (-each.pixels, -each.size, each.name, each.id))


_COPY_MARK = re.compile(
    r"(?:\s*\(\d{1,3}\)|\s*-?\s*copy(?:\s*\(\d{1,3}\)|\s+\d{1,3})?|[_-]copy\d{0,3})$",
    re.IGNORECASE,
)
_COPY_OF = re.compile(r"^copy of\s+", re.IGNORECASE)


def copy_base(name: str) -> str:
    """A file's name without what a copy adds to it ("(2)", "Copy", "- Copy", "Copy of"), in
    one case: "IMG_2041 (2).jpg" and "IMG_2041 - Copy.jpg" are both "img_2041"."""
    stem = PureWindowsPath(name).stem.strip()
    text = _COPY_OF.sub("", stem)
    while True:
        shorter = _COPY_MARK.sub("", text).strip()
        if shorter == text:
            break
        text = shorter
    return (text or stem).casefold()


def is_copy_name(name: str) -> bool:
    """Whether a file's name is a copy's: "IMG_2041 (2).jpg", "Beach - Copy.png"."""
    return copy_base(name) != PureWindowsPath(name).stem.strip().casefold()


def _exact(pictures: Sequence[Known]) -> Iterable[_Join]:
    by_digest: dict[str, list[int]] = {}
    for at, each in enumerate(pictures):
        if each.digest:
            by_digest.setdefault(each.digest, []).append(at)
    for places in by_digest.values():
        for first, second in itertools.pairwise(places):
            yield _Join((0, 0), first, second, burst=False, exact=True)


def _saved_again(pictures: Sequence[Known]) -> Iterable[_Join]:
    places = [at for at, each in enumerate(pictures) if each.hash is not None and each.fine]
    if len(places) < 2:
        return
    hashes = np.array([pictures[at].hash for at in places], dtype=np.int64)
    for i, j, distance in near_pairs(hashes, NEAR):
        a, b = pictures[places[i]], pictures[places[j]]
        if not _same_shape(a, b) or a.fine is None or b.fine is None:
            continue
        if fine_apart(a.fine, b.fine) > FINE:
            continue
        burst = _burst_like(a, b)
        yield _Join((1, distance), places[i], places[j], burst=burst, exact=False)


def _bursts(pictures: Sequence[Known]) -> Iterable[_Join]:
    """Shots of one moment: the same camera in the same folder, taken within BURST_GAP of each
    other, compared with their neighbours in time only."""
    runs: dict[tuple[str, str], list[int]] = {}
    for at, each in enumerate(pictures):
        if each.camera and each.taken is not None and each.hash is not None:
            runs.setdefault((each.folder.casefold(), each.camera), []).append(at)
    for places in runs.values():
        places.sort(key=lambda at: (pictures[at].taken or datetime.min, pictures[at].name))
        for index, at in enumerate(places):
            this = pictures[at]
            for back in range(index - 1, -1, -1):  # its neighbours in time, the nearest first
                before = places[back]
                earlier = pictures[before]
                if this.taken is None or earlier.taken is None:
                    break
                if this.taken - earlier.taken > BURST_GAP:
                    break
                if earlier.hash is None or this.hash is None or not _burst_like(earlier, this):
                    continue
                distance = apart(earlier.hash, this.hash)
                if distance <= BURST:
                    yield _Join((2, distance), before, at, burst=True, exact=False)


def _burst_like(a: Known, b: Known) -> bool:
    """Whether two pictures could be shots of one burst: the same camera, folder and size, taken
    within BURST_GAP, under names that aren't one's copy of the other."""
    return (
        a.camera is not None
        and a.camera == b.camera
        and a.folder.casefold() == b.folder.casefold()
        and a.taken is not None
        and b.taken is not None
        and abs(a.taken - b.taken) <= BURST_GAP
        and (a.width, a.height) == (b.width, b.height)
        and copy_base(a.name) != copy_base(b.name)
    )


def _same_shape(a: Known, b: Known) -> bool:
    if min(a.width, a.height, b.width, b.height) <= 0:
        return False
    return abs((a.width / a.height) / (b.width / b.height) - 1) <= SHAPE


class _Sets:
    """Pictures joined into groups, refusing a join that would put two pictures the owner said
    aren't the same, or two of one family, in one group."""

    def __init__(self, pictures: Sequence[Known], not_same: set[tuple[int, int]]) -> None:
        self._pictures = pictures
        self._not_same = not_same
        self._parent = list(range(len(pictures)))
        self._members: dict[int, list[int]] = {}
        self._families: dict[int, set[int]] = {}
        self._burst: dict[int, bool] = {}
        self._exact: dict[int, bool] = {}

    def _root(self, at: int) -> int:
        while self._parent[at] != at:
            self._parent[at] = self._parent[self._parent[at]]
            at = self._parent[at]
        return at

    def _of(self, root: int) -> list[int]:
        return self._members.get(root, [root])

    def _families_of(self, root: int) -> set[int]:
        found = self._families.get(root)
        if found is not None:
            return found
        family = self._pictures[root].family
        return {family} if family is not None else set()

    def join(self, join: _Join) -> None:
        first, second = self._root(join.first), self._root(join.second)
        if first == second:
            return  # joined already, by a pair more alike
        if self._families_of(first) & self._families_of(second):
            return  # two of one family: what Mado made is never a duplicate of its original
        if self._said_apart(self._of(first), self._of(second)):
            return
        members = self._of(first) + self._of(second)
        families = self._families_of(first) | self._families_of(second)
        burst = self._burst.get(first, False) or self._burst.get(second, False) or join.burst
        exact = self._exact.get(first, True) and self._exact.get(second, True) and join.exact
        self._parent[second] = first
        self._members[first] = members
        self._families[first] = families
        self._burst[first] = burst
        self._exact[first] = exact
        for gone in (self._members, self._families, self._burst, self._exact):
            gone.pop(second, None)

    def _said_apart(self, these: list[int], those: list[int]) -> bool:
        if not self._not_same:
            return False
        for a in these:
            for b in those:
                one, other = self._pictures[a].id, self._pictures[b].id
                if (min(one, other), max(one, other)) in self._not_same:
                    return True
        return False

    def groups(self) -> list[tuple[list[int], bool, bool]]:
        return [
            (members, self._burst.get(root, False), self._exact.get(root, True))
            for root, members in self._members.items()
            if len(members) > 1
        ]
