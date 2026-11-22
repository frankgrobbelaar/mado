"""The smaller copies the window shows: a thumbnail, a screen-sized view and a full-size copy."""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from mado import previews as mado_previews
from mado.config import DataPaths
from mado.core.files import Kind
from mado.pictures import NeedsFfmpegError, UnreadableError
from mado.previews import FULL_KEPT, Previews, Source, save_copy
from tests.drawn import draw, exif, picture
from tests.heif_files import heif

FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]


FORMATS = {".jpg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".heic": "HEIC"}


def source(path: Path, number: int = 1, *, problem: str | None = None, raw: bool = False) -> Source:
    stat = path.stat()
    kind: Kind = "raw" if raw else "heif" if path.suffix == ".heic" else "picture"
    return Source(
        id=number,
        path=path,
        kind=kind,
        format=FORMATS.get(path.suffix),
        version=f"{stat.st_mtime_ns:x}-{stat.st_size:x}",
        problem=problem,
    )


@pytest.fixture
def previews(paths: DataPaths) -> Previews:
    return Previews(paths, ffmpeg=lambda: None)


def test_a_thumbnail_is_made_once_about_512_pixels_and_kept(
    previews: Previews, paths: DataPaths, tmp_path: Path
):
    picture = source(draw(tmp_path / "IMG.jpg", size=(2000, 1500)))

    made = previews.thumbnail(picture)
    stamp = made.stat().st_mtime_ns

    assert made.is_relative_to(paths.cache)
    with Image.open(made) as thumbnail:
        assert (thumbnail.format, thumbnail.size) == ("WEBP", (512, 384))
    assert previews.thumbnail(picture) == made
    assert made.stat().st_mtime_ns == stamp  # kept, not made again


def test_a_thumbnail_is_turned_the_way_the_picture_is_shown(previews: Previews, tmp_path: Path):
    picture = source(draw(tmp_path / "IMG.jpg", size=(640, 480), described=exif(orientation=6)))

    with Image.open(previews.thumbnail(picture)) as thumbnail:
        assert thumbnail.size == (384, 512)


def test_a_picture_that_changes_gets_new_copies(previews: Previews, tmp_path: Path):
    path = draw(tmp_path / "IMG.jpg", size=(640, 480))
    before = previews.thumbnail(source(path))

    draw(path, size=(480, 640))
    os.utime(path, (1, 1))
    after = previews.thumbnail(source(path))

    assert after != before
    with Image.open(after) as thumbnail:
        assert thumbnail.size == (384, 512)


def test_a_view_is_the_size_of_a_screen_and_never_bigger_than_the_picture(
    previews: Previews, tmp_path: Path
):
    big = source(draw(tmp_path / "big.png", size=(3000, 2000)), number=1)
    small = source(draw(tmp_path / "small.png", size=(800, 600)), number=2)

    with Image.open(previews.view(big)) as view:
        assert view.size == (2560, 1707)
    with Image.open(previews.view(small)) as view:
        assert view.size == (800, 600)


def test_a_format_the_window_shows_itself_is_shown_at_full_size_as_it_is(
    previews: Previews, tmp_path: Path
):
    path = draw(tmp_path / "IMG.jpg")

    assert previews.full(source(path)) == (path, "image/jpeg")


def test_a_format_the_window_cant_show_gets_a_full_size_copy_and_only_a_few_are_kept(
    previews: Previews, paths: DataPaths, tmp_path: Path
):
    made = [
        previews.full(source(draw(tmp_path / f"scan {n}.tif", size=(90, 60)), number=n))
        for n in range(1, FULL_KEPT + 3)
    ]

    last, media = made[-1]
    assert media == "image/png"
    with Image.open(last) as copy:
        assert (copy.format, copy.size) == ("PNG", (90, 60))
    kept = sorted(paths.cache.glob("full/*.png"))
    assert len(kept) == FULL_KEPT
    assert not made[0][0].exists()  # the oldest went


def test_forgetting_a_picture_takes_its_copies_away(
    previews: Previews, paths: DataPaths, tmp_path: Path
):
    first = source(draw(tmp_path / "first.tif"), number=1)
    second = source(draw(tmp_path / "second.tif"), number=2)
    for each in (first, second):
        previews.thumbnail(each)
        previews.view(each)
        previews.full(each)

    previews.forget([1])

    left = {path.name.split("-")[0] for path in paths.cache.rglob("*.*")}
    assert left == {"2"}


def test_a_copy_being_sent_while_the_same_one_is_made_again_stays_as_it_is(tmp_path: Path):
    target = tmp_path / "cache" / "1-v-thumbnail.webp"
    save_copy(picture((40, 30)), target, "WEBP")
    sent = target.open("rb")  # the window reading it: Windows won't replace it meanwhile
    try:
        save_copy(picture((40, 30)), target, "WEBP")
    finally:
        sent.close()

    assert sorted(path.name for path in target.parent.iterdir()) == [target.name]  # no leftover


def test_forgetting_a_picture_whose_copy_is_being_sent_takes_the_rest_away(
    previews: Previews, paths: DataPaths, tmp_path: Path
):
    picture_source = source(draw(tmp_path / "first.tif"), number=1)
    thumbnail = previews.thumbnail(picture_source)
    view = previews.view(picture_source)
    sent = thumbnail.open("rb")
    try:
        previews.forget([1])
    finally:
        sent.close()

    assert not view.exists()
    assert thumbnail.exists()  # left for now: its name says its version, so it's never shown wrong


def test_the_oldest_full_size_copy_being_sent_is_kept_for_now(previews: Previews, tmp_path: Path):
    first, _ = previews.full(source(draw(tmp_path / "scan 1.tif"), number=1))
    sent = first.open("rb")
    try:
        for n in range(2, FULL_KEPT + 3):
            previews.full(source(draw(tmp_path / f"scan {n}.tif"), number=n))
    finally:
        sent.close()

    assert first.exists()


def test_a_picture_that_wont_open_or_isnt_readable_yet_has_no_copies(
    previews: Previews, tmp_path: Path
):
    path = draw(tmp_path / "IMG.jpg")

    with pytest.raises(UnreadableError, match="half copied"):
        previews.thumbnail(source(path, problem="The file is damaged or was only half copied."))
    with pytest.raises(UnreadableError, match="RAW"):
        previews.view(source(path, raw=True))


def test_a_heif_needs_ffmpeg_for_its_copies(previews: Previews, tmp_path: Path):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif(width=64, height=48))

    with pytest.raises(NeedsFfmpegError):
        previews.thumbnail(source(path))


def test_a_heif_gets_its_copies_through_ffmpeg(paths: DataPaths, tmp_path: Path):
    path = tmp_path / "IMG.heic"
    path.write_bytes(heif(width=64, height=48))
    previews = Previews(paths, ffmpeg=lambda: FFMPEG)

    with Image.open(previews.thumbnail(source(path))) as thumbnail:
        assert thumbnail.size == (64, 48)
    full, media = previews.full(source(path))
    assert media == "image/png"
    assert full.is_relative_to(paths.cache)


def test_a_copy_asked_for_twice_at_once_is_made_once(
    previews: Previews, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    picture = source(draw(tmp_path / "IMG.jpg", size=(800, 600)))
    decoded: list[Path] = []
    real = mado_previews.decode

    def slow(path: Path, kind: Kind, **options: Any) -> Image.Image:
        decoded.append(path)
        time.sleep(0.2)  # long enough for the second ask to come while the first is made
        return real(path, kind, **options)

    monkeypatch.setattr(mado_previews, "decode", slow)
    with ThreadPoolExecutor(2) as pool:
        asks = [pool.submit(previews.thumbnail, picture) for _ in range(2)]
        made = [ask.result() for ask in asks]

    assert made[0] == made[1]
    assert decoded == [picture.path]
