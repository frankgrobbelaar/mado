"""What a picture's EXIF says about it, in Mado's words: when, which camera, which way up, where."""

from datetime import datetime

import pytest

from mado.core.facts import camera, located, shown_size, taken


def test_when_a_picture_was_taken_comes_from_exifs_own_way_of_writing_it():
    assert taken("2026:11:12 18:42:07") == datetime(2026, 11, 12, 18, 42, 7)
    assert taken("2026:11:12 18:42:07\x00") == datetime(2026, 11, 12, 18, 42, 7)
    assert taken("2026-11-12 18:42:07") == datetime(2026, 11, 12, 18, 42, 7)
    assert taken("2026:11:12T18:42:07") == datetime(2026, 11, 12, 18, 42, 7)


@pytest.mark.parametrize(
    "written",
    [
        None,
        "",
        "0000:00:00 00:00:00",  # a camera whose clock was never set
        "    :  :     :  :  ",
        "2026:13:40 25:00:00",
        "yesterday",
        "1801:01:01 00:00:00",  # before photography
    ],
)
def test_a_date_that_isnt_one_says_nothing(written: str | None):
    assert taken(written) is None


@pytest.mark.parametrize(
    ("make", "model", "named"),
    [
        ("Pixelworks", "PW-7 Pro", "Pixelworks PW-7 Pro"),
        ("Lumen", "Lumen X100", "Lumen X100"),  # the model names its maker already
        ("LUMEN CORPORATION", "LUMEN Z 6", "LUMEN Z 6"),
        ("  Lumen \x00", " X100 \x00", "Lumen X100"),
        (None, "X100", "X100"),
        ("Lumen", None, "Lumen"),
        (None, None, None),
        ("", "  ", None),
        ("Lumen", "\t", "Lumen"),  # a model that's only a tab
        ("\n", "\t\x00", None),
    ],
)
def test_a_camera_is_named_by_its_maker_and_model_once(
    make: str | None, model: str | None, named: str | None
):
    assert camera(make, model) == named


@pytest.mark.parametrize(
    ("orientation", "size"),
    [
        (1, (4032, 3024)),
        (3, (4032, 3024)),
        (6, (3024, 4032)),
        (8, (3024, 4032)),
        (None, (4032, 3024)),
    ],
)
def test_a_picture_turned_on_its_side_is_shown_taller_than_wide(
    orientation: int | None, size: tuple[int, int]
):
    assert shown_size(4032, 3024, orientation) == size


def test_a_picture_carries_a_location_when_its_gps_has_both_halves():
    assert located({1: "S", 2: (33.0, 55.0, 0.0), 3: "E", 4: (18.0, 25.0, 0.0)})
    assert not located({1: "S", 2: (33.0, 55.0, 0.0)})  # half a location isn't one
    assert not located({0: b"\x02\x02\x00\x00"})  # only the GPS version, as some phones write
    assert not located({})
