"""What Mado's tools do to an HDR photo's gain map: sized with the picture, erased parts filled,
a cut-out's ground none or blurred, a pencil sketch fading it, a look making it one channel."""

import numpy as np
import pytest

from mado.core.edits import Blur, CutOut, Erase, Subject
from mado.core.framing import frame
from mado.core.gainmap import Channel, GainMap, Info
from mado.core.gains import MOST, edited, flat, looked, painted, restored, sized
from mado.core.painting import CLASSICS, PAINTERS, Painting

INFO = Info((Channel(0.0, 3.0),), 0.0, 3.0)


def gain_map(width: int, height: int, *, spot: tuple[int, int] | None = None) -> GainMap:
    """A gain map with none anywhere but a bright square (three stops) at `spot`."""
    gains = np.zeros((height, width), np.float32)
    if spot is not None:
        x, y = spot
        gains[y : y + 4, x : x + 4] = 3.0
    return GainMap(gains, INFO)


class TestSized:
    def test_kept_at_its_share_of_the_picture_made(self) -> None:
        gain = gain_map(100, 75)  # a quarter of a 400 × 300 picture
        made = sized(gain, frame(400, 300, 400, 300, "crop"), (400, 300), (1600, 1200))
        assert made.size == (400, 300)  # a quarter of 1600 × 1200

    def test_full_size_stays_full_size_up_to_its_most(self) -> None:
        gain = gain_map(400, 300)
        made = sized(gain, frame(400, 300, 400, 300, "crop"), (400, 300), (8000, 6000))
        assert made.size == (MOST, round(MOST * 0.75))

    def test_cropped_with_the_picture(self) -> None:
        # The right half kept: the bright square at the gain map's right edge stays at its edge.
        gain = gain_map(100, 50, spot=(92, 20))
        cropped = frame(400, 200, 200, 200, "crop", (1.0, 0.5))
        made = sized(gain, cropped, (400, 200), (200, 200))
        assert made.size == (50, 50)
        assert made.gains[:, -8:].max() > 2.0  # the square, at the right
        assert made.gains[:, :30].max() < 0.1  # the rest none

    def test_its_edges_carried_on_when_extended(self) -> None:
        gain = GainMap(np.full((50, 50), 1.5, np.float32), INFO)
        extended = frame(200, 200, 400, 200, "extend")
        made = sized(gain, extended, (200, 200), (400, 200))
        assert made.size == (100, 50)
        assert np.allclose(made.gains, 1.5, atol=1e-4)  # the new edges as the old

    def test_a_colour_gain_map_keeps_its_colours(self) -> None:
        gains = np.stack([np.full((30, 40), v, np.float32) for v in (1.0, 2.0, 3.0)], axis=2)
        made = sized(
            GainMap(gains, INFO), frame(160, 120, 160, 120, "crop"), (160, 120), (320, 240)
        )
        assert made.gains.shape == (60, 80, 3)
        assert made.gains[10, 10].tolist() == pytest.approx([1.0, 2.0, 3.0], abs=1e-4)


