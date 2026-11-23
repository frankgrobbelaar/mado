"""Editing by clicking, in the engine: picking parts, the edits made in order at full size, what's
kept (in memory, and each mask in the cache, made again from its clicks when that's gone), and
looks on a part. SAM and the erasing models are stand-ins (tests/edit_models.py); U²-Net, which
Mado ships, is the real one on the processor."""

import contextlib
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mado import editing
from mado.ai import Ai
from mado.config import DataPaths
from mado.core.edits import Blur, Click, CutOut, Edit, Erase, Part, Stroke, Subject
from mado.cutting import cut
from mado.directml import Sessions
from mado.editing import EditingError, Editor, picture_key
from mado.tools import Tools
from tests.conftest import ON_PROCESSOR
from tests.drawn import sailboat
from tests.edit_models import FakeSam, with_editing_models

SAIL = (0.6375, 0.517)  # a click on the boat's bigger sail
SKY = (0.1, 0.05)
SEA = (0.5, 0.95)


@pytest.fixture
def boat() -> tuple[Image.Image, np.ndarray]:
    return sailboat((800, 600))


@pytest.fixture
def models(paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Ai, FakeSam]:
    ai = Ai(Sessions(), Tools(paths), lambda: ON_PROCESSOR, room=lambda: None)
    return ai, with_editing_models(monkeypatch, ai, tmp_path / "models")


@pytest.fixture
def editor(models: tuple[Ai, FakeSam], paths: DataPaths) -> Editor:
    return Editor(models[0], paths.cache / "edits")


KEY = picture_key(Path("D:/Pictures/Little sail.jpg"), "18f3-4c2b")


def _sail() -> Part:
    return Part((Click(*SAIL),), choice=1)


