"""Mado's own Display P3 profile: what it calls itself, and its colours as Little CMS reads them."""

import io
import struct
from typing import Any

import pytest
from PIL import Image, ImageCms

from mado.core.icc import DISPLAY_P3, display_p3

_CMS: Any = ImageCms


def _to_srgb(colour: tuple[int, int, int]) -> tuple[int, ...]:
    picture = Image.new("RGB", (1, 1), colour)
    p3 = _CMS.ImageCmsProfile(io.BytesIO(DISPLAY_P3))
    turned = _CMS.profileToProfile(picture, p3, _CMS.createProfile("sRGB"))
    return turned.getpixel((0, 0))


def _colourant(tag: bytes) -> tuple[float, ...]:
    data = display_p3()
    count = struct.unpack(">I", data[128:132])[0]
    for at in range(count):
        signature, offset, size = struct.unpack(">4sII", data[132 + 12 * at : 144 + 12 * at])
        if signature == tag:
            found = data[offset : offset + size]
            return tuple(value / 65536 for value in struct.unpack(">3i", found[8:20]))
    raise AssertionError(f"no {tag!r}")


def test_it_calls_itself_display_p3() -> None:
    profile = _CMS.ImageCmsProfile(io.BytesIO(DISPLAY_P3))
    assert _CMS.getProfileDescription(profile).strip() == "Display P3"
    assert profile.profile.xcolor_space == "RGB "


def test_srgbs_red_written_in_display_p3_comes_back_as_srgbs_red() -> None:
    red, green, blue = _to_srgb((234, 51, 35))
    assert red >= 252
    assert green <= 6
    assert blue <= 6


def test_greys_stay_grey_on_srgbs_curve() -> None:
    assert _to_srgb((128, 128, 128)) == (128, 128, 128)
    assert _to_srgb((255, 255, 255)) == (255, 255, 255)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [(b"rXYZ", (0.5151, 0.2412, -0.0010)), (b"gXYZ", (0.2920, 0.6922, 0.0419))],
)
def test_its_primaries_are_display_p3s_seen_in_d50(
    tag: bytes, expected: tuple[float, float, float]
) -> None:
    assert _colourant(tag) == pytest.approx(expected, abs=0.001)
