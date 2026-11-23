"""Masks by their maths: parts together and apart, strokes drawn, edges grown and softened,
masks following the picture's edges, outlines, and how much detail a place has."""

import numpy as np

from mado.core.masks import (
    Brush,
    area,
    bounds,
    box,
    detail,
    feathered,
    grown,
    guided,
    guided_coefficients,
    outline,
    path,
    square_around,
    stroked,
    together,
    without,
)


def _disc(size: tuple[int, int], middle: tuple[float, float], radius: float) -> np.ndarray:
    width, height = size
    ys, xs = np.mgrid[0:height, 0:width]
    inside = (xs + 0.5 - middle[0]) ** 2 + (ys + 0.5 - middle[1]) ** 2 <= radius**2
    return (inside * 255).astype(np.uint8)


def test_parts_go_together_and_one_can_be_taken_out_of_another():
    sun = _disc((100, 80), (30, 30), 10)
    sail = _disc((100, 80), (70, 40), 12)

    both = together([sun, sail], (80, 100))

    assert area(both) == area(sun) + area(sail)
    assert area(without(both, sail)) == area(sun)
    assert together([], (4, 5)).shape == (4, 5)


def test_a_box_mean_keeps_flat_places_flat_and_counts_the_edges_again():
    values = np.zeros((20, 30), np.float32)
    values[:, 15:] = 1.0

    mean = box(values, 3)

    assert np.allclose(mean[:, :10], 0)
    assert np.allclose(mean[:, 20:], 1)
    assert np.isclose(mean[0, 15], 4 / 7)  # three columns before it, itself and three after
    assert np.allclose(box(values, 0), values)


def test_an_edge_feathered_fades_and_a_grown_mask_reaches_further_out():
    sail = _disc((120, 120), (60, 60), 20)

    soft = feathered(sail, 8)
    wider = grown(sail, 5)

    assert soft[60, 60] == 255
    assert soft[0, 0] == 0
    edge = soft[60, 75:85]
    assert (np.diff(edge.astype(int)) <= 0).all()
    assert 0 < edge[3] < 255
    assert area(wider) > area(sail)
    assert wider[60, 60 + 20 + 4] == 255
    assert sail[60, 60 + 20 + 4] == 0
    assert grown(sail, 0)[60, 60] == 255


def test_bounds_and_the_square_an_erase_is_drawn_in_stays_inside_the_picture():
    hole = np.zeros((300, 400), np.uint8)
    hole[100:140, 350:390] = 255

    found = bounds(hole)

    assert found is not None
    assert found == (350, 100, 390, 140)
    assert bounds(np.zeros((5, 5), np.uint8)) is None
    x0, y0, x1, y1 = square_around(found, (400, 300), least=128, margin=0.5)
    assert x1 - x0 == y1 - y0 == 128
    assert x0 >= 0
    assert x1 <= 400
    assert y0 >= 0
    assert y1 <= 300
    assert x0 <= 350
    assert x1 >= 390
    # A square bigger than a side keeps that side whole.
    assert square_around(found, (400, 300), least=512, margin=0.25) == (0, 0, 400, 300)


def test_strokes_paint_in_order_and_alt_takes_away_what_was_painted():
    line = Brush(((10.0, 50.0), (90.0, 50.0)), width=10)
    rubbed = Brush(((50.0, 50.0),), width=20, take=True)
    again = Brush(((50.0, 50.0),), width=4)

    painted = stroked([line], (100, 100))
    taken = stroked([line, rubbed], (100, 100))
    back = stroked([line, rubbed, again], (100, 100))

    assert painted[50, 20] == 255
    assert painted[40, 20] == 0
    assert painted[50, 50] == 255
    assert taken[50, 50] == 0
    assert taken[50, 20] == 255
    assert back[50, 50] == 255
    tapped = stroked([Brush(((5.0, 5.0),), width=6)], (20, 20))
    assert tapped[5, 5] == 255
    assert tapped[5, 12] == 0


def test_a_soft_mask_guided_by_the_picture_snaps_to_its_edge():
    # A sail on a sky, its edge at x = 40; the mask's edge was blurred over 16 pixels.
    guide = np.zeros((64, 80, 3), np.float32)
    guide[..., 2] = 0.9
    guide[:, 40:, :] = (0.95, 0.95, 0.9)
    truth = np.zeros((64, 80), np.float32)
    truth[:, 40:] = 1.0
    blurry = np.clip((np.arange(80, dtype=np.float32) - 32) / 16, 0, 1)[None, :].repeat(64, 0)
    blurry = blurry.astype(np.float32)

    slope, offset = guided_coefficients(guide, blurry, radius=6, eps=1e-4)
    snapped = guided(guide, slope, offset)

    rises = np.diff(snapped[32])
    assert int(np.argmax(rises)) == 39  # the step is where the picture's edge is
    assert rises.max() > 5 * np.diff(blurry[32]).max()
    assert np.abs((snapped >= 0.5) - truth).mean() == 0


def test_a_filled_place_without_grain_has_less_detail_than_the_grain_round_it():
    rng = np.random.default_rng(4)
    grey = (0.5 + rng.normal(0, 0.05, (60, 60))).astype(np.float32)
    grey[20:40, 20:40] = 0.5
    hole = np.zeros((60, 60), bool)
    hole[20:40, 20:40] = True

    assert detail(grey, hole) < detail(grey, ~hole) / 5
    assert detail(grey[:2, :2], hole[:2, :2]) == 0.0


def test_an_outline_goes_round_each_piece_and_round_a_hole_in_one():
    ring = _disc((40, 40), (20, 20), 15) > 0
    ring &= ~(_disc((40, 40), (20, 20), 6) > 0)
    dot = np.zeros((40, 40), bool)
    dot[2, 2] = True

    lines = outline(ring)

    assert len(lines) == 2  # outside and the hole
    outer = max(lines, key=len)
    xs = [x for x, _y in outer]
    assert min(xs) < 6
    assert max(xs) > 33
    assert all(line[0] == line[-1] for line in lines)  # closed
    single = outline(dot)
    assert len(single) == 1
    assert {round(x, 1) for x, _y in single[0]} <= {1.5, 2.0, 2.5}


def test_an_outline_is_a_path_in_a_frame_a_thousand_across_and_down():
    whole = np.ones((10, 20), bool)

    drawn = path(outline(whole), (20, 10))

    assert drawn.startswith("M")
    assert drawn.endswith("Z")
    numbers = [
        float(n) for n in drawn.replace("M", " ").replace("L", " ").replace("Z", " ").split()
    ]
    assert min(numbers) == 0
    assert max(numbers) == 1000
    assert path([], (20, 10)) == ""
