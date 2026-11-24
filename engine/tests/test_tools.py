"""The tools Mado downloads: ffmpeg on first run, checked, unpacked and found again, and an AI
model, file by file, the first time it's wanted."""

import hashlib
import io
import re
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from urllib.error import URLError

import pytest

from mado.config import DataPaths
from mado.tools import Download, File, Tools, manifest

PROGRAM = "ffprobe.exe"


def archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return buffer.getvalue()


BUILD = archive(
    {
        "ffmpeg-n9.0-win64-lgpl-shared/bin/ffprobe.exe": b"probe",
        "ffmpeg-n9.0-win64-lgpl-shared/bin/ffmpeg.exe": b"mpeg",
        "ffmpeg-n9.0-win64-lgpl-shared/bin/avcodec-63.dll": b"codecs",
        "ffmpeg-n9.0-win64-lgpl-shared/doc/ffmpeg.html": b"docs",
    }
)


def listing(data: bytes, version: str = "9.0.2") -> Download:
    """The ffmpeg entry, pointing at `data` instead of the real build."""
    ffmpeg = next(item for item in manifest() if item.id == "ffmpeg")
    return replace(ffmpeg, version=version, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def serving(data: bytes):
    def fetch(url: str) -> io.BytesIO:
        return io.BytesIO(data)

    return fetch


def offline(url: str) -> io.BytesIO:
    raise URLError("No connection could be made")


def downloaded(tools: Tools, tool: str = "ffmpeg") -> None:
    tools.start(tool)
    tools.wait(tool, timeout=10)


def test_the_list_says_what_each_download_is_and_where_it_comes_from():
    items = manifest()

    assert [item.id for item in items] == [
        "webview2",
        "ffmpeg",
        "libraw",
        "realesrgan-x4plus",
        "lama",
        "sam2.1-hiera-tiny",
        "mi-gan",
        "birefnet-lite",
        "depth-anything-v2-small",
        "siglip-base-patch16-224",
        "pp-ocrv6-small",
        "scunet",
        "fbcnn",
        "nafnet",
        "oldphoto-scratch-detector",
        "ddcolor-tiny",
        "style-van-gogh-starry-night",
        "style-hokusai-great-wave",
        "style-monet-water-lilies-1915",
        "style-seurat-gravelines",
        "microast",
    ]
    for item in items:
        addresses = [each.url for each in item.files] if item.files else [item.url]
        assert all((address or "").startswith("https://") for address in addresses)
        assert all((item.name, item.purpose, item.licence, item.home))
    for item in (item for item in items if item.by == "mado" and not item.files):
        assert (item.size or 0) > 0
        assert re.fullmatch(r"[0-9a-f]{64}", item.sha256 or "")
        assert item.keep
    for item in (item for item in items if item.files):
        assert item.size == sum(each.size for each in item.files)
        assert all(re.fullmatch(r"[0-9a-f]{64}", each.sha256) for each in item.files)
        assert all(each.size > 0 for each in item.files)


def test_ffmpeg_is_pinned_to_one_build_that_stays_online():
    ffmpeg = next(item for item in manifest() if item.id == "ffmpeg")

    # BtbN keeps each month's last build for two years; "latest" changes every day.
    assert ffmpeg.url is not None
    assert "/autobuild-" in ffmpeg.url
    assert "latest" not in ffmpeg.url
    assert ffmpeg.licence == "LGPL-2.1-or-later"
    assert ffmpeg.notices == ("LICENSE.txt",)  # its licence comes with it, kept beside it


def test_libraw_is_its_own_windows_build_fetched_the_first_time_a_raw_is_read():
    libraw = next(item for item in manifest() if item.id == "libraw")

    # LibRaw's own build, from its own site: never one built by Mado or anyone else.
    assert libraw.url == "https://www.libraw.org/data/LibRaw-0.22.3-Win64.zip"
    assert libraw.version == "0.22.3"
    assert libraw.size == 3503107
    assert libraw.sha256 == "4e2213a0b10e32199a30b9114a61376cdb40f94df861262b4a6dca659701276b"
    assert libraw.licence == "LGPL-2.1-only OR CDDL-1.0"
    assert (libraw.by, libraw.when, libraw.keep) == ("mado", "asked", "bin")
    assert libraw.notices == ("LICENSE.LGPL", "LICENSE.CDDL", "COPYRIGHT")


def test_the_ai_models_come_from_mados_own_release_the_first_time_theyre_asked_for():
    models = [item for item in manifest() if item.id in ("realesrgan-x4plus", "lama")]

    assert [item.when for item in models] == ["asked", "asked"]
    for item in models:
        assert all(
            "/frankgrobbelaar/mado/releases/download/models-1/" in each.url for each in item.files
        )
        assert any(each.name.startswith("LICENSE") for each in item.files)  # with its licence


def test_the_editing_models_come_from_mados_second_set_of_models_with_their_licences():
    models = {
        item.id: item
        for item in manifest()
        if item.id in ("sam2.1-hiera-tiny", "mi-gan", "birefnet-lite")
    }

    assert sorted(models) == ["birefnet-lite", "mi-gan", "sam2.1-hiera-tiny"]
    for item in models.values():
        assert item.when == "asked"
        assert item.licence in ("Apache-2.0", "MIT")
        assert item.size == sum(each.size for each in item.files)
        assert all(
            "/frankgrobbelaar/mado/releases/download/models-2/" in each.url for each in item.files
        )
        assert all(re.fullmatch(r"[0-9a-f]{64}", each.sha256) for each in item.files)
        assert any(each.name.startswith("LICENSE") for each in item.files)
    # SAM 2.1's two parts each keep their weights beside them, under the names they look for.
    assert [each.name for each in models["sam2.1-hiera-tiny"].files][:4] == [
        "vision_encoder.onnx",
        "vision_encoder.onnx_data",
        "prompt_encoder_mask_decoder.onnx",
        "prompt_encoder_mask_decoder.onnx_data",
    ]


def test_the_depth_model_comes_from_mados_second_set_with_its_licence():
    [item] = [each for each in manifest() if each.id == "depth-anything-v2-small"]

    assert item.name == "Depth Anything V2 Small"
    assert item.when == "asked"
    assert item.licence == "Apache-2.0"  # Small only: its bigger sizes are non-commercial
    assert item.size == sum(each.size for each in item.files) == 99072196
    assert [each.name for each in item.files] == [
        "depth-anything-v2-small.onnx",
        "LICENSE-Depth-Anything-V2.txt",
    ]
    assert all(
        "/frankgrobbelaar/mado/releases/download/models-2/" in each.url for each in item.files
    )
    assert (
        item.files[0].sha256 == "afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c"
    )


def test_the_fixes_models_come_from_mados_first_and_third_sets_with_their_licences():
    models = {item.id: item for item in manifest() if item.id in ("scunet", "fbcnn", "nafnet")}

    assert sorted(models) == ["fbcnn", "nafnet", "scunet"]
    for item in models.values():
        assert item.when == "asked"
        assert item.size == sum(each.size for each in item.files)
        assert any(each.name.startswith("LICENSE") for each in item.files)
        assert all(re.fullmatch(r"[0-9a-f]{64}", each.sha256) for each in item.files)
    sets = {name: {each.url.split("/")[-2] for each in item.files} for name, item in models.items()}
    assert sets == {"scunet": {"models-1"}, "fbcnn": {"models-1"}, "nafnet": {"models-3"}}
    # Each model's file is named as the fixes look for it.
    assert next(each.name for each in models["scunet"].files) == "scunet-color-real-psnr.onnx"
    assert next(each.name for each in models["fbcnn"].files) == "fbcnn-color.onnx"
    assert next(each.name for each in models["nafnet"].files) == "nafnet-gopro-width32.onnx"


def test_restorings_models_come_with_their_licences_named_as_restoring_looks_for_them():
    models = {
        item.id: item
        for item in manifest()
        if item.id in ("oldphoto-scratch-detector", "ddcolor-tiny")
    }

    detector, colourer = models["oldphoto-scratch-detector"], models["ddcolor-tiny"]
    assert (detector.name, detector.licence) == ("Old-photo scratch detector", "MIT")
    assert (colourer.name, colourer.licence) == ("DDColor tiny", "Apache-2.0")
    for item in (detector, colourer):
        assert item.when == "asked"
        assert item.size == sum(each.size for each in item.files)
        assert any(each.name.startswith("LICENSE") for each in item.files)
        assert all(re.fullmatch(r"[0-9a-f]{64}", each.sha256) for each in item.files)
    # Each model's file is named as mado/ai.py looks for it, in the set it was published in.
    assert detector.files[0].name == "oldphoto-scratch-detector-fp16.onnx"
    assert colourer.files[0].name == "ddcolor-tiny.onnx"
    assert all("/releases/download/models-3/" in each.url for each in detector.files)
    assert all("/releases/download/models-1/" in each.url for each in colourer.files)


def test_the_painting_styles_come_from_mados_third_set_with_their_licences():
    painters = [item for item in manifest() if item.id.startswith("style-")]
    microast = next(item for item in manifest() if item.id == "microast")

    # The four that earned their place (docs/stack/styles.md), each named after its painter.
    assert [item.name for item in painters] == [
        "After Van Gogh",
        "After Hokusai",
        "After Monet",
        "After Seurat",
    ]
    for item in [*painters, microast]:
        assert item.when == "asked"
        assert item.size == sum(each.size for each in item.files)
        assert all("/releases/download/models-3/" in each.url for each in item.files)
        assert any(each.name.startswith("LICENSE") for each in item.files)
    for item in painters:
        assert item.licence == "MIT AND BSD-3-Clause"  # Mado's own, the network's design BSD-3
        assert [each.name for each in item.files] == [
            f"{item.id}.onnx",
            "LICENSE-pytorch-examples.txt",
        ]
        assert item.files[0].size == 6887451
    assert microast.licence == "MIT"
    assert [each.name for each in microast.files] == [
        "microast-style.onnx",
        "microast-stylize.onnx",
        "LICENSE-MicroAST.txt",
    ]
    # The never-published pilot's checksum isn't the one listed.
    van_gogh = painters[0].files[0].sha256
    assert van_gogh == "73321b4fe4903555ef08ba85e5d60934d6cd670bdd6d6b052b7bcfa55a85d337"


def test_only_mados_own_downloads_are_offered_by_the_engine(paths: DataPaths):
    tools = Tools(paths, fetch=serving(BUILD))

    assert [item.id for item, _ in tools.status()] == [
        "ffmpeg",
        "libraw",
        "realesrgan-x4plus",
        "lama",
        "sam2.1-hiera-tiny",
        "mi-gan",
        "birefnet-lite",
        "depth-anything-v2-small",
        "siglip-base-patch16-224",
        "pp-ocrv6-small",
        "scunet",
        "fbcnn",
        "nafnet",
        "oldphoto-scratch-detector",
        "ddcolor-tiny",
        "style-van-gogh-starry-night",
        "style-hokusai-great-wave",
        "style-monet-water-lilies-1915",
        "style-seurat-gravelines",
        "microast",
    ]
    with pytest.raises(KeyError):
        tools.start("webview2")


def test_a_tool_is_downloaded_checked_and_unpacked_into_the_data_folder(paths: DataPaths):
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD))
    assert tools.path("ffprobe") is None

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert progress.done == len(BUILD)
    assert tools.path("ffprobe") == paths.tools / "ffmpeg" / PROGRAM
    assert (paths.tools / "ffmpeg" / "avcodec-63.dll").read_bytes() == b"codecs"
    assert not (paths.tools / "ffmpeg" / "ffmpeg.html").exists()  # only the bin folder is kept
    assert [file.name for file in paths.tools.iterdir()] == ["ffmpeg"]  # no download left behind


