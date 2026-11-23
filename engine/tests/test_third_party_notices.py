"""The licence check and the notices file that every installer and release carries."""

from pathlib import Path

import pytest
from third_party_notices import (
    MICROSOFT,
    PYTHON_LICENCES,
    PYTHON_NOTES,
    WINDOWS,
    Part,
    allowed,
    assets,
    cpp_runtime,
    downloaded_only,
    downloaded_parts,
    is_licence_file,
    is_windows_runtime,
    render,
    sources_in,
)

MIT = """MIT License

Copyright (c) 2020 Someone

Permission is hereby granted, free of charge, to any person obtaining a copy..."""


@pytest.mark.parametrize(
    "expression",
    [
        "MIT",
        "MIT OR Apache-2.0",
        "MIT/Apache-2.0",  # Cargo's old spelling
        "Apache-2.0 / MIT",
        "(MIT OR Apache-2.0) AND Unicode-3.0",
        "Apache-2.0 WITH LLVM-exception",
        "GPL-2.0-or-later WITH Bootloader-exception",  # PyInstaller
        "MIT OR GPL-3.0-only",  # Mado takes the MIT choice
        "MPL-2.0",
        MICROSOFT,  # not open source, but free to pass on: its C++ runtime
        f"MIT AND {MICROSOFT}",  # ONNX Runtime, with Microsoft's DirectML inside
    ],
)
def test_licences_mado_can_meet(expression: str):
    assert allowed(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "GPL-3.0-only",
        "LGPL-2.1-or-later",
        "MIT AND GPL-3.0-only",  # both apply, and one can't be met
        "GPL-3.0-only WITH Classpath-exception-2.0",
        "LicenseRef-Proprietary",
        "MIT OR",
        "(MIT",
        "MIT Apache-2.0",  # no operator between them
    ],
)
def test_licences_that_stop_the_build(expression: str):
    assert not allowed(expression)


@pytest.mark.parametrize(
    "name",
    [
        "LICENSE",
        "LICENSE.txt",
        "LICENSE-MIT",
        "license-apache.md",
        "LICENCE",
        "LICENSES.txt",
        "UNLICENSE",
        "COPYING",
        "NOTICE",
        "AUTHORS.md",
        "ThirdPartyNotices.txt",  # ONNX Runtime's, for what's built into it
        "THIRD-PARTY-NOTICES.txt",
    ],
)
def test_licence_files_are_recognised(name: str):
    assert is_licence_file(name)


@pytest.mark.parametrize(
    "name",
    ["license.py", "license.rs", "README.md", "Cargo.toml", "lib.rs", "third_party_notices.py"],
)
def test_other_files_are_not(name: str):
    assert not is_licence_file(name)


def test_files_are_read_from_pyinstallers_records():
    fastapi = r"C:\venv\Lib\site-packages\fastapi\__init__.py"
    record = (
        r"C:\build\PYZ-00.pyz",
        [
            ("fastapi", fastapi, "PYMODULE"),
            ("W ignore", "", "OPTION"),  # not a file
            ("pyi_rth_inspect", ("nested", r"C:\x\pyi_rth_inspect.py", "PYSOURCE"), "X"),
        ],
    )

    assert list(sources_in(record)) == [Path(fastapi), Path(r"C:\x\pyi_rth_inspect.py")]


def test_microsofts_cpp_runtime_is_known_only_as_windows_own_copy():
    """Python needs it; a copy another program left on PATH could be any version."""
    assert is_windows_runtime(WINDOWS / "MSVCP140_1.dll")
    assert is_windows_runtime(Path(str(WINDOWS).upper()) / "vcruntime140.dll")
    assert not is_windows_runtime(Path(r"C:\Program Files\ImageMagick-7.1\MSVCP140_1.dll"))
    assert not is_windows_runtime(Path(r"C:\Program Files\Java\jdk-25\bin\msvcp140.dll"))
    assert not is_windows_runtime(WINDOWS / "d3d12.dll")  # Windows' own, never carried


def test_microsofts_cpp_runtime_is_one_part_of_the_engine():
    (part,) = cpp_runtime(["vcruntime140.dll", "msvcp140_1.dll", "msvcp140.dll"])

    assert (
        part.name == "Microsoft Visual C++ runtime (msvcp140.dll, msvcp140_1.dll, vcruntime140.dll)"
    )
    assert part.licence == MICROSOFT
    assert "Mado's licence doesn't cover it" in " ".join(part.texts[0].split())
    assert cpp_runtime([]) == []


