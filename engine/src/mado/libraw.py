"""LibRaw, the camera RAW reader Mado downloads the first time it reads a RAW (downloads.json),
used through its DLL with ctypes: a RAW's facts, the preview its camera kept inside it, and the
picture developed. LibRaw is LGPL, so Mado never ships it: it loads only the copy in its tools
folder, downloaded from the listed address and checked against the listed SHA-256.

Its DLL rather than its programs: those take a file's name in the PC's old code page, so a RAW in
a folder named in Japanese wouldn't open, and those that take a camera's preview out write it
beside the RAW, where Mado writes nothing before Save (docs/stack/libraw.md has the times). Each
file gets a LibRaw of its own, opened to read, closed after: nothing is written anywhere.

Developing follows the camera: its white balance, the RAW's own crop and turn, into Display P3
(a camera's colours go past sRGB, and Mado keeps a picture's wide colours through every tool) on
sRGB's curve, at 8 bits, the depth Mado's pipeline works in. LibRaw's C API sets most of that;
the half size and the camera's white balance it has no call for are set in its options struct,
whose place LibRaw's own calls confirm before Mado writes to it.
"""

import ctypes
import itertools
import logging
import os
import sys
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from ctypes import (
    POINTER,
    Structure,
    c_char,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_longlong,
    c_ubyte,
    c_uint,
    c_ushort,
    c_void_p,
    c_wchar_p,
)
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from mado.core import raw
from mado.core.icc import DISPLAY_P3

log = logging.getLogger(__name__)

DLL = "libraw.dll"
_P3, _BITS = 7, 8  # LibRaw's DCI-P3 D65, at 8 bits
_SRGB_POWER, _SRGB_SLOPE = 1 / 2.4, 12.92  # sRGB's curve, which Display P3 shares
_NO_PREVIEW = (-5, -6, -9)  # no thumbnail, one LibRaw can't hand over, none at that number
_JPEG, _BITMAP = 1, 2  # LibRaw's kinds of image handed over
# Where LibRaw keeps its options in each reader's data, by version: measured from its header
# (docs/stack/libraw.md says how), and confirmed through its own calls before it's written to.
_OPTIONS_AT = {"0.22.3": 5232}
_SIZES_AT = 8  # right after the picture's pointer, the first thing it keeps
_LONG_PATH = 259  # longer than this, a path is handed over in Windows' long form
_DLL_FOLDERS: list[object] = []  # the bundle's own folder, kept added for the engine's life
_UNSUPPORTED = -2  # LIBRAW_FILE_UNSUPPORTED: at unpack, packed in a way it can't unpack
_UNSUPPORTED_FORMAT = 1 << 14  # LIBRAW_DECODER_UNSUPPORTED_FORMAT
_ZLIB, _JPEG_LIB = 1 << 6, 1 << 7  # LIBRAW_CAPS_ZLIB, LIBRAW_CAPS_JPEG: what a build has
# Decoders that need a library a build may lack (LibRaw's own Windows build has neither).
_NEEDS = {
    "deflate_dng_load_raw()": _ZLIB,
    "lossy_dng_load_raw()": _JPEG_LIB,
    "kodak_jpeg_load_raw()": _JPEG_LIB,
}
# This engine's run, which names its notes of the RAWs LibRaw is reading (Reader.reading).
SESSION = uuid.uuid4().hex[:12]


class RawError(Exception):
    """LibRaw said no: its error number, at which stage, and its own words."""

    def __init__(self, code: int, stage: Literal["open", "unpack", "develop"], said: str) -> None:
        self.code, self.stage, self.said = code, stage, said
        self.problem = raw.problem(code, stage, said)
        super().__init__(self.problem.sentence)


class ReaderBrokenError(Exception):
    """The LibRaw found isn't one Mado can use: not the version it knows, or it won't load."""


class _Inset(Structure):
    _fields_ = (
        ("cleft", c_ushort),
        ("ctop", c_ushort),
        ("cwidth", c_ushort),
        ("cheight", c_ushort),
    )


