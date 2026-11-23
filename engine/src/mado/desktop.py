"""Windows' desktop: this PC's monitors as Windows arranges them, and the wallpaper on each.

The wallpaper goes through IDesktopWallpaper, Windows' own per-monitor wallpaper (what Settings ›
Personalisation › Background sets); the monitors come from the display APIs, per-monitor DPI
aware so their pixels are their own, and their names from DisplayConfig. All by ctypes, with no
package. `Desktop` is the seam: the studio (mado/wallpaper.py) asks it, the tests hand it a fake,
and only `mado serve` hands it `WindowsDesktop`, so no test ever touches the owner's wallpaper.
Anywhere else, `NoDesktop` reads nothing and sets nothing.

Mado changes only the wallpaper: each monitor's picture, how pictures are laid when Windows had
them spanned (as a span shows only one picture), and Windows' slideshow put back as it was. It
never changes any other Windows setting; Windows spotlight, which no API turns on, is only read.
"""

import ctypes
import logging
import re
import sys
import winreg
from collections.abc import Generator, Sequence
from contextlib import contextmanager, suppress
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Protocol

from mado.core.wallpaper import Monitor

log = logging.getLogger(__name__)

FILL, SPAN = 4, 5  # IDesktopWallpaper's DESKTOP_WALLPAPER_POSITION: fill, and span across all
_SPOTLIGHT = 3  # Explorer\Wallpapers' BackgroundType for Windows spotlight


class DesktopError(Exception):
    """Something Windows wouldn't do for the wallpaper, with a sentence saying what."""


@dataclass(frozen=True)
class Seen:
    """A monitor as Windows has it now, and the file it says the monitor shows (None: a colour,
    or Windows doesn't say)."""

    monitor: Monitor
    wallpaper: str | None


@dataclass(frozen=True)
class Slideshow:
    """Windows' wallpaper slideshow: the folder it shows, how long each picture stays and
    whether it shuffles them."""

    folder: str
    interval: int  # milliseconds
    shuffle: bool


class Desktop(Protocol):
    """What the studio needs of Windows' desktop."""

    @property
    def here(self) -> bool:
        """Whether wallpapers can be set here at all."""
        ...

    def monitors(self) -> list[Seen]: ...

    def set_wallpaper(self, monitor: str, path: str) -> None: ...

    def position(self) -> int | None: ...

    def set_position(self, position: int) -> None: ...

    def slideshow(self) -> Slideshow | None: ...

    def start_slideshow(self, slideshow: Slideshow) -> None: ...

    def spotlight(self) -> bool: ...


class NoDesktop:
    """Where Mado can't set wallpapers (tests, unless they bring a fake; anywhere but Windows)."""

    here = False

    def monitors(self) -> list[Seen]:
        return []

    def set_wallpaper(self, monitor: str, path: str) -> None:
        raise DesktopError(_ONLY_WINDOWS)

    def position(self) -> int | None:
        return None

    def set_position(self, position: int) -> None:
        raise DesktopError(_ONLY_WINDOWS)

    def slideshow(self) -> Slideshow | None:
        return None

    def start_slideshow(self, slideshow: Slideshow) -> None:
        raise DesktopError(_ONLY_WINDOWS)

    def spotlight(self) -> bool:
        return False


_ONLY_WINDOWS = "Mado sets wallpapers only on Windows' own desktop."


# Joining Windows' three views of a monitor: pure, so it's tested anywhere.


@dataclass(frozen=True)
class Display:
    """A monitor as the display APIs see it: its GDI name ("\\\\.\\DISPLAY1"), its place and
    pixels (per-monitor DPI aware), its DPI, its turn and whether it's the main one."""

    device: str
    x: int
    y: int
    width: int
    height: int
    dpi: int
    rotation: int
    main: bool


@dataclass(frozen=True)
class Named:
    """What DisplayConfig says of the monitor on a GDI name: its own name and its device path,
    the name IDesktopWallpaper knows it by."""

    device: str
    name: str
    path: str


