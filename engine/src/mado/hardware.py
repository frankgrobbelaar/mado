"""What Mado knows about this PC: what Windows says it has (its graphics cards, each with its own
memory as the registry has it, its processor and its memory), what testing it found, and how
fast each AI model goes on it. mado/pc_check.py tests and times it; mado/core/hardware.py
decides from both.

All of it is kept in the settings: "pc" (what it has, and what testing found) and "pc_speeds"
(each model's seconds for a megapixel of tiles, on the card or the processor). Every picture
made measures its model again, blended into the time kept, so the times stay this PC's own.
"""

import ctypes
import json
import sqlite3
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, cast

from mado.core.estimate import blended
from mado.core.hardware import (
    Card,
    Checked,
    Place,
    best_card,
    cards_from,
    defaults,
    place_of,
    processor_name,
)
from mado.core.models import Quality

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Windows' display adapters and the processor's cores, as one JSON object.
_ASK = (
    "$cards = @(Get-CimInstance Win32_VideoController | "
    "Select-Object Name, PNPDeviceID, DriverVersion, AdapterRAM); "
    "$cores = (Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum; "
    "@{cards = $cards; cores = $cores} | ConvertTo-Json -Compress -Depth 3"
)
_DISPLAY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
_PROCESSOR = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
_PC, _SPEEDS = "pc", "pc_speeds"


@dataclass(frozen=True)
class Facts:
    """What this PC has, as Windows says."""

    cards: tuple[Card, ...]
    processor: str | None  # "Intel Core i5-9600K"
    cores: int | None
    memory: int | None  # bytes installed


@dataclass(frozen=True)
class Measured:
    """How this PC's times were measured: by a test (`tested`) at `at`, and by how many pictures
    made since."""

    at: str
    tested: bool
    pictures: int


@dataclass(frozen=True)
class Here:
    """Where the AI models run on this PC, the card they run on, and their speeds there."""

    place: Place
    card: Card | None
    speeds: dict[str, float]

    def starts_on(self) -> dict[Literal["photo", "drawing"], Quality]:
        """Which of Fast and Best each kind of picture starts on here."""
        return defaults(self.place, self.card, self.speeds)


UNKNOWN = Facts((), None, None, None)


def here(conn: sqlite3.Connection) -> Here:
    """Where the models run here, as testing found (the card, till a test says otherwise)."""
    facts, checked = stored(conn)
    card = best_card(facts.cards) if facts else None
    return Here(place_of(checked), card, speeds(conn))


def look() -> Facts | None:
    """This PC's graphics cards, processor and memory, as Windows has them, or None when Windows
    didn't answer (what was known before stays). Nothing off Windows."""
    if sys.platform != "win32":
        return UNKNOWN
    asked = _asked()
    if asked is None:
        return None
    listed, cores = asked
    return Facts(cards_from(listed, _memories()), processor_name(_processor()), cores, _memory())


def stored(conn: sqlite3.Connection) -> tuple[Facts | None, Checked | None]:
    """What Mado found when it last looked at this PC, and what testing it found."""
    kept = _setting(conn, _PC)
    facts, checked = kept.get("facts"), kept.get("checked")
    if not isinstance(facts, dict) or not isinstance(checked, dict):
        return None, None
    found = cast("dict[str, object]", checked)
    ai, at, problem = found.get("ai"), found.get("at"), found.get("problem")
    if not isinstance(ai, bool) or not isinstance(at, str):
        return None, None
    try:
        return _facts(cast("dict[str, object]", facts)), Checked(
            ai, at, problem if isinstance(problem, str) else None
        )
    except TypeError, ValueError:  # not as Mado wrote it
        return None, None


def keep(conn: sqlite3.Connection, facts: Facts, checked: Checked) -> None:
    _save(conn, _PC, {"facts": asdict(facts), "checked": asdict(checked)})


def speeds(conn: sqlite3.Connection) -> dict[str, float]:
    """Each model's seconds for a megapixel of tiles here, by "model@place", as measured (the
    estimates take the guess for any not measured yet)."""
    found = _setting(conn, _SPEEDS).get("speeds")
    if not isinstance(found, dict):
        return {}
    kept = cast("dict[str, object]", found)
    return {
        name: float(value)
        for name, value in kept.items()
        if isinstance(value, int | float) and value > 0
    }


