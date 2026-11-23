"""Searching the library by describing a picture, by the words in it, and by its name, all from
the same words (docs/stack/search.md). Pure: the vectors, scores and words come in, what's found
goes out (mado/search.py reads the library and keeps what it read).

- Describing: SigLIP base reads each picture and each search into 768 numbers, made one long so
  their product is how alike they are; its own score for a picture and a search is the sigmoid
  of that times the scale it learned, plus its bias. A picture is what was described when its
  score passes CUT (calibrated on made-up scenes: a search for something that isn't there
  finds nothing, rather than the least bad pictures). SigLIP base was trained on English, so a
  search in another language says so and isn't described.
- More like this: the pictures whose vectors are nearest a picture's, the nearest first, as
  alike as LIKE at least.
- Words: what an OCR reader read in a picture, matched however it's written (capitals, and
  the accents of Latin, Greek and Cyrillic letters, fold away; each word searched for may be the
  start of a word read, and a Chinese or Japanese one is found anywhere in a line), with the words
  that matched marked.
"""

import math
import string
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
from PIL import Image

type Vectors = npt.NDArray[np.float32]  # one picture's 768 numbers to a row, each row one long

DIMENSIONS = 768  # the numbers SigLIP base reads a picture or a search into
TOKENS = 64  # its text tower reads a search as exactly this many tokens
END = 1  # </s>: ends a search and pads it out to TOKENS
# SigLIP base's own scale and bias (google/siglip-base-patch16-224 at 7fd15f0's logit_scale and
# logit_bias): its score is the sigmoid of the scaled likeness plus the bias.
SCALE = math.exp(4.764997)
BIAS = -12.932437
CUT = 0.01  # SigLIP's score a picture needs to be what was described
LIKE = 0.6  # how alike (their vectors' product) a picture must be to be "more like this"
LIKE_MOST = 60  # pictures "more like this" shows at most
SIDE = 224  # SigLIP base reads a picture squeezed to this square
_PUNCTUATION = str.maketrans("", "", string.punctuation)

# Words that mark a search as written in another language: little words, and a few things often
# searched for, in the languages a search in Latin letters is likeliest to be in, none of them
# an English word too, nor often searched for in English ("aux cable", "MIT", "Big Sur", "est.").
_FOREIGN = frozenset(
    {
        # French
        "le", "des", "une", "du", "avec", "dans", "chez", "très", "plage", "neige", "chien",
        "mer", "ciel", "soleil", "voiture", "fleur", "fleurs",
        # German
        "der", "das", "und", "ein", "eine", "auf", "ist", "nicht", "zum", "zur", "hund",
        "katze", "himmel", "schnee", "baum", "meer", "sonne", "blumen",
        # Spanish, Portuguese and Italian
        "una", "por", "playa", "perro", "gato", "cielo", "nieve", "coche", "flores", "uma",
        "praia", "cachorro", "gli", "nel", "spiaggia", "fiori",
        # Dutch and Afrikaans
        "het", "een", "bij", "hond", "kat", "lucht", "sneeuw", "bloemen", "sneeu", "honde",
    }
)  # fmt: skip
# Words that mark it as English, which win over a foreign-looking word beside them.
_ENGLISH = frozenset(
    {
        "the", "a", "an", "of", "with", "in", "on", "at", "and", "by", "from", "to", "under",
        "over", "near", "my", "our", "some", "two", "three", "is", "are", "picture", "photo",
    }
)  # fmt: skip

type Script = Literal[
    "latin", "greek", "cyrillic", "chinese", "japanese", "korean", "arabic", "hebrew", "thai",
    "devanagari", "other",
]  # fmt: skip
# The writing systems by the first word of their letters' Unicode names.
_SCRIPTS: dict[str, Script] = {
    "LATIN": "latin",
    "GREEK": "greek",
    "CYRILLIC": "cyrillic",
    "CJK": "chinese",
    "HIRAGANA": "japanese",
    "KATAKANA": "japanese",
    "HANGUL": "korean",
    "ARABIC": "arabic",
    "HEBREW": "hebrew",
    "THAI": "thai",
    "DEVANAGARI": "devanagari",
}


# Describing.


