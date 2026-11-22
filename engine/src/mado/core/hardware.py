"""What a PC can do for Mado, from what it has and what testing it found (mado/hardware.py looks
and keeps, mado/pc_check.py tests): its graphics cards, whether the AI models run on one
(DirectML), the tile size each model takes there, and which of Fast and Best each kind of
picture starts on. Pure.

Mado was first measured on the owner's GTX 1660 Super; on any other PC it says whether the
models run on the graphics card, how long a picture takes there, and starts on the lighter model
where the heavier one would be slow, so nothing is promised that the PC can't do. A PC without a
card that runs them works on the processor, and says so.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from mado.core.estimate import seconds_for
from mado.core.framing import frame
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST, Model, Quality
from mado.core.tiles import count

type Maker = Literal["nvidia", "amd", "intel", "other"]
type Place = Literal["card", "processor"]
type Pace = Literal["ready", "slow"]

GIB = 1024**3
ROOMY = 8 * GIB  # a card's own memory at which the heavy models take big tiles
SLOW = 120.0  # seconds a 12-megapixel photo may take with Best before Fast goes first
TYPICAL = (4032, 3024)  # the picture every time here is for: a phone's 12-megapixel photo
TYPICAL_FOR = (3840, 2160)  # made for a 4K screen
# Windows' listing tells a card's memory only up to this (4 GB less a megabyte): one at it has
# 4 GB or more.
_LISTING_CAP = 0xFFF00000
_VENDORS: dict[str, Maker] = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel"}


@dataclass(frozen=True)
class Card:
    """A graphics card, or the processor's graphics."""

    name: str  # "NVIDIA GeForce GTX 1660 SUPER"
    maker: Maker
    memory: int | None  # bytes of its own; None when Windows doesn't say
    integrated: bool  # the processor's graphics, sharing the PC's memory
    driver: str | None  # its driver's version, as its maker writes it: "617.42"


@dataclass(frozen=True)
class Checked:
    """What testing this PC found."""

    ai: bool  # the AI models ran on a graphics card (DirectML)
    at: str  # when, ISO
    problem: str | None = None  # what the card said when they didn't


@dataclass(frozen=True)
class Ability:
    """A kind of picture on this PC, at one quality: how it's made and how long a typical one
    takes."""

    kind: Literal["photo", "drawing"]
    quality: Quality
    model: str  # the model's name
    pace: Pace
    seconds: float  # a 12-megapixel photo made for a 4K screen
    download: bool  # the model is a download, fetched the first time it's asked for


def place_of(checked: Checked | None) -> Place:
    """Where the AI models run: on the graphics card unless testing found they don't (then the
    processor, openly). Before the first test, the card: one that can't run them says so."""
    return "processor" if checked is not None and not checked.ai else "card"


def tile_for(model: Model, place: Place, card: Card | None) -> int:
    """The tile size a model runs at: 256 pixels on the processor (it reports often enough to
    show progress and stop when asked) and for the heavy models on a card with less than 8 GB of
    its own (a 512 tile takes over 4 GB there); else 512."""
    if place == "processor":
        return 256
    if model.heavy and (card is None or card.integrated or (card.memory or 0) < ROOMY):
        return 256
    return 512


def overlap_for(tile: int) -> int:
    """How far tiles overlap their neighbours, faded across so no seam shows."""
    return 32 if tile >= 512 else 16


def typical_seconds(
    model: Model, place: Place, card: Card | None, speeds: Mapping[str, float]
) -> float:
    """How long a phone's 12-megapixel photo takes here, made for a 4K screen."""
    width, height = TYPICAL
    made = frame(width, height, *TYPICAL_FOR, "crop")
    tile = tile_for(model, place, card)
    tiles = count(round(made.kept.width), round(made.kept.height), tile, overlap_for(tile))
    return seconds_for(model.id, place, tiles, tile, TYPICAL_FOR[0] * TYPICAL_FOR[1], speeds)


def defaults(
    place: Place, card: Card | None, speeds: Mapping[str, float]
) -> dict[Literal["photo", "drawing"], Quality]:
    """Which of Fast and Best each kind of picture starts on here: Best where a typical picture
    takes it at most two minutes on the graphics card, else Fast. The owner can always choose."""
    if place == "processor":
        return {"photo": "fast", "drawing": "fast"}
    return {
        "photo": "best" if typical_seconds(BEST_PHOTO, place, card, speeds) <= SLOW else "fast",
        "drawing": "best" if typical_seconds(BEST_DRAWING, place, card, speeds) <= SLOW else "fast",
    }