def measured(conn: sqlite3.Connection) -> Measured | None:
    """How this PC's times were measured, or None while they're a guess."""
    kept = _setting(conn, _SPEEDS)
    at = kept.get("at")
    if not isinstance(at, str):
        return None
    made = kept.get("pictures")
    return Measured(at, kept.get("tested") is True, made if isinstance(made, int) else 0)


def keep_speeds(conn: sqlite3.Connection, found: Mapping[str, float], now: datetime) -> None:
    """A test's times ("model@place": those it could time) in place of the ones kept; the rest
    stay as they were. Nothing changes when it timed nothing."""
    if not found:
        return
    times = {**speeds(conn), **found}
    _save(
        conn,
        _SPEEDS,
        {"speeds": times, "at": now.isoformat(timespec="seconds"), "tested": True, "pictures": 0},
    )


def forget_speeds(conn: sqlite3.Connection) -> None:
    """Back to the guesses: the times were another graphics card's."""
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_SPEEDS,))


def learn(conn: sqlite3.Connection, paces: Mapping[str, float], now: datetime) -> None:
    """A picture just made took each model the seconds a megapixel of tiles in `paces` (by
    `key(model, place)`, where it ran): each blended into the time kept for it, and the picture
    counted once, however many models made it."""
    paces = {name: seconds for name, seconds in paces.items() if seconds > 0}
    if not paces:
        return
    kept = _setting(conn, _SPEEDS)
    times = speeds(conn)
    for name, seconds in paces.items():
        times[name] = blended(times.get(name), seconds)
    made = kept.get("pictures")
    since = kept.get("at") if isinstance(kept.get("at"), str) else now.isoformat(timespec="seconds")
    _save(
        conn,
        _SPEEDS,
        {
            "speeds": times,
            "at": since,
            "tested": kept.get("tested") is True,
            "pictures": (made if isinstance(made, int) else 0) + 1,
        },
    )


def _setting(conn: sqlite3.Connection, name: str) -> dict[str, object]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (name,)).fetchone()
    try:
        found: object = json.loads(row["value"]) if row else None
    except ValueError:
        return {}
    return cast("dict[str, object]", found) if isinstance(found, dict) else {}


def _save(conn: sqlite3.Connection, name: str, value: dict[str, object]) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (name, json.dumps(value)),
        )


def _facts(kept: dict[str, object]) -> Facts:
    cards: list[Card] = []
    for each in cast("list[object]", kept.get("cards") or []):
        if not isinstance(each, dict):
            continue
        card = cast("dict[str, object]", each)
        name, maker, memory = card.get("name"), card.get("maker"), card.get("memory")
        integrated, driver = card.get("integrated"), card.get("driver")
        if not isinstance(name, str) or maker not in ("nvidia", "amd", "intel", "other"):
            raise ValueError("not a card Mado kept")
        cards.append(
            Card(
                name,
                maker,
                memory if isinstance(memory, int) else None,
                integrated is True,
                driver if isinstance(driver, str) else None,
            )
        )
    processor, cores, memory = kept.get("processor"), kept.get("cores"), kept.get("memory")
    return Facts(
        tuple(cards),
        processor if isinstance(processor, str) else None,
        cores if isinstance(cores, int) else None,
        memory if isinstance(memory, int) else None,
    )


def _asked() -> tuple[list[dict[str, object]], int | None] | None:
    """Windows' display adapters (Win32_VideoController) and the processor's cores, or None when
    PowerShell didn't answer."""
    try:
        result = subprocess.run(  # noqa: S603 - a fixed command, no shell
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _ASK],  # noqa: S607
            stdin=subprocess.DEVNULL,  # the engine's own input is the app's
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_NO_WINDOW,
            check=False,
        )
        found: object = json.loads(result.stdout)
    except OSError, subprocess.TimeoutExpired, ValueError:
        return None
    if not isinstance(found, dict):
        return None
    answer = cast("dict[str, object]", found)
    listed = answer.get("cards")
    entries = cast("list[object]", listed) if isinstance(listed, list) else [listed]
    cards = [cast("dict[str, object]", each) for each in entries if isinstance(each, dict)]
    cores = answer.get("cores")
    return cards, cores if isinstance(cores, int) and cores > 0 else None


