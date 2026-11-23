"""LibRaw through its DLL, reading made-up DNGs: what a RAW says of itself, the preview its camera
kept, the picture developed with the camera's white balance into Display P3, cropped and turned as
the RAW says, and RAWs it can't read. The real LibRaw, fetched as Mado fetches it."""

import io
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageCms

from mado.core.icc import DISPLAY_P3
from mado.libraw import NeedsReaderError, RawError, Reader
from mado.tools import manifest
from tests.dng_files import BLUE, GREEN, RED, alike, card, dng, truncated
from tests.drawn import scene

_CMS: Any = ImageCms


def _srgb(image: Image.Image) -> np.ndarray:
    """A developed picture's colours in sRGB, through its own profile."""
    p3 = _CMS.ImageCmsProfile(io.BytesIO(image.info["icc_profile"]))
    turned = _CMS.profileToProfile(image, p3, _CMS.createProfile("sRGB"))
    return np.asarray(turned, np.float64)


def test_its_the_listed_version(reader: Reader) -> None:
    listed = next(item for item in manifest() if item.id == "libraw")

    assert reader.library().version == listed.version == "0.22.3"


def test_reads_what_a_raw_says_of_itself_without_developing_it(
    reader: Reader, tmp_path: Path
) -> None:
    path = dng(tmp_path / "IMG_2041.dng", scene(3, (1200, 800)), taken="2026:11:12 18:42:07")

    facts = reader.library().facts(path)

    assert (facts.width, facts.height) == (1200, 800)
    assert (facts.make, facts.model) == ("Lumen", "X100")
    assert facts.taken == datetime(2026, 11, 12, 18, 42, 7)
    assert facts.flip == 0
    assert facts.crop is None
    assert facts.latitude is None


def test_a_raw_on_its_side_says_its_size_as_shown(reader: Reader, tmp_path: Path) -> None:
    library = reader.library()
    clockwise = library.facts(dng(tmp_path / "a.dng", scene(3, (1200, 800)), orientation=6))
    anticlockwise = library.facts(dng(tmp_path / "b.dng", scene(3, (1200, 800)), orientation=8))

    assert (clockwise.width, clockwise.height, clockwise.flip) == (1200, 800, 6)
    assert (anticlockwise.width, anticlockwise.height, anticlockwise.flip) == (1200, 800, 5)
    assert clockwise.stored == (800, 1200)


def test_the_raws_own_crop_is_its_size(reader: Reader, tmp_path: Path) -> None:
    picture = scene(3, (1200, 800))
    library = reader.library()

    cropped = library.facts(dng(tmp_path / "a.dng", picture, crop=(100, 50, 1000, 700)))
    assert (cropped.width, cropped.height) == (1000, 700)
    assert cropped.crop == (100, 50, 1000, 700)


def test_the_preview_its_camera_kept(reader: Reader, tmp_path: Path) -> None:
    library = reader.library()
    picture = scene(3, (1200, 800))

    small = library.preview(dng(tmp_path / "small.dng", picture, preview=400))
    whole = library.preview(dng(tmp_path / "whole.dng", picture))
    none = library.preview(dng(tmp_path / "none.dng", picture, preview=None, thumbnail=False))

    assert small is not None
    assert (small.kind, small.size) == ("jpeg", (400, 267))
    assert whole is not None
    assert whole.size == (1200, 800)
    assert none is None


def test_developed_at_half_and_full_size_in_display_p3(reader: Reader, tmp_path: Path) -> None:
    path = dng(tmp_path / "a.dng", scene(3, (1200, 800)))
    library = reader.library()

    half = library.develop(path, half=True)
    full = library.develop(path, half=False)

    assert (half.size, full.size) == ((600, 400), (1200, 800))
    assert full.mode == "RGB"
    assert full.info["icc_profile"] == DISPLAY_P3
    assert alike(full, scene(3, (1200, 800))) > 0.95


def test_developed_with_the_cameras_white_balance(reader: Reader, tmp_path: Path) -> None:
    # The made-up sensor sees red at half green's strength: only its white balance makes grey grey.
    path = dng(tmp_path / "card.dng", card())

    pixels = _srgb(reader.library().develop(path, half=False))

    ground = pixels[200:215, 290:310].reshape(-1, 3).mean(axis=0)
    assert np.ptp(ground) < 6  # grey, not tinted
    for colour, (row, column) in ((RED, (325, 120)), (GREEN, (325, 270)), (BLUE, (325, 420))):
        found = pixels[row, column]
        assert int(np.argmax(found)) == int(np.argmax(colour))  # its own colour leads


