"""Reading pictures: what each one is, and decoding it the way it's shown, for the window."""

import struct
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from mado.pictures import NeedsFfmpegError, UnreadableError, decode, read_facts
from tests.drawn import draw, exif, picture
from tests.heif_files import exif_item, heif

FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]


def test_a_cameras_jpeg_says_when_where_and_with_what_it_was_taken(tmp_path: Path):
    described = exif(
        taken="2026:11:12 18:42:07", make="Pixelworks", model="PW-7 Pro", orientation=6, where=True
    )
    path = draw(tmp_path / "IMG_2041.JPG", size=(64, 48), described=described)

    facts = read_facts(path, "picture")

    assert facts.format == "JPEG"
    assert (facts.width, facts.height) == (48, 64)  # turned on its side to be shown
    assert facts.orientation == 6
    assert facts.taken == datetime(2026, 11, 12, 18, 42, 7)
    assert facts.camera == "Pixelworks PW-7 Pro"
    assert facts.located


def test_a_picture_without_exif_says_nothing_it_doesnt_know(tmp_path: Path):
    facts = read_facts(draw(tmp_path / "Screenshot.png", size=(80, 60)), "picture")

    assert (facts.format, facts.width, facts.height) == ("PNG", 80, 60)
    assert facts.taken is None
    assert facts.camera is None
    assert facts.orientation is None
    assert not facts.located


def test_a_clock_never_set_isnt_when_a_picture_was_taken(tmp_path: Path):
    path = draw(tmp_path / "IMG.jpg", described=exif(taken="0000:00:00 00:00:00"))

    assert read_facts(path, "picture").taken is None


def test_damaged_exif_leaves_the_picture_readable_with_what_could_be_read(tmp_path: Path):
    data = bytearray(exif(make="Pixelworks", where=True).tobytes())
    order = "<" if bytes(data[6:8]) == b"II" else ">"
    pointer = data.find(struct.pack(f"{order}HHI", 0x8825, 4, 1), 6)  # where its GPS is
    data[pointer + 8 : pointer + 12] = struct.pack(f"{order}I", 0x7FFF0000)  # far past the end
    path = tmp_path / "IMG.jpg"
    picture((40, 30)).save(path, exif=bytes(data))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # Pillow says the EXIF is corrupt
        facts = read_facts(path, "picture")

    assert (facts.width, facts.camera, facts.located) == (40, "Pixelworks", False)


@pytest.mark.parametrize(
    ("name", "named"),
    [
        ("a.png", "PNG"),
        ("a.webp", "WebP"),
        ("a.avif", "AVIF"),
        ("a.tif", "TIFF"),
        ("a.bmp", "BMP"),
        ("a.gif", "GIF"),
        ("a.jpeg", "JPEG"),
    ],
)
def test_every_format_pillow_knows_is_read_and_named(tmp_path: Path, name: str, named: str):
    facts = read_facts(draw(tmp_path / name, size=(40, 30)), "picture")

    assert (facts.format, facts.width, facts.height) == (named, 40, 30)


def test_a_file_that_isnt_a_picture_wont_open(tmp_path: Path):
    path = tmp_path / "IMG_2041.jpg"
    path.write_text("not a picture at all", encoding="utf-8")

    with pytest.raises(UnreadableError, match="not a picture"):
        read_facts(path, "picture")


def test_a_picture_whose_parts_inflate_past_pillows_limits_wont_open(tmp_path: Path):
    path = tmp_path / "huge profile.png"
    picture((8, 8)).save(path, icc_profile=bytes(2 << 20))  # 2 MB of profile, a few KB packed

    with pytest.raises(UnreadableError, match="damaged"):
        read_facts(path, "picture")


