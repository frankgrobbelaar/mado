"""Search: what the Library's search box finds by a picture's name, by what it shows and by the
words in it, all from the same words; More like this, from a picture's page; and how far reading
the library for search has got, which can be paused (docs/stack/search.md)."""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from mado import favourites
from mado.api.common import ApiModel, Database, Finding, Searching, Toolbox
from mado.api.pictures import (
    PictureItem,
    Showing,
    Shown,
    group_tags,
    item_of,
    shown_where,
)
from mado.api.tools import Tool, tool_of
from mado.core.search import (
    Choice,
    Reader,
    first_seen,
    in_english,
    marked,
    match_query,
    reads,
    unreadable,
)
from mado.directml import ModelError
from mado.duplicates import choices
from mado.ocr import PPOCR
from mado.search import LISTED, Search, away_folders, chosen
from mado.siglip import SIGLIP
from mado.tools import Tools

router = APIRouter()

MOST = 500  # pictures a group shows at most
type Kind = Literal["words", "described", "name", "like"]


class WordsPiece(ApiModel):
    """A stretch of a picture's words, marked when it's a word the search matched."""

    text: str
    marked: bool


class SearchHit(PictureItem):
    """A picture a search found."""

    score: float | None = None  # SigLIP's score for it (described), or how alike it is (like)
    words: list[WordsPiece] | None = None  # its words, those the search matched marked (words)
    away: bool = False  # its drive isn't connected: found by what Mado read of it before


class SearchGroup(ApiModel):
    kind: Kind  # how its pictures were found
    pictures: list[SearchHit]  # best first; a picture found two ways is in the first group only
    total: int  # all it found, of which it shows MOST at most


class WordsReader(ApiModel):
    """The reader of the words in pictures: the owner's choice, the one in use, its model (Best)
    or Windows' languages (Fast), and where Best reads."""

    chosen: Choice
    reader: Reader
    model: Tool | None  # PP-OCRv6's download (Best's)
    languages: list[str]  # the languages Windows reads words in here ("en-GB")
    place: Literal["card", "processor"]  # where Best reads


class SearchProblem(ApiModel):
    """A reader that couldn't run: reading waits on it till Go on (`/search/resume`) or the next
    scan, the other reader reading on."""

    reader: Literal["pictures", "words"]  # SigLIP's, or the reader of words'
    said: str  # what went wrong, in words


class SearchState(ApiModel):
    """How far reading the library for search has got, and what it waits for."""

    read: int  # pictures read as they are now
    of: int  # the library's pictures that open, on drives connected (or read before)
    reading: bool  # reading now
    paused: bool  # the owner paused it
    busy: bool  # the queue has the graphics card: reading takes its turns more slowly
    failed: int  # pictures that couldn't be read now: tried again after the next scan
    problem: SearchProblem | None  # a reader that couldn't run
    describer: Tool | None  # SigLIP's download
    words: WordsReader


class SearchResults(ApiModel):
    search: str  # what was searched for: the words, or (like) the picture's name
    groups: list[SearchGroup]  # those that found anything: words, then described, then name
    total: int  # pictures found, each once
    english: bool  # describing works in English: a search in another language isn't described
    unreadable: str | None  # a writing its words are in that the words reader can't read: "Greek"
    state: SearchState


@router.get("/search")
def search(
    conn: Database, shown: Showing, finding: Searching, finder: Finding, toolbox: Toolbox
) -> SearchResults:
    """What the Library's search box finds, in a folder or the whole library (or the
    favourites): pictures whose words match, those that look like what was described (SigLIP's
    score past its cut, best first), and those with every word in their name. Fetches what
    reading needs, the first time the library is searched."""
    words = shown.words.strip()
    state = _state(conn, finding, toolbox)
    _fetch(finding, state)
    english = in_english(words)
    readable = reads(state.words.reader, state.words.languages)
    groups = found_groups(conn, finding, shown, english=english) if words else []
    hits = _hits(conn, finder, groups, words)
    shown_groups = [group for group in hits if group.pictures]
    return SearchResults(
        search=words,
        groups=shown_groups,
        total=sum(group.total for group in shown_groups),
        english=english,
        unreadable=_named(unreadable(words, readable)),
        state=state,
    )


