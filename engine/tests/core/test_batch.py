"""Many at once, by its rules: nights, the pictures See it first makes, what the rest takes, room
on a drive, a batch's steps and the words for them."""

from datetime import datetime

import pytest

from mado.core.batch import (
    MARGIN,
    SPACE_HELD,
    Step,
    StepError,
    at_night,
    calibrated,
    cutout_detail,
    fits,
    fitting,
    folder_words,
    look_chip,
    may_start,
    morning,
    paint_detail,
    ready_words,
    recipe_of,
    sampled,
    saving_chip,
    size_chip,
    size_detail,
    steps_in_order,
    told,
)
from mado.core.sizes import PRINTS, SCREENS, Size

TV = next(size for size in SCREENS if size.id == "tv-8k")
PHONE = next(size for size in SCREENS if size.id == "phone")
A3 = next(size for size in PRINTS if size.id == "print-a3")


def at(hour: int, minute: int = 0, day: int = 22) -> datetime:
    return datetime(2026, 11, day, hour, minute).astimezone()


@pytest.mark.parametrize(
    ("moment", "night"),
    [(at(22, 59), False), (at(23, 0), True), (at(2, 30), True), (at(6, 59), True), (at(7), False)],
)
def test_the_night_runs_from_23_00_to_07_00(moment: datetime, night: bool):
    assert at_night(moment) is night


def test_the_morning_is_the_07_00_that_ends_the_night_a_moment_is_in():
    assert morning(at(23, 30)) == at(7, day=23)
    assert morning(at(3)) == at(7)
    assert morning(at(14)) == at(7, day=23)  # by day, the coming night's


def test_a_batch_for_tonight_starts_only_at_night_the_others_at_once():
    assert may_start("now", at(14))
    assert may_start("after", at(14))
    assert not may_start("tonight", at(14))
    assert may_start("tonight", at(23, 5))


def test_see_it_first_spreads_its_three_across_the_batch_and_tries_three_others_each_time():
    first = sampled(48, 0)
    second = sampled(48, 1)

    assert len(first) == 3 == len(set(first))
    assert first[0] == 0
    assert max(first) - min(first) >= 16  # from across the batch, not three neighbours
    assert not set(first) & set(second)
    assert all(0 <= each < 48 for each in first + second)


def test_a_small_batch_shows_all_it_has_and_comes_round_again():
    assert sorted(sampled(2, 0)) == [0, 1]
    assert sorted(sampled(3, 5)) == [0, 1, 2]
    assert sampled(0, 0) == []
    assert len(set(sampled(4, 1))) == 3  # one new, and two from the start again


def test_the_whole_batch_is_reckoned_by_how_see_it_first_went_against_its_guesses():
    guesses = [10.0] * 48
    assert calibrated(guesses, []) == 480.0
    # The three seen first took twice their guess: so does the rest.
    assert calibrated(guesses, [(10.0, 20.0), (10.0, 20.0), (10.0, 20.0)]) == 960.0
    # Held to a third to three times, so one strange picture can't throw it.
    assert calibrated(guesses, [(10.0, 300.0)]) == 1440.0
    assert calibrated(guesses, [(10.0, 0.0)]) == 160.0


def test_a_drive_has_room_while_a_margin_stays_free():
    assert fits(100, 100 + MARGIN)
    assert not fits(101, 100 + MARGIN)
    assert fitting([10, 20, 30], 35 + MARGIN) == 2  # in turn: 10, then 20 fit; 30 doesn't
    assert fitting([50, 1], 40 + MARGIN) == 0  # the first one waits, so the rest do


def test_steps_are_made_in_mados_order_whatever_order_they_are_listed_in():
    look: Step = {"step": "look", "look": "warm-film", "strength": 0.6, "touches": {}}
    size: Step = {"step": "size", "size": "tv-8k", "shape": "crop"}

    assert steps_in_order([look, size]) == [size, look]
    assert recipe_of([look, size]) == {
        "edit": None,
        "fix": None,
        "size": {"size": "tv-8k", "shape": "crop"},
        "depth": None,
        "paint": None,
        "look": {"look": "warm-film", "strength": 0.6, "touches": {}},
    }
    assert recipe_of([look]) == {
        "edit": None,
        "fix": None,
        "size": None,
        "depth": None,
        "paint": None,
        "look": {"look": "warm-film", "strength": 0.6, "touches": {}},
    }