def _memories() -> dict[str, int]:
    """Each display adapter's own memory, by name, as its driver wrote it in the registry."""
    if sys.platform != "win32":
        return {}
    import winreg

    found: dict[str, int] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY) as adapters:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(adapters, index)
                except OSError:
                    break
                index += 1
                if not name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(adapters, name) as adapter:
                        desc = str(winreg.QueryValueEx(adapter, "DriverDesc")[0])
                        size = winreg.QueryValueEx(adapter, "HardwareInformation.qwMemorySize")[0]
                except OSError:
                    continue
                if isinstance(size, int) and size > 0:
                    found[desc] = size
    except OSError:
        return {}
    return found


def _processor() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PROCESSOR) as handle:
            return str(winreg.QueryValueEx(handle, "ProcessorNameString")[0])
    except OSError:
        return None


def _memory() -> int | None:
    """The memory installed, in bytes."""
    if sys.platform != "win32":
        return None
    kilobytes = ctypes.c_ulonglong(0)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel.GetPhysicallyInstalledSystemMemory(ctypes.byref(kilobytes)):
        return None
    return int(kilobytes.value) * 1024


class _Guid(ctypes.Structure):
    _fields_ = (
        ("first", ctypes.c_uint32),
        ("second", ctypes.c_uint16),
        ("third", ctypes.c_uint16),
        ("rest", ctypes.c_ubyte * 8),
    )


class _MemoryInfo(ctypes.Structure):
    _fields_ = (
        ("budget", ctypes.c_uint64),
        ("usage", ctypes.c_uint64),
        ("available", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64),
    )


def _guid(text: str) -> _Guid:
    found = uuid.UUID(text)
    made = _Guid()
    made.first, made.second, made.third = found.fields[0], found.fields[1], found.fields[2]
    for at, value in enumerate(found.bytes[8:]):
        made.rest[at] = value
    return made


_FACTORY6 = "c1b6694f-ff09-44a9-b03c-77900a0a1d17"  # IDXGIFactory6
_ADAPTER3 = "645967a4-1392-4310-a798-8053ce3e93fd"  # IDXGIAdapter3
_HIGH_PERFORMANCE = 2  # DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE, as DirectML is asked for


def room() -> int | None:
    """Bytes of the graphics card's own memory this process may still use: what Windows budgets
    it (the card's memory less what other apps hold) less what its sessions hold already. Asked
    of DirectX (DXGI), so it's the same for any maker's card, and of the high-performance card,
    as DirectML is. None off Windows, or when DirectX doesn't say."""
    if sys.platform != "win32":
        return None
    try:
        return _asked_room()
    except OSError, AttributeError, ValueError:
        return None


def _asked_room() -> int | None:
    dxgi = ctypes.WinDLL("dxgi")
    factory = ctypes.c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(_guid(_FACTORY6)), ctypes.byref(factory)) != 0:
        return None
    adapter = ctypes.c_void_p()
    try:
        # IDXGIFactory6::EnumAdapterByGpuPreference is the 30th of its methods.
        found = _method(
            factory,
            29,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        )(0, _HIGH_PERFORMANCE, ctypes.byref(_guid(_ADAPTER3)), ctypes.byref(adapter))
        if found != 0 or not adapter.value:
            return None
        info = _MemoryInfo()
        # IDXGIAdapter3::QueryVideoMemoryInfo, its own memory (the local segment group, 0).
        asked = _method(adapter, 14, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(_MemoryInfo))(
            0, 0, ctypes.byref(info)
        )
        if asked != 0:
            return None
        return max(int(info.budget) - int(info.usage), 0)
    finally:
        if adapter.value:
            _method(adapter, 2)()  # Release
        _method(factory, 2)()


def _method(thing: ctypes.c_void_p, index: int, *kinds: type) -> Callable[..., int]:
    """A COM object's method by its place in its table of methods."""
    table = ctypes.cast(thing, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    shape = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *kinds)
    call = shape(table[index])
    return lambda *args: int(call(thing, *args))