@router.get("/search/like/{picture_id}")
def like(
    picture_id: int, conn: Database, finding: Searching, finder: Finding, toolbox: Toolbox
) -> SearchResults:
    """The library's pictures most like one, by what SigLIP read of each, nearest first: read
    now when it hasn't been yet. 404 for a picture that isn't in the library."""
    row = conn.execute(
        f"SELECT p.* FROM pictures AS p WHERE p.id = ? AND {LISTED}",  # noqa: S608 - fixed
        (picture_id,),
    ).fetchone()
    if row is None:  # outside the library, gone, or one reading never reads
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That picture isn't in your library.")
    state = _state(conn, finding, toolbox)
    _fetch(finding, state)
    groups: list[tuple[Kind, list[int], dict[int, float], dict[int, str]]] = []
    if finding.siglip.ready():
        try:
            nearest = finding.like(conn, picture_id)
        except ModelError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
        ids, scores = _fresh(conn, nearest, Shown(None, "", "", "newest"))
        groups.append(("like", ids, scores, {}))
    shown_groups = [group for group in _hits(conn, finder, groups) if group.pictures]
    return SearchResults(
        search=row["name"],
        groups=shown_groups,
        total=sum(group.total for group in shown_groups),
        english=True,
        unreadable=None,
        state=state,
    )


@router.get("/search/state")
def search_state(conn: Database, finding: Searching, toolbox: Toolbox) -> SearchState:
    """How far reading the library for search has got, and what it waits for."""
    return _state(conn, finding, toolbox)


@router.post("/search/pause")
def pause(conn: Database, finding: Searching, toolbox: Toolbox) -> SearchState:
    """Pauses reading the library after the picture it's on, till it's asked to go on."""
    finding.pause(conn, paused=True)
    return _state(conn, finding, toolbox)


@router.post("/search/resume")
def resume(conn: Database, finding: Searching, toolbox: Toolbox) -> SearchState:
    """Goes on reading the library."""
    finding.pause(conn, paused=False)
    return _state(conn, finding, toolbox)


def found_groups(
    conn: sqlite3.Connection, finding: Search, shown: Shown, *, english: bool = True
) -> list[tuple[Kind, list[int], dict[int, float], dict[int, str]]]:
    """What a search finds in the pictures a list shows, as groups: each kind, its pictures best
    first (each once, in the first group that holds it), their scores and their words."""
    words = shown.words.strip()
    worded: list[int] = []
    texts: dict[int, str] = {}
    query = match_query(words)
    if query is not None:
        hits = finding.worded(conn, query)
        allowed = _allowed(conn, hits, shown)
        worded = [each for each in hits if each in allowed]
        texts = finding.texts(conn, worded[:MOST])  # the words of those shown, no more
    described: list[int] = []
    scores: dict[int, float] = {}
    if english and finding.siglip.ready():
        with suppress(ModelError):  # SigLIP that can't run: names and words still find
            described, scores = _fresh(conn, finding.described_as(words), shown)
    named = _named_ids(conn, shown)
    kept = first_seen([worded, described, named])
    kinds: list[Kind] = ["words", "described", "name"]
    return [
        (kind, ids, scores if kind == "described" else {}, texts if kind == "words" else {})
        for kind, ids in zip(kinds, kept, strict=True)
    ]


def found_ids(conn: sqlite3.Connection, finding: Search, shown: Shown) -> list[int]:
    """Every picture a search finds in a list, in the order its results show them (Many at once
    from a search, and a picture's neighbours opened from its results)."""
    if shown.like is not None:
        try:
            nearest = finding.like(conn, shown.like) if finding.siglip.ready() else []
        except ModelError:
            nearest = []
        ids, _scores = _fresh(conn, nearest, replace(shown, words="", like=None))
        return ids
    groups = found_groups(conn, finding, shown, english=in_english(shown.words))
    return [each for _kind, ids, _scores, _texts in groups for each in ids]


def _fresh(
    conn: sqlite3.Connection, ranked: Sequence[tuple[int, int, int, float]], shown: Shown
) -> tuple[list[int], dict[int, float]]:
    """Of pictures ranked by their vectors, those a list shows whose files are as they were
    read, in order."""
    allowed = _allowed(conn, [each[0] for each in ranked], shown, versions=True)
    ids: list[int] = []
    scores: dict[int, float] = {}
    for picture_id, size, modified, score in ranked:
        if allowed.get(picture_id) == (size, modified):
            ids.append(picture_id)
            scores[picture_id] = score
    return ids, scores


