"""Reading words at Best, its pure half: the detector's canvas, lines found in its map (turned
ones too) in reading order, each cut out straight, read 48 pixels high, and the recogniser's
answer decoded into words."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mado.core.ocr import (
    LINE_HEIGHT,
    LINE_WIDTH,
    TALLEST,
    Line,
    Placed,
    Words,
    _blobs,  # pyright: ignore[reportPrivateUsage]
    cut_out,
    decoded,
    detector_input,
    line_width,
    lines,
    on_white,
    placed,
    reading_order,
    recogniser_input,
    text_of,
    worth_keeping,
)

CANVASES = [(1280, 960), (960, 1280), (1280, 736), (736, 1280), (1280, 1280)]


def test_a_photo_a_screenshot_and_a_square_each_take_the_canvas_they_fill_most():
    assert placed(4032, 3024, CANVASES) == Placed(1280, 960, 1280 / 4032)
    assert placed(1920, 1080, CANVASES).width == 1280
    assert placed(1920, 1080, CANVASES).height == 736
    assert placed(1080, 1920, CANVASES).height == 1280
    assert (placed(2000, 2000, CANVASES).width, placed(2000, 2000, CANVASES).height) == (1280, 1280)


def test_a_small_picture_grows_at_most_twice_its_size():
    found = placed(300, 200, CANVASES)

    assert found.scale == 2.0


def test_the_detector_sees_the_picture_from_minus_one_to_one_in_its_canvas_corner():
    pixels = np.zeros((10, 20, 3), np.uint8)
    pixels[:, :, 0] = 255  # red
    tensor = detector_input(pixels, Placed(32, 32, 1.0))

    assert tensor.shape == (1, 3, 32, 32)
    assert tensor.dtype == np.float32
    # Blue, green and red, as OpenCV reads a picture and PaddleOCR's models were trained on.
    assert np.allclose(tensor[0, 2, :10, :20], 1.0)
    assert np.allclose(tensor[0, :2, :10, :20], -1.0)
    assert np.allclose(tensor[0, :, 10:, :], -1.0)  # the canvas past it is black


def test_a_line_of_one_letter_or_none_isnt_kept():
    read = [
        Words("1", 0.9),
        Words("●", 0.99),
        Words("人", 0.95),
        Words("ZUMI 73", 0.98),
        Words("in", 0.9),
    ]

    assert text_of(read) == "ZUMI 73" + chr(10) + "in"
    assert worth_keeping("P7")
    assert not worth_keeping(" · O ")


def test_a_see_through_picture_is_read_on_white():
    picture = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
    picture.putpixel((0, 0), (20, 20, 20, 255))  # a dark word's pixel

    shown = on_white(picture)

    assert shown.mode == "RGB"
    assert shown.getpixel((1, 1)) == (255, 255, 255)
    assert shown.getpixel((0, 0)) == (20, 20, 20)
    assert on_white(Image.new("L", (2, 2), 7)).getpixel((0, 0)) == (7, 7, 7)


def test_a_picture_bigger_than_its_canvas_is_refused():
    with pytest.raises(ValueError, match="bigger"):
        detector_input(np.zeros((40, 40, 3), np.uint8), Placed(32, 32, 1.0))


def _map(width: int, height: int, *boxes: tuple[float, float, float, float, float]) -> np.ndarray:
    """A made-up detector map: each box (centre x, y, width, height, turned degrees) sure text."""
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for cx, cy, w, h, degrees in boxes:
        turn = np.deg2rad(degrees)
        corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        draw.polygon(
            [
                (cx + x * np.cos(turn) - y * np.sin(turn), cy + x * np.sin(turn) + y * np.cos(turn))
                for x, y in corners
            ],
            fill=230,
        )
    return np.asarray(image, np.float32) / 255.0


def test_lines_are_found_grown_and_given_back_in_the_pictures_pixels():
    found = _map(400, 300, (100, 50, 120, 20, 0))
    canvas = Placed(400, 300, 0.5)  # the picture was 800 × 600

    [line] = lines(found, canvas, 800, 600)

    (x0, y0), (x1, _), (_, y2), _ = line.corners
    assert x0 < 2 * 40 < 2 * 160 < x1  # grown past the blob's own edges, then doubled
    assert y0 < 2 * 40
    assert y2 > 2 * 60
    assert line.score > 0.8


def test_a_turned_line_keeps_its_turn():
    found = _map(400, 300, (200, 150, 200, 24, -20))

    [line] = lines(found, Placed(400, 300, 1.0), 400, 300)

    (x0, y0), (x1, y1), _, _ = line.corners
    assert np.degrees(np.arctan2(y1 - y0, x1 - x0)) == pytest.approx(-20, abs=2)


def test_a_thin_blob_or_a_faint_one_is_no_line():
    found = np.zeros((300, 400), np.float32)
    found[50, 40:160] = 0.9  # a pixel high
    found[200:240, 100:300] = 0.35  # past the threshold, but not sure enough over its box

    assert lines(found, Placed(400, 300, 1.0), 400, 300) == []


def test_on_a_thumbnail_a_blob_as_thick_as_a_quarter_of_it_is_a_plain_sky_not_a_line():
    # The detector on a small picture takes a plain sky, or a wall, for text: lines of words on a
    # thumbnail are never so thick. In full, a big headline can be: none is left out there.
    found = _map(400, 300, (200, 60, 380, 100, 0), (200, 240, 200, 20, 0))

    [line] = lines(found, Placed(400, 300, 1.0), 400, 300, tallest=TALLEST)
    assert line.corners[0][1] > 200  # the thin line, not the sky

    assert len(lines(found, Placed(400, 300, 1.0), 400, 300)) == 2


def test_blobs_touching_at_a_corner_are_one_and_apart_are_two():
    mask = np.zeros((40, 60), bool)
    mask[5:10, 5:15] = True
    mask[10:15, 15:25] = True  # only its corner touches the first
    mask[20:30, 40:55] = True

    found = _blobs(mask)

    assert len(found) == 2
    assert sorted(len(points) for points in found) == [20, 20]  # a run's two ends a row


def test_lines_are_in_reading_order_rows_then_left_to_right():
    found = _map(600, 400, (450, 52, 100, 20, 0), (120, 50, 100, 20, 0), (300, 200, 300, 20, 0))

    found_lines = lines(found, Placed(600, 400, 1.0), 600, 400)

    middles = [round((line.corners[0][0] + line.corners[2][0]) / 2) for line in found_lines]
    assert middles == pytest.approx([120, 450, 300], abs=3)


def test_reading_order_counts_a_row_by_its_tops():
    def at(x: float, y: float) -> Line:
        return Line(((x, y), (x + 10, y), (x + 10, y + 5), (x, y + 5)), 1.0)

    ordered = reading_order([at(50, 104), at(10, 100), at(10, 140)])

    assert [line.corners[0] for line in ordered] == [(10, 100), (50, 104), (10, 140)]


def test_a_turned_line_is_cut_out_straight():
    picture = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(picture)
    corners = ((40.0, 80.0), (160.0, 40.0), (170.0, 70.0), (50.0, 110.0))
    draw.polygon(corners, fill=(200, 30, 30))

    cut = cut_out(picture, Line(corners, 1.0))

    assert cut is not None
    assert abs(cut.width - 126) <= 2
    assert abs(cut.height - 31) <= 2
    middle = np.asarray(cut, np.float32)[cut.height // 2, cut.width // 4 : 3 * cut.width // 4]
    assert np.all(middle[:, 0] > 150)
    assert np.all(middle[:, 1] < 90)


def test_a_line_far_taller_than_wide_is_turned_to_be_read():
    picture = Image.new("RGB", (100, 200), "white")
    tall = Line(((40.0, 10.0), (60.0, 10.0), (60.0, 190.0), (40.0, 190.0)), 1.0)

    cut = cut_out(picture, tall)

    assert cut is not None
    assert cut.width > cut.height


def test_a_line_with_no_height_cant_be_cut():
    flat = Line(((10.0, 10.0), (50.0, 10.0), (50.0, 10.0), (10.0, 10.0)), 1.0)

    assert cut_out(Image.new("RGB", (60, 60)), flat) is None


def test_a_line_is_read_as_wide_as_its_shape_or_at_the_width_that_holds_it():
    short = Image.new("RGB", (40, 20))
    long = Image.new("RGB", (900, 30))

    assert line_width(short) == LINE_WIDTH
    assert line_width(long) == 1440
    assert line_width(long, (320, 640, 1280)) == 1280  # the widest, squeezed
    assert line_width(Image.new("RGB", (300, 30)), (320, 640, 1280)) == 640


def test_lines_go_to_the_recogniser_48_high_their_rest_left_at_0():
    cuts = [Image.new("RGB", (96, 48), "white"), Image.new("RGB", (48, 48), "black")]

    batch = recogniser_input(cuts, 160)

    assert batch.shape == (2, 3, LINE_HEIGHT, 160)
    assert np.allclose(batch[0, :, :, :96], 1.0)
    assert np.allclose(batch[0, :, :, 96:], 0.0)
    assert np.allclose(batch[1, :, :, :48], -1.0)


def test_lines_go_to_the_recogniser_blue_green_red():
    batch = recogniser_input([Image.new("RGB", (48, 48), (255, 0, 0))], 48)

    assert np.allclose(batch[0, 2], 1.0)  # red, last
    assert np.allclose(batch[0, :2], -1.0)


def _answer(columns: list[int], classes: int = 6, sure: float = 0.9) -> np.ndarray:
    found = np.full((len(columns), classes), (1 - sure) / (classes - 1), np.float32)
    for at, index in enumerate(columns):
        found[at, index] = sure
    return found


def test_the_recognisers_answer_is_decoded_repeats_run_together_and_blanks_out():
    characters = ["a", "b", "c", "d"]  # 1 to 4; 0 is the blank, 5 the space
    answer = np.stack([_answer([1, 1, 0, 1, 2, 2, 5, 3, 0]), _answer([0, 0, 0, 0, 0, 0, 0, 0, 0])])

    first, empty = decoded(answer, characters)

    assert first.text == "aab c"
    assert first.score == pytest.approx(0.9)
    assert empty == Words("", 0.0)


def test_the_words_a_picture_shows_are_the_lines_read_surely():
    read = [Words("ZUMI  73", 0.97), Words("x?", 0.31), Words("", 0.0), Words("Harbour", 0.8)]

    assert text_of(read) == "ZUMI 73\nHarbour"