@dataclass(frozen=True)
class Listed:
    """A monitor IDesktopWallpaper lists: its device path, its rectangle and its wallpaper."""

    path: str
    x: int
    y: int
    width: int
    height: int
    wallpaper: str | None


def joined(
    displays: Sequence[Display], names: Sequence[Named], listed: Sequence[Listed]
) -> list[Seen]:
    """The monitors IDesktopWallpaper lists that Windows shows now, each with what the display
    APIs say of it: found by its device path through DisplayConfig, else by its rectangle."""
    by_device = {each.device.casefold(): each for each in displays}
    found: list[Seen] = []
    for each in listed:
        named = next((n for n in names if n.path.casefold() == each.path.casefold()), None)
        display = by_device.get(named.device.casefold()) if named else None
        if display is None:
            display = next(
                (
                    d
                    for d in displays
                    if (d.x, d.y, d.width, d.height) == (each.x, each.y, each.width, each.height)
                ),
                None,
            )
        if display is None:
            continue  # listed, but not showing: unplugged, or turned off
        number = _number(display.device)
        found.append(
            Seen(
                Monitor(
                    id=each.path,
                    name=(named.name.strip() if named else "") or f"Screen {number}",
                    number=number,
                    x=display.x,
                    y=display.y,
                    width=display.width,
                    height=display.height,
                    scale=round(display.dpi / 96, 2) if display.dpi > 0 else 1.0,
                    rotation=display.rotation,
                    main=display.main,
                ),
                each.wallpaper or None,
            )
        )
    return found


def _number(device: str) -> int:
    """The number in a GDI name: 3 for "\\\\.\\DISPLAY3"."""
    found = re.search(r"(\d+)\s*$", device)
    return int(found[1]) if found else 0


# Windows itself, through ctypes.


