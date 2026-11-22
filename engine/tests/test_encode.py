"""Saving a picture Mado made: its formats, what it keeps of its original, and the check before
it's kept."""

import errno
import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageCms

from mado.core.quality import Format
from mado.encode import SaveError, check, in_srgb, prepared_exif, profile_name, save
from tests.drawn import EXIF_IFD, GPS_IFD, ORIENTATION, TAKEN, exif, picture

ORIGINAL = exif(taken="2026:11:12 18:42:07", make="Pixelworks", model="PW-7", orientation=6,
                where=True)  # fmt: skip


CMS: Any = ImageCms  # partly unknown to Pyright, as in mado/pictures.py


def _p3() -> bytes:
    """A made-up profile to carry over: Pillow's own Lab one."""
    return CMS.ImageCmsProfile(CMS.createProfile("LAB")).tobytes()


@pytest.mark.parametrize("format_", ["JPEG", "PNG", "WebP", "AVIF"])
def test_each_format_saves_and_checks(tmp_path: Path, format_: Format):
    target = tmp_path / f"made.{format_.lower()}"

    save(picture((96, 64)), target, format_, 90, exif=None, profile=None, dpi=None)

    check(target, (96, 64))
    with Image.open(target) as written:
        assert written.format == {"WebP": "WEBP"}.get(format_, format_)


def test_see_through_parts_saved_as_jpeg_are_white_not_what_was_hidden(tmp_path: Path):
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))  # hidden black, all see-through
    image.paste((200, 30, 30, 255), (8, 8, 24, 24))
    target = tmp_path / "made.jpg"

    save(image, target, "JPEG", 95, exif=None, profile=None, dpi=None)

    with Image.open(target) as written:
        assert written.mode == "RGB"
        corner = written.getpixel((1, 1))
        middle = written.getpixel((16, 16))
    assert isinstance(corner, tuple)
    assert min(corner) >= 250
    assert isinstance(middle, tuple)
    assert middle[0] > 180 > middle[1]


def test_the_date_and_camera_come_over_upright_with_the_new_size_and_no_location():
    made = prepared_exif(ORIGINAL, keep_camera=True, keep_location=False, size=(7680, 4320),
                         dpi=None)  # fmt: skip

    assert made is not None
    assert made[ORIENTATION] == 1
    assert made.get_ifd(EXIF_IFD)[TAKEN] == "2026:11:12 18:42:07"
    assert made[0x010F] == "Pixelworks"
    assert not made.get_ifd(GPS_IFD)


def test_the_location_comes_over_only_when_kept_and_nothing_when_the_camera_isnt():
    kept = prepared_exif(ORIGINAL, keep_camera=True, keep_location=True, size=(10, 10), dpi=300)

    assert kept is not None
    assert kept.get_ifd(GPS_IFD)
    assert kept[0x011A] == 300.0  # a print's resolution
    assert prepared_exif(ORIGINAL, keep_camera=False, keep_location=True, size=(1, 1),
                         dpi=None) is None  # fmt: skip


def test_the_exif_and_profile_are_written_with_the_picture(tmp_path: Path):
    target = tmp_path / "made.jpg"
    made = prepared_exif(ORIGINAL, keep_camera=True, keep_location=False, size=(96, 64), dpi=300)
    profile = _p3()

    save(picture((96, 64)), target, "JPEG", 95, exif=made, profile=profile, dpi=300)

    with Image.open(target) as written:
        read = written.getexif()
        assert read.get_ifd(EXIF_IFD)[TAKEN] == "2026:11:12 18:42:07"
        assert not read.get_ifd(GPS_IFD)
        assert written.info.get("icc_profile") == profile
        assert written.info.get("dpi") == pytest.approx((300, 300))


def test_colours_not_kept_are_turned_into_srgb_not_stripped():
    wide: bytes = CMS.ImageCmsProfile(CMS.createProfile("sRGB")).tobytes()

    turned = in_srgb(picture((8, 8)), wide)

    assert turned.size == (8, 8)
    assert profile_name(wide) is not None
    assert profile_name(None) is None


def test_a_picture_that_came_out_wrong_is_never_kept(tmp_path: Path):
    target = tmp_path / "made.jpg"
    save(picture((96, 64)), target, "JPEG", 90, exif=None, profile=None, dpi=None)

    with pytest.raises(SaveError, match="came out 96 × 64, not 100 × 64"):
        check(target, (100, 64))
    target.write_bytes(target.read_bytes()[:200])
    with pytest.raises(SaveError, match="didn't come out whole"):
        check(target, (96, 64))


def test_a_folder_it_cant_write_to_says_so(tmp_path: Path):
    with pytest.raises(SaveError, match="couldn't write"):
        save(picture(), tmp_path / "missing" / "made.png", "PNG", None, exif=None, profile=None,
             dpi=None)  # fmt: skip


def test_exif_read_back_through_bytes_is_whole():
    written = io.BytesIO()
    picture().save(written, format="JPEG", exif=ORIGINAL)
    with Image.open(written) as again:
        assert again.getexif()[ORIENTATION] == 6


def test_a_full_drive_says_so_and_is_told_apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def full(*_args: object, **_options: object) -> None:
        raise OSError(errno.ENOSPC, "There is not enough space on the disk")

    monkeypatch.setattr(Image.Image, "save", full)

    with pytest.raises(SaveError) as raised:
        save(picture(), tmp_path / "made.png", "PNG", None, exif=None, profile=None, dpi=None)

    assert raised.value.full
