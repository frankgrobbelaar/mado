"""What a PC can do for Mado: its cards, where the models run, their tiles, and the defaults."""

from mado.core.hardware import (
    GIB,
    Card,
    Checked,
    abilities,
    best_card,
    cards_from,
    defaults,
    place_of,
    processor_name,
    tile_for,
    typical_seconds,
)
from mado.core.models import BEST_DRAWING, BEST_PHOTO, FAST

SUPER = Card("NVIDIA GeForce GTX 1660 SUPER", "nvidia", 6 * GIB, False, "617.42")
ROOMY = Card("NVIDIA GeForce RTX 4080", "nvidia", 16 * GIB, False, "617.42")
LAPTOP = Card("Intel UHD Graphics", "intel", 128 * 1024**2, True, "31.0")


def test_windows_listing_gives_the_cards_on_the_pcs_bus_with_their_own_memory():
    listed: list[dict[str, object]] = [
        {
            "Name": "NVIDIA GeForce GTX 1660 SUPER",
            "PNPDeviceID": "PCI\\VEN_10DE&DEV_21C4",
            "DriverVersion": "32.0.16.1742",
            "AdapterRAM": 0xFFF00000,
        },
        {"Name": "Microsoft Basic Display Adapter", "PNPDeviceID": "ROOT\\BASICDISPLAY"},
    ]

    cards = cards_from(listed, {"NVIDIA GeForce GTX 1660 SUPER": 6 * GIB})

    assert cards == (SUPER,)


def test_the_card_mado_works_on_is_the_dedicated_one_with_the_most_memory():
    assert best_card([LAPTOP, SUPER]) == SUPER
    assert best_card([LAPTOP]) == LAPTOP
    assert best_card([]) is None


def test_the_models_run_on_the_card_unless_testing_found_they_dont():
    assert place_of(None) == "card"
    assert place_of(Checked(ai=True, at="2026-11-22T10:00:00")) == "card"
    assert place_of(Checked(ai=False, at="2026-11-22T10:00:00", problem="no DirectX 12")) == (
        "processor"
    )


def test_heavy_models_take_small_tiles_on_a_card_under_8_gb():
    assert tile_for(FAST, "card", SUPER) == 512
    assert tile_for(BEST_PHOTO, "card", SUPER) == 256
    assert tile_for(BEST_PHOTO, "card", ROOMY) == 512
    assert tile_for(FAST, "processor", None) == 256


def test_best_goes_first_where_a_typical_photo_takes_it_two_minutes_at_most():
    assert defaults("card", SUPER, {}) == {"photo": "best", "drawing": "best"}
    slow = {"realesrgan-x4plus@card": 30.0, "realesrgan-x4plus-anime-6b@card": 20.0}
    assert defaults("card", SUPER, slow) == {"photo": "fast", "drawing": "fast"}
    assert defaults("processor", None, {}) == {"photo": "fast", "drawing": "fast"}


def test_a_typical_photo_takes_seconds_with_fast_and_longer_with_best_on_the_card():
    fast = typical_seconds(FAST, "card", SUPER, {})
    best = typical_seconds(BEST_PHOTO, "card", SUPER, {})
    drawing = typical_seconds(BEST_DRAWING, "card", SUPER, {})

    assert 2 < fast < 15
    assert fast < drawing < best < 120


def test_about_lists_each_kind_at_each_quality():
    found = abilities("processor", None, {})

    assert [(a.kind, a.quality) for a in found] == [
        ("photo", "fast"),
        ("photo", "best"),
        ("drawing", "fast"),
        ("drawing", "best"),
    ]
    assert found[1].pace == "slow"
    assert found[1].download


def test_a_processor_reads_as_people_say_it():
    assert processor_name("Intel(R) Core(TM) i5-9600K CPU @ 3.70GHz") == "Intel Core i5-9600K"