def canonical(search: str) -> str:
    """A search as SigLIP's own tokenizer canonicalises it: lower case, no punctuation, single
    spaces (tokenizer.json, which Mado reads it with, doesn't)."""
    return " ".join(search.lower().translate(_PUNCTUATION).split())


def padded(ids: Sequence[int]) -> list[int]:
    """A search's token ids as SigLIP's text tower takes them: ended by </s>, then padded with it
    to exactly TOKENS (the tower reads the last place, so a shorter search reads wrong); a long
    search is cut, keeping its end."""
    kept = list(ids)
    while kept and kept[-1] == END:
        kept.pop()
    kept = kept[: TOKENS - 1]
    return kept + [END] * (TOKENS - len(kept))


def picture_input(picture: Image.Image) -> npt.NDArray[np.float32]:
    """A picture as SigLIP's vision model takes it: squeezed to SIDE × SIDE (bicubic), what's
    see-through laid on white, its colours from -1 to 1, as 1 × 3 × SIDE × SIDE."""
    if picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info:
        backed = Image.new("RGBA", picture.size, (255, 255, 255, 255))
        backed.alpha_composite(picture.convert("RGBA"))
        picture = backed
    squeezed = picture.convert("RGB").resize((SIDE, SIDE), Image.Resampling.BICUBIC)
    values = np.asarray(squeezed, np.float32) / 127.5 - 1.0
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None], dtype=np.float32)


def unit(vectors: npt.ArrayLike) -> Vectors:
    """Vectors made one long each (a zero vector stays zero), as 32-bit floats."""
    found = np.atleast_2d(np.asarray(vectors, np.float32))
    lengths = np.linalg.norm(found, axis=1, keepdims=True)
    return np.ascontiguousarray(found / np.maximum(lengths, 1e-12), dtype=np.float32)


def scores(likeness: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """SigLIP's own score, 0 to 1, for how alike a picture and a search are (their vectors'
    product)."""
    logits = np.clip(SCALE * likeness.astype(np.float64) + BIAS, -60.0, 60.0)
    return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32)


def likeness_for(score: float) -> float:
    """The vectors' product at which SigLIP's score is `score`: where a cut falls."""
    return (math.log(score / (1.0 - score)) - BIAS) / SCALE


@dataclass(frozen=True)
class Ranked:
    """What a search found by description: the rows of the vectors, best first, with SigLIP's
    score for each."""

    rows: tuple[int, ...]
    scores: tuple[float, ...]


def described(vectors: Vectors, search: Vectors, cut: float = CUT) -> Ranked:
    """The pictures (rows of `vectors`) SigLIP scores as what `search` describes, at `cut` or
    more, the best first."""
    if vectors.shape[0] == 0:
        return Ranked((), ())
    likeness = vectors @ search.reshape(-1)
    floor = likeness_for(cut)
    rows = np.flatnonzero(likeness >= floor)
    if rows.size == 0:
        return Ranked((), ())
    order = rows[np.argsort(-likeness[rows], kind="stable")]
    found = scores(likeness[order])
    return Ranked(tuple(int(each) for each in order), tuple(float(each) for each in found))


def nearest(vectors: Vectors, row: int, *, alike: float = LIKE, most: int = LIKE_MOST) -> Ranked:
    """The pictures most like the one at `row`, the nearest first, as alike as `alike` at least
    and `most` of them at most; never the picture itself. Their scores are how alike they are."""
    likeness = vectors @ vectors[row]
    likeness[row] = -np.inf
    rows = np.flatnonzero(likeness >= alike)
    if rows.size > most:
        rows = rows[np.argpartition(-likeness[rows], most - 1)[:most]]
    order = rows[np.argsort(-likeness[rows], kind="stable")]
    return Ranked(
        tuple(int(each) for each in order), tuple(float(likeness[each]) for each in order)
    )


# Which reader reads the words.

type Reader = Literal["fast", "best"]
type Choice = Literal["auto", "fast", "best"]