def test_a_click_reads_the_picture_once_and_picks_the_part_round_it(
    editor: Editor, models: tuple[Ai, FakeSam], boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat
    sam = models[1]

    first = editor.pick(image, KEY, (), (), Click(*SAIL))

    assert len(first.parts) == 1
    assert first.parts[0].clicks == (Click(*SAIL),)
    assert first.parts[0].choice == 1  # the answer SAM is surest of
    assert first.read is not None
    assert first.outline.startswith("M")
    assert first.place == "processor"
    again = editor.pick(image, KEY, (), first.parts, Click(*SKY))
    assert len(again.parts) == 2
    assert again.read is None  # read once: every click after that is the picking alone
    assert sam.reads == 1


def test_an_alt_click_takes_from_the_part_its_in_and_one_outside_every_part_says_so(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat
    picked = editor.pick(image, KEY, (), (_sail(),), None)

    taken = editor.pick(image, KEY, (), picked.parts, Click(*SAIL, keep=False))
    missed = editor.pick(image, KEY, (), picked.parts, Click(*SEA, keep=False))

    assert taken.parts[0].clicks == (Click(*SAIL), Click(*SAIL, keep=False))
    assert not taken.missed
    assert taken.outline == ""  # the stand-in took the whole sail away
    assert missed.missed
    assert missed.parts == picked.parts


def test_an_erase_fills_the_part_and_leaves_the_rest_of_the_picture_exactly_as_it_was(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, mask = boat

    erased = editor.state(image, KEY, (Erase((_sail(),)),))

    before, after = np.asarray(image), np.asarray(erased)
    sail_middle = (int(0.6 * 600 / 1.2), int(0.64 * 800))
    assert tuple(before[sail_middle]) == (255, 255, 255)
    assert tuple(after[sail_middle]) != (255, 255, 255)
    far = np.zeros(mask.shape, bool)
    far[:, :200] = True  # the sun and the sky well away from the boat
    assert (after[far] == before[far]).all()
    assert erased.size == image.size


def test_brush_strokes_are_erased_and_what_alt_took_away_stays(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat
    sun = (255, 246, 216)
    strokes = (
        Stroke(((0.2, 0.233), (0.25, 0.233)), 0.15),  # across the sun
        Stroke(((0.225, 0.233),), 0.06, take=True),  # its middle taken back out
    )

    erased = np.asarray(editor.state(image, KEY, (Erase(strokes=strokes),)))

    before = np.asarray(image)
    assert tuple(before[140, 150]) == tuple(before[140, 180]) == sun
    assert tuple(erased[140, 150]) != sun  # painted: erased
    assert tuple(erased[140, 180]) == sun  # taken back out: as it was
    assert (erased[500:, :] == before[500:, :]).all()  # nowhere near the strokes


def test_a_part_cut_out_onto_nothing_keeps_the_whole_picture_under_its_see_through_parts(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat

    cut = editor.state(image, KEY, (CutOut((_sail(),), "nothing"),))

    assert cut.mode == "RGBA"
    alpha = np.asarray(cut.getchannel("A"))
    assert alpha[300, 512] > 200  # the sail
    assert alpha[30, 80] == 0  # the sky
    assert (np.asarray(cut.convert("RGB")) == np.asarray(image)).all()


def test_a_part_cut_out_onto_a_colour_or_the_rest_blurred(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat

    coloured = np.asarray(editor.state(image, KEY, (CutOut((_sail(),), "colour", (10, 20, 30)),)))
    blurred = np.asarray(editor.state(image, KEY, (CutOut((_sail(),), "blurred"),)))

    assert tuple(coloured[30, 80]) == (10, 20, 30)
    assert coloured[300, 512].min() > 200  # the sail stays
    sun_edge = np.asarray(image)[140, 126:146].astype(int)  # across the sun's left edge
    assert (
        np.abs(np.diff(blurred[140, 126:146].astype(int), axis=0)).max()
        < np.abs(np.diff(sun_edge, axis=0)).max()
    )


def test_what_s_behind_a_part_is_blurred_and_the_part_stays_sharp(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat

    blurred = np.asarray(editor.state(image, KEY, (Blur((_sail(),)),))).astype(int)

    before = np.asarray(image).astype(int)
    assert np.abs(blurred[290:310, 505:520] - before[290:310, 505:520]).max() <= 2  # the sail
    edge = slice(126, 146)  # across the sun's left edge
    assert (
        np.abs(np.diff(blurred[140, edge], axis=0)).max()
        < np.abs(np.diff(before[140, edge], axis=0)).max()
    )


def test_the_subject_is_found_without_a_click_by_the_shipped_model(
    editor: Editor,
):
    ground = Image.new("RGB", (480, 360), (40, 70, 140))
    ImageDraw.Draw(ground).ellipse([170, 110, 310, 250], fill=(235, 60, 40))

    cut = editor.state(ground, KEY, (Subject("fast", "nothing"),))

    alpha = np.asarray(cut.getchannel("A"))
    assert alpha[180, 240] > 128  # the disc
    assert alpha[10, 10] < 64  # the ground


def test_edits_are_kept_and_their_masks_made_again_without_picking_once_memory_lets_them_go(
    editor: Editor,
    models: tuple[Ai, FakeSam],
    paths: DataPaths,
    boat: tuple[Image.Image, np.ndarray],
):
    image, _mask = boat
    ai, sam = models
    edits = (Erase((_sail(),)), CutOut((Part((Click(*SEA),), choice=1),), "nothing"))

    made = editor.state(image, KEY, edits)

    assert editor.state(image, KEY, edits) is made
    kept = list((paths.cache / "edits").rglob("*.png"))
    assert len(kept) == 2  # each edit's mask, in a folder for the picture and its version
    assert kept[0].parent.name == "18f3-4c2b"
    reads = sam.reads
    fresh = Editor(ai, paths.cache / "edits")  # Mado started again: nothing in memory
    again = fresh.state(image, KEY, edits)
    assert sam.reads == reads  # the masks came from the cache, not from picking again
    assert (np.asarray(again) == np.asarray(made)).all()


def test_a_kept_mask_the_picture_no_longer_fits_is_made_again(
    editor: Editor,
    models: tuple[Ai, FakeSam],
    paths: DataPaths,
    boat: tuple[Image.Image, np.ndarray],
):
    image, _mask = boat
    edits = (Erase((_sail(),)),)
    made = np.asarray(editor.state(image, KEY, edits))
    for kept in (paths.cache / "edits").rglob("*.png"):
        Image.new("L", (40, 30), 255).save(kept)  # as if a later Mado read the file at 40 x 30

    again = Editor(models[0], paths.cache / "edits").state(image, KEY, edits)

    assert (np.asarray(again) == made).all()


def test_edits_made_for_a_batch_keep_nothing_once_theyre_made(
    editor: Editor, paths: DataPaths, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat
    key = picture_key(Path("D:/Pictures/Tide pool.jpg"), "1a-2b")
    edits = (Subject("fast", "colour", (255, 255, 255)),)

    editor.state(image, key, edits, keep=False)

    assert not list((paths.cache / "edits").rglob("*"))  # no mask kept for a month
    assert editor.state(image, KEY, (Erase((_sail(),)),)) is editor.state(
        image, KEY, (Erase((_sail(),)),)
    )  # what the owner edits is kept as before


def test_two_threads_making_one_pictures_edits_never_wait_on_each_other(
    editor: Editor, boat: tuple[Image.Image, np.ndarray], monkeypatch: pytest.MonkeyPatch
):
    """Three edits made on one thread and the first two on another, from nothing kept: each
    step's lock used to be its own, so with two of them sharing one of the locks each thread
    could hold one and wait for the other's."""
    image, _mask = boat
    edits: tuple[Edit, ...] = (
        Erase((_sail(),)),
        Erase(strokes=(Stroke(((0.2, 0.233),), 0.05),)),
        Erase(strokes=(Stroke(((0.8, 0.1),), 0.05),)),
    )
    digest = vars(editing)["_digest"]
    shared = {digest(KEY, edits[:1]), digest(KEY, edits)}
    both_hold = threading.Barrier(2)

    def stepped(key: str, made: tuple[Edit, ...]) -> str:
        if (threading.current_thread().name, len(made)) in {("three", 2), ("two", 1)}:
            with contextlib.suppress(threading.BrokenBarrierError):
                both_hold.wait(timeout=2)  # each holds a step's lock now
        return digest(key, made)

    def bucket(value: object) -> int:  # the first step and the third share a lock
        return 0 if value in shared else 1

    monkeypatch.setattr(editing, "_digest", stepped)
    monkeypatch.setattr(editing, "hash", bucket, raising=False)
    made: dict[str, Image.Image] = {}

    def making(name: str, upto: int) -> threading.Thread:
        def run() -> None:
            made[name] = editor.state(image, KEY, edits[:upto])

        return threading.Thread(target=run, name=name, daemon=True)

    three, two = making("three", 3), making("two", 2)
    three.start()
    two.start()
    three.join(timeout=20)
    two.join(timeout=20)

    assert sorted(made) == ["three", "two"]


def test_a_see_through_part_cut_out_onto_a_colour_shows_the_colour_through_it():
    pixels = np.zeros((60, 80, 4), np.uint8)
    pixels[...] = (200, 30, 30, 255)
    pixels[25:35, 35:45, 3] = 0  # a hole in the picture itself
    picture = Image.fromarray(pixels, "RGBA")
    mask = np.zeros((60, 80), np.uint8)
    mask[10:50, 20:60] = 255

    coloured = np.asarray(cut(picture, mask, "colour", (0, 0, 255)))

    assert tuple(coloured[30, 40]) == (0, 0, 255)  # the hole: the colour, not grey
    assert tuple(coloured[15, 25]) == (200, 30, 30)  # the part
    assert tuple(coloured[5, 5]) == (0, 0, 255)  # outside it


def test_a_see_through_part_cut_out_onto_the_rest_blurred_keeps_its_own_colours():
    pixels = np.zeros((60, 80, 4), np.uint8)
    pixels[...] = (200, 30, 30, 255)
    pixels[25:35, 35:45, 3] = 128  # half see-through, in the picture itself
    picture = Image.fromarray(pixels, "RGBA")
    mask = np.zeros((60, 80), np.uint8)
    mask[10:50, 20:60] = 255

    blurred = np.asarray(cut(picture, mask, "blurred", (0, 0, 0)))

    assert tuple(blurred[30, 40]) == (200, 30, 30, 128)  # its colour, as see-through as it was
    assert tuple(blurred[15, 25]) == (200, 30, 30, 255)


def test_a_look_on_a_part_fades_in_at_its_edge(
    editor: Editor, boat: tuple[Image.Image, np.ndarray]
):
    image, _mask = boat

    mask = editor.look_mask(image, KEY, (), (Part((Click(*SEA),), choice=1),))

    assert mask[590, 400] == 255  # the sea where it was clicked
    assert mask[20, 400] == 0  # the sky
    column = mask[:, 100]  # down across the part's top edge
    assert ((column > 0) & (column < 255)).any()


def test_a_picture_too_big_to_edit_says_so(
    editor: Editor, boat: tuple[Image.Image, np.ndarray], monkeypatch: pytest.MonkeyPatch
):
    image, _mask = boat
    monkeypatch.setattr(editing, "MOST_PIXELS", 100_000)

    with pytest.raises(EditingError, match="megapixels"):
        editor.state(image, KEY, (Erase((_sail(),)),))
    with pytest.raises(EditingError, match="Size tab"):  # said before a part is picked
        editor.pick(image, KEY, (), (), Click(*SAIL))
    with pytest.raises(EditingError, match="megapixels"):
        editor.look_mask(image, KEY, (), (_sail(),))


def test_a_fill_much_smoother_than_whats_round_it_has_smeared(editor: Editor):
    squares = (np.indices((400, 400)) // 12).sum(axis=0) % 2  # a crisp check
    busy = Image.fromarray(np.where(squares[..., None] == 1, 230, 30).astype(np.uint8).repeat(3, 2))
    flat = Image.new("RGB", (400, 400), (90, 140, 200))
    stroke = (Stroke(((0.5, 0.5),), 0.2),)

    editor.state(busy, "busy|1", (Erase(strokes=stroke),))
    editor.state(flat, "flat|1", (Erase(strokes=stroke),))

    busy_made = editor.made("busy|1", (Erase(strokes=stroke),))
    flat_made = editor.made("flat|1", (Erase(strokes=stroke),))
    assert busy_made is not None
    assert busy_made.smeared
    assert flat_made is not None
    assert not flat_made.smeared
