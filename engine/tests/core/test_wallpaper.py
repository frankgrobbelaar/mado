from dataclasses import replace

import pytest

from mado.core.framing import Box
from mado.core.wallpaper import (
    ALL,
    Candidate,
    Cut,
    Monitor,
    Rect,
    arrangement,
    bounds,
    framed,
    key_of,
    made,
    ordered,
    part_for,
    parts_across,
    picks,
    spread,
    suits,
)

DESK = Monitor("\\\\?\\DISPLAY#MADE0001#1", "Studio 27", 1, 0, 0, 2560, 1440, main=True)
SIDE = Monitor("\\\\?\\DISPLAY#MADE0002#2", "Side 24", 2, 2560, 0, 1920, 1080)
TALL = Monitor("\\\\?\\DISPLAY#MADE0003#3", "Panel 24", 3, 2560, 360, 1080, 1920, rotation=90)


def test_a_monitors_key_is_short_and_stays_the_same_however_windows_writes_its_name():
    assert key_of(DESK.id) == key_of(DESK.id.upper())
    assert key_of(DESK.id) != key_of(SIDE.id)
    assert len(key_of(DESK.id)) == 10


def test_the_arrangement_changes_with_pixels_places_and_turns_but_not_scale_or_names():
    both = arrangement([DESK, SIDE])
    assert arrangement([SIDE, DESK]) == both
    assert arrangement([DESK, replace(SIDE, name="Another")]) == both
    assert arrangement([DESK, replace(SIDE, scale=1.5)]) == both
    assert arrangement([DESK, replace(SIDE, width=2560, height=1440)]) != both
    assert arrangement([DESK, replace(SIDE, y=200)]) != both
    assert arrangement([DESK, replace(SIDE, rotation=180)]) != both
    assert arrangement([DESK]) != both


def test_the_main_monitor_comes_first_then_by_windows_number():
    assert [each.name for each in ordered([TALL, SIDE, DESK])] == [
        "Studio 27",
        "Side 24",
        "Panel 24",
    ]
    assert ordered([replace(SIDE, main=True), replace(DESK, main=False)])[0].name == "Side 24"


def test_side_by_side_monitors_are_spread_by_the_gap_and_keep_their_line():
    places = spread([DESK, SIDE], 30)

    assert places[DESK.id] == Rect(0, 0, 2560, 1440)
    assert places[SIDE.id] == Rect(2590, 0, 1920, 1080)
    assert spread([DESK, SIDE], 0)[SIDE.id] == Rect(2560, 0, 1920, 1080)


def test_a_monitor_beside_another_lower_down_moves_across_but_not_down():
    places = spread([DESK, TALL], 24)

    assert places[TALL.id] == Rect(2584, 360, 1080, 1920)


def test_stacked_monitors_are_spread_down_and_a_row_of_three_twice():
    below = Monitor("b", "Below", 2, 300, 1440, 1920, 1080)
    assert spread([DESK, below], 40)[below.id] == Rect(300, 1480, 1920, 1080)

    third = Monitor("c", "Third", 3, 4480, 0, 1920, 1080)
    places = spread([DESK, SIDE, third], 10)
    assert [places[each.id].x for each in (DESK, SIDE, third)] == [0, 2570, 4500]


def test_a_monitor_under_another_keeps_its_column_once_the_gap_moves_it():
    left = Monitor("a", "A", 1, 0, 0, 1920, 1080, main=True)
    right = Monitor("b", "B", 2, 1920, 0, 1920, 1080)
    under = Monitor("c", "C", 3, 1920, 1080, 1920, 1080)

    places = spread([left, right, under], 20)

    assert places["b"].x == places["c"].x == 1940
    assert places["c"].y == 1100


def test_the_bounds_hold_every_monitor():
    assert bounds(spread([DESK, SIDE], 30).values()) == Rect(0, 0, 4510, 1440)
    assert bounds([Rect(-1920, 200, 1920, 1080), Rect(0, 0, 2560, 1440)]) == Rect(
        -1920, 0, 4480, 1440
    )


def test_a_crop_is_the_biggest_part_with_the_monitors_shape_around_the_subject():
    made_ = framed(4032, 3024, (2560, 1440), "crop", Cut(), (0.5, 0.4))

    assert made_.kept == made_.canvas
    assert made_.kept.width == pytest.approx(4032)
    assert made_.kept.height == pytest.approx(4032 * 1440 / 2560)
    assert made_.kept.y + made_.kept.height / 2 == pytest.approx(0.4 * 3024)


def test_zooming_in_takes_a_smaller_part_around_where_the_owner_moved_it():
    made_ = framed(4032, 3024, (2560, 1440), "crop", Cut(0.25, 0.5, 2.0), (0.5, 0.5))

    assert made_.kept.width == pytest.approx(2016)
    assert made_.kept.height == pytest.approx(1134)
    assert made_.kept.x + made_.kept.width / 2 == pytest.approx(1008)
    assert made_.share == pytest.approx(1 - (2016 * 1134) / (4032 * 3024))


def test_a_part_moved_past_the_edge_stays_inside_the_picture_and_zoom_is_held():
    made_ = framed(4032, 3024, (2560, 1440), "crop", Cut(1.0, 0.0, 9.0), (0.5, 0.5))

    assert made_.kept.width == pytest.approx(4032 / 4)
    assert made_.kept.x + made_.kept.width == pytest.approx(4032)
    assert made_.kept.y == pytest.approx(0)


def test_extending_keeps_all_of_the_picture_whatever_the_cut():
    made_ = framed(3000, 3000, (2560, 1440), "extend", Cut(0.1, 0.1, 3.0), (0.5, 0.5))

    assert made_.kept == Box(0, 0, 3000, 3000)
    assert made_.canvas.width / made_.canvas.height == pytest.approx(2560 / 1440)
    assert made_.sides == "sides"


