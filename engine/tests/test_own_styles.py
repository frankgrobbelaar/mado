"""The owner's own painting styles: a picture's style kept as its 512 numbers with a small copy of
the picture (never the picture itself), found again by its id, renamed and deleted, named as the
owner says but never as one of Mado's; and any style a recipe names, found."""

import sqlite3
from datetime import datetime

import numpy as np
import pytest

from mado import own_styles
from mado.core.painting import code_text
from mado.own_styles import StyleNameError

NOW = datetime.fromisoformat("2026-11-24T10:30:00+02:00")
CODE = np.linspace(-2, 2, 512, dtype=np.float32)
THUMBNAIL = b"RIFF\x10\x00\x00\x00WEBPVP8 tiny"  # what's stored is what was given


def test_a_style_is_kept_as_its_numbers_and_a_small_copy_and_found_again(
    conn: sqlite3.Connection,
):
    kept = own_styles.kept(conn, "Lantern glow", CODE, THUMBNAIL, "Night market.jpg", NOW)

    assert kept.id.startswith("yours-")
    assert kept.name == "Lantern glow"
    assert kept.source == "Night market.jpg"
    found = own_styles.found(conn, kept.id)
    assert found is not None
    style = found[1]
    assert style.kind == "picture"
    assert style.name == "Lantern glow"
    assert style.code is not None
    assert np.array_equal(style.code, CODE)
    assert own_styles.thumbnail(conn, kept.id) == THUMBNAIL
    # Only the numbers and the small copy: 2 KB and a few, nothing the size of a picture.
    row = conn.execute(
        "SELECT length(code) AS code, length(thumbnail) AS small FROM styles"
    ).fetchone()
    assert row["code"] == 2048


def test_a_name_is_the_owners_but_never_taken_twice_or_one_of_mados(conn: sqlite3.Connection):
    own_styles.kept(conn, "Lantern glow", CODE, THUMBNAIL, "a.jpg", NOW)

    with pytest.raises(StyleNameError, match="already"):
        own_styles.kept(conn, "LANTERN GLOW", CODE, THUMBNAIL, "b.jpg", NOW)
    with pytest.raises(StyleNameError, match="Mado's own"):
        own_styles.kept(conn, "After Van Gogh", CODE, THUMBNAIL, "c.jpg", NOW)
    with pytest.raises(StyleNameError, match="name"):
        own_styles.kept(conn, "   ", CODE, THUMBNAIL, "d.jpg", NOW)
    with pytest.raises(StyleNameError, match="60"):
        own_styles.kept(conn, "x" * 61, CODE, THUMBNAIL, "e.jpg", NOW)


def test_a_style_is_renamed_and_deleted_and_its_number_never_given_again(
    conn: sqlite3.Connection,
):
    first = own_styles.kept(conn, "Lantern glow", CODE, THUMBNAIL, "a.jpg", NOW)

    renamed = own_styles.renamed(conn, first.id, "Evening lanterns")
    assert renamed is not None
    assert renamed.name == "Evening lanterns"
    assert own_styles.deleted(conn, first.id)
    assert own_styles.found(conn, first.id) is None
    second = own_styles.kept(conn, "Lantern glow", CODE, THUMBNAIL, "a.jpg", NOW)
    assert second.id != first.id  # a recipe naming the first fails rather than take this one
    assert not own_styles.deleted(conn, first.id)
    assert own_styles.renamed(conn, "yours-999", "Anything") is None


def test_a_recipes_style_is_found_by_its_id_or_carried_whole(conn: sqlite3.Connection):
    kept = own_styles.kept(conn, "Lantern glow", CODE, THUMBNAIL, "a.jpg", NOW)

    mados = own_styles.resolve(conn, {"style": "hokusai"})
    yours = own_styles.resolve(conn, {"style": kept.id})
    carried = own_styles.resolve(
        conn, {"style": "picture", "code": code_text(CODE), "named": "Night market"}
    )

    assert mados is not None
    assert mados.name == "After Hokusai"
    assert yours is not None
    assert yours.name == "Lantern glow"
    assert carried is not None
    assert carried.name == "Night market style"
    assert carried.code is not None
    assert np.array_equal(carried.code, CODE)
    assert own_styles.resolve(conn, {"style": "yours-999"}) is None
    assert own_styles.resolve(conn, {"style": "klimt"}) is None
    assert own_styles.resolve(conn, {"style": "picture", "code": "broken"}) is None


def test_the_owners_styles_are_listed_oldest_first(conn: sqlite3.Connection):
    own_styles.kept(conn, "B style", CODE, THUMBNAIL, "b.jpg", NOW)
    own_styles.kept(conn, "A style", CODE, THUMBNAIL, "a.jpg", NOW)

    assert [kept.name for kept in own_styles.listed(conn)] == ["B style", "A style"]
