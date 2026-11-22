"""The sizes a picture can be made for: screens, prints at 300 dpi, the owner's screens, and any
other."""

import pytest

from mado.core.sizes import (
    PRINTS,
    SCREENS,
    Screen,
    SizeError,
    print_pixels,
    remember,
    resolve,
    shape_name,
    turned,
    yours,
)


def test_the_screens_are_the_devices_as_drawn_with_their_exact_pixels():
    assert [(s.name, s.width, s.height) for s in SCREENS] == [
        ("Phone", 1290, 2796),
        ("Tablet", 2048, 2732),
        ("Laptop", 2560, 1600),
        ("Monitor 4K", 3840, 2160),
        ("Ultrawide", 3440, 1440),
        ("TV 8K", 7680, 4320),
    ]


def test_prints_are_their_paper_at_300_dpi():
    assert print_pixels(100, 150) == (1181, 1772)
    assert [(p.name, p.width, p.height) for p in PRINTS] == [
        ("10 × 15 cm", 1181, 1772),
        ("A4", 2480, 3508),
        ("A3", 3508, 4961),
    ]


def test_a_print_turns_to_the_pictures_way_round_and_a_screen_does_not():
    a4 = resolve("print-a4")
    phone = resolve("phone")

    assert turned(a4, 4032, 3024) == (3508, 2480)  # a landscape photo: the paper turns
    assert turned(a4, 3024, 4032) == (2480, 3508)
    assert turned(phone, 4032, 3024) == (1290, 2796)  # a phone stays tall


def test_any_other_size_comes_in_pixels_or_centimetres():
    pixels = resolve("other-5000x3000")
    printed = resolve("other-20x30cm")

    assert (pixels.width, pixels.height, pixels.label) == (5000, 3000, "5000 × 3000")
    assert (printed.width, printed.height, printed.name) == (2362, 3543, "20 × 30 cm")
    assert printed.turns


@pytest.mark.parametrize("asked", ["other-5x5", "other-40000x10", "other-20000x20000", "laptop2"])
def test_a_size_mado_cant_make_says_why(asked: str):
    with pytest.raises(SizeError):
        resolve(asked)


def test_shapes_have_the_names_people_know():
    assert shape_name(7680, 4320) == "16:9"
    assert shape_name(4032, 3024) == "4:3"
    assert shape_name(3024, 4032) == "3:4"
    assert shape_name(1290, 2796) == "9:19.5"
    assert shape_name(3440, 1440) == "21:9"
    assert shape_name(2560, 1600) == "16:10"
    assert shape_name(2480, 3508) is None  # paper's has no such name


def test_the_owners_screens_are_remembered_by_size_and_named_once():
    seen = remember([], [(2560, 1600, False), (3440, 1440, True)])

    assert seen == [Screen("Main screen", 3440, 1440), Screen("Screen 2", 2560, 1600)]
    # Seen again, at a desk with another screen: the new size joins at the front.
    again = remember(seen, [(3440, 1440, True), (1920, 1080, False)])
    assert again == [
        Screen("Screen 3", 1920, 1080),
        Screen("Main screen", 3440, 1440),
        Screen("Screen 2", 2560, 1600),
    ]
    assert next(size.id for size in yours(again)) == "yours-1920x1080"
    assert resolve("yours-3440x1440", again).name == "Main screen"


def test_a_screen_too_small_or_too_big_to_make_for_isnt_remembered():
    seen = remember([], [(8, 8, True), (100_000, 100_000, False), (1920, 1080, False)])

    assert seen == [Screen("Screen 2", 1920, 1080)]
    # Nor offered, if a damaged record kept one.
    assert [size.id for size in yours([Screen("Huge", 90_000, 90_000), *seen])] == [
        "yours-1920x1080"
    ]
