"""The owner's own looks: a .cube file imported, a mix kept, renamed and deleted, kept small in
the database, and named as the owner says, never as one of Mado's looks."""

import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from mado import own_looks
from mado.core.cube import CubeError, read
from mado.core.grids import SIDE, blended, identity
from mado.core.looks import mado_look
from mado.core.touches import Touches
from mado.own_looks import LookNameError

NOW = datetime.fromisoformat("2026-11-22T21:30:00+02:00")


def _cube(path: Path, points: int = 17, title: str | None = "Holiday warm") -> Path:
    grid = identity(points) ** 0.9  # a gentle lift: a look of the owner's own
    header = f'TITLE "{title}"\n' if title else ""
    rows = "\n".join(f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in grid.reshape(-1, 3).tolist())
    path.write_text(f"# made by hand\n{header}LUT_3D_SIZE {points}\n{rows}\n", encoding="utf-8")
    return path


def test_a_cube_file_is_kept_small_and_named_after_its_title(
    conn: sqlite3.Connection, tmp_path: Path
):
    path = _cube(tmp_path / "warm.cube", points=65)

    kept = own_looks.imported(conn, path, NOW)

    assert kept.name == "Holiday warm"
    assert kept.kind == "cube"
    assert kept.points == 65
    assert kept.source == "warm.cube"
    assert kept.id.startswith("yours-")
    stored = conn.execute("SELECT length(grid) FROM looks").fetchone()[0]
    assert stored < path.stat().st_size / 20  # tens of kilobytes, not 7 MB
    look = own_looks.resolve(conn, kept.id)
    assert look is not None
    assert look.grid is not None
    assert np.allclose(look.grid, identity(65) ** 0.9, atol=1e-4)


def test_a_cube_file_without_a_title_is_named_after_its_file_and_numbered_when_taken(
    conn: sqlite3.Connection, tmp_path: Path
):
    first = own_looks.imported(conn, _cube(tmp_path / "Teal pop.cube", title=None), NOW)
    second = own_looks.imported(conn, _cube(tmp_path / "teal POP.cube", title=None), NOW)
    mados = own_looks.imported(conn, _cube(tmp_path / "x.cube", title="Silver"), NOW)

    assert first.name == "Teal pop"
    assert second.name == "teal POP (2)"
    assert mados.name == "Silver (2)"  # Silver is one of Mado's own


def test_a_long_title_taken_is_cut_to_fit_its_number(conn: sqlite3.Connection, tmp_path: Path):
    title = "A long look made for evenings by the harbour, warm and soft"  # 59 letters

    first = own_looks.imported(conn, _cube(tmp_path / "a.cube", title=title), NOW)
    second = own_looks.imported(conn, _cube(tmp_path / "b.cube", title=title), NOW)

    assert first.name == title
    assert second.name.endswith(" (2)")
    assert len(second.name) <= own_looks.LONGEST
    assert second.name.startswith(title[:50])


def test_a_deleted_looks_id_is_never_given_to_another(conn: sqlite3.Connection):
    original = mado_look("original")
    assert original is not None
    own_looks.kept(conn, "One", original, 1.0, Touches(grain=10), NOW)
    second = own_looks.kept(conn, "Two", original, 1.0, Touches(grain=20), NOW)
    own_looks.deleted(conn, second.id)

    third = own_looks.kept(conn, "Three", original, 1.0, Touches(grain=30), NOW)

    assert third.id != second.id
    assert own_looks.resolve(conn, second.id) is None  # a job still naming Two fails, safely


def test_names_are_one_name_however_their_letters_are_written(conn: sqlite3.Connection):
    original = mado_look("original")
    assert original is not None
    own_looks.kept(conn, "Été chaud", original, 1.0, Touches(grain=10), NOW)

    with pytest.raises(LookNameError, match="You have a look called Été chaud already"):
        own_looks.kept(conn, "ÉTÉ CHAUD", original, 1.0, Touches(grain=10), NOW)


def test_a_file_mado_cant_use_says_why(conn: sqlite3.Connection, tmp_path: Path):
    (tmp_path / "notes.cube").write_text("these are my notes\n", encoding="utf-8")
    (tmp_path / "photo.cube").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

    with pytest.raises(CubeError, match="it has no table of colours in it"):
        own_looks.imported(conn, tmp_path / "notes.cube", NOW)
    with pytest.raises(CubeError, match="it isn't text"):
        own_looks.imported(conn, tmp_path / "photo.cube", NOW)
    with pytest.raises(CubeError, match=r"couldn't find gone.cube"):
        own_looks.imported(conn, tmp_path / "gone.cube", NOW)
    assert own_looks.listed(conn) == []


