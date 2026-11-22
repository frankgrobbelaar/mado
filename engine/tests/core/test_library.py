"""How library folders may sit together, where a picture sits in one, and a scan's pace."""

from pathlib import PureWindowsPath

from mado.core.library import Covered, Holds, fits, inner_folder, time_left


def test_a_folder_on_its_own_fits_beside_the_others():
    existing = [PureWindowsPath(r"D:\Pictures\Phone")]

    assert fits(PureWindowsPath(r"D:\Pictures\Camera"), existing) is None


def test_a_folder_already_in_the_library_or_inside_one_is_covered():
    phone = PureWindowsPath(r"D:\Pictures\Phone")

    assert fits(phone, [phone]) == Covered(phone)
    assert fits(PureWindowsPath(r"D:\Pictures\Phone\2026"), [phone]) == Covered(phone)


def test_a_folder_holding_library_folders_takes_them_in():
    phone = PureWindowsPath(r"D:\Pictures\Phone")
    camera = PureWindowsPath(r"D:\Pictures\Camera")
    scans = PureWindowsPath(r"E:\Scans")

    assert fits(PureWindowsPath(r"D:\Pictures"), [phone, camera, scans]) == Holds((phone, camera))


def test_a_picture_sits_in_its_library_folder_by_the_folders_between():
    root = PureWindowsPath(r"D:\Pictures\Phone")

    assert inner_folder(root, PureWindowsPath(r"D:\Pictures\Phone\IMG_2041.HEIC")) == ""
    assert inner_folder(root, PureWindowsPath(r"D:\Pictures\Phone\2026\Holiday\IMG.jpg")) == (
        "2026/Holiday"
    )


def test_time_left_waits_for_a_pace_then_goes_by_it():
    assert time_left(done=2, total=100, elapsed=1.0) is None  # too few to go by
    assert time_left(done=10, total=100, elapsed=5.0) == 45.0
    assert time_left(done=100, total=100, elapsed=50.0) == 0.0