# The writing systems each reader reads: PP-OCRv6's characters, and Windows' by its languages.
BEST_READS: frozenset[Script] = frozenset({"latin", "greek", "chinese", "japanese"})
_WINDOWS_READS: dict[str, frozenset[Script]] = {
    "el": frozenset({"greek"}),
    "ru": frozenset({"cyrillic"}),
    "uk": frozenset({"cyrillic"}),
    "bg": frozenset({"cyrillic"}),
    "sr": frozenset({"cyrillic", "latin"}),
    "ja": frozenset({"japanese", "chinese"}),
    "zh": frozenset({"chinese"}),
    "ko": frozenset({"korean"}),
    "ar": frozenset({"arabic"}),
    "he": frozenset({"hebrew"}),
    "th": frozenset({"thai"}),
    "hi": frozenset({"devanagari"}),
}


def reader_for(choice: Choice, place: Literal["card", "processor"], windows_reads: bool) -> Reader:
    """The words reader in use: the owner's choice; or, as this PC suits, Best where the AI runs
    on a graphics card (a picture's words in a third of a second), Fast on the processor alone
    (where Best takes seconds a picture), and Best when Windows has no OCR to read with."""
    if choice != "auto":
        return choice
    return "best" if place == "card" or not windows_reads else "fast"


def reads(reader: Reader, languages: Iterable[str]) -> frozenset[Script]:
    """The writing systems a reader reads: Best's own; Windows', those of its OCR languages
    ("en-GB" is Latin)."""
    if reader == "best":
        return BEST_READS
    found: set[Script] = set()
    for tag in languages:
        found |= _WINDOWS_READS.get(tag.split("-")[0].lower(), frozenset({"latin"}))
    return frozenset(found)


def unreadable(search: str, readable: frozenset[Script]) -> Script | None:
    """A writing system the search's words are in that the reader in use can't read, if any:
    never one no reader names ("other"), which a note couldn't name either."""
    missing = sorted(scripts_of(search) - readable - {"other"})
    return missing[0] if missing else None


# The search's own words: its language and writing.


def words_of(search: str) -> list[str]:
    """A search's words, as typed (quotes and other punctuation around them left out)."""
    return [cleaned for each in search.split() if (cleaned := each.strip(_QUOTES))]


_QUOTES = string.punctuation + "“”‘’«»„"  # noqa: RUF001 - quotes round a word, as typed


def scripts_of(search: str) -> set[Script]:
    """The writing systems a search's letters are in. A mark that lengthens or repeats ("ー",
    "々") belongs to the letters round it; narrow and wide letters ("ｺ", "Ｚ") are their
    writing's."""  # noqa: RUF002 - a wide letter, on purpose
    found: set[Script] = set()
    for letter in search:
        if not letter.isalpha() or unicodedata.category(letter) == "Lm":
            continue
        words = unicodedata.name(letter, "").split(" ")
        if words[0] in ("HALFWIDTH", "FULLWIDTH") and len(words) > 1:
            words = words[1:]
        found.add(_SCRIPTS.get(words[0], "other"))
    return found


def in_english(search: str) -> bool:
    """Whether a search reads as English, which SigLIP base understands: Latin letters only, and
    no little word of another language unless an English one is beside it."""
    if scripts_of(search) - {"latin"}:
        return False
    lowered = {each.lower() for each in words_of(search)}
    if lowered & _ENGLISH:
        return True
    return not lowered & _FOREIGN


# Words.


# The writings whose accents fold away (as they're often left off: capitals in Greek are
# written without them); elsewhere a mark makes another letter (Japanese "ガ" isn't "カ").
_FOLDED = ("LATIN ", "GREEK ", "CYRILLIC ")
# Writings with no spaces between words: each letter is a word of its own in the words index.
_UNSPACED = ("CJK ", "HIRAGANA ", "KATAKANA", "HALFWIDTH KATAKANA", "IDEOGRAPHIC ")


def folded(text: str) -> str:
    """Text as the words index compares it, a letter for a letter: lower case, the accents of
    Latin, Greek and Cyrillic letters taken off ("É" is "e", "ά" is "α"), Greek's final "ς" a
    "σ"; "ß" stays "ß", as SQLite's FTS5 leaves it."""  # noqa: RUF002 - Greek, on purpose
    return "".join(_folded_letter(letter) for letter in text)


def _folded_letter(letter: str) -> str:
    lower = letter.lower()[:1] or letter  # "İ" lowers to two letters: the first
    if lower == "ς":
        return "σ"  # noqa: RUF001 - Greek, on purpose
    parts = unicodedata.normalize("NFD", lower)
    if len(parts) > 1 and unicodedata.name(parts[0], "").startswith(_FOLDED):
        return parts[0]
    return lower