def _allowed(
    conn: sqlite3.Connection, ids: Sequence[int], shown: Shown, *, versions: bool = False
) -> dict[int, tuple[int, int] | None]:
    """Of some pictures, those the list shows (its folder, the favourites) that reading reads
    (one won't-open or marked as damaged since is no longer found by what was read of it), each
    with its file's size and time when asked."""
    if not ids:
        return {}
    where, values = shown_where(replace(shown, words="", like=None))
    rows = conn.execute(
        f"""SELECT p.id, p.size, p.modified FROM pictures AS p
            WHERE p.id IN (SELECT value FROM json_each(?)) AND {where}
              AND {LISTED}""",  # noqa: S608 - fixed pieces
        [json.dumps(list(ids)), *values],
    ).fetchall()
    return {row["id"]: (row["size"], row["modified"]) if versions else None for row in rows}


def _named_ids(conn: sqlite3.Connection, shown: Shown) -> list[int]:
    """The pictures with every word of the search in their name, in the list's order: every
    one, as Many at once takes them all (a group shows the first `MOST`)."""
    where, values = shown_where(replace(shown, like=None))
    way = "DESC" if shown.order == "newest" else "ASC"
    return [
        row["id"]
        for row in conn.execute(
            f"""SELECT id FROM pictures WHERE {where}
                ORDER BY taken_at {way}, id {way}""",  # noqa: S608 - fixed pieces
            values,
        )
    ]


def _hits(
    conn: sqlite3.Connection,
    finder: Finding,
    groups: Sequence[tuple[Kind, list[int], dict[int, float], dict[int, str]]],
    words: str = "",
) -> list[SearchGroup]:
    """The groups as the window shows them: each picture with its tag, its heart, whether its
    drive is away, its score and its words with those matched marked."""
    everyone = [each for _kind, ids, _scores, _texts in groups for each in ids[:MOST]]
    rows = {
        row["id"]: row
        for row in conn.execute(
            "SELECT * FROM pictures WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(everyone),),
        )
    }
    tags = group_tags(finder.found(), choices(conn))
    hearts = favourites.among(conn, everyone)
    away = away_folders(conn)
    made: list[SearchGroup] = []
    for kind, ids, scores, texts in groups:
        pictures: list[SearchHit] = []
        for each in ids[:MOST]:
            row = rows.get(each)
            if row is None:
                continue
            item = item_of(row, tags.get(each), each in hearts)
            text = texts.get(each)
            pictures.append(
                SearchHit(
                    **item.model_dump(by_alias=False),
                    score=scores.get(each),
                    words=None
                    if text is None
                    else [WordsPiece(text=p.text, marked=p.marked) for p in marked(text, words)],
                    away=row["folder_id"] in away,
                )
            )
        made.append(SearchGroup(kind=kind, pictures=pictures, total=len(ids)))
    return made


def _state(conn: sqlite3.Connection, finding: Search, toolbox: Tools) -> SearchState:
    progress = finding.progress(conn)
    languages = finding.fast.languages()
    reader = finding.reader_now(conn)
    return SearchState(
        read=progress.read,
        of=progress.of,
        reading=progress.reading,
        paused=progress.paused,
        busy=progress.busy,
        failed=progress.failed,
        problem=None
        if progress.problem is None
        else SearchProblem(reader=progress.problem[0], said=progress.problem[1]),
        describer=_tool(toolbox, SIGLIP),
        words=WordsReader(
            chosen=chosen(conn),
            reader=reader,
            model=_tool(toolbox, PPOCR),
            languages=languages,
            place=finding.best.place(),
        ),
    )


def _tool(toolbox: Tools, tool: str) -> Tool | None:
    for item, progress in toolbox.status():
        if item.id == tool:
            return tool_of(item, progress)
    return None


def _fetch(finding: Search, state: SearchState) -> None:
    """Fetches what reading needs, the first time the library is searched: SigLIP, and
    PP-OCRv6 where the words are read at Best. Never again by itself after a download that
    didn't match the list."""
    if not finding.siglip.ready():
        finding.siglip.fetch()
    if state.words.reader == "best" and not finding.best.ready():
        finding.best.fetch()


def _named(script: str | None) -> str | None:
    return None if script is None else script.capitalize()
