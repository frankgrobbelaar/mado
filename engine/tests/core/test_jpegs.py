"""A JPEG's pieces: its segments, the XMP, ISO 21496-1 and MPF an Ultra HDR JPEG keeps, and an
Ultra HDR JPEG put together, read back by Mado and by Pillow's own MPO reader."""

import io

import numpy as np
import pytest
from PIL import Image
from PIL.MpoImagePlugin import MpoImageFile

from mado.core.gainmap import (
    Channel,
    Info,
    container_length,
    from_iso,
    from_xmp,
    iso_version_only,
    xmp_version,
)
from mado.core.jpegs import (
    JpegError,
    head,
    segment,
    segments,
    ultra_hdr,
    with_segments,
    without_hdr,
)
from tests.drawn import picture

INFO = Info((Channel(0.0, 2.5, 1.0, 1 / 64, 1 / 64),), 0.0, 2.5)


def jpeg(image: Image.Image, **options: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90, **options)
    return out.getvalue()


def gain_map(size: tuple[int, int]) -> bytes:
    values = np.tile(np.linspace(0, 255, size[0], dtype=np.uint8), (size[1], 1))
    return jpeg(Image.fromarray(values, "L"))


def test_its_segments_up_to_its_picture() -> None:
    data = jpeg(picture((64, 48)))
    found = list(segments(data))
    assert found[-1].marker == 0xDA  # the start of scan, last
    assert all(each.end <= len(data) for each in found)


def test_not_a_jpeg() -> None:
    with pytest.raises(JpegError, match="doesn't start"):
        list(segments(b"\x89PNG\r\n\x1a\n"))


def test_an_ordinary_jpeg_has_no_parts() -> None:
    found = head(jpeg(picture((64, 48))))
    assert found.xmp is None
    assert found.iso is None
    assert found.parts == ()
    assert found.whole


def test_a_head_cut_short_says_so() -> None:
    data = jpeg(picture((64, 48)), exif=Image.Exif().tobytes(), icc_profile=bytes(3000))
    assert not head(data[:200]).whole


class TestUltraHdr:
    def made(self, **options: object) -> tuple[bytes, bytes, bytes]:
        first = jpeg(picture((160, 120)), **options)
        second = gain_map((40, 30))
        return ultra_hdr(first, second, INFO), first, second

    def test_pillows_mpo_reader_finds_both_pictures(self) -> None:
        data, _first, second = self.made()
        with Image.open(io.BytesIO(data)) as plain:
            assert plain.format == "JPEG"  # Pillow opens Ultra HDR as its picture alone
        # Its MPO reader, asked directly, reads the MPF as Mado wrote it.
        with MpoImageFile(io.BytesIO(data)) as opened:
            assert getattr(opened, "n_frames", 1) == 2
            assert opened.size == (160, 120)
            opened.seek(1)
            assert opened.size == (40, 30)
            assert opened.mode == "L"
            with Image.open(io.BytesIO(second)) as alone:
                assert np.array_equal(np.asarray(opened), np.asarray(alone))

    def test_mados_reader_finds_the_gain_map_and_its_numbers(self) -> None:
        data, _first, _second = self.made()
        primary = head(data)
        assert primary.xmp is not None
        assert xmp_version(primary.xmp) == "1.0"
        assert primary.iso is not None
        assert iso_version_only(primary.iso)
        assert len(primary.parts) == 2
        found = primary.parts[1]
        assert data[found.start : found.start + 2] == b"\xff\xd8"
        assert found.start + found.length == len(data)  # right after the picture
        assert container_length(primary.xmp) == found.length
        assert primary.parts[0].length == found.start  # the picture is all before it
        own = head(data[found.start :])
        assert own.xmp is not None
        assert own.iso is not None
        assert from_xmp(own.xmp) == INFO
        assert from_iso(own.iso) == INFO

    def test_the_picture_keeps_its_exif_and_colours(self) -> None:
        exif = Image.Exif()
        exif[0x010F] = "Lumen"
        profile = b"made-up colour profile, as Pillow only carries it"
        data, _first, _second = self.made(exif=exif.tobytes(), icc_profile=profile)
        with Image.open(io.BytesIO(data)) as opened:
            assert opened.getexif()[0x010F] == "Lumen"
            assert opened.info.get("icc_profile") == profile
        found = list(segments(data))
        assert found[0].marker in (0xE0, 0xE1)  # JFIF or EXIF first, as they were

    def test_an_old_gain_maps_own_pieces_go(self) -> None:
        once, _first, _second = self.made()
        again = ultra_hdr(once[: head(once).parts[1].start], gain_map((40, 30)), INFO)
        assert len(head(again).parts) == 2
        xmps = [
            each
            for each in segments(again)
            if again[each.payload].startswith(b"http://ns.adobe.com/xap/1.0/\x00")
        ]
        assert len(xmps) == 1


def test_segments_go_after_the_apps() -> None:
    data = jpeg(picture((32, 24)), exif=Image.Exif().tobytes())
    added = with_segments(data, segment(0xE2, b"made-up piece"))
    markers = [each.marker for each in segments(added)]
    assert markers.index(0xE2) < markers.index(0xDB)  # before the tables
    assert markers[0] in (0xE0, 0xE1)
    assert without_hdr(added) == added  # not an HDR piece: kept


def test_a_segment_too_big() -> None:
    with pytest.raises(JpegError, match="too big"):
        segment(0xE1, bytes(70000))