class _Sizes(Structure):
    _fields_ = (
        ("raw_height", c_ushort),
        ("raw_width", c_ushort),
        ("height", c_ushort),
        ("width", c_ushort),
        ("top_margin", c_ushort),
        ("left_margin", c_ushort),
        ("iheight", c_ushort),
        ("iwidth", c_ushort),
        ("raw_pitch", c_uint),
        ("pixel_aspect", c_double),
        ("flip", c_int),
        ("mask", c_int * 32),
        ("raw_aspect", c_ushort),
        ("raw_inset_crops", _Inset * 2),
    )


class _Params(Structure):
    _fields_ = (
        ("greybox", c_uint * 4),
        ("cropbox", c_uint * 4),
        ("aber", c_double * 4),
        ("gamm", c_double * 6),
        ("user_mul", c_float * 4),
        ("bright", c_float),
        ("threshold", c_float),
        ("half_size", c_int),
        ("four_color_rgb", c_int),
        ("highlight", c_int),
        ("use_auto_wb", c_int),
        ("use_camera_wb", c_int),
        ("use_camera_matrix", c_int),
        ("output_color", c_int),
        ("output_profile", c_char_p),
        ("camera_profile", c_char_p),
        ("bad_pixels", c_char_p),
        ("dark_frame", c_char_p),
        ("output_bps", c_int),
        ("output_tiff", c_int),
        ("output_flags", c_int),
        ("user_flip", c_int),
        ("user_qual", c_int),
        ("user_black", c_int),
        ("user_cblack", c_int * 4),
        ("user_sat", c_int),
        ("med_passes", c_int),
        ("auto_bright_thr", c_float),
        ("adjust_maximum_thr", c_float),
        ("no_auto_bright", c_int),
        ("use_fuji_rotate", c_int),
        ("use_p1_correction", c_int),
        ("green_matching", c_int),
        ("dcb_iterations", c_int),
        ("dcb_enhance_fl", c_int),
        ("fbdd_noiserd", c_int),
        ("exp_correc", c_int),
        ("exp_shift", c_float),
        ("exp_preser", c_float),
        ("no_auto_scale", c_int),
        ("no_interpolation", c_int),
    )


class _IParams(Structure):
    _fields_ = (
        ("guard", c_char * 4),
        ("make", c_char * 64),
        ("model", c_char * 64),
        ("software", c_char * 64),
        ("normalized_make", c_char * 64),
        ("normalized_model", c_char * 64),
        ("maker_index", c_uint),
        ("raw_count", c_uint),
        ("dng_version", c_uint),
        ("is_foveon", c_uint),
        ("colors", c_int),
        ("filters", c_uint),
    )


class _Gps(Structure):
    _fields_ = (
        ("latitude", c_float * 3),
        ("longitude", c_float * 3),
        ("gpstimestamp", c_float * 3),
        ("altitude", c_float),
        ("altref", c_char),
        ("latref", c_char),
        ("longref", c_char),
        ("gpsstatus", c_char),
        ("gpsparsed", c_char),
    )


class _Other(Structure):
    _fields_ = (
        ("iso_speed", c_float),
        ("shutter", c_float),
        ("aperture", c_float),
        ("focal_len", c_float),
        ("timestamp", c_longlong),
        ("shot_order", c_uint),
        ("gpsdata", c_uint * 32),
        ("parsed_gps", _Gps),
    )


class _Lens(Structure):  # its first fields: the lens's name is all Mado carries
    _fields_ = (
        ("MinFocal", c_float),
        ("MaxFocal", c_float),
        ("MaxAp4MinFocal", c_float),
        ("MaxAp4MaxFocal", c_float),
        ("EXIF_MaxAp", c_float),
        ("LensMake", c_char * 128),
        ("Lens", c_char * 128),
    )


class _Processed(Structure):
    _fields_ = (
        ("type", c_int),
        ("height", c_ushort),
        ("width", c_ushort),
        ("colors", c_ushort),
        ("bits", c_ushort),
        ("data_size", c_uint),
        ("data", c_ubyte * 1),
    )


class _Decoder(Structure):
    _fields_ = (("decoder_name", c_char_p), ("decoder_flags", c_uint))