def test_a_tools_licence_files_are_kept_beside_it(paths: DataPaths):
    build = archive(
        {
            "LibRaw-0.22.3/bin/libraw.dll": b"reader",
            "LibRaw-0.22.3/bin/dcraw_emu.exe": b"a sample program",  # not used: not kept
            "LibRaw-0.22.3/LICENSE.LGPL": b"lesser",
            "LibRaw-0.22.3/LICENSE.CDDL": b"common",
            "LibRaw-0.22.3/COPYRIGHT": b"notice",
            "LibRaw-0.22.3/Changelog.txt": b"changes",
            "LibRaw-0.22.3/src/decoder.cpp": b"code",
        }
    )
    libraw = next(item for item in manifest() if item.id == "libraw")
    listed = replace(libraw, size=len(build), sha256=hashlib.sha256(build).hexdigest())
    tools = Tools(paths, items=(listed,), fetch=serving(build))

    downloaded(tools, "libraw")

    folder = tools.folder("libraw")
    assert folder is not None
    assert folder == paths.tools / "libraw"
    assert sorted(file.name for file in folder.iterdir()) == [
        "COPYRIGHT",
        "LICENSE.CDDL",
        "LICENSE.LGPL",
        "libraw.dll",
        "mado-download.json",
    ]
    assert (folder / "LICENSE.LGPL").read_bytes() == b"lesser"
    (folder / "COPYRIGHT").unlink()  # one gone: it's fetched again, with its licence
    assert tools.folder("libraw") is None


