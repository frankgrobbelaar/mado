"""Searching: a search as SigLIP reads it, its own score and the cut that leaves out what isn't
there, More like this, a search's language and writing, and words matched however they're
written, with the matches marked."""

import numpy as np
import pytest

from mado.core.search import (
    BEST_READS,
    CUT,
    END,
    TOKENS,
    Piece,
    canonical,
    described,
    first_seen,
    folded,
    in_english,
    index_terms,
    likeness_for,
    marked,
    match_query,
    nearest,
    padded,
    scores,
    scripts_of,
    unit,
    unreadable,
    words_of,
)


def test_a_search_is_canonicalised_as_siglips_own_tokenizer_does():
    assert canonical("  A Red boat,  on the SEA! ") == "a red boat on the sea"
    assert canonical("well-lit") == "welllit"  # punctuation goes, as SiglipTokenizer takes it


def test_a_search_is_ended_and_padded_to_exactly_64_tokens():
    ids = padded([262, 266, 1226, END])

    assert len(ids) == TOKENS
    assert ids[:3] == [262, 266, 1226]
    assert ids[3:] == [END] * (TOKENS - 3)


def test_a_long_search_is_cut_and_still_ends():
    ids = padded(list(range(2, 200)))

    assert len(ids) == TOKENS
    assert ids[-1] == END
    assert ids[: TOKENS - 1] == list(range(2, 2 + TOKENS - 1))


def test_the_score_is_siglips_sigmoid_and_the_cut_falls_where_it_says():
    at = likeness_for(CUT)

    assert scores(np.array([at], np.float32))[0] == pytest.approx(CUT, rel=1e-3)
    low, high = scores(np.array([at - 0.02, at + 0.02], np.float32))
    assert low < CUT < high


def test_vectors_are_made_one_long_and_a_zero_one_stays_zero():
    found = unit([[3.0, 4.0], [0.0, 0.0]])

    assert np.allclose(found[0], [0.6, 0.8])
    assert np.allclose(found[1], [0.0, 0.0])
    assert found.dtype == np.float32