class WindowsDesktop:
    """This PC's desktop. Each call does its work on the calling thread, with COM opened and
    closed around it, so any of the engine's threads may call."""

    @property
    def here(self) -> bool:
        return sys.platform == "win32"

    def monitors(self) -> list[Seen]:
        """The monitors showing now, as Windows arranges them, with their wallpapers. Raises
        DesktopError when Windows won't say."""
        if not self.here:
            return []
        with _per_monitor_aware():
            displays = _displays()
            names = _names()
            with _wallpaper() as paper:
                listed = paper.listed()
        return joined(displays, names, listed)

    def set_wallpaper(self, monitor: str, path: str) -> None:
        with _wallpaper() as paper:
            paper.check(
                paper.call(3, (wintypes.LPCWSTR, wintypes.LPCWSTR), monitor, path),
                "Windows wouldn't set the wallpaper",
            )

    def position(self) -> int | None:
        with _wallpaper() as paper:
            found = ctypes.c_int()
            hr = paper.call(11, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(found))
            return found.value if hr >= 0 else None

    def set_position(self, position: int) -> None:
        with _wallpaper() as paper:
            paper.check(
                paper.call(10, (ctypes.c_int,), position),
                "Windows wouldn't change how wallpapers are laid",
            )

    def slideshow(self) -> Slideshow | None:
        """Windows' slideshow, when one is on: its folder and options."""
        with _wallpaper() as paper:
            state = ctypes.c_int()
            hr = paper.call(17, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(state))
            if hr < 0 or not state.value & _DSS_SLIDESHOW:
                return None
            items = ctypes.c_void_p()
            if paper.call(13, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(items)) < 0:
                return None
            try:
                folder = _first_path(items)
            finally:
                _release(items)
            options, tick = ctypes.c_int(), ctypes.c_uint()
            paper.call(
                15,
                (ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)),
                ctypes.byref(options),
                ctypes.byref(tick),
            )
            if not folder:
                return None
            return Slideshow(folder, tick.value, bool(options.value & _DSO_SHUFFLE))

    def start_slideshow(self, slideshow: Slideshow) -> None:
        """Windows' slideshow on again, as it was: its folder, interval and shuffle."""
        item, items = ctypes.c_void_p(), ctypes.c_void_p()
        _shell32.SHCreateItemFromParsingName.argtypes = (
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        )
        _shell32.SHCreateShellItemArrayFromShellItem.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        )
        with _wallpaper() as paper:
            hr = _shell32.SHCreateItemFromParsingName(
                slideshow.folder, None, ctypes.byref(_guid(_IID_ITEM)), ctypes.byref(item)
            )
            paper.check(hr, f"Windows couldn't find the slideshow's folder, {slideshow.folder}")
            try:
                hr = _shell32.SHCreateShellItemArrayFromShellItem(
                    item, ctypes.byref(_guid(_IID_ITEMS)), ctypes.byref(items)
                )
                paper.check(hr, "Windows wouldn't take the slideshow's folder")
                try:
                    paper.check(
                        paper.call(12, (ctypes.c_void_p,), items),
                        "Windows wouldn't start the slideshow again",
                    )
                    paper.call(
                        14,
                        (ctypes.c_int, ctypes.c_uint),
                        _DSO_SHUFFLE if slideshow.shuffle else 0,
                        slideshow.interval,
                    )
                finally:
                    _release(items)
            finally:
                _release(item)

    def spotlight(self) -> bool:
        """Whether Windows spotlight draws the desktop: Settings › Personalisation › Background."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WALLPAPERS) as key:
                value, _kind = winreg.QueryValueEx(key, "BackgroundType")
        except OSError:
            return False
        return value == _SPOTLIGHT


_WALLPAPERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers"
_CLSID_WALLPAPER = "{C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD}"
_IID_WALLPAPER = "{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}"
_IID_ITEM = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"  # IShellItem
_IID_ITEMS = "{B63EA76D-1F85-456F-A19C-48159EFA858B}"  # IShellItemArray
_DSS_SLIDESHOW = 0x2  # DESKTOP_SLIDESHOW_STATE: a slideshow is set
_DSO_SHUFFLE = 0x1  # DESKTOP_SLIDESHOW_OPTIONS: shuffle
_SIGDN_FILESYSPATH = 0x80058000 - 0x100000000  # as the signed int ctypes passes
_COINIT_APARTMENT = 0x2
_CLSCTX = 0x1 | 0x4  # in this process, or Explorer's
_CHANGED_MODE = -2147417850  # RPC_E_CHANGED_MODE: COM already open on this thread, another way

if sys.platform == "win32":
    _ole32: Any = ctypes.WinDLL("ole32")
    _user32: Any = ctypes.WinDLL("user32", use_last_error=True)
    _shell32: Any = ctypes.WinDLL("shell32")
    _shcore: Any = ctypes.WinDLL("shcore")
else:  # pragma: no cover - Mado runs on Windows; the seam lets tests run anywhere
    _ole32 = _user32 = _shell32 = _shcore = None


class _Guid(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    )


def _guid(text: str) -> _Guid:
    found = _Guid()
    _ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(found))
    return found


class _Paper:
    """IDesktopWallpaper, opened: its methods by their place in its table."""

    def __init__(self, pointer: ctypes.c_void_p) -> None:
        self._pointer = pointer
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0]
        self._table = ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))

    def call(self, index: int, types: tuple[Any, ...], *args: object) -> int:
        method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(self._table[index])
        hr: int = method(self._pointer, *args)
        return hr

    @staticmethod
    def check(hr: int, what: str) -> None:
        """Windows refusing, said in words; its code, which means nothing to the owner, kept in
        the log."""
        if hr < 0:
            log.warning("%s: Windows answered %#010x", what, hr & 0xFFFFFFFF)
            raise DesktopError(f"{what}.")

    def listed(self) -> list[Listed]:
        """Every monitor IDesktopWallpaper lists that has a rectangle now, with its wallpaper."""
        count = ctypes.c_uint()
        self.check(
            self.call(6, (ctypes.POINTER(ctypes.c_uint),), ctypes.byref(count)),
            "Windows wouldn't say how many monitors there are",
        )
        found: list[Listed] = []
        for index in range(count.value):
            pointer = ctypes.c_void_p()
            if (
                self.call(
                    5,
                    (ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)),
                    index,
                    ctypes.byref(pointer),
                )
                < 0
            ):
                continue
            path = _taken(pointer)
            rect = wintypes.RECT()
            if (
                self.call(
                    7, (wintypes.LPCWSTR, ctypes.POINTER(wintypes.RECT)), path, ctypes.byref(rect)
                )
                != 0
            ):
                continue  # S_FALSE or worse: it isn't showing
            paper = ctypes.c_void_p()
            hr = self.call(
                4, (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)), path, ctypes.byref(paper)
            )
            wallpaper = _taken(paper) if hr >= 0 else None
            found.append(
                Listed(
                    path,
                    rect.left,
                    rect.top,
                    rect.right - rect.left,
                    rect.bottom - rect.top,
                    wallpaper or None,
                )
            )
        return found


@contextmanager
def _wallpaper() -> Generator[_Paper]:
    """IDesktopWallpaper for the length of a `with`, COM opened on this thread for it."""
    if _ole32 is None:
        raise DesktopError(_ONLY_WINDOWS)
    _ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    _ole32.CoCreateInstance.argtypes = (
        ctypes.POINTER(_Guid),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    )
    opened = _ole32.CoInitializeEx(None, _COINIT_APARTMENT)
    pointer = ctypes.c_void_p()
    try:
        hr = _ole32.CoCreateInstance(
            ctypes.byref(_guid(_CLSID_WALLPAPER)),
            None,
            _CLSCTX,
            ctypes.byref(_guid(_IID_WALLPAPER)),
            ctypes.byref(pointer),
        )
        _Paper.check(hr, "Windows' desktop wallpaper didn't answer")
        try:
            yield _Paper(pointer)
        finally:
            _release(pointer)
    finally:
        if opened >= 0 and opened != _CHANGED_MODE:
            _ole32.CoUninitialize()


def _release(pointer: ctypes.c_void_p) -> None:
    if pointer.value:
        table = ctypes.cast(
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(pointer)


def _taken(pointer: ctypes.c_void_p) -> str:
    """A string Windows handed over, its memory given back."""
    if not pointer.value:
        return ""
    try:
        return ctypes.wstring_at(pointer.value)
    finally:
        _ole32.CoTaskMemFree(pointer)


def _first_path(items: ctypes.c_void_p) -> str:
    """The first item's path in an IShellItemArray (the slideshow's folder)."""
    table = ctypes.cast(
        ctypes.cast(items, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p)
    )
    count = ctypes.c_uint()
    ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint))(table[7])(
        items, ctypes.byref(count)
    )
    if count.value < 1:
        return ""
    item = ctypes.c_void_p()
    hr = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
    )(table[8])(items, 0, ctypes.byref(item))
    if hr < 0:
        return ""
    try:
        item_table = ctypes.cast(
            ctypes.cast(item, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p)
        )
        name = ctypes.c_void_p()
        hr = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(item_table[5])(item, _SIGDN_FILESYSPATH, ctypes.byref(name))
        return _taken(name) if hr >= 0 else ""
    finally:
        _release(item)


@contextmanager
def _per_monitor_aware() -> Generator[None]:
    """This thread sees every monitor's own pixels, not ones scaled to the main monitor's DPI."""
    if _user32 is None:
        yield
        return
    _user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    _user32.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    before = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # per monitor, v2
    try:
        yield
    finally:
        if before:
            _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(before))


class _MonitorInfo(ctypes.Structure):  # MONITORINFOEXW
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    )


class _DevMode(ctypes.Structure):  # DEVMODEW, the display's half of its union
    _fields_ = (
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    )


def _displays() -> list[Display]:
    """Every monitor showing now, as the display APIs see it on a per-monitor aware thread."""
    handles: list[int] = []

    def each(handle: int, _dc: int, _rect: object, _data: int) -> bool:
        handles.append(handle)
        return True

    callback = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )(each)
    _user32.EnumDisplayMonitors(None, None, callback, 0)
    found: list[Display] = []
    for handle in handles:
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        if not _user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            continue
        dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
        if _shcore.GetDpiForMonitor(handle, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
            dpi_x.value = 96
        mode = _DevMode(dmSize=ctypes.sizeof(_DevMode))
        turned = 0
        if _user32.EnumDisplaySettingsExW(info.szDevice, -1, ctypes.byref(mode), 0):
            turned = int(mode.dmDisplayOrientation) % 4 * 90
        rect = info.rcMonitor
        found.append(
            Display(
                device=info.szDevice,
                x=rect.left,
                y=rect.top,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                dpi=dpi_x.value,
                rotation=turned,
                main=bool(info.dwFlags & 1),
            )
        )
    return found


class _Luid(ctypes.Structure):
    _fields_ = (("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG))


class _PathInfo(ctypes.Structure):  # DISPLAYCONFIG_PATH_INFO, 72 bytes
    _fields_ = (
        ("source_adapter", _Luid),
        ("source_id", ctypes.c_uint32),
        ("source_mode", ctypes.c_uint32),
        ("source_status", ctypes.c_uint32),
        ("target_adapter", _Luid),
        ("target_id", ctypes.c_uint32),
        ("target_mode", ctypes.c_uint32),
        ("technology", ctypes.c_uint32),
        ("rotation", ctypes.c_uint32),
        ("scaling", ctypes.c_uint32),
        ("refresh_numerator", ctypes.c_uint32),
        ("refresh_denominator", ctypes.c_uint32),
        ("scanlines", ctypes.c_uint32),
        ("available", wintypes.BOOL),
        ("target_status", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
    )


class _ModeInfo(ctypes.Structure):  # DISPLAYCONFIG_MODE_INFO, 64 bytes
    _fields_ = (
        ("kind", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("adapter", _Luid),
        ("rest", ctypes.c_ubyte * 48),
    )


class _InfoHeader(ctypes.Structure):  # DISPLAYCONFIG_DEVICE_INFO_HEADER
    _fields_ = (
        ("type", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("adapter", _Luid),
        ("id", ctypes.c_uint32),
    )


class _SourceName(ctypes.Structure):  # DISPLAYCONFIG_SOURCE_DEVICE_NAME
    _fields_ = (("header", _InfoHeader), ("gdi", ctypes.c_wchar * 32))


class _TargetName(ctypes.Structure):  # DISPLAYCONFIG_TARGET_DEVICE_NAME
    _fields_ = (
        ("header", _InfoHeader),
        ("flags", ctypes.c_uint32),
        ("technology", ctypes.c_uint32),
        ("manufacturer", ctypes.c_uint16),
        ("product", ctypes.c_uint16),
        ("connector", ctypes.c_uint32),
        ("friendly", ctypes.c_wchar * 64),
        ("path", ctypes.c_wchar * 128),
    )


def _names() -> list[Named]:
    """Each active monitor's own name and device path, by its GDI name; none where DisplayConfig
    won't say (its rectangle finds it then)."""
    found: list[Named] = []
    with suppress(OSError, AttributeError, ValueError):
        paths_count, modes_count = ctypes.c_uint32(), ctypes.c_uint32()
        if _user32.GetDisplayConfigBufferSizes(
            2, ctypes.byref(paths_count), ctypes.byref(modes_count)
        ):
            return found
        paths = (_PathInfo * max(paths_count.value, 1))()
        modes = (_ModeInfo * max(modes_count.value, 1))()
        if _user32.QueryDisplayConfig(
            2, ctypes.byref(paths_count), paths, ctypes.byref(modes_count), modes, None
        ):
            return found
        for path in paths[: paths_count.value]:
            source = _SourceName()
            source.header = _InfoHeader(
                1, ctypes.sizeof(_SourceName), path.source_adapter, path.source_id
            )
            target = _TargetName()
            target.header = _InfoHeader(
                2, ctypes.sizeof(_TargetName), path.target_adapter, path.target_id
            )
            if _user32.DisplayConfigGetDeviceInfo(ctypes.byref(source)) or (
                _user32.DisplayConfigGetDeviceInfo(ctypes.byref(target))
            ):
                continue
            found.append(Named(source.gdi, target.friendly, target.path))
    return found