@dataclass(frozen=True)
class RawFacts:
    """What LibRaw reads of a RAW without developing it."""

    width: int  # as it's shown, developed at full size: cropped and turned upright
    height: int
    flip: int  # LibRaw's, as dcraw had it
    make: str
    model: str
    taken: datetime | None  # by the camera's clock
    iso: float
    shutter: float  # seconds
    aperture: float
    focal: float  # millimetres
    lens: str
    latitude: float | None  # where it was taken, when it says
    longitude: float | None
    stored: tuple[int, int]  # as LibRaw develops it, before its crop and turn
    crop: raw.Box | None  # the RAW's own crop, in that


@dataclass(frozen=True)
class Preview:
    """The preview a camera kept inside its RAW, as stored (not turned)."""

    data: bytes
    kind: Literal["jpeg", "bitmap"]
    size: tuple[int, int]
    colors: int


class LibRaw:
    """One loaded libraw.dll, shared by every thread: each file it reads gets a reader of its
    own, so they never share a LibRaw."""

    def __init__(self, dll: Path) -> None:
        if getattr(sys, "frozen", False):  # its C++ runtime is the engine's own, in its bundle
            bundle: Any = getattr(sys, "_MEIPASS", None)
            if isinstance(bundle, str) and not _DLL_FOLDERS:
                _DLL_FOLDERS.append(os.add_dll_directory(bundle))
        try:
            self._dll = ctypes.CDLL(str(dll))
        except OSError as error:
            raise ReaderBrokenError(
                f"Mado's RAW reader wouldn't load ({error}). Mado fetches it again."
            ) from None
        self._declare()
        version = self._dll.libraw_version()
        self.version: str = version.decode().split("-")[0] if version else "?"
        options = _OPTIONS_AT.get(self.version)
        if options is None:
            raise ReaderBrokenError(
                f"Mado doesn't know LibRaw {self.version}, the RAW reader it found. Mado fetches "
                "the one it knows again."
            )
        self._options = options
        self._confirm()

    def facts(self, path: Path) -> RawFacts:
        """What the RAW says of itself: its size as shown, the camera, when it was taken."""
        with self._opened(path) as reader:
            return self._facts(reader)

    def preview(self, path: Path) -> Preview | None:
        """The biggest preview its camera kept inside it, JPEG or bitmap; None when it has
        none LibRaw can hand over."""
        with self._opened(path) as reader:
            code = self._dll.libraw_unpack_thumb(reader)
            if code in _NO_PREVIEW:
                return None
            self._check(code, "unpack")
            error = c_int(0)
            made = self._dll.libraw_dcraw_make_mem_thumb(reader, ctypes.byref(error))
            if not made:
                return None
            try:
                found = made.contents
                data = ctypes.string_at(
                    ctypes.addressof(found) + _Processed.data.offset, found.data_size
                )
                kind, colors = found.type, found.colors
                size = (found.width, found.height)
            finally:
                self._dll.libraw_dcraw_clear_mem(made)
        if kind == _JPEG:
            try:
                with Image.open(BytesIO(data)) as header:
                    size = header.size
            except OSError, SyntaxError, ValueError:
                return None  # a preview Pillow can't read: the picture is developed instead
            return Preview(data, "jpeg", size, 3)
        if kind == _BITMAP and colors in (1, 3) and size[0] * size[1] * colors == len(data):
            return Preview(data, "bitmap", size, colors)
        return None  # a JPEG XL or H.265 preview: the picture is developed instead

    def develop(self, path: Path, *, half: bool) -> Image.Image:
        """The picture developed (at half size, when asked), cropped and turned upright, in
        Display P3 at 8 bits."""
        with self._opened(path) as reader:
            facts = self._facts(reader, adjusted=False)
            options = _Params.from_address(reader + self._options)
            options.half_size = int(half)
            options.use_camera_wb = 1
            self._dll.libraw_set_output_color(reader, _P3)
            self._dll.libraw_set_output_bps(reader, _BITS)
            self._dll.libraw_set_gamma(reader, 0, _SRGB_POWER)
            self._dll.libraw_set_gamma(reader, 1, _SRGB_SLOPE)
            self._unpack(reader)
            self._check(self._dll.libraw_dcraw_process(reader), "develop")
            error = c_int(0)
            made = self._dll.libraw_dcraw_make_mem_image(reader, ctypes.byref(error))
            if not made:
                self._check(error.value or -1, "develop")
            self._dll.libraw_recycle(reader)  # its working memory goes before the picture's copy
            try:
                found = made.contents
                width, height, colors = found.width, found.height, found.colors
                start = ctypes.addressof(found) + _Processed.data.offset
                pixels = (ctypes.c_char * found.data_size).from_address(start)
                mode = "L" if colors == 1 else "RGB"
                image = Image.frombuffer(mode, (width, height), pixels, "raw", mode, 0, 1).copy()
            finally:
                self._dll.libraw_dcraw_clear_mem(made)
        image = _cropped(image, facts)
        if image.mode == "RGB":
            image.info["icc_profile"] = DISPLAY_P3
        return image

    def _unpack(self, reader: int) -> None:
        """Unpacks the RAW's pixels. One packed in a way this build can't unpack (deflate, which
        needs zlib; a lossy JPEG, which needs libjpeg; JPEG XL, which needs Adobe's DNG SDK)
        says so, rather than as LibRaw's data error, which reads as damage."""
        decoder = _Decoder()  # asked first: a failed unpack forgets which it chose
        known = self._dll.libraw_get_decoder_info(reader, ctypes.byref(decoder)) == 0
        name = (decoder.decoder_name or b"").decode("latin-1") if known else ""
        flags = decoder.decoder_flags if known else 0
        code = self._dll.libraw_unpack(reader)
        if code == 0:
            return
        needs = _NEEDS.get(name, 0)
        if flags & _UNSUPPORTED_FORMAT or (needs and not self._dll.libraw_capabilities() & needs):
            raise RawError(_UNSUPPORTED, "unpack", f"no {name} in this build")
        self._check(code, "unpack")

    @contextmanager
    def _opened(self, path: Path) -> Generator[int]:
        reader: int | None = self._dll.libraw_init(0)
        if not reader:
            raise RawError(-100007, "open", "no memory for a reader")
        try:
            self._check(self._dll.libraw_open_wfile(reader, _long(path)), "open")
            yield reader
        finally:
            self._dll.libraw_close(reader)

    def _facts(self, reader: int, *, adjusted: bool = True) -> RawFacts:
        sizes = _Sizes.from_address(reader + _SIZES_AT)
        names = self._dll.libraw_get_iparams(reader).contents
        other = self._dll.libraw_get_imgother(reader).contents
        lens = self._dll.libraw_get_lensinfo(reader).contents
        width, height, flip = sizes.width, sizes.height, sizes.flip
        inset = sizes.raw_inset_crops[0]
        crop = raw.shown_crop(
            raw.Inset(inset.cleft, inset.ctop, inset.cwidth, inset.cheight),
            width=width,
            height=height,
            left_margin=sizes.left_margin,
            top_margin=sizes.top_margin,
        )
        shown = raw.developed_size(width, height, crop, flip)
        if adjusted:  # what developing really makes: a Fuji's turned sensor, stretched pixels
            self._dll.libraw_adjust_sizes_info_only(reader)
            made = (sizes.iwidth, sizes.iheight)
            unturned = (made[1], made[0]) if flip & 4 else made
            if unturned != (width, height):
                crop, shown = None, made
        gps = other.parsed_gps
        located = bool(gps.gpsparsed) and any(gps.latitude) and any(gps.longitude)
        return RawFacts(
            width=shown[0],
            height=shown[1],
            flip=flip,
            make=_text(names.make),
            model=_text(names.model),
            taken=_moment(other.timestamp),
            iso=other.iso_speed,
            shutter=other.shutter,
            aperture=other.aperture,
            focal=other.focal_len,
            lens=_text(lens.Lens),
            latitude=_degrees(gps.latitude, gps.latref, b"S") if located else None,
            longitude=_degrees(gps.longitude, gps.longref, b"W") if located else None,
            stored=(width, height),
            crop=crop,
        )

    def _check(self, code: int, stage: Literal["open", "unpack", "develop"]) -> None:
        if code != 0:
            said = self._dll.libraw_strerror(code)
            raise RawError(code, stage, said.decode("latin-1") if said else "")

    def _confirm(self) -> None:
        """LibRaw's options sit where Mado expects: values set through its own calls read back
        through Mado's view of them, before Mado writes any itself."""
        reader: int | None = self._dll.libraw_init(0)
        if not reader:
            raise ReaderBrokenError("Mado's RAW reader couldn't start.")
        try:
            names = ctypes.addressof(self._dll.libraw_get_iparams(reader).contents)
            if names != reader + _SIZES_AT + ctypes.sizeof(_Sizes):
                raise ReaderBrokenError("Mado's RAW reader keeps its facts where Mado didn't look.")
            options = _Params.from_address(reader + self._options)
            plain = (options.half_size, options.use_camera_wb, options.user_flip, options.user_qual)
            self._dll.libraw_set_output_bps(reader, 16)
            self._dll.libraw_set_output_color(reader, 4)
            self._dll.libraw_set_gamma(reader, 0, 0.5)
            self._dll.libraw_set_no_auto_bright(reader, 1)
            self._dll.libraw_set_user_mul(reader, 2, 1.5)
            self._dll.libraw_set_highlight(reader, 2)
            self._dll.libraw_set_bright(reader, 1.25)
            confirmed = (
                plain == (0, 0, -1, -1)
                and options.output_bps == 16
                and options.output_color == 4
                and abs(options.gamm[0] - 0.5) < 1e-9
                and options.no_auto_bright == 1
                and options.user_mul[2] == 1.5
                and options.highlight == 2
                and options.bright == 1.25
            )
            if not confirmed:
                raise ReaderBrokenError(
                    f"LibRaw {self.version} keeps its options where Mado didn't look, so Mado "
                    "doesn't use it."
                )
        finally:
            self._dll.libraw_close(reader)

    def _declare(self) -> None:
        dll = self._dll
        dll.libraw_version.restype = c_char_p
        dll.libraw_strerror.restype = c_char_p
        dll.libraw_strerror.argtypes = [c_int]
        dll.libraw_init.restype = c_void_p
        dll.libraw_init.argtypes = [c_uint]
        dll.libraw_open_wfile.restype = c_int
        dll.libraw_open_wfile.argtypes = [c_void_p, c_wchar_p]
        for name in (
            "libraw_unpack",
            "libraw_unpack_thumb",
            "libraw_dcraw_process",
            "libraw_adjust_sizes_info_only",
        ):
            getattr(dll, name).restype = c_int
            getattr(dll, name).argtypes = [c_void_p]
        for name in ("libraw_close", "libraw_recycle"):
            getattr(dll, name).restype = None
            getattr(dll, name).argtypes = [c_void_p]
        for name in ("libraw_dcraw_make_mem_thumb", "libraw_dcraw_make_mem_image"):
            getattr(dll, name).restype = POINTER(_Processed)
            getattr(dll, name).argtypes = [c_void_p, POINTER(c_int)]
        dll.libraw_dcraw_clear_mem.restype = None
        dll.libraw_dcraw_clear_mem.argtypes = [POINTER(_Processed)]
        dll.libraw_get_iparams.restype = POINTER(_IParams)
        dll.libraw_get_iparams.argtypes = [c_void_p]
        dll.libraw_get_imgother.restype = POINTER(_Other)
        dll.libraw_get_imgother.argtypes = [c_void_p]
        dll.libraw_get_lensinfo.restype = POINTER(_Lens)
        dll.libraw_get_lensinfo.argtypes = [c_void_p]
        for name in ("libraw_set_output_color", "libraw_set_output_bps"):
            getattr(dll, name).restype = None
            getattr(dll, name).argtypes = [c_void_p, c_int]
        dll.libraw_set_no_auto_bright.restype = None
        dll.libraw_set_no_auto_bright.argtypes = [c_void_p, c_int]
        dll.libraw_set_highlight.restype = None
        dll.libraw_set_highlight.argtypes = [c_void_p, c_int]
        dll.libraw_set_gamma.restype = None
        dll.libraw_set_gamma.argtypes = [c_void_p, c_int, c_float]
        dll.libraw_set_user_mul.restype = None
        dll.libraw_set_user_mul.argtypes = [c_void_p, c_int, c_float]
        dll.libraw_set_bright.restype = None
        dll.libraw_set_bright.argtypes = [c_void_p, c_float]
        dll.libraw_get_decoder_info.restype = c_int
        dll.libraw_get_decoder_info.argtypes = [c_void_p, POINTER(_Decoder)]
        dll.libraw_capabilities.restype = c_uint
        dll.libraw_capabilities.argtypes = []


