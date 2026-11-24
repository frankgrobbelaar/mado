"""HDR photos on the PC: whether a picture carries a gain map Mado reads, and the gain map itself,
turned the way its picture is shown, from made-up HDR photos written by code."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mado import hdr
from mado.core.gainmap import Channel, Info
from mado.core.heif import Property
from mado.core.heif_writer import Entry, heif_file
from mado.core.jpegs import head, ultra_hdr
from tests.conftest import FFMPEG
from tests.hdr_files import (
    INFO,
    avif_hdr,
    damaged_avif,
    gains_for,
    heic_with_gain_map,
    iso_only_jpeg,
    jpeg,
    phone_style,
    scene,
    ultra_hdr_jpeg,
)


def written(tmp_path: Path, data: bytes, name: str = "Harbour at dusk.jpg") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def read(path: Path, tmp_path: Path) -> hdr.GainMap | None:
    return hdr.read(path, ffmpeg=FFMPEG, scratch=tmp_path / "scratch")


class TestJpeg:
    def test_an_ultra_hdr_jpeg(self, tmp_path: Path) -> None:
        found = hdr.facts(written(tmp_path, ultra_hdr_jpeg((320, 240))))
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.alternate_headroom == 3.0
        assert found.size == (80, 60)  # a quarter of the picture's size

    def test_its_gain_map_as_stops(self, tmp_path: Path) -> None:
        path = written(tmp_path, ultra_hdr_jpeg((320, 240)))
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.size == (80, 60)
        want = gains_for(scene((320, 240)), 0.25, 3.0)
        assert np.abs(gain.gains - want).mean() < 0.05  # a JPEG's few steps off
        assert gain.gains.max() > 2.5  # the sun goes most of three stops brighter

    def test_a_gain_map_at_full_size(self, tmp_path: Path) -> None:
        path = written(tmp_path, ultra_hdr_jpeg((320, 240), fraction=1.0))
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.size == (320, 240)

    def test_turned_as_its_picture_is(self, tmp_path: Path) -> None:
        path = written(tmp_path, ultra_hdr_jpeg((320, 240), orientation=6))
        with Image.open(path) as opened:
            assert opened.size == (240, 320)  # stored on its side
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.size == (80, 60)  # upright, as the picture is shown
        want = gains_for(scene((320, 240)), 0.25, 3.0)
        assert np.abs(gain.gains - want).mean() < 0.05

    def test_a_colour_gain_map(self, tmp_path: Path) -> None:
        gain = read(written(tmp_path, ultra_hdr_jpeg(colour=True)), tmp_path)
        assert gain is not None
        assert gain.gains.shape == (60, 80, 3)
        assert gain.info.colour
        red, blue = gain.gains[..., 0].max(), gain.gains[..., 2].max()
        assert blue == pytest.approx(red * 0.5, abs=0.1)

    def test_found_by_its_xmp_alone(self, tmp_path: Path) -> None:
        # No MPF and no ISO numbers: the XMP's directory says how long its gain map is.
        path = written(tmp_path, ultra_hdr_jpeg(pieces=("xmp",)))
        found = hdr.facts(path)
        assert found.state == "hdr"
        assert read(path, tmp_path) is not None

    def test_found_by_iso_and_mpf_alone(self, tmp_path: Path) -> None:
        path = written(tmp_path, iso_only_jpeg())
        found = hdr.facts(path)
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.alternate_headroom == 3.0

    def test_a_phones_own_xmp(self, tmp_path: Path) -> None:
        xmp = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Made-up phone 1.0"><rdf:RDF xmlns:rdf'
            b'="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about=""'
            b' xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/" hdrgm:Version="1.0"'
            b' hdrgm:GainMapMin="0" hdrgm:GainMapMax="2.3" hdrgm:Gamma="1" hdrgm:OffsetSDR="0"'
            b' hdrgm:OffsetHDR="0" hdrgm:HDRCapacityMin="0" hdrgm:HDRCapacityMax="2.3"'
            b' hdrgm:BaseRenditionIsHDR="False"/></rdf:RDF></x:xmpmeta>'
        )
        path = written(tmp_path, phone_style(ultra_hdr_jpeg(), xmp))
        found = hdr.facts(path)
        assert found.info == Info((Channel(0.0, 2.3, 1.0, 0.0, 0.0),), 0.0, 2.3)

    def test_a_version_mado_doesnt_know(self, tmp_path: Path) -> None:
        path = written(tmp_path, ultra_hdr_jpeg(version="2.0", pieces=("xmp",)))
        found = hdr.facts(path)
        assert found.state == "unreadable"
        assert found.why == "is version 2.0, which Mado doesn't know yet"
        assert read(path, tmp_path) is None  # shown and saved as it is

    def test_found_by_its_xmp_where_its_mpf_is_wrong(self, tmp_path: Path) -> None:
        # Its MPF's second offset points into the gain map's middle; its XMP's directory doesn't.
        data = bytearray(ultra_hdr_jpeg())
        tiff = data.index(b"MPF\x00") + 4
        at = tiff + 74  # the second entry's start (Mado's MPF: big-endian, entries at 50)
        offset = int.from_bytes(data[at : at + 4], "big")
        data[at : at + 4] = (offset + 9).to_bytes(4, "big")
        path = written(tmp_path, bytes(data))
        assert hdr.facts(path).state == "hdr"
        assert read(path, tmp_path) is not None

    def test_a_gain_map_that_says_nothing_of_how_much_brighter(self, tmp_path: Path) -> None:
        picture = scene()
        data = ultra_hdr(jpeg(picture), jpeg(Image.new("L", (80, 60), 128)), None)
        found = hdr.facts(written(tmp_path, data))
        assert found.state == "unreadable"
        assert found.why == "doesn't say how much brighter it goes"

    def test_an_ordinary_jpeg_and_png(self, tmp_path: Path) -> None:
        assert hdr.facts(written(tmp_path, jpeg(scene()))).state == "none"
        png = tmp_path / "Still lake.png"
        scene().save(png)
        assert hdr.facts(png) == hdr.NONE
        assert hdr.facts(tmp_path / "gone.jpg") == hdr.NONE

    def test_a_gain_map_cut_off(self, tmp_path: Path) -> None:
        data = ultra_hdr_jpeg()
        path = written(tmp_path, data[: len(data) - 300])
        found = hdr.facts(path)
        assert found.state == "hdr"  # its numbers are whole: it's its pixels that aren't
        assert read(path, tmp_path) is None  # so it's kept as an ordinary picture

    def test_a_gain_map_claiming_billions_of_pixels(self, tmp_path: Path) -> None:
        # Its frame header says 65535 × 65535, which Pillow refuses as a decompression bomb.
        data = bytearray(ultra_hdr_jpeg())
        start = head(bytes(data)).parts[1].start
        frame = data.index(b"\xff\xc0", start)
        data[frame + 5 : frame + 9] = b"\xff\xff\xff\xff"
        path = written(tmp_path, bytes(data))
        assert hdr.facts(path).state == "hdr"
        assert read(path, tmp_path) is None


class TestHeic:
    def test_apples_gain_map_with_its_headroom_in_xmp(self, tmp_path: Path) -> None:
        path = written(tmp_path, heic_with_gain_map("apple", headroom=4.0), "IMG_2041.HEIC")
        found = hdr.facts(path)
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.stops == pytest.approx(2.0)
        assert found.size == (160, 120)
        gain = read(path, tmp_path)
        assert gain is not None
        want = gains_for(scene((320, 240)), 0.5, 2.0)
        assert np.abs(gain.gains - want).mean() < 0.06

    def test_apples_headroom_in_its_makernote(self, tmp_path: Path) -> None:
        data = heic_with_gain_map("apple", xmp_headroom=False, makernote=(1.2, 0.5))
        found = hdr.facts(written(tmp_path, data, "IMG_2042.HEIC"))
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.stops == pytest.approx(-0.303 * 0.5 + 2.303, abs=1e-4)

    def test_apples_without_a_headroom(self, tmp_path: Path) -> None:
        data = heic_with_gain_map("apple", xmp_headroom=False)
        found = hdr.facts(written(tmp_path, data, "IMG_2043.HEIC"))
        assert found.state == "unreadable"
        assert found.why == "doesn't say how much brighter it goes"

    def test_iso_21496_1s_tmap(self, tmp_path: Path) -> None:
        path = written(tmp_path, heic_with_gain_map("iso"), "IMG_2044.HEIC")
        found = hdr.facts(path)
        assert found.state == "hdr"
        assert found.info is not None
        assert found.info.alternate_headroom == 3.0
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.size == (160, 120)

    def test_turned_as_its_picture(self, tmp_path: Path) -> None:
        # The picture turned a quarter clockwise (irot 3); the gain map, with no turn of its own,
        # turns with it.
        path = written(tmp_path, heic_with_gain_map("apple", picture_turn=3), "IMG_2045.HEIC")
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.size == (120, 160)

    def test_its_own_turn_first(self, tmp_path: Path) -> None:
        data = heic_with_gain_map("iso", picture_turn=3, gain_turn=1)
        gain = read(written(tmp_path, data, "IMG_2046.HEIC"), tmp_path)
        assert gain is not None
        assert gain.size == (120, 160)  # a quarter round either way: on its side

    def test_hevc_through_ffmpeg_from_mados_own_folder(self, tmp_path: Path) -> None:
        # A HEVC gain map goes to ffmpeg in a file of Mado's own, gone once it's decoded.
        data = heic_with_gain_map("apple")
        made = bytearray(data)
        heic = bytes(made).replace(b"av01", b"hvc1")  # ffmpeg (the tests' stand-in) decodes it
        path = written(tmp_path, heic, "IMG_2047.HEIC")
        gain = read(path, tmp_path)
        assert gain is not None
        assert gain.gains.shape == (48, 64)  # what the stand-in draws
        assert not any((tmp_path / "scratch").iterdir())

    def test_hevc_that_ffmpeg_gives_only_part_of(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One tile of a grid, say: not the gain map's shape, so not laid over the whole picture.
        monkeypatch.setenv("MADO_FAKE_SIZE", "64x16")
        heic = heic_with_gain_map("apple").replace(b"av01", b"hvc1")
        path = written(tmp_path, heic, "IMG_2049.HEIC")
        assert hdr.facts(path).state == "hdr"
        assert read(path, tmp_path) is None
        assert not any((tmp_path / "scratch").iterdir())

    def test_a_heic_without_one(self, tmp_path: Path) -> None:
        props = (
            Property(b"ispe", bytes(4) + (64).to_bytes(4, "big") + (48).to_bytes(4, "big"), False),
        )
        plain = heif_file(
            (b"heic", (b"mif1", b"heic")), 1, [Entry(1, b"hvc1", False, props, b"x")], {}, ()
        )
        assert hdr.facts(written(tmp_path, plain, "IMG_2048.HEIC")) == hdr.NONE


def test_an_avif_with_a_gain_map(tmp_path: Path) -> None:
    path = written(tmp_path, avif_hdr((320, 240)), "Night market.avif")
    found = hdr.facts(path)
    assert found.state == "hdr"
    assert found.info is not None
    assert found.info.stops == pytest.approx(INFO.alternate_headroom, abs=1e-5)
    assert not found.info.base_is_hdr
    gain = read(path, tmp_path)
    assert gain is not None
    assert gain.size == (80, 60)
    want = gains_for(scene((320, 240)), 0.25, 3.0)
    assert np.abs(gain.gains - want).mean() < 0.06
    assert INFO.alternate_headroom == gain.info.alternate_headroom


def test_an_avif_whose_gain_map_wont_decode_is_an_ordinary_picture(tmp_path: Path) -> None:
    path = written(tmp_path, damaged_avif(), "Night market.avif")
    assert hdr.facts(path).state == "hdr"  # its numbers read: it's its pixels that don't
    assert read(path, tmp_path) is None


def test_a_huge_photos_full_size_gain_map_is_read_no_bigger_than_any_copy_kept(tmp_path: Path):
    path = written(tmp_path, ultra_hdr_jpeg((4400, 300), fraction=1.0), "Panorama.jpg")
    assert hdr.facts(path).size == (4400, 300)
    gain = read(path, tmp_path)
    assert gain is not None
    assert max(gain.size) <= 4096  # smooth: kept as every copy of it is