def test_a_download_that_doesnt_match_the_list_is_thrown_away(paths: DataPaths):
    tampered = BUILD + b"!"
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(tampered))

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem == (
        "The ffmpeg download didn't match what Mado expects, so Mado didn't use it. "
        "Try again; if it happens again, the file online has changed."
    )
    assert tools.path("ffprobe") is None
    assert not any(paths.tools.iterdir())


def test_a_download_that_didnt_match_isnt_fetched_again_by_itself_only_when_asked(
    paths: DataPaths,
):
    fetched: list[str] = []

    def tampered(url: str) -> io.BytesIO:
        fetched.append(url)
        return io.BytesIO(BUILD + b"!")

    tools = Tools(paths, items=(listing(BUILD),), fetch=tampered)
    downloaded(tools)

    tools.start("ffmpeg", by_itself=True)  # what waits for it asks again a minute on
    tools.wait("ffmpeg", timeout=10)
    assert len(fetched) == 1  # the file online isn't the one listed: not fetched over and over
    downloaded(tools)  # Try again
    assert len(fetched) == 2


def test_no_connection_says_so_and_a_retry_works(paths: DataPaths):
    item = listing(BUILD)
    tools = Tools(paths, items=(item,), fetch=offline)

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem == (
        "Mado couldn't download ffmpeg: No connection could be made. "
        "Check the internet connection, then try again."
    )

    retry = Tools(paths, items=(item,), fetch=serving(BUILD))
    downloaded(retry)
    assert retry.path("ffprobe") is not None