def test_a_half_copied_picture_reads_its_facts_but_wont_decode(tmp_path: Path):
    whole = draw(tmp_path / "whole.jpg", size=(400, 300))
    half = tmp_path / "Old pier.jpg"
    half.write_bytes(whole.read_bytes()[: whole.stat().st_size // 2])

    assert read_facts(half, "picture").width == 400
    with pytest.raises(UnreadableError, match="damaged or was only half copied"):
        decode(half, "picture", longest=None)


def test_a_picture_is_decoded_the_way_its_shown_and_no_bigger_than_asked(tmp_path: Path):
    turned = draw(tmp_path / "turned.jpg", size=(64, 48), described=exif(orientation=6))
    large = draw(tmp_path / "large.png", size=(400, 300))

    assert decode(turned, "picture", longest=None).size == (48, 64)
    assert decode(large, "picture", longest=100).size == (100, 75)
    assert decode(large, "picture", longest=1000).size == (400, 300)  # never made bigger


def test_a_jpeg_too_big_for_the_screen_is_decoded_at_a_smaller_scale_first(tmp_path: Path):
    large = draw(tmp_path / "large.jpg", size=(2000, 1500))

    assert decode(large, "picture", longest=256).size == (256, 192)


@pytest.mark.parametrize(
    ("mode", "shown"),
    [("I;16", "L"), ("P", "RGB"), ("CMYK", "RGB"), ("LA", "RGBA"), ("1", "L"), ("RGBA", "RGBA")],
)
def test_every_kind_of_pixel_is_decoded_to_one_the_window_shows(
    tmp_path: Path, mode: str, shown: str
):
    path = tmp_path / ("p.tif" if mode in ("I;16", "CMYK", "1") else "p.png")
    image = (
        picture((40, 30)).convert("L").convert(mode) if mode == "I;16" else picture((40, 30), mode)
    )
    image.save(path)

    assert decode(path, "picture", longest=None).mode == shown


def test_a_sixteen_bit_picture_keeps_its_light_and_dark(tmp_path: Path):
    path = tmp_path / "scan.png"
    Image.new("I;16", (8, 8), 40000).save(path)

    [(count, value)] = decode(path, "picture", longest=None).getcolors() or []

    assert (count, value) == (64, 40000 // 256)


def test_a_transparent_gif_keeps_its_see_through_parts(tmp_path: Path):
    path = tmp_path / "sticker.gif"
    image = Image.new("P", (10, 10), 0)
    image.putpalette([0, 0, 0, 255, 0, 0])
    image.info["transparency"] = 0
    image.save(path, transparency=0)

    decoded = decode(path, "picture", longest=None)

    assert decoded.mode == "RGBA"
    assert decoded.getpixel((0, 0)) == (0, 0, 0, 0)


def test_a_heifs_facts_come_from_its_layout_and_exif_without_ffmpeg(tmp_path: Path):
    described = exif(taken="2026:11:12 18:42:07", make="Pixelworks", model="PW-7 Pro", where=True)
    path = tmp_path / "IMG_2041.HEIC"
    path.write_bytes(
        heif(width=4032, height=3024, transforms=((b"irot", 3),), exif=exif_item(described))
    )

    facts = read_facts(path, "heif")

    assert facts.format == "HEIC"
    assert (facts.width, facts.height) == (3024, 4032)
    assert facts.orientation == 6
    assert facts.taken == datetime(2026, 11, 12, 18, 42, 7)
    assert facts.camera == "Pixelworks PW-7 Pro"
    assert facts.located


def test_a_heif_keeping_its_exif_inside_its_layout_is_read_too(tmp_path: Path):
    path = tmp_path / "burst.heif"
    path.write_bytes(heif(exif=exif_item(exif(taken="2026:11:13 09:12:00")), exif_in_meta=True))

    facts = read_facts(path, "heif")

    assert facts.format == "HEIF"
    assert facts.taken == datetime(2026, 11, 13, 9, 12)


def test_a_heif_without_exif_still_says_its_size(tmp_path: Path):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif(width=640, height=480))

    facts = read_facts(path, "heif")

    assert (facts.width, facts.height, facts.taken, facts.camera) == (640, 480, None, None)


def test_a_file_named_heic_that_isnt_one_wont_open(tmp_path: Path):
    path = tmp_path / "IMG.heic"
    path.write_bytes(b"\x00\x00\x00\x10ftypheic" + b"\x00" * 4)

    with pytest.raises(UnreadableError):
        read_facts(path, "heif")


def test_a_heif_is_decoded_by_ffmpeg_then_turned_the_way_its_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif(width=640, height=480, transforms=((b"irot", 3),)))
    monkeypatch.setenv("MADO_FAKE_SIZE", "640x480")

    assert decode(path, "heif", longest=None, ffmpeg=FFMPEG).size == (480, 640)
    assert decode(path, "heif", longest=320, ffmpeg=FFMPEG).size == (240, 320)


def test_a_heif_needs_ffmpeg_to_be_decoded(tmp_path: Path):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif())

    with pytest.raises(NeedsFfmpegError):
        decode(path, "heif", longest=512, ffmpeg=None)


def test_a_heif_ffmpeg_cant_decode_wont_open_and_says_what_ffmpeg_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif())
    monkeypatch.setenv("MADO_FAKE_FAIL", "1")

    with pytest.raises(UnreadableError, match="Invalid data found"):
        decode(path, "heif", longest=512, ffmpeg=FFMPEG)


def test_a_heif_ffmpeg_gives_only_a_part_of_isnt_shown_as_the_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif(width=4032, height=3024))
    monkeypatch.setenv("MADO_FAKE_SIZE", "512x512")  # one tile of the grid

    with pytest.raises(UnreadableError, match="only part"):
        decode(path, "heif", longest=None, ffmpeg=FFMPEG)


def test_camera_raw_isnt_decoded_yet(tmp_path: Path):
    path = tmp_path / "_MG_0042.CR3"
    path.write_bytes(b"raw")

    with pytest.raises(UnreadableError, match="RAW"):
        decode(path, "raw", longest=512)
