"""Gain maps: what Adobe's XMP, ISO 21496-1's numbers and Apple's headroom say, the values as
gains in stops, and what Mado's tools do to them."""

import numpy as np
import pytest

from mado.core.gainmap import (
    ISO_VERSIONS,
    Channel,
    GainMapError,
    Info,
    alternate,
    apple_gains,
    apple_headroom,
    apple_info,
    apple_xmp_headroom,
    container_length,
    encoded_of,
    filled,
    from_iso,
    from_xmp,
    gain_map_xmp,
    gains_of,
    iso_numbers,
    iso_version_only,
    primary_xmp,
    scaled,
    single,
    size_for,
    stops_between,
    turned,
    weight,
    xmp_version,
)

ONE = Info(channels=(Channel(0.0, 3.0, 1.0, 1 / 64, 1 / 64),), base_headroom=0.0,
           alternate_headroom=3.0)  # fmt: skip
COLOUR = Info(
    channels=(
        Channel(-0.5, 3.0, 1.0, 0.01, 0.02),
        Channel(0.0, 2.5, 1.2, 0.015, 0.015),
        Channel(0.25, 2.0, 0.8, 0.02, 0.01),
    ),
    base_headroom=0.0,
    alternate_headroom=3.0,
    base_colours=False,
)


def phone_xmp(fields: str, prefix: str = "hdrgm") -> bytes:
    """An Ultra HDR gain map's XMP as a phone might write it, `fields` inside its description."""
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description '
        f'xmlns:{prefix}="http://ns.adobe.com/hdr-gain-map/1.0/" {fields}</rdf:Description>'
        "</rdf:RDF></x:xmpmeta>"
    ).encode()


class TestAdobesXmp:
    def test_a_phones_gain_map_numbers(self) -> None:
        packet = phone_xmp(
            'hdrgm:Version="1.0" hdrgm:GainMapMin="0" hdrgm:GainMapMax="3.5" hdrgm:Gamma="1"'
            ' hdrgm:OffsetSDR="0" hdrgm:OffsetHDR="0" hdrgm:HDRCapacityMin="0"'
            ' hdrgm:HDRCapacityMax="3.5" hdrgm:BaseRenditionIsHDR="False">'
        )
        info = from_xmp(packet)
        assert info == Info((Channel(0.0, 3.5, 1.0, 0.0, 0.0),), 0.0, 3.5)
        assert info is not None
        assert not info.base_is_hdr
        assert info.stops == 3.5

    def test_what_it_leaves_out_is_adobes_default(self) -> None:
        info = from_xmp(phone_xmp('hdrgm:GainMapMax="2" hdrgm:HDRCapacityMax="2">'))
        assert info == Info((Channel(0.0, 2.0, 1.0, 1 / 64, 1 / 64),), 0.0, 2.0)

    def test_elements_and_a_colour_gain_maps_lists(self) -> None:
        packet = phone_xmp(
            'hdrgm:Version="1.0">'
            "<hdrgm:GainMapMin><rdf:Seq><rdf:li>-0.5</rdf:li><rdf:li>0</rdf:li>"
            "<rdf:li>0.25</rdf:li></rdf:Seq></hdrgm:GainMapMin>"
            "<hdrgm:GainMapMax><rdf:Seq><rdf:li>3</rdf:li><rdf:li>2.5</rdf:li>"
            "<rdf:li>2</rdf:li></rdf:Seq></hdrgm:GainMapMax>"
            "<hdrgm:HDRCapacityMax>3</hdrgm:HDRCapacityMax>"
        )
        info = from_xmp(packet)
        assert info is not None
        assert info.colour
        assert [c.low for c in info.channels] == [-0.5, 0.0, 0.25]
        assert [c.high for c in info.channels] == [3.0, 2.5, 2.0]

    def test_any_prefix_bound_to_the_namespace(self) -> None:
        packet = phone_xmp('g:GainMapMax="2" g:HDRCapacityMax="2.5">', prefix="g")
        info = from_xmp(packet)
        assert info is not None
        assert info.channels[0].high == 2.0
        assert info.stops == 2.5

    def test_a_primarys_names_only_its_version(self) -> None:
        packet = primary_xmp(1234)
        assert xmp_version(packet) == "1.0"
        assert from_xmp(packet) is None
        assert container_length(packet) == 1234

    def test_no_namespace_is_no_gain_map(self) -> None:
        assert xmp_version(b"<x:xmpmeta/>") is None
        assert from_xmp(b"<x:xmpmeta/>") is None
        assert container_length(b"<x:xmpmeta/>") is None

    def test_a_version_it_doesnt_know(self) -> None:
        packet = phone_xmp('hdrgm:Version="2.0" hdrgm:GainMapMax="2" hdrgm:HDRCapacityMax="2">')
        with pytest.raises(GainMapError, match=r"version 2.0"):
            from_xmp(packet)

    def test_numbers_that_arent(self) -> None:
        with pytest.raises(GainMapError, match="not a number"):
            from_xmp(phone_xmp('hdrgm:GainMapMax="lots" hdrgm:HDRCapacityMax="2">'))
        with pytest.raises(GainMapError, match="most gain is less"):
            from_xmp(
                phone_xmp('hdrgm:GainMapMin="3" hdrgm:GainMapMax="1" hdrgm:HDRCapacityMax="2">')
            )

    def test_an_hdr_base_is_the_hdr_rendition_with_its_own_offset(self) -> None:
        packet = phone_xmp(
            'hdrgm:GainMapMin="-3" hdrgm:GainMapMax="0" hdrgm:OffsetSDR="0.01"'
            ' hdrgm:OffsetHDR="0.02" hdrgm:HDRCapacityMin="0" hdrgm:HDRCapacityMax="3"'
            ' hdrgm:BaseRenditionIsHDR="True">'
        )
        info = from_xmp(packet)
        assert info is not None
        assert info.base_is_hdr
        assert (info.base_headroom, info.alternate_headroom) == (3.0, 0.0)
        assert info.channels[0].base_offset == 0.02  # the HDR rendition's
        assert info.channels[0].alternate_offset == 0.01

    @pytest.mark.parametrize("info", [ONE, COLOUR, Info((Channel(-3, 0, 1, 0.02, 0.01),), 3, 0)])
    def test_mados_own_reads_back_the_same(self, info: Info) -> None:
        found = from_xmp(gain_map_xmp(info))
        assert found is not None
        assert found.base_headroom == pytest.approx(info.base_headroom)
        assert found.alternate_headroom == pytest.approx(info.alternate_headroom)
        for got, want in zip(found.channels, info.channels, strict=True):
            assert got.low == pytest.approx(want.low, abs=1e-6)
            assert got.high == pytest.approx(want.high, abs=1e-6)
            assert got.gamma == pytest.approx(want.gamma, abs=1e-6)
            assert got.base_offset == pytest.approx(want.base_offset, abs=1e-6)
            assert got.alternate_offset == pytest.approx(want.alternate_offset, abs=1e-6)

    def test_apples_headroom_in_its_xmp(self) -> None:
        packet = (
            b'<x:xmpmeta><rdf:Description xmlns:HDRGainMap="http://ns.apple.com/HDRGainMap/1.0/"'
            b' HDRGainMap:HDRGainMapVersion="65536" HDRGainMap:HDRGainMapHeadroom="3.2"/>'
            b"</x:xmpmeta>"
        )
        assert apple_xmp_headroom(packet) == 3.2
        assert apple_xmp_headroom(b"<x:xmpmeta/>") is None