def test_the_fixes_come_after_a_cut_out_and_before_the_size():
    cut: Step = {"step": "cutout", "quality": "fast", "behind": "nothing", "colour": None}
    fix: Step = {
        "step": "fix",
        "noise": {"strength": 0.8},
        "blur": None,
        "jpeg": None,
        "dark": None,
    }
    size: Step = {"step": "size", "size": "tv-8k"}

    assert steps_in_order([size, fix, cut]) == [cut, fix, size]
    assert recipe_of([size, fix])["fix"] == {
        "noise": {"strength": 0.8},
        "blur": None,
        "jpeg": None,
        "dark": None,
    }
    with pytest.raises(StepError, match="one set of fixes"):
        recipe_of([fix, fix])
    nothing_on: Step = {"step": "fix", "noise": None, "blur": None, "jpeg": None, "dark": None}
    with pytest.raises(StepError, match="no fix turned on"):
        recipe_of([size, nothing_on])


def test_the_depth_tools_come_after_the_size_before_a_painting_style_and_the_look():
    look: Step = {"step": "look", "look": "warm-film", "strength": 0.6, "touches": {}}
    depth: Step = {
        "step": "depth",
        "portrait": {"focus": None, "aperture": 2.8, "quality": None},
        "fog": None,
        "tilt": None,
    }
    size: Step = {"step": "size", "size": "tv-8k"}
    paint: Step = {"step": "paint", "style": "hokusai", "strength": 1, "colours": False}

    assert steps_in_order([look, depth, size]) == [size, depth, look]
    assert steps_in_order([paint, look, depth, size]) == [size, depth, paint, look]
    assert recipe_of([look, depth])["depth"] == {
        "portrait": {"focus": None, "aperture": 2.8, "quality": None},
        "fog": None,
        "tilt": None,
    }
    with pytest.raises(StepError, match="one set of depth tools"):
        recipe_of([depth, depth])
    nothing_on: Step = {"step": "depth", "portrait": None, "fog": None, "tilt": None}
    with pytest.raises(StepError, match="no tool turned on"):
        recipe_of([size, nothing_on])


def test_cutting_out_the_subject_goes_first_as_the_recipes_edit():
    cut: Step = {"step": "cutout", "quality": "fast", "behind": "nothing", "colour": None}
    size: Step = {"step": "size", "size": "tv-8k"}

    assert steps_in_order([size, cut]) == [cut, size]
    assert recipe_of([size, cut]) == {
        "edit": {
            "version": None,
            "edits": [{"kind": "subject", "quality": "fast", "behind": "nothing", "colour": None}],
        },
        "fix": None,
        "size": {"size": "tv-8k"},
        "depth": None,
        "paint": None,
        "look": None,
    }
    assert cutout_detail("best", "colour") == "Best, on a colour"
    assert cutout_detail(None, "nothing") == "As this PC suits, with nothing behind it"
    assert cutout_detail("fast", "blurred") == "Fast, on the rest of the picture blurred"


def test_a_painting_style_comes_after_the_size_and_before_the_look():
    look: Step = {"step": "look", "look": "warm-film", "strength": 0.6, "touches": {}}
    paint: Step = {"step": "paint", "style": "hokusai", "strength": 0.8}
    size: Step = {"step": "size", "size": "tv-8k"}

    assert steps_in_order([look, paint, size]) == [size, paint, look]
    assert recipe_of([look, paint])["paint"] == {"style": "hokusai", "strength": 0.8}
    with pytest.raises(StepError, match="one painting style"):
        recipe_of([paint, paint])
    assert paint_detail("After Hokusai", 0.8, colours=True, setting=None) == (
        "After Hokusai at 80%, in each picture's own colours"
    )
    assert paint_detail("Oil paint", 1.0, colours=False, setting=("Brush", 70)) == (
        "Oil paint, brush 70"
    )


def test_a_recipe_makes_one_size_and_one_look_and_needs_one_of_them():
    size: Step = {"step": "size", "size": "tv-8k"}
    later: Step = {"step": "sparkle"}  # a later Mado's step, in a recipe this one can't make
    with pytest.raises(StepError, match="one size"):
        recipe_of([size, size])
    with pytest.raises(StepError, match="Pick"):
        recipe_of([])
    with pytest.raises(StepError, match="doesn't know"):
        recipe_of([later])