def test_an_archive_cant_write_outside_the_tools_folder(paths: DataPaths):
    sneaky = archive({"ffmpeg/bin/ffprobe.exe": b"probe", "ffmpeg/bin/../../../escaped.txt": b"x"})
    tools = Tools(paths, items=(listing(sneaky),), fetch=serving(sneaky))

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert "unsafe" in (progress.problem or "")
    assert not (paths.root / "escaped.txt").exists()
    assert not (paths.root.parent / "escaped.txt").exists()


def test_a_newer_build_in_the_list_replaces_the_one_installed(paths: DataPaths):
    downloaded(Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD)))
    newer = archive({"ffmpeg-n9.1/bin/ffprobe.exe": b"newer probe"})
    tools = Tools(paths, items=(listing(newer, version="9.1.0"),), fetch=serving(newer))

    [(_, before)] = tools.status()
    assert before.state == "missing"  # the installed build isn't the one listed any more
    downloaded(tools)

    assert (paths.tools / "ffmpeg" / PROGRAM).read_bytes() == b"newer probe"
    assert not (paths.tools / "ffmpeg" / "avcodec-63.dll").exists()


def test_a_development_copy_of_ffmpeg_can_stand_in(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    own = tmp_path / "ffmpeg-bin"
    own.mkdir()
    (own / PROGRAM).write_bytes(b"probe")
    monkeypatch.setenv("MADO_FFMPEG_DIR", str(own))

    tools = Tools(paths, items=(listing(BUILD),), fetch=offline)

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert tools.path("ffprobe") == own / PROGRAM


def test_the_installed_engine_never_takes_a_development_copy(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    own = tmp_path / "ffmpeg-bin"
    own.mkdir()
    (own / PROGRAM).write_bytes(b"probe")
    monkeypatch.setenv("MADO_FFMPEG_DIR", str(own))
    monkeypatch.setattr(sys, "frozen", True, raising=False)  # as the installer bundles it

    tools = Tools(paths, items=(listing(BUILD),), fetch=offline)

    [(_, progress)] = tools.status()
    assert progress.state == "missing"  # only what it downloaded and checked itself
    assert tools.path("ffprobe") is None


class Dropping(io.BytesIO):
    """A download that stops partway, as when the connection drops."""

    def read(self, size: int | None = -1, /) -> bytes:
        if self.tell() > 0:
            raise ConnectionResetError(10054, "An existing connection was forcibly closed")
        return super().read(10)


def test_a_connection_dropping_mid_download_says_so(paths: DataPaths):
    tools = Tools(paths, items=(listing(BUILD),), fetch=lambda url: Dropping(BUILD))

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem == (
        "Mado couldn't download ffmpeg: the connection dropped "
        "(An existing connection was forcibly closed). "
        "Check the internet connection, then try again."
    )
    assert not any(paths.tools.iterdir())


def test_anything_unexpected_still_ends_the_download_with_a_way_on(paths: DataPaths):
    def odd(url: str) -> io.BytesIO:
        raise ValueError("unknown url type")

    tools = Tools(paths, items=(listing(BUILD),), fetch=odd)

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"  # never stuck at "downloading"
    assert progress.problem == "Mado couldn't get ffmpeg (unknown url type). Try again."


def test_a_tool_that_stopped_working_is_offered_again(paths: DataPaths):
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD))
    downloaded(tools)

    tools.broken("ffmpeg")

    [(_, progress)] = tools.status()
    assert progress.state == "missing"
    assert tools.path("ffprobe") is None
    downloaded(tools)
    assert tools.path("ffprobe") == paths.tools / "ffmpeg" / PROGRAM