def test_a_file_too_big_is_refused_before_its_read(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("mado.core.cube.MOST_BYTES", 100)
    path = _cube(tmp_path / "big.cube", points=3)

    with pytest.raises(CubeError, match="bigger than any look Mado reads"):
        own_looks.imported(conn, path, NOW)


def test_a_mix_is_kept_as_its_look_at_its_strength_with_its_touches(conn: sqlite3.Connection):
    warm = mado_look("warm-film")
    assert warm is not None
    assert warm.grid is not None

    kept = own_looks.kept(conn, "  Holiday   warm ", warm, 0.6, Touches(grain=20, vignette=35), NOW)

    assert kept.name == "Holiday warm"
    assert kept.kind == "mix"
    assert kept.touches == Touches(grain=20, vignette=35)
    assert kept.source == "Warm film at 60%, grain 20, vignette 35"
    look = own_looks.resolve(conn, kept.id)
    assert look is not None
    assert look.grid is not None
    assert np.allclose(look.grid, blended(warm.grid, 0.6), atol=1e-4)


def test_a_mix_of_the_original_keeps_its_colours_and_its_touches(conn: sqlite3.Connection):
    original = mado_look("original")
    assert original is not None

    kept = own_looks.kept(conn, "Dusty", original, 1.0, Touches(dust=40), NOW)

    look = own_looks.resolve(conn, kept.id)
    assert look is not None
    assert look.grid is not None
    assert np.allclose(look.grid, identity(SIDE), atol=1e-4)
    assert kept.touches == Touches(dust=40)
    assert kept.source == "Dust 40"  # what the mix is made of, named


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("   ", "Give it a name first."),
        ("x" * 61, "Keep its name to 60 letters or fewer."),
        ("warm FILM", "warm FILM is one of Mado's own looks. Pick another name."),
        ("holiday WARM", "You have a look called Holiday warm already. Pick another name."),
    ],
)
def test_a_name_a_look_cant_have_says_why(conn: sqlite3.Connection, name: str, said: str):
    original = mado_look("original")
    assert original is not None
    own_looks.kept(conn, "Holiday warm", original, 1.0, Touches(grain=10), NOW)

    with pytest.raises(LookNameError) as refused:
        own_looks.kept(conn, name, original, 1.0, Touches(grain=10), NOW)

    assert str(refused.value) == said


def test_a_look_is_renamed_and_deleted(conn: sqlite3.Connection):
    original = mado_look("original")
    assert original is not None
    first = own_looks.kept(conn, "Holiday warm", original, 1.0, Touches(grain=10), NOW)
    own_looks.kept(conn, "Night city", original, 1.0, Touches(glow=30), NOW)

    renamed = own_looks.renamed(conn, first.id, "Summer warm")
    same = own_looks.renamed(conn, first.id, "SUMMER warm")  # its own name, another way

    assert renamed is not None
    assert renamed.name == "Summer warm"
    assert same is not None
    assert same.name == "SUMMER warm"
    with pytest.raises(LookNameError, match="Night city already"):
        own_looks.renamed(conn, first.id, "night city")
    assert own_looks.renamed(conn, "yours-99", "Gone") is None
    assert own_looks.deleted(conn, first.id)
    assert not own_looks.deleted(conn, first.id)
    assert [each.name for each in own_looks.listed(conn)] == ["Night city"]
    assert own_looks.resolve(conn, first.id) is None


def test_a_look_is_written_out_as_a_cube_file_another_app_reads(conn: sqlite3.Connection):
    warm = mado_look("warm-film")
    assert warm is not None
    assert warm.grid is not None

    text = own_looks.cube_text('Holiday "warm"', warm.grid)

    back = read(text)
    assert back.title == "Holiday 'warm'"
    assert np.allclose(back.grid, warm.grid, atol=1e-5)


def test_mados_own_looks_are_found_by_their_ids_too(conn: sqlite3.Connection):
    found = own_looks.resolve(conn, "teal-and-orange")

    assert found is not None
    assert found.name == "Teal and orange"
    assert own_looks.resolve(conn, "yours-x") is None
    assert own_looks.resolve(conn, "kodachrome") is None
