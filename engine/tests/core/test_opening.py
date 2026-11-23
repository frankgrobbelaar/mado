from datetime import datetime

from mado.core.opening import (
    Entry,
    long_form,
    not_a_picture,
    not_there,
    nothing_to_open,
    pasted_name,
    what_opens,
)


def test_one_picture_opens_its_page():
    assert what_opens([Entry(r"D:\Holiday\Warm dunes.jpg", "picture")]) == "page"


def test_one_picture_among_other_files_still_opens_its_page():
    entries = [
        Entry(r"D:\Holiday\Warm dunes.jpg", "picture"),
        Entry(r"D:\Holiday\notes.txt", "other"),
        Entry(r"E:\Gone\Still lake.heic", "missing"),
    ]
    assert what_opens(entries) == "page"


def test_several_pictures_or_a_folder_open_many_at_once():
    two = [Entry(r"D:\Holiday\a.jpg", "picture"), Entry(r"D:\Holiday\b.png", "picture")]
    assert what_opens(two) == "many"
    assert what_opens([Entry(r"D:\Holiday", "folder")]) == "many"
    assert what_opens([Entry(r"D:\Holiday", "folder"), Entry(r"D:\a.jpg", "picture")]) == "many"


def test_nothing_that_is_a_picture_opens_nothing():
    assert what_opens([Entry(r"D:\notes.txt", "other"), Entry(r"E:\a.jpg", "missing")]) == (
        "nothing"
    )
    assert what_opens([]) == "nothing"


def test_a_file_mado_cant_read_is_told_the_formats_it_reads():
    said = not_a_picture("Brochure.pdf")
    assert said.startswith("Brochure.pdf isn't a picture Mado reads.")
    assert "JPEG, PNG, HEIC, WebP, AVIF, TIFF, BMP and GIF" in said


def test_a_path_not_there_says_whether_its_drive_is_connected():
    assert not_there(r"F:\Trip\Pier.jpg", drive_there=False) == (
        "Pier.jpg is on F:, which isn't connected. Connect it, then open it again."
    )
    assert not_there(r"D:\Trip\Pier.jpg", drive_there=True) == (
        "Pier.jpg isn't there any more: it was moved or deleted."
    )


def test_nothing_to_open_says_why_for_one_and_the_formats_for_more():
    assert nothing_to_open([("notes.txt", "notes.txt isn't a picture.")]) == (
        "notes.txt isn't a picture."
    )
    assert "None of those are pictures Mado reads" in nothing_to_open(
        [("a.txt", "x"), ("b.txt", "y")]
    )


def test_several_paths_not_there_say_their_drive_or_that_they_went():
    unplugged = [Entry(r"F:\Trip\a.jpg", "missing"), Entry(r"F:\Trip\b.jpg", "missing")]
    left = [("a.jpg", "a"), ("b.jpg", "b")]
    assert nothing_to_open(left, unplugged, unplugged_drives={"F:"}) == (
        "Those are on F:, which isn't connected. Connect it, then open them again."
    )
    went = [Entry(r"D:\Trip\a.jpg", "missing"), Entry(r"D:\Trip\b.jpg", "missing")]
    assert nothing_to_open(left, went, unplugged_drives=set()) == (
        "None of those are there any more: they were moved or deleted."
    )


def test_windows_long_form_reaches_long_paths_on_drives_and_network_shares():
    assert long_form(r"D:\Trip\Pier.jpg") == r"\\?\D:\Trip\Pier.jpg"
    assert long_form(r"\\nas\photos\Pier.jpg") == r"\\?\UNC\nas\photos\Pier.jpg"
    assert long_form(r"\\?\D:\Trip\Pier.jpg") == r"\\?\D:\Trip\Pier.jpg"


def test_a_pasted_picture_is_named_by_when_it_was_pasted():
    now = datetime(2026, 11, 23, 14, 5, 12)
    assert pasted_name(now, lambda _name: False) == "Pasted 2026-11-23 14.05.png"
    taken = {"Pasted 2026-11-23 14.05.png", "Pasted 2026-11-23 14.05 (2).png"}
    assert pasted_name(now, taken.__contains__) == "Pasted 2026-11-23 14.05 (3).png"