def test_one_for_each_cuts_a_part_with_the_monitors_own_shape():
    part = part_for(TALL, (4032, 3024), "crop", Cut(), (0.5, 0.5))

    assert part.monitor == TALL
    assert part.box.width / part.box.height == pytest.approx(1080 / 1920)
    assert part.box.height == pytest.approx(3024)


def test_one_across_all_lays_the_picture_over_the_monitors_as_they_sit():
    found = parts_across([DESK, SIDE], 0, (8960, 2880), "crop", Cut(), (0.5, 0.5))

    desk, side = (next(part for part in found if part.monitor == each) for each in (DESK, SIDE))
    assert desk.box == Box(0, 0, 5120, 2880)
    assert side.box.x == pytest.approx(5120)
    assert side.box.width == pytest.approx(3840)
    assert side.box.height == pytest.approx(2160)
    assert desk.monitor.width / desk.box.width == pytest.approx(side.monitor.width / side.box.width)


def test_across_with_a_gap_skips_what_the_bezels_hide():
    found = parts_across([DESK, SIDE], 40, (9040, 2880), "crop", Cut(), (0.5, 0.5))

    side = next(part for part in found if part.monitor == SIDE)
    assert side.box.x == pytest.approx(5200)


def test_across_extended_shares_one_canvas_so_its_drawn_edges_meet():
    found = parts_across([DESK, SIDE], 0, (3000, 2000), "extend", Cut(), (0.5, 0.5))

    assert found[0].frame == found[1].frame
    canvas = found[0].frame.canvas
    assert canvas.width / canvas.height == pytest.approx(4480 / 1440)
    assert found[0].box.x == pytest.approx(canvas.x)


def test_each_part_says_how_its_made_and_when_it_looks_painted():
    near = made(part_for(DESK, (1920, 1080), "crop", Cut(), (0.5, 0.5)), 1920, 1080, "photo",
                "fast", guessed=True)  # fmt: skip
    assert near.method == "ai"
    assert near.scale == pytest.approx(2560 / 1920)
    assert near.warning is None
    assert near.how == "Made with the photo model, guessed from the picture."

    big = made(part_for(SIDE, (4032, 3024), "crop", Cut(), (0.5, 0.5)), 4032, 3024, "photo",
               "best", guessed=False)  # fmt: skip
    assert big.method == "shrink"
    assert big.model is None

    tiny = made(part_for(DESK, (320, 180), "crop", Cut(), (0.5, 0.5)), 320, 180, "photo", "fast",
                guessed=True)  # fmt: skip
    assert tiny.warning is not None
    assert "8 times bigger" in tiny.warning


def test_a_picture_suits_a_monitor_its_way_round_with_enough_pixels():
    assert suits(4032, 3024, 2560, 1440)
    assert not suits(3024, 4032, 2560, 1440)  # a tall picture on a wide monitor
    assert suits(3024, 4032, 1080, 1920)
    assert suits(3000, 3000, 1080, 1920)  # a square suits either way
    assert suits(640, 360, 1920, 1080)  # three times bigger looks real
    assert not suits(320, 180, 2560, 1440)  # eight times bigger looks painted
    assert not suits(0, 0, 1920, 1080)


def _candidates(*sizes: tuple[int, int, str | None]) -> list[Candidate]:
    return [Candidate(number, width, height, shown) for number, (width, height, shown) in
            enumerate(sizes, start=1)]  # fmt: skip


def test_the_days_picture_is_one_not_shown_for_longest_never_shown_first():
    found = _candidates((4000, 2250, "2026-11-20"), (4000, 2250, None), (4000, 2250, "2026-11-10"))

    assert picks(found, [DESK], "each", 0, "2026-11-23") == {DESK.id: 2}
    shown = [replace(found[1], shown="2026-11-23"), found[0], found[2]]
    assert picks(shown, [DESK], "each", 0, "2026-11-24") == {DESK.id: 3}


def test_each_monitor_gets_a_picture_that_suits_it_and_none_twice_while_others_suit():
    found = _candidates((4000, 2250, None), (2250, 4000, None), (4000, 2250, None))

    chosen = picks(found, [DESK, TALL], "each", 0, "2026-11-23")

    assert chosen[TALL.id] == 2
    assert chosen[DESK.id] in (1, 3)


def test_a_monitor_nothing_suits_is_left_as_it_is():
    found = _candidates((4000, 2250, None))

    assert picks(found, [DESK, TALL], "each", 0, "2026-11-23") == {DESK.id: 1}
    assert picks([], [DESK], "each", 0, "2026-11-23") == {}


def test_the_only_picture_that_suits_goes_on_two_monitors_rather_than_none():
    found = _candidates((4000, 2250, None))

    assert picks(found, [DESK, SIDE], "each", 0, "2026-11-23") == {DESK.id: 1, SIDE.id: 1}


def test_ties_are_broken_by_the_day_the_same_way_all_that_day():
    found = _candidates(*[(4000, 2250, None)] * 12)

    first = picks(found, [DESK], "each", 0, "2026-11-23")
    assert picks(found, [DESK], "each", 0, "2026-11-23") == first
    days = {picks(found, [DESK], "each", 0, f"2026-11-{day:02}")[DESK.id] for day in range(1, 29)}
    assert len(days) > 3


def test_one_across_all_picks_a_picture_that_suits_the_whole_arrangement():
    found = _candidates((600, 338, None), (6000, 1500, None))  # the first seven times too small

    assert picks(found, [DESK, SIDE], "across", 0, "2026-11-23") == {ALL: 2}
    assert picks(_candidates((640, 480, None)), [DESK, SIDE], "across", 0, "2026-11-23") == {}