def test_the_notices_show_each_licence_text_once():
    sections = {
        "The shell (Rust)": [
            Part("a", "1.0.0", "MIT", "https://crates.io/crates/a/1.0.0", (MIT,)),
            Part("b", "2.0.0", "MIT", "https://crates.io/crates/b/2.0.0", (MIT + "\n",)),
            Part("NSIS", "", "Zlib", "https://nsis.sourceforge.io"),
        ]
    }

    text = render("0.1.0", sections)

    assert text.startswith("Third-party notices for Mado 0.1.0\n")
    assert "  1. The shell (Rust): 3\n" in text
    assert text.count("Copyright (c) 2020 Someone") == 1
    assert "b 2.0.0\nLicence: MIT\nSource: https://crates.io/crates/b/2.0.0\n" in text
    assert "(The licence text is the same as for a 1.0.0, above.)" in text
    assert "NSIS\nLicence: Zlib\n" in text
    assert "It comes with no licence file; the licence named above applies." in text


def test_the_ai_models_mado_ships_are_listed_with_their_licences():
    found = assets()

    assert [part.name.split(" (")[-1].rstrip(")") for part in found] == [
        "realesr-general-x4v3",
        "realesr-general-wdn-x4v3",
        "realesrgan-x4plus-anime-6b",
        "u2netp",
    ]
    assert all(allowed(part.licence) for part in found)
    assert all(part.texts and "Xintao Wang" in part.texts[0] for part in found[:3])
    assert "Apache License" in found[2].texts[1]  # BasicSR's network
    cut_out = found[3]  # U²-Net's small model, converted to ONNX by rembg
    assert cut_out.licence == "Apache-2.0 AND MIT"
    assert "Apache License" in cut_out.texts[0]
    assert "Daniel Gatis" in cut_out.texts[1]


def test_onnx_runtime_is_shipped_with_microsofts_directml_inside_it():
    licence = PYTHON_LICENCES["onnxruntime-directml"]

    assert licence == f"MIT AND {MICROSOFT}"
    assert allowed(licence)


def test_tokenizers_whose_wheel_carries_no_licence_is_named_apache_with_a_note():
    assert PYTHON_LICENCES["tokenizers"] == "Apache-2.0"
    assert "Apache License" in PYTHON_NOTES["tokenizers"]
    assert "apache.org/licenses/LICENSE-2.0" in PYTHON_NOTES["tokenizers"]


def test_what_mado_downloads_is_told_apart_from_what_it_ships():
    found = {part.name: part for part in downloaded_parts()}

    assert list(found)[:2] == ["ffmpeg", "LibRaw"]
    libraw = found["LibRaw"]
    assert (libraw.version, libraw.licence) == ("0.22.3", "LGPL-2.1-only OR CDDL-1.0")
    assert not allowed(libraw.licence)  # Mado couldn't ship it: it never does
    assert "Not inside Mado" in libraw.texts[0]
    assert "https://www.libraw.org/data/LibRaw-0.22.3-Win64.zip" in libraw.texts[0]
    # Each keeps the licence files it comes with: an archive's (its `notices`), or a model's own.
    for name in ("LibRaw", "ffmpeg", "LaMa", "SCUNet", "FBCNN", "NAFNet"):
        assert "keeps its licence files beside it" in found[name].texts[0]
    # The fixes' models are on licences Mado could ship, though it only downloads them.
    for name in ("SCUNet", "FBCNN", "NAFNet"):
        assert allowed(found[name].licence), name
        assert "the first time it's needed" in found[name].texts[0]
    text = render("0.1.0", {"The installer": []}, list(found.values()))
    assert "  2. Downloaded to the PC, never shipped:" in text
    assert text.index("Downloaded to the PC, never shipped") > text.index("1. The installer")


@pytest.mark.parametrize(
    "name",
    ["libraw.dll", "LibRaw.dll", "ffmpeg.exe", "ffprobe.exe", "avcodec-62.dll", "swscale-9.dll"],
)
def test_a_bundle_carrying_what_mado_only_downloads_stops_the_build(name: str):
    assert downloaded_only(Path(r"C:\build\_internal") / name)


@pytest.mark.parametrize("name", ["python314.dll", "onnxruntime.dll", "libjpeg-62.dll", "avif.dll"])
def test_what_mado_ships_isnt_taken_for_a_download(name: str):
    assert not downloaded_only(Path(r"C:\build\_internal") / name)