def unspaced(letter: str) -> bool:
    """Whether a letter is Chinese or Japanese, written with no spaces between words."""
    return _word_letter(letter) and unicodedata.name(letter, "").startswith(_UNSPACED)


def index_terms(text: str) -> str:
    """What the words index keeps of a picture's words: folded, each Chinese and Japanese
    letter a word of its own, so a word inside a line is found, not only a line's start (FTS5's
    unicode61 would take a whole run of them for one word)."""
    return "".join(f" {letter} " if unspaced(letter) else letter for letter in folded(text))


def match_query(search: str) -> str | None:
    """A search as an FTS5 query of the words index, every word wanted: a word in a writing
    with spaces may start a word read; a Chinese or Japanese one is its letters in a row,
    anywhere in a line. None for a search with no word in it."""
    terms: list[str] = []
    for word in words_of(search):
        tokens = _tokens(index_terms(word))
        if not tokens:
            continue
        if any(unspaced(letter) for letter in word):
            terms.append('"' + " ".join(tokens) + '"')
        else:
            terms.extend(f'"{token}"*' for token in tokens)
    return " AND ".join(terms) if terms else None


def _word_letter(letter: str) -> bool:
    """A letter FTS5's unicode61 keeps in a word: a letter or digit, or a mark on one."""
    return letter.isalnum() or unicodedata.category(letter).startswith("M")


def _tokens(text: str) -> list[str]:
    """Text split as FTS5's unicode61 splits it: runs of letters, digits and their marks."""
    found: list[str] = []
    current: list[str] = []
    for letter in text:
        if _word_letter(letter):
            current.append(letter)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found


@dataclass(frozen=True)
class Piece:
    """A stretch of a picture's words, marked when it's a word the search matched."""

    text: str
    marked: bool


def marked(text: str, search: str, *, around: int = 32) -> list[Piece]:
    """A picture's words with those the search matched marked, cut to the stretch around the
    first match (`around` letters either side), as a tile shows them; the start of the words
    when none matched."""
    flat = " ".join(text.split())
    plain = folded(flat)  # a letter for a letter: what's found in it is found in `flat`
    wanted: list[str] = []  # starts of words, in writings with spaces
    rows: list[str] = []  # Chinese and Japanese words: their letters in a row
    for word in words_of(search):
        if any(unspaced(letter) for letter in word):
            rows.append("".join(_tokens(index_terms(word))))
        else:
            wanted.extend(_tokens(folded(word)))
    spans: list[tuple[int, int]] = []
    at = 0
    for word in flat.split(" "):
        start = flat.index(word, at) if word else at
        end = start + len(word)
        at = end
        bare = _tokens(index_terms(plain[start:end]))
        if bare and any(token.startswith(each) for token in bare for each in wanted):
            spans.append((start, end))
    for row in rows:
        found = plain.find(row) if row else -1
        while found >= 0:
            spans.append((found, found + len(row)))
            found = plain.find(row, found + len(row))
    spans = _merged(spans)
    if not spans:
        return [Piece(flat[: around * 2], False)] if flat else []
    first = spans[0][0]
    low = max(0, first - around)
    high = min(len(flat), max(spans[0][1], first) + around)
    pieces: list[Piece] = []
    if low > 0:
        pieces.append(Piece("…", False))
    cursor = low
    for start, end in spans:
        if end <= low or start >= high:
            continue
        if start > cursor:
            pieces.append(Piece(flat[cursor:start], False))
        pieces.append(Piece(flat[max(start, cursor) : end], True))
        cursor = end
    if cursor < high:
        pieces.append(Piece(flat[cursor:high], False))
    if high < len(flat):
        pieces.append(Piece("…", False))
    return pieces


def _merged(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Stretches of text in order, those that overlap made one."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def first_seen(groups: Iterable[Iterable[int]]) -> list[list[int]]:
    """Groups of pictures with each picture kept only in the first group that holds it."""
    seen: set[int] = set()
    kept: list[list[int]] = []
    for group in groups:
        mine: list[int] = []
        for each in group:
            if each not in seen:
                seen.add(each)
                mine.append(each)
        kept.append(mine)
    return kept