class TestEdited:
    def test_an_erased_lamps_gain_is_filled_from_round_it(self) -> None:
        gain = GainMap(np.full((40, 40), 0.5, np.float32), INFO)
        gain.gains[10:14, 10:14] = 3.0  # the lamp
        hole = np.zeros((160, 160), np.uint8)
        hole[30:70, 30:70] = 255  # erased, at the picture's size
        made = edited(gain, [(Erase(), hole)])
        assert made is not None
        assert made.gains[10:14, 10:14].max() == pytest.approx(0.5, abs=0.05)

    def test_a_cut_out_on_a_colour_has_none_behind_it(self) -> None:
        gain = GainMap(np.full((40, 40), 2.0, np.float32), INFO)
        subject = np.zeros((40, 40), np.uint8)
        subject[10:30, 10:30] = 255
        made = edited(gain, [(CutOut((), behind="colour"), subject)])
        assert made is not None
        assert made.gains[20, 20] == pytest.approx(2.0)  # the subject keeps its gain
        assert made.gains[2, 2] == 0.0  # the colour behind it: the same on any screen

    def test_a_cut_out_on_nothing_keeps_no_hdr(self) -> None:
        gain = gain_map(40, 40)
        assert edited(gain, [(Subject(behind="nothing"), np.zeros((40, 40), np.uint8))]) is None

    def test_whats_behind_blurred_the_part_kept(self) -> None:
        # A quarter-size gain map of a 3200 × 2400 photo: the lens blur is 0.6% of its short side.
        gains = np.zeros((600, 800), np.float32)
        gains[::6, ::6] = 3.0  # little lights all over
        gain = GainMap(gains, INFO)
        part = np.zeros((600, 800), np.uint8)
        part[200:400, 300:500] = 255
        made = edited(gain, [(Blur(()), part)])
        assert made is not None
        inner = (slice(220, 380), slice(320, 480))
        assert np.array_equal(made.gains[inner], gains[inner])  # the part as it was
        assert made.gains[:150, :150].max() < 1.0  # the lights behind it blurred out
        assert made.gains[:150, :150].mean() == pytest.approx(gains[:150, :150].mean(), abs=0.02)


class TestPaintedAndLooked:
    def test_a_painter_keeps_the_gain_map(self) -> None:
        gain = gain_map(20, 20, spot=(5, 5))
        assert painted(gain, Painting(PAINTERS[0])) is gain
        oil = next(each for each in CLASSICS if each.id == "oil")
        assert painted(gain, Painting(oil)) is gain

    def test_a_pencil_sketch_fades_it_with_its_strength(self) -> None:
        gain = gain_map(20, 20, spot=(5, 5))
        pencil = next(each for each in CLASSICS if each.id == "pencil")
        made = painted(gain, Painting(pencil, strength=0.4))
        assert made is not None
        assert made.gains.max() == pytest.approx(3.0 * 0.6)
        assert painted(gain, Painting(pencil, strength=1.0)) is None  # paper: no light left

    def test_a_look_makes_a_colour_gain_map_one_channel(self) -> None:
        gains = np.stack([np.full((4, 4), v, np.float32) for v in (1.0, 2.0, 3.0)], axis=2)
        made = looked(GainMap(gains, INFO))
        assert made.gains.shape == (4, 4)
        assert made.gains[0, 0] == pytest.approx(0.2126 + 2 * 0.7152 + 3 * 0.0722)

    def test_flat_is_no_hdr(self) -> None:
        assert flat(gain_map(4, 4))
        assert not flat(gain_map(8, 8, spot=(1, 1)))


class TestRestored:
    def test_a_filled_scratchs_gain_is_filled_from_round_it(self) -> None:
        # A white scratch on a photographed print glows on an HDR screen; filled, it mustn't.
        gain = GainMap(np.full((40, 40), 0.5, np.float32), INFO)
        gain.gains[:, 20:22] = 3.0  # the scratch, top to bottom
        scratch = np.zeros((160, 160), np.uint8)
        scratch[:, 76:92] = 255  # what restoring filled, at the picture's size
        made = restored(gain, scratch, recoloured=False)
        assert made.gains[:, 20:22].max() == pytest.approx(0.5, abs=0.05)
        assert made.gains[5, 5] == pytest.approx(0.5)

    def test_colour_brought_in_or_back_keeps_it_one_channel_as_a_look_does(self) -> None:
        gains = np.stack([np.full((4, 4), v, np.float32) for v in (1.0, 2.0, 3.0)], axis=2)
        made = restored(GainMap(gains, INFO), None, recoloured=True)
        assert made.gains.shape == (4, 4)
        grey = gain_map(8, 8, spot=(1, 1))
        assert np.array_equal(restored(grey, None, recoloured=True).gains, grey.gains)