def test_a_size_is_said_as_the_boards_say_it():
    assert size_chip(TV) == "TV 8K"
    assert size_chip(PHONE) == "Phone 1290 × 2796"
    assert size_chip(A3) == "A3 at 300 dpi"
    assert size_chip(
        Size("other-5000x3000", "5000 × 3000", 5000, 3000, "other", "screen", "x")
    ) == ("5000 × 3000")
    assert size_detail(TV, "crop", None) == (
        "TV 8K, 7680 × 4320, cropped around the subject; the right model for each picture"
    )
    assert size_detail(TV, "extend", "best") == (
        "TV 8K, 7680 × 4320, its edges extended; Best for each picture"
    )
    assert size_detail(A3, "crop", "fast").startswith("A3 at 300 dpi, turned to each picture")


def test_a_look_and_saving_are_said_as_the_boards_say_them():
    assert look_chip("Warm film", 0.6) == ("Warm film", "60")
    assert look_chip("Warm film", 1.0) == ("Warm film", None)
    assert saving_chip("new", "JPEG", 95, "Edited") == "JPEG 95 into Edited"
    assert saving_chip("new", "PNG", None, None) == "PNG beside the originals"
    assert saving_chip("replace", "JPEG", 92, None) == "JPEG 92 in place of the originals"
    assert saving_chip("new", "WebP", 90, "D:\\Prints") == "WebP 90 into Prints"


def test_where_new_pictures_go_is_said_from_the_folder_they_share():
    assert folder_words(None, "D:\\Pictures\\Holiday") == "beside the originals"
    assert folder_words("Edited", "D:\\Pictures\\Holiday") == "Holiday › Edited"
    assert folder_words("Edited", None) == "a folder called Edited beside each"
    assert folder_words("D:\\Prints\\Big", "D:\\Pictures\\Holiday") == "D:\\Prints\\Big"
    # A watch folder's results, inside it: said from the folder, as a folder by name is.
    assert folder_words("D:\\Pictures\\To TV\\Done", "D:\\Pictures\\To TV") == "To TV › Done"
    assert folder_words("d:\\pictures\\to tv\\Done\\Big", "D:\\Pictures\\To TV") == (
        "To TV › Done › Big"
    )
    assert folder_words("D:\\Pictures\\To TV 2", "D:\\Pictures\\To TV") == ("D:\\Pictures\\To TV 2")


def test_a_finished_batch_is_ready_for_what_it_was_made_for():
    assert ready_words("Holiday", "tv", None) == "Holiday is ready for the TV"
    assert ready_words("Holiday", "phone", None) == "Holiday is ready for the phone"
    assert ready_words("Scans", "print", None) == "Scans is ready to print"
    assert ready_words("Holiday", None, "Warm film at 60%") == "Holiday has Warm film at 60%"


def test_the_notification_says_what_the_batch_came_to():
    assert told("Holiday prints", made=48, failed=0, made_for="TV 8K", look=None) == (
        "Holiday prints is done",
        "48 pictures made for TV 8K",
    )
    assert told("Holiday prints", made=47, failed=1, made_for="TV 8K", look="Warm film") == (
        "Holiday prints is done",
        "47 pictures made for TV 8K, with Warm film · 1 didn't work",
    )
    assert told("Holiday prints", made=0, failed=3, made_for=None, look="Warm film") == (
        "Holiday prints didn't work",
        "None of its 3 pictures could be made. The queue says why.",
    )
    assert told("Holiday", made=1, failed=0, made_for=None, look="Warm film") == (
        "Holiday is done",
        "1 picture made with Warm film",
    )
    assert told(
        "Cut-outs for cards",
        made=12,
        failed=0,
        made_for=None,
        look=None,
        edit="cut out the subject",
    ) == ("Cut-outs for cards is done", "12 pictures made: cut out the subject")
    assert told(
        "Cards", made=2, failed=0, made_for="TV 8K", look=None, edit="cut out the subject"
    ) == (
        "Cards is done",
        "2 pictures made: cut out the subject, for TV 8K",
    )


def test_space_is_reckoned_by_see_it_first_more_freely_than_time():
    sizes = [18_000_000.0] * 20
    # Three made-up pictures came out far smaller than JPEG usually does: so will the rest.
    found = [(18_000_000.0, 2_500_000.0)] * 3
    assert calibrated(sizes, found, held=SPACE_HELD) == pytest.approx(20 * 2_500_000.0)
    assert calibrated(sizes, found) == pytest.approx(20 * 6_000_000.0)  # time's hold: a third