def test_a_tool_missing_one_of_its_files_is_offered_again(paths: DataPaths):
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD))
    downloaded(tools)

    (paths.tools / "ffmpeg" / "avcodec-63.dll").unlink()  # as an antivirus might

    [(_, progress)] = tools.status()
    assert progress.state == "missing"
    assert tools.path("ffprobe") is None


def test_a_development_copy_is_never_thrown_out(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    own = tmp_path / "ffmpeg-bin"
    own.mkdir()
    (own / PROGRAM).write_bytes(b"probe")
    monkeypatch.setenv("MADO_FFMPEG_DIR", str(own))
    tools = Tools(paths, items=(listing(BUILD),), fetch=offline)

    tools.broken("ffmpeg")

    assert (own / PROGRAM).exists()
    assert tools.path("ffprobe") == own / PROGRAM


MODEL_FILES = {"config.json": b"{}", "encoder_model.onnx": b"encoder" * 50, "vocab.json": b"[]"}


def model_listing(files: dict[str, bytes] = MODEL_FILES) -> Download:
    """An AI model that comes as several files, at made-up addresses."""
    listed = tuple(
        File(name, f"https://models.test/{name}", len(data), hashlib.sha256(data).hexdigest())
        for name, data in files.items()
    )
    total = sum(each.size for each in listed)
    return Download(
        "model-test",
        "Test model",
        "1",
        "Sees.",
        "MIT",
        "https://models.test",
        None,
        total,
        None,
        None,
        "mado",
        "asked",
        listed,
    )


class Serving:
    """The model's files by address, counting what's fetched."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.fetched: list[str] = []

    def __call__(self, url: str) -> io.BytesIO:
        name = url.rsplit("/", 1)[1]
        self.fetched.append(name)
        return io.BytesIO(self.files[name])


def test_a_model_is_fetched_file_by_file_each_checked(paths: DataPaths):
    tools = Tools(paths, items=(model_listing(),), fetch=Serving(MODEL_FILES))
    assert tools.folder("model-test") is None

    downloaded(tools, "model-test")

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert progress.done == sum(len(data) for data in MODEL_FILES.values())
    folder = paths.tools / "model-test"
    assert tools.folder("model-test") == folder
    assert {name: (folder / name).read_bytes() for name in MODEL_FILES} == MODEL_FILES
    assert [file.name for file in paths.tools.iterdir()] == ["model-test"]


def test_a_file_that_doesnt_match_fails_the_model_and_a_retry_fetches_only_what_is_missing(
    paths: DataPaths,
):
    tampered = Serving({**MODEL_FILES, "encoder_model.onnx": b"not the model"})
    tools = Tools(paths, items=(model_listing(),), fetch=tampered)

    downloaded(tools, "model-test")

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem is not None
    assert progress.problem.startswith("The Test model download didn't match")
    assert tools.folder("model-test") is None

    again = Serving(MODEL_FILES)
    retry = Tools(paths, items=(model_listing(),), fetch=again)
    downloaded(retry, "model-test")

    assert retry.folder("model-test") == paths.tools / "model-test"
    assert again.fetched == ["encoder_model.onnx", "vocab.json"]  # config.json came whole before


def test_a_model_missing_a_file_is_offered_again(paths: DataPaths):
    tools = Tools(paths, items=(model_listing(),), fetch=Serving(MODEL_FILES))
    downloaded(tools, "model-test")

    (paths.tools / "model-test" / "vocab.json").unlink()

    [(_, progress)] = tools.status()
    assert progress.state == "missing"
    assert tools.folder("model-test") is None


def test_a_development_copy_of_a_model_can_stand_in(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    own = tmp_path / "model"
    own.mkdir()
    monkeypatch.setenv("MADO_MODEL_TEST_DIR", str(own))

    tools = Tools(paths, items=(model_listing(),), fetch=offline)

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert tools.folder("model-test") == own
