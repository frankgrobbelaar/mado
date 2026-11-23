"""Reading pictures: what each one is, and decoding it the way it's shown, for the window."""

import struct
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from mado.core.icc import DISPLAY_P3
from mado.libraw import Reader
from mado.pictures import (
    Facts,
    InUseError,
    NeedsFfmpegError,
    NeedsReaderError,
    UnreadableError,
    decode,
    read_exif,
    read_facts,
)
from tests.dng_files import alike, card, dng, truncated
from tests.drawn import draw, exif, picture, scene
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


def test_a_raws_facts_come_from_its_reader_without_developing_it(tmp_path: Path, reader: Reader):
    path = dng(tmp_path / "_MG_0042.dng", scene(3, (1200, 800)), orientation=6)

    found = read_facts(path, "raw", reader)

    assert found == Facts(
        format="DNG",
        width=1200,
        height=800,
        orientation=6,
        taken=datetime(2026, 11, 12, 18, 42, 7),
        camera="Lumen X100",
        located=False,
    )


def test_a_raw_waits_for_its_reader(tmp_path: Path):
    path = dng(tmp_path / "_MG_0042.dng", scene(3, (600, 400)))

    with pytest.raises(NeedsReaderError):
        read_facts(path, "raw")
    with pytest.raises(NeedsReaderError):
        decode(path, "raw", longest=512)


def test_a_raws_thumbnail_is_the_preview_its_camera_kept(tmp_path: Path, reader: Reader):
    picture_ = scene(3, (1200, 800))
    kept = ImageOps.invert(picture_)  # unlike the picture, to tell which was shown
    path = dng(tmp_path / "_MG_0042.dng", picture_, preview=kept)

    small = decode(path, "raw", longest=512, reader=reader)

    assert small.size == (512, 341)
    assert alike(small, kept) > 0.9 > alike(small, picture_)


def test_a_raw_on_its_side_shows_its_preview_upright(tmp_path: Path, reader: Reader):
    shown = card((1200, 800))
    path = dng(tmp_path / "_MG_0042.dng", shown, orientation=8)

    small = decode(path, "raw", longest=512, reader=reader)

    assert small.size == (512, 341)
    assert alike(small, shown) > 0.9


def test_a_raw_without_a_preview_is_developed_at_half_size(tmp_path: Path, reader: Reader):
    shown = scene(3, (1200, 800))
    path = dng(tmp_path / "_MG_0042.dng", shown, preview=None, thumbnail=False)

    small = decode(path, "raw", longest=512, reader=reader)

    assert small.size == (512, 341)
    assert small.info["icc_profile"] == DISPLAY_P3  # developed: a camera's colours stay wide
    assert alike(small, shown) > 0.95


def test_a_raws_view_is_developed_so_its_page_shows_what_save_makes(tmp_path: Path, reader: Reader):
    shown = scene(3, (1200, 800))
    path = dng(tmp_path / "_MG_0042.dng", shown, preview=ImageOps.invert(shown))

    view = decode(path, "raw", longest=2560, reader=reader)

    assert view.size == (1200, 800)
    assert alike(view, shown) > 0.95  # the picture developed, not its camera's preview


def test_a_raw_at_full_size_is_developed_upright_and_cropped(tmp_path: Path, reader: Reader):
    path = dng(
        tmp_path / "_MG_0042.dng", card((1200, 800)), orientation=6, crop=(50, 100, 700, 1000)
    )

    whole = decode(path, "raw", longest=None, reader=reader)

    assert whole.size == (1000, 700)
    assert whole.mode == "RGB"
    assert whole.info["icc_profile"] == DISPLAY_P3


def test_a_damaged_raw_reads_its_facts_but_wont_develop(tmp_path: Path, reader: Reader):
    path = truncated(dng(tmp_path / "_MG_0042.dng", scene(3, (1200, 800)), preview=None))

    assert read_facts(path, "raw", reader).width == 1200  # what it says of itself is all there
    with pytest.raises(UnreadableError, match="only half copied"):
        decode(path, "raw", longest=None, reader=reader)


def test_a_file_named_as_a_raw_that_isnt_one_wont_open(tmp_path: Path, reader: Reader):
    path = tmp_path / "_MG_0042.NEF"
    picture().save(path, "JPEG")

    with pytest.raises(UnreadableError, match="doesn't know"):
        read_facts(path, "raw", reader)


def test_a_raw_open_in_another_app_says_so(tmp_path: Path, reader: Reader):
    path = dng(tmp_path / "_MG_0042.dng", scene(3, (600, 400)))

    # Another app writing to it (sharing reads and writes, as most do): LibRaw, which opens a
    # file sharing only reads, can't, and that's no damage of the RAW's. Nothing is written.
    with path.open("r+b"):
        with pytest.raises(InUseError, match="open in another app"):
            read_facts(path, "raw", reader)
        with pytest.raises(InUseError, match="open in another app"):
            decode(path, "raw", longest=512, reader=reader)
    assert read_facts(path, "raw", reader).width == 600


def test_while_libraw_reads_a_raw_a_note_says_which_and_goes_after(
    tmp_path: Path, libraw_folder: Path, monkeypatch: pytest.MonkeyPatch
):
    notes = tmp_path / "Mado" / "reading-raw"
    reader = Reader(lambda: libraw_folder, notes=notes)
    path = dng(tmp_path / "_MG_0042.dng", scene(3, (600, 400)))
    library = reader.library()
    noted: list[str] = []
    read = library.develop

    def develop(at: Path, *, half: bool) -> Image.Image:  # LibRaw at work on it
        noted.extend(note.read_text(encoding="utf-8") for note in notes.glob("*.txt"))
        return read(at, half=half)

    monkeypatch.setattr(library, "develop", develop)
    decode(path, "raw", longest=None, reader=reader)

    assert noted == [str(path)]  # an engine it stopped would leave this for the next to find
    assert list(notes.glob("*.txt")) == []


def test_a_raw_whose_cameras_preview_is_damaged_is_developed_instead(
    tmp_path: Path, reader: Reader
):
    shown = scene(3, (1200, 800))
    path = dng(tmp_path / "_MG_0042.dng", shown, preview_cut=0.5)

    small = decode(path, "raw", longest=512, reader=reader)

    assert small.size == (512, 341)
    assert small.info["icc_profile"] == DISPLAY_P3  # developed
    assert alike(small, shown) > 0.95


def test_a_raws_date_and_camera_go_with_the_pictures_made_from_it(tmp_path: Path, reader: Reader):
    path = dng(tmp_path / "_MG_0042.dng", scene(3, (600, 400)))

    found = read_exif(path, "raw", reader)

    assert found is not None
    assert (found[0x010F], found[0x0110]) == ("Lumen", "X100")
    assert found.get_ifd(0x8769)[0x9003] == "2026:11:12 18:42:07"


def _in_use(*_args: object, **_options: object) -> None:
    raise PermissionError(13, "The process cannot access the file", "Pier.jpg", 32)


def test_a_picture_open_in_another_app_says_so_rather_than_that_its_damaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = draw(tmp_path / "Pier.jpg")
    monkeypatch.setattr(Image, "open", _in_use)

    with pytest.raises(UnreadableError, match="open in another app"):
        decode(path, "picture", longest=None)
    with pytest.raises(UnreadableError, match="open in another app"):
        read_facts(path, "picture")
