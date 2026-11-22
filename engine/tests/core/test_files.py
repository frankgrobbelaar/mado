"""What a scan counts as a picture, and what it lists but can't read yet."""

import pytest

from mado.core.files import kind_of, skipped_folder


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("IMG_2041.JPG", "picture"),
        ("Harbour at dusk.jpeg", "picture"),
        ("scan-0001.tif", "picture"),
        ("Screenshot 2026-11-12 184207.png", "picture"),
        ("sticker.webp", "picture"),
        ("night.avif", "picture"),
        ("old.bmp", "picture"),
        ("wave.gif", "picture"),
        ("IMG_2041.HEIC", "heif"),
        ("burst.heif", "heif"),
        ("DSCF0012.HIF", "heif"),
        ("_MG_0042.CR3", "raw"),
        ("DSC_0007.NEF", "raw"),
        ("DSC01234.ARW", "raw"),
        ("PXL_20261112.dng", "raw"),
    ],
)
def test_pictures_are_known_by_their_extension_in_any_case(name: str, kind: str):
    assert kind_of(name) == kind


@pytest.mark.parametrize(
    "name",
    [
        "notes.txt",
        "holiday.mp4",
        "Thumbs.db",
        "desktop.ini",
        "jpg",
        "._IMG_2041.JPG",  # what a Mac leaves beside a picture on a shared drive
        ".hidden.png",
        "IMG_2041.JPG.part",  # still copying
    ],
)
def test_other_files_and_hidden_ones_are_not_pictures(name: str):
    assert kind_of(name) is None


@pytest.mark.parametrize(
    ("name", "skipped"),
    [
        ("$RECYCLE.BIN", True),
        ("System Volume Information", True),
        ("system volume information", True),
        ("@eaDir", True),  # a network drive's own thumbnails
        (".thumbnails", True),
        ("2026", False),
        ("Holiday", False),
    ],
)
def test_a_scan_skips_the_folders_windows_and_drives_keep_for_themselves(name: str, skipped: bool):
    assert skipped_folder(name) is skipped
