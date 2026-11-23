"""A new picture's name, a replacement's, and where a picture set aside waits."""

from datetime import date
from pathlib import PureWindowsPath

from mado.core.naming import aside_name, in_quarantine, new_name, quarantine_root, replacement_name


def test_a_new_picture_is_named_after_its_original_and_what_it_was_made_for():
    nothing: set[str] = set()

    assert new_name("Harbour at dusk", "TV 8K", ".jpg", nothing.__contains__) == (
        "Harbour at dusk (TV 8K).jpg"
    )


def test_a_picture_saved_as_it_is_keeps_its_originals_name():
    assert new_name("Pasted 2026-11-23 14.05", "", ".png", lambda _name: False) == (
        "Pasted 2026-11-23 14.05.png"
    )
    taken = {"pasted 2026-11-23 14.05.png"}
    assert new_name("Pasted 2026-11-23 14.05", "", ".png", lambda name: name.lower() in taken) == (
        "Pasted 2026-11-23 14.05 (2).png"
    )


def test_a_name_thats_taken_gets_the_next_number_whatever_its_case():
    taken = {"harbour at dusk (tv 8k).jpg", "harbour at dusk (tv 8k) (2).jpg"}

    found = new_name("Harbour at dusk", "TV 8K", ".jpg", lambda name: name.casefold() in taken)

    assert found == "Harbour at dusk (TV 8K) (3).jpg"


def test_a_label_never_puts_a_character_windows_refuses_in_a_name():
    nothing: set[str] = set()

    assert new_name("Pier", "10/15", ".png", nothing.__contains__) == "Pier (10-15).png"


def test_a_replacement_keeps_its_originals_name_with_its_new_formats_extension():
    assert replacement_name("Harbour at dusk.heic", ".jpg") == "Harbour at dusk.jpg"
    assert replacement_name("Old pier.JPEG", ".jpg") == "Old pier.JPEG"
    assert replacement_name("Old pier.png", ".png") == "Old pier.png"


def test_a_picture_set_aside_waits_on_its_own_drive_in_a_folder_a_day():
    root = quarantine_root(PureWindowsPath(r"D:\Pictures\Phone\Harbour at dusk.heic"))
    day = root / date(2026, 11, 22).isoformat()

    assert root == PureWindowsPath(r"D:\Mado quarantine")
    assert in_quarantine(day / "Harbour at dusk.heic", root)
    assert not in_quarantine(root / "Harbour at dusk.heic", root)  # not in a day's folder
    assert not in_quarantine(PureWindowsPath(r"D:\Pictures\2026-11-22\x.jpg"), root)


def test_two_pictures_of_one_name_set_aside_the_same_day_both_keep():
    taken = {"Harbour at dusk.heic"}

    assert aside_name("Harbour at dusk.heic", taken.__contains__) == "Harbour at dusk (2).heic"