class TestIso:
    @pytest.mark.parametrize("info", [ONE, COLOUR, Info((Channel(-3, 0, 1, 0.02, 0.01),), 3, 0)])
    def test_mados_own_numbers_read_back_the_same(self, info: Info) -> None:
        found = from_iso(iso_numbers(info))
        assert found.base_colours == info.base_colours
        assert found.colour == info.colour
        assert found.base_headroom == pytest.approx(info.base_headroom)
        assert found.alternate_headroom == pytest.approx(info.alternate_headroom)
        for got, want in zip(found.channels, info.channels, strict=True):
            assert got.low == pytest.approx(want.low, abs=1e-6)
            assert got.high == pytest.approx(want.high, abs=1e-6)
            assert got.gamma == pytest.approx(want.gamma, abs=1e-6)

    def test_the_layout_iso_21496_1_gives(self) -> None:
        data = iso_numbers(ONE)
        assert data[:4] == b"\x00\x00\x00\x00"  # minimum and writer version
        assert data[4] == 0x40  # one channel, in the base's colours
        assert len(data) == 5 + 2 * 8 + 5 * 8
        assert int.from_bytes(data[13:17], "big") == 3_000_000  # the alternate headroom, 3
        assert int.from_bytes(data[17:21], "big") == 1_000_000
        assert iso_numbers(COLOUR)[4] == 0x80  # three channels, in the HDR rendition's colours

    def test_numbers_over_one_shared_denominator(self) -> None:
        # flags: one channel, base colours, a common denominator; then it, and numerators alone
        numbers = [8, 0, 24, 0, 24, 8, 0, 0]  # headrooms, then low, high, gamma, offsets
        data = (
            b"\x00\x00\x00\x00"
            + bytes([0x48])
            + b"".join(each.to_bytes(4, "big", signed=True) for each in numbers)
        )
        info = from_iso(data)
        assert info.base_headroom == 0.0
        assert info.alternate_headroom == 3.0
        assert info.channels[0] == Channel(0.0, 3.0, 1.0, 0.0, 0.0)

    def test_a_base_pictures_versions_alone(self) -> None:
        assert iso_version_only(ISO_VERSIONS)
        assert not iso_version_only(iso_numbers(ONE))

    def test_a_version_it_doesnt_know(self) -> None:
        with pytest.raises(GainMapError, match="version 1"):
            from_iso(b"\x00\x01\x00\x01" + iso_numbers(ONE)[4:])

    def test_made_backwards_isnt_kept(self) -> None:
        data = bytearray(iso_numbers(ONE))
        data[4] |= 0x04
        with pytest.raises(GainMapError, match="backwards"):
            from_iso(bytes(data))

    def test_cut_short_or_dividing_by_nought(self) -> None:
        with pytest.raises(GainMapError, match="cut short"):
            from_iso(iso_numbers(ONE)[:30])
        data = bytearray(iso_numbers(ONE))
        data[9:13] = bytes(4)  # the base headroom's denominator
        with pytest.raises(GainMapError, match="nought"):
            from_iso(bytes(data))


