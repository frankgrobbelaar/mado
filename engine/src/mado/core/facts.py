"""What a picture's EXIF says about it, in Mado's words: when it was taken, which camera took it,
which way up it goes and whether it carries a location. mado/pictures.py reads the EXIF."""

from collections.abc import Mapping
from datetime import datetime

_FIRST_YEAR = 1826  # the oldest surviving photograph: anything before is a clock never set
_SIDEWAYS = frozenset({5, 6, 7, 8})  # orientations that turn a picture a quarter round
_GPS_LATITUDE, _GPS_LONGITUDE = 2, 4


def taken(written: str | None) -> datetime | None:
    """When a picture was taken, from EXIF's "2026:11:12 18:42:07": local time on the camera's
    clock, as it was set. None when there's no date, or it isn't one (a clock never set writes
    zeros)."""
    if not written:
        return None
    text = written.strip("\x00 ")
    if len(text) < 19:
        return None
    date, time = text[:10].replace("-", ":"), text[11:19]
    try:
        moment = datetime.strptime(f"{date} {time}", "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return moment if moment.year >= _FIRST_YEAR else None


def camera(make: str | None, model: str | None) -> str | None:
    """The camera, by its maker and model: "Pixelworks PW-7 Pro". A model that names its maker
    already ("Lumen X100") isn't given the maker twice."""
    maker = (make or "").replace("\x00", " ").strip()
    name = (model or "").replace("\x00", " ").strip()
    if not name:
        return maker or None
    if not maker or name.split()[0].casefold() == maker.split()[0].casefold():
        return name
    return f"{maker} {name}"


def shown_size(width: int, height: int, orientation: int | None) -> tuple[int, int]:
    """A picture's size as it's shown: taller than wide when its orientation turns it on its
    side."""
    return (height, width) if orientation in _SIDEWAYS else (width, height)


def located(gps: Mapping[int, object]) -> bool:
    """Whether a picture's GPS says where it was taken: a latitude and a longitude both."""
    return bool(gps.get(_GPS_LATITUDE)) and bool(gps.get(_GPS_LONGITUDE))