def _library(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Made-up vectors: a search, and twelve pictures, the first four near it."""
    rng = np.random.default_rng(seed)
    search = unit(rng.normal(size=768))[0]
    others = unit(rng.normal(size=(12, 768)))
    near = unit(search + others[:4] * np.array([[0.4], [0.5], [0.6], [0.7]]))
    return search, np.vstack([near, others[4:]])


def test_a_description_finds_the_pictures_past_the_cut_best_first():
    search, vectors = _library()
    ranked = described(vectors, search)

    assert ranked.rows == (0, 1, 2, 3)
    assert list(ranked.scores) == sorted(ranked.scores, reverse=True)
    assert all(score >= CUT for score in ranked.scores)


def test_a_description_of_something_not_there_finds_nothing():
    rng = np.random.default_rng(5)
    elsewhere = unit(rng.normal(size=768))[0]
    others = rng.normal(size=(50, 768))
    unrelated = others - (others @ elsewhere)[:, None] * elsewhere  # nothing of it in them
    vectors = unit(unrelated + 0.05 * elsewhere)  # the least bad still a little alike

    assert described(vectors, elsewhere).rows == ()
    assert described(np.zeros((0, 768), np.float32), elsewhere).rows == ()


def test_more_like_this_leaves_the_picture_itself_out_and_keeps_to_the_nearest():
    search, vectors = _library()
    vectors = np.vstack([unit(search), vectors])  # row 0 is the picture itself

    found = nearest(vectors, 0, alike=0.5, most=3)

    assert 0 not in found.rows
    assert found.rows == (1, 2, 3)
    assert list(found.scores) == sorted(found.scores, reverse=True)


def test_more_like_this_finds_nothing_when_nothing_is_alike():
    rng = np.random.default_rng(7)
    vectors = unit(rng.normal(size=(20, 768)))

    assert nearest(vectors, 3).rows == ()


@pytest.mark.parametrize(
    ("search", "english"),
    [
        ("a red boat on the sea", True),
        ("sunset", True),
        ("café by the harbour", True),
        ("Zürich lake", True),
        ("plage au coucher du soleil", False),
        ("der Hund im Schnee", False),
        ("perro en la playa", False),
        ("chien on the beach", True),  # an English word beside it wins
        ("aux cable", True),
        ("MIT dome", True),
        ("Big Sur coast", True),
        ("морской берег", False),  # noqa: RUF001 - Cyrillic, as a search in it is
        ("Βάρκα", False),
        ("海の夕日", False),
    ],
)
def test_a_search_in_another_language_is_told_apart(search: str, english: bool):
    assert in_english(search) is english


def test_a_searchs_writing_systems():
    assert scripts_of("boat 42") == {"latin"}
    assert scripts_of("Βάρκα") == {"greek"}
    assert scripts_of("берег") == {"cyrillic"}  # noqa: RUF001 - Cyrillic, on purpose
    assert scripts_of("夕日") == {"chinese"}
    assert scripts_of("ゆうひ") == {"japanese"}
    assert scripts_of("노을") == {"korean"}
    assert scripts_of("!? 12") == set()
    # A mark that lengthens or repeats belongs to the letters round it; narrow kana are kana.
    assert scripts_of("コーヒー") == {"japanese"}
    assert scripts_of("佐々木") == {"chinese"}
    assert scripts_of("ｺｰﾋｰ") == {"japanese"}
    assert scripts_of("ＺＵＭＩ") == {"latin"}  # noqa: RUF001 - wide letters, on purpose


def test_a_writing_no_reader_names_is_never_said_unreadable():
    assert unreadable("ラーメン", BEST_READS) is None
    assert unreadable("ᚠᚢᚦ", BEST_READS) is None  # runes: "other"
    assert unreadable("Βάρκα", frozenset({"latin"})) == "greek"


def test_words_of_a_search_leave_quotes_and_punctuation_round_them_out():
    assert words_of(" “Zumi”  73, (street) ") == ["Zumi", "73", "street"]


def test_words_fold_their_capitals_and_the_accents_of_latin_greek_and_cyrillic():
    assert folded("Tréval BRÜNIK") == "treval brunik"
    assert folded("Straße") == "straße"  # as FTS5 leaves it
    assert folded("ΚΑΦΈΣ καφές") == "καφεσ καφεσ"  # Greek's accents and final sigma
    assert folded("Ёлка") == "елка"
    assert folded("ガラス") == "ガラス"  # a voicing mark makes another letter: kept
    assert len(folded("İstanbul")) == len("İstanbul")  # a letter for a letter


def test_the_words_index_keeps_each_chinese_and_japanese_letter_apart():
    assert index_terms("東京タワー Café 73").split() == ["東", "京", "タ", "ワ", "ー", "cafe", "73"]
    assert index_terms("ｺｰﾋｰ 々").split() == ["ｺ", "ｰ", "ﾋ", "ｰ", "々"]


def test_a_search_becomes_an_fts5_query_of_word_starts_all_wanted():
    assert match_query("Zumi") == '"zumi"*'
    assert match_query("Café au-lait") == '"cafe"* AND "au"* AND "lait"*'
    assert match_query('he said "hi"') == '"he"* AND "said"* AND "hi"*'
    assert match_query("ΚΑΦΈΣ") == '"καφεσ"*'
    assert match_query("  !!! ") is None
    assert match_query("") is None


def test_a_chinese_or_japanese_word_is_its_letters_in_a_row():
    assert match_query("ガラス") == '"ガ ラ ス"'  # glass, never カラス, a crow
    assert match_query("東京タワー 2026") == '"東 京 タ ワ ー" AND "2026"*'


def test_the_words_that_matched_are_marked_however_they_were_written():
    pieces = marked("Tréval brünik ZUMI 73 street", "zum treval")

    assert Piece("Tréval", True) in pieces
    assert Piece("ZUMI", True) in pieces
    assert "".join(piece.text for piece in pieces) == "Tréval brünik ZUMI 73 street"


def test_greek_and_japanese_words_are_marked_too():
    assert Piece("ΚΑΦΕΣ", True) in marked("ΚΑΦΕΣ ZUMI", "καφές")
    pieces = marked("東京タワーへようこそ", "タワー")
    assert Piece("タワー", True) in pieces
    assert "".join(piece.text for piece in pieces) == "東京タワーへようこそ"


def test_long_words_are_cut_to_the_stretch_round_the_first_match():
    text = " ".join(["lorem"] * 30 + ["Glimmerwick"] + ["ipsum"] * 30)
    pieces = marked(text, "glimmer", around=12)

    assert pieces[0] == Piece("…", False)
    assert pieces[-1] == Piece("…", False)
    assert [piece.text for piece in pieces if piece.marked] == ["Glimmerwick"]
    assert len("".join(piece.text for piece in pieces)) < 50


def test_words_with_nothing_matched_show_their_start():
    assert marked("Harbour lights", "zumi") == [Piece("Harbour lights", False)]
    assert marked("", "zumi") == []


def test_a_picture_is_shown_once_in_the_first_group_that_holds_it():
    assert first_seen([[3, 1], [1, 2, 3, 4], [4, 5]]) == [[3, 1], [2, 4], [5]]