class TestApple:
    @pytest.mark.parametrize(
        ("maker33", "maker48", "stops"),
        [
            (0.5, 0.005, -20 * 0.005 + 1.8),
            (0.5, 0.5, -0.101 * 0.5 + 1.601),
            (1.2, 0.005, -70 * 0.005 + 3.0),
            (1.2, 0.5, -0.303 * 0.5 + 2.303),
            (1.2, 9.0, 0.0),  # never less than none
        ],
    )
    def test_its_makernotes_headroom(self, maker33: float, maker48: float, stops: float) -> None:
        assert apple_headroom(maker33, maker48) == pytest.approx(2.0**stops)

    def test_none_without_its_tags(self) -> None:
        assert apple_headroom(None, 0.5) is None

    def test_its_linear_values_as_stops(self) -> None:
        encoded = np.array([[0, 255, 188]], np.uint8)  # 188 is about half, off sRGB's curve
        found = apple_gains(encoded, 4.0)
        assert found[0, 0] == pytest.approx(0.0)
        assert found[0, 1] == pytest.approx(2.0)  # all the headroom: four times brighter
        linear = ((188 / 255 + 0.055) / 1.055) ** 2.4
        assert found[0, 2] == pytest.approx(np.log2(1 + 3 * linear), abs=1e-5)
        info = apple_info(4.0)
        assert info.stops == pytest.approx(2.0)
        assert not info.base_is_hdr


class TestValues:
    def test_a_grey_gain_maps_values_as_stops(self) -> None:
        encoded = np.array([[0, 128, 255]], np.uint8)
        found = gains_of(encoded, ONE)
        assert found.shape == (1, 3)
        assert found.tolist()[0] == pytest.approx([0.0, 3.0 * 128 / 255, 3.0], abs=1e-6)

    def test_the_curve(self) -> None:
        curved = Info((Channel(0.0, 2.0, 2.0, 0.0, 0.0),), 0.0, 2.0)
        found = gains_of(np.array([[64]], np.uint8), curved)
        assert found[0, 0] == pytest.approx(2.0 * (64 / 255) ** 0.5, abs=1e-6)

    def test_a_colour_gain_map_each_by_its_own(self) -> None:
        encoded = np.full((2, 2, 3), 255, np.uint8)
        found = gains_of(encoded, COLOUR)
        assert found.shape == (2, 2, 3)
        assert found[0, 0].tolist() == pytest.approx([3.0, 2.5, 2.0])

    def test_written_and_read_again_within_a_step(self) -> None:
        rng = np.random.default_rng(4)
        gains = rng.uniform(-0.3, 2.7, (40, 30)).astype(np.float32)
        values, info = encoded_of(gains, ONE)
        assert values.dtype == np.uint8
        assert values.shape == (40, 30)
        assert info.channels[0].low == pytest.approx(float(gains.min()), abs=1e-6)
        assert info.channels[0].high == pytest.approx(float(gains.max()), abs=1e-6)
        assert info.alternate_headroom == 3.0  # the photo's headroom, kept
        step = (info.channels[0].high - info.channels[0].low) / 255
        assert np.abs(gains_of(values, info) - gains).max() <= step / 2 + 1e-6

    def test_flat_gains_still_span_a_little(self) -> None:
        values, info = encoded_of(np.zeros((4, 4), np.float32), ONE)
        assert info.channels[0].high > info.channels[0].low
        assert np.abs(gains_of(values, info)).max() < 0.01

    def test_colour_gains_written_a_channel_each(self) -> None:
        gains = np.stack([np.full((3, 3), v, np.float32) for v in (0.5, 1.0, 2.0)], axis=2)
        values, info = encoded_of(gains, COLOUR)
        assert values.shape == (3, 3, 3)
        assert info.colour
        assert np.allclose(gains_of(values, info), gains, atol=0.01)