def test_developed_upright_and_cropped_as_the_raw_says(reader: Reader, tmp_path: Path) -> None:
    picture = card((1200, 800))
    path = dng(tmp_path / "a.dng", picture, orientation=6, crop=(50, 100, 700, 1000))

    developed = reader.library().develop(path, half=False)
    half = reader.library().develop(path, half=True)

    # Stored on its side and cropped there (50 to 750 across, 100 to 1100 down): shown upright,
    # that's 100 to 1100 across and 50 to 750 down.
    assert developed.size == (1000, 700)
    assert half.size == pytest.approx((500, 350), abs=1)
    kept = picture.crop((100, 50, 1100, 750))
    assert alike(developed, kept) > 0.9
    assert alike(half, kept) > 0.9


def test_a_linear_raw_is_cropped_as_developed_whatever_size_that_is(
    reader: Reader, tmp_path: Path
) -> None:
    # Every colour in each pixel (some phones', a monochrome camera's): LibRaw develops it at its
    # full size even when asked for half, and its crop follows the size it made.
    picture = card((1200, 800))
    path = dng(tmp_path / "a.dng", picture, linear=True, crop=(100, 50, 1000, 700))
    library = reader.library()

    facts = library.facts(path)
    half = library.develop(path, half=True)

    assert (facts.width, facts.height) == (1000, 700)
    assert half.width / half.height == pytest.approx(1000 / 700, rel=0.01)
    assert alike(half, picture.crop((100, 50, 1100, 750))) > 0.9


def test_a_raw_packed_in_a_way_this_reader_cant_unpack_says_so_not_damaged(
    reader: Reader, tmp_path: Path
) -> None:
    # Deflate (an HDR merge's DNG): this build of LibRaw has no zlib to unpack it.
    path = dng(tmp_path / "merged.dng", scene(3, (600, 400)), preview=None, compression=8)

    with pytest.raises(RawError) as raised:
        reader.library().develop(path, half=True)

    assert (raised.value.problem.kind, raised.value.stage) == ("unknown", "unpack")
    assert "packed in a way the reader doesn't know yet" in str(raised.value)


def test_a_damaged_raw_says_so(reader: Reader, tmp_path: Path) -> None:
    path = truncated(dng(tmp_path / "half.dng", scene(3, (1200, 800)), preview=None))

    with pytest.raises(RawError) as raised:
        reader.library().develop(path, half=True)

    assert raised.value.problem.kind == "damaged"
    assert "only half copied" in str(raised.value)


def test_a_file_it_doesnt_know_says_so(reader: Reader, tmp_path: Path) -> None:
    path = tmp_path / "IMG_2041.nef"
    scene(3, (120, 80)).save(path, "JPEG")

    with pytest.raises(RawError) as raised:
        reader.library().facts(path)

    assert (raised.value.problem.kind, raised.value.stage) == ("unknown", "open")


def test_a_raw_in_a_folder_named_in_any_language_opens(reader: Reader, tmp_path: Path) -> None:
    path = dng(tmp_path / "東京 Café" / "写真.dng", scene(3, (600, 400)))

    facts = reader.library().facts(path)

    assert (facts.width, facts.height) == (600, 400)


def test_while_it_isnt_there_asking_fetches_it_once_a_minute() -> None:
    fetched: list[float] = []
    now = [0.0]
    reader = Reader(lambda: None, lambda: fetched.append(now[0]), clock=lambda: now[0])

    for moment in (0.0, 30.0, 61.0):
        now[0] = moment
        with pytest.raises(NeedsReaderError):
            reader.library()

    assert fetched == [0.0, 61.0]
    assert not reader.ready()


def test_one_that_wont_load_goes_back_to_be_fetched_again(tmp_path: Path) -> None:
    folder = tmp_path / "libraw"
    folder.mkdir()
    (folder / "libraw.dll").write_bytes(b"not a library at all")
    fetched: list[int] = []
    broken: list[int] = []
    reader = Reader(lambda: folder, lambda: fetched.append(1), lambda: broken.append(1))

    with pytest.raises(NeedsReaderError):
        reader.library()

    assert (broken, fetched) == ([1], [1])