def _cropped(image: Image.Image, facts: RawFacts) -> Image.Image:
    """The developed picture cut to the RAW's own crop, as its turn and the size it came out
    place it: whole or half (LibRaw halves only a colour filter array's pixels, so a linear
    RAW asked for at half size comes out whole)."""
    if facts.crop is None:
        return image
    x, y, w, h = facts.crop
    whole = facts.stored
    halved = ((whole[0] + 1) // 2, (whole[1] + 1) // 2)
    unturned = (image.height, image.width) if facts.flip & 4 else image.size
    if unturned == whole:
        box, stored = (x, y, w, h), whole
    elif unturned == halved:
        box = (x // 2, y // 2, (x + w + 1) // 2 - x // 2, (y + h + 1) // 2 - y // 2)
        stored = halved
    else:
        return image  # developing made another size than LibRaw said: left whole, never cut wrong
    left, top, width, height = raw.turned_box(box, stored, facts.flip)
    return image.crop((left, top, left + width, top + height))


def opens_to_read(path: Path) -> None:
    """Opens the file as LibRaw does, to read, sharing only reads, and lets it go: raises the
    OSError Windows gives (32, its sharing violation, while another app writes to it), so an app
    holding it shows as that rather than as damage, which LibRaw can't tell it from."""
    if os.name != "nt":
        with path.open("rb"):
            return
    handle = _KERNEL32.CreateFileW(
        _long(path), _GENERIC_READ, _FILE_SHARE_READ, None, _OPEN_EXISTING, _NORMAL, None
    )
    if handle is None or handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    _KERNEL32.CloseHandle(handle)


_GENERIC_READ, _FILE_SHARE_READ, _OPEN_EXISTING, _NORMAL = 0x80000000, 1, 3, 0x80
_INVALID_HANDLE = ctypes.c_void_p(-1).value
if os.name == "nt":
    _KERNEL32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateFileW.restype = c_void_p
    _KERNEL32.CreateFileW.argtypes = [c_wchar_p, c_uint, c_uint, c_void_p, c_uint, c_uint, c_void_p]
    _KERNEL32.CloseHandle.restype = c_int
    _KERNEL32.CloseHandle.argtypes = [c_void_p]


def _long(path: Path) -> str:
    """A path as Windows takes it: in its long form past the old length limit."""
    text = str(path)
    if len(text) > _LONG_PATH and not text.startswith("\\\\?\\"):
        absolute = os.path.normpath(Path(text).absolute())
        return (
            f"\\\\?\\UNC\\{absolute[2:]}" if absolute.startswith("\\\\") else f"\\\\?\\{absolute}"
        )
    return text


def _text(value: bytes) -> str:
    return value.decode("utf-8", "replace").replace("\x00", "").strip()


def _moment(stamp: int) -> datetime | None:
    """When LibRaw says it was taken, as the camera's clock said it: LibRaw read it as local
    time, so it goes back as local time."""
    if stamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(stamp)
    except OverflowError, OSError, ValueError:
        return None


def _degrees(parts: Any, ref: bytes, negative: bytes) -> float:
    degrees = float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600
    return -degrees if ref == negative else degrees


class Reader:
    """The RAW reader as the engine has it: LibRaw once it's downloaded, fetched the first time a
    RAW is read or opened. While it isn't there, asking for it starts the download (again after
    a minute when the last try failed; Try again starts it at once) and raises NeedsReaderError.
    """

    def __init__(
        self,
        folder: Callable[[], Path | None],
        fetch: Callable[[], None] = lambda: None,
        broken: Callable[[], None] = lambda: None,
        *,
        notes: Path | None = None,
        retry_after: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`folder` says where LibRaw's files are once they're there; `fetch` starts getting
        them; `broken` sends one that won't load back to be fetched again. `notes` is the folder
        where each RAW LibRaw reads is noted while it does (`reading`)."""
        self._folder = folder
        self._fetch = fetch
        self._broken = broken
        self._notes = notes
        self._retry_after = retry_after
        self._clock = clock
        self._lock = threading.Lock()
        self._loaded: tuple[Path, LibRaw] | None = None
        self._asked_at: float | None = None
        self._count = itertools.count(1)

    def library(self) -> LibRaw:
        """The loaded LibRaw. Raises NeedsReaderError while it isn't there, starting to fetch
        it, or when the one there won't load, which goes back to be fetched again: a RAW waits
        for its reader rather than being blamed for it."""
        folder = self._folder()
        if folder is None or not (folder / DLL).is_file():
            self._ask()
            raise NeedsReaderError
        dll = folder / DLL
        with self._lock:
            if self._loaded is not None and self._loaded[0] == dll:
                return self._loaded[1]
            try:
                loaded = LibRaw(dll)
            except ReaderBrokenError:
                log.exception("Mado's RAW reader won't do, so it's to be fetched again")
            else:
                self._loaded = (dll, loaded)
                return loaded
        self._broken()
        self._ask()
        raise NeedsReaderError

    def ready(self) -> bool:
        """Whether LibRaw is there, without asking for it."""
        folder = self._folder()
        return folder is not None and (folder / DLL).is_file()

    def ask(self) -> None:
        """Asks for LibRaw while it isn't there, as reading a RAW would: a RAW listed while it
        waits (by an earlier Mado, or before a failed download and a restart) asks too."""
        if not self.ready():
            self._ask()

    @contextmanager
    def reading(self, path: Path) -> Generator[None]:
        """Notes the RAW LibRaw reads now in a file of its own, named for this engine's run, so
        a RAW that stops the engine outright is found as the next one starts (`stopped_on`)."""
        note: Path | None = None
        if self._notes is not None:
            note = self._notes / f"{SESSION}-{next(self._count)}.txt"
            try:
                self._notes.mkdir(parents=True, exist_ok=True)
                note.write_text(str(path), encoding="utf-8")
            except OSError:  # a note Mado can't write never stops a read
                note = None
        try:
            yield
        finally:
            if note is not None:
                note.unlink(missing_ok=True)

    def stopped_on(self) -> list[Path]:
        """The RAWs an earlier engine was reading as it stopped, by the notes it left (the
        notes go); this engine's own, reads going on now, are left."""
        found: list[Path] = []
        if self._notes is None or not self._notes.is_dir():
            return found
        for note in self._notes.glob("*.txt"):
            if note.name.startswith(f"{SESSION}-"):
                continue
            try:
                found.append(Path(note.read_text(encoding="utf-8").strip()))
                note.unlink()
            except OSError:
                log.warning("Mado couldn't read or clear its note %s", note)
        return found

    def forget_notes(self) -> None:
        """This engine's notes go as it stops cleanly: what it was reading didn't stop it."""
        if self._notes is None or not self._notes.is_dir():
            return
        for note in self._notes.glob(f"{SESSION}-*.txt"):
            note.unlink(missing_ok=True)

    def _ask(self) -> None:
        now = self._clock()
        with self._lock:
            if self._asked_at is not None and now - self._asked_at < self._retry_after:
                return
            self._asked_at = now
        try:
            self._fetch()
        except Exception:  # fetching is the tools' business: a RAW still waits, saying so
            log.exception("Mado couldn't start fetching its RAW reader")


class NeedsReaderError(Exception):
    """A camera RAW can't be read till Mado's RAW reader is there: it's on its way."""

    def __init__(self) -> None:
        super().__init__(
            "Mado is getting its camera RAW reader, a small download it fetches the first time "
            "it reads a RAW. The RAW opens once it's here."
        )