class TestRenditions:
    def test_the_weight_by_a_screens_headroom(self) -> None:
        assert weight(ONE, 0.0) == 0.0  # an ordinary screen: the base
        assert weight(ONE, 1.5) == 0.5
        assert weight(ONE, 4.0) == 1.0
        hdr_base = Info((Channel(0, 3, 1, 0, 0),), 3.0, 0.0)
        assert weight(hdr_base, 0.0) == 1.0  # an ordinary screen: all the gain, dividing by it
        assert weight(hdr_base, 3.0) == 0.0

    def test_the_hdr_rendition_and_back(self) -> None:
        base = np.full((2, 2, 3), 0.25, np.float32)
        gains = np.full((2, 2), 2.0, np.float32)
        info = Info((Channel(0, 3, 1, 0, 0),), 0.0, 3.0)
        hdr = alternate(base, gains, info)
        assert np.allclose(hdr, 1.0)  # four times brighter
        assert np.allclose(stops_between(base, hdr, info, colour=False), 2.0)
        assert np.allclose(alternate(base, gains, info, 0.5), 0.5)

    def test_an_hdr_base_is_made_ordinary_by_dividing_by_its_gains(self) -> None:
        # Gains always say how much brighter the HDR rendition is than the ordinary one, as ISO
        # 21496-1 and Chromium have them: an HDR base's ordinary rendition divides by them. Edge
        # drew a grey HDR base with gains of -1 twice as bright on an ordinary screen.
        base = np.full((2, 2, 3), 0.5, np.float32)
        gains = np.full((2, 2), 1.0, np.float32)
        info = Info((Channel(0, 3, 1, 0, 0),), 3.0, 0.0)
        ordinary = alternate(base, gains, info)
        assert np.allclose(ordinary, 0.25)  # half as bright
        assert np.allclose(stops_between(base, ordinary, info, colour=False), 1.0)
        darker = Info((Channel(-1, 0, 1, 0, 0),), 1.0, 0.0)
        assert np.allclose(alternate(base, -np.ones((2, 2), np.float32), darker), 1.0)


class TestTools:
    def test_one_channel_by_each_colours_share_of_light(self) -> None:
        gains = np.zeros((2, 2, 3), np.float32)
        gains[..., 1] = 2.0
        found = single(gains)
        assert found.shape == (2, 2)
        assert np.allclose(found, 2.0 * 0.7152)
        grey = np.ones((2, 2), np.float32)
        assert single(grey) is grey

    def test_scaled_toward_none(self) -> None:
        gains = np.full((2, 2), 2.0, np.float32)
        assert np.allclose(scaled(gains, 0.25), 0.5)
        place = np.array([[0.0, 1.0], [0.5, 1.0]], np.float32)
        assert scaled(gains, place).tolist() == [[0.0, 2.0], [1.0, 2.0]]

    def test_a_hole_filled_from_round_it(self) -> None:
        gains = np.zeros((32, 32), np.float32)
        gains[:, 16:] = 2.0
        gains[12:20, 4:12] = 3.0  # a bright lamp, erased
        hole = np.zeros((32, 32), np.float32)
        hole[10:22, 2:14] = 1.0
        found = filled(gains, hole)
        assert np.abs(found[12:20, 4:10]).max() < 0.6  # the lamp's gain gone: the wall's taken
        assert np.array_equal(found[hole == 0], gains[hole == 0])  # the rest as it was

    def test_a_colour_hole_filled_too(self) -> None:
        gains = np.ones((16, 16, 3), np.float32)
        gains[4:8, 4:8] = 5.0
        hole = np.zeros((16, 16), np.float32)
        hole[3:9, 3:9] = 1.0
        assert np.allclose(filled(gains, hole)[5, 5], 1.0, atol=0.05)

    def test_the_size_kept_beside_a_picture(self) -> None:
        assert size_for((7680, 4320), (0.25, 0.25), 4096) == (1920, 1080)
        assert size_for((8064, 6048), (1.0, 1.0), 4096) == (4096, 3072)  # at most 4096 across
        assert size_for((3, 2), (0.25, 0.25), 4096) == (1, 1)

    @pytest.mark.parametrize("orientation", range(1, 9))
    def test_turned_as_its_picture_is(self, orientation: int) -> None:
        from PIL import Image, ImageOps

        stored = np.arange(12, dtype=np.float32).reshape(3, 4)
        picture = Image.fromarray(stored.astype(np.uint8))
        exif = picture.getexif()
        exif[0x0112] = orientation
        picture.info["exif"] = exif.tobytes()
        upright = np.asarray(ImageOps.exif_transpose(picture)).astype(np.float32)
        assert np.array_equal(turned(stored, orientation), upright)