def abilities(place: Place, card: Card | None, speeds: Mapping[str, float]) -> tuple[Ability, ...]:
    """Each kind of picture at each quality on this PC, in the order About lists them."""
    kinds: tuple[tuple[Literal["photo", "drawing"], Model], ...] = (
        ("photo", BEST_PHOTO),
        ("drawing", BEST_DRAWING),
    )
    found: list[Ability] = []
    for kind, best in kinds:
        ways: tuple[tuple[Quality, Model], ...] = (("fast", FAST), ("best", best))
        for quality, model in ways:
            took = typical_seconds(model, place, card, speeds)
            pace: Pace = "slow" if took > SLOW else "ready"
            found.append(Ability(kind, quality, model.name, pace, took, model.download is not None))
    return tuple(found)


def maker_of(name: str, vendor: str | None = None) -> Maker:
    """Who made a card, by its PCI vendor id ("10de") or else its name."""
    if vendor and vendor.casefold() in _VENDORS:
        return _VENDORS[vendor.casefold()]
    lowered = name.casefold()
    if any(word in lowered for word in ("nvidia", "geforce", "quadro")):
        return "nvidia"
    if any(word in lowered for word in ("amd", "radeon")):
        return "amd"
    if "intel" in lowered:
        return "intel"
    return "other"


def is_integrated(maker: Maker, memory: int | None) -> bool:
    """Whether a card is the processor's graphics: Intel's and AMD's have little memory of their
    own (dedicated ones have 2 GB or more)."""
    return maker in ("intel", "amd") and (memory is None or memory < 2 * GIB)


def driver_name(version: str | None, maker: Maker) -> str | None:
    """A driver's version as its maker writes it: NVIDIA's "617.42" from Windows'
    "32.0.16.1742"; others' as Windows has it."""
    if version is None:
        return None
    if maker == "nvidia":
        digits = version.replace(".", "")[-5:]
        if len(digits) == 5 and digits.isdigit():
            return f"{int(digits[:3])}.{digits[3:]}"
    return version


def best_card(cards: Sequence[Card]) -> Card | None:
    """The card Mado works on: the dedicated one with the most memory, else the processor's
    graphics. DirectML picks the same one, asked for the PC's high-performance card."""
    dedicated = [card for card in cards if not card.integrated]
    if dedicated:
        return max(dedicated, key=lambda card: card.memory or 0)
    return cards[0] if cards else None


def processor_name(name: str | None) -> str | None:
    """A processor as people say it: "Intel Core i5-9600K" for Windows' "Intel(R) Core(TM)
    i5-9600K CPU @ 3.70GHz"."""
    if not name:
        return None
    cleaned = name.replace("(R)", "").replace("(TM)", "").replace("(tm)", "")
    cleaned = cleaned.split(" CPU @")[0].split(" @ ")[0]
    for word in (" Processor", " CPU", " with Radeon Graphics"):
        cleaned = cleaned.replace(word, "")
    return " ".join(cleaned.split()) or None


def cards_from(listed: Sequence[dict[str, object]], memories: dict[str, int]) -> tuple[Card, ...]:
    """The cards Windows lists (Win32_VideoController: its Name, PNPDeviceID, DriverVersion and
    AdapterRAM), each with its own memory as the registry has it (`memories`, by name: the
    listing stops at 4 GB). Only cards on the PC's bus: not Windows' basic or remote display,
    nor a virtual one."""
    found: list[Card] = []
    for entry in listed:
        name = str(entry.get("Name") or "").strip()
        device = str(entry.get("PNPDeviceID") or "")
        if not name or not device.upper().startswith("PCI\\"):
            continue
        vendor = device.upper().split("VEN_")[1][:4] if "VEN_" in device.upper() else None
        maker = maker_of(name, vendor)
        listed_ram = entry.get("AdapterRAM")
        reported = listed_ram if isinstance(listed_ram, int) and listed_ram > 0 else None
        if reported is not None and reported >= _LISTING_CAP:
            reported = max(reported, 4 * GIB)  # at least: the listing can't say more
        memory = memories.get(name) or reported
        driver = entry.get("DriverVersion")
        found.append(
            Card(
                name,
                maker,
                memory,
                is_integrated(maker, memory),
                driver_name(str(driver) if driver else None, maker),
            )
        )
    return tuple(found)
