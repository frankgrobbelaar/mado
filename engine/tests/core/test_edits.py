"""The edit step: parts, strokes and edits as they're kept, what a picture's name and History say
of them, and what they need."""

import pytest

from mado.core.edits import (
    Blur,
    Click,
    CutOut,
    EditError,
    Editing,
    Erase,
    Part,
    Stroke,
    Subject,
    as_json,
    editing_from,
    label,
    models_for,
    parts_named,
    phrase,
    see_through,
)

BOAT = Part((Click(0.65, 0.46),))
SKY = Part((Click(0.3, 0.1), Click(0.5, 0.2, keep=False)), choice=2)


def test_an_edit_step_comes_back_as_it_was_kept():
    editing = Editing(
        (
            Erase((BOAT,), (Stroke(((0.1, 0.2), (0.3, 0.4)), 0.02, take=True),), "best"),
            CutOut((SKY,), "colour", (12, 34, 56)),
            Blur((BOAT,)),
            Subject("fast", "blurred"),
        ),
        version="18f3-4c2b",
    )

    assert editing_from(as_json(editing)) == editing
    assert editing_from(None) is None


def test_clicks_and_choices_are_held_to_the_picture_and_the_three_answers():
    kept = editing_from(
        {
            "edits": [
                {
                    "kind": "cutout",
                    "parts": [{"clicks": [{"x": 1.4, "y": -2, "keep": True}], "choice": 7}],
                    "colour": "not a colour",
                }
            ]
        }
    )

    assert kept is not None
    cut = kept.edits[0]
    assert isinstance(cut, CutOut)
    assert cut.parts[0] == Part((Click(1.0, 0.0),), choice=2)
    assert cut.colour == (255, 255, 255)
    assert cut.behind == "nothing"
    assert kept.version is None


_REFUSED: list[tuple[object, str]] = [
    ({"edits": [{"kind": "paint"}]}, "doesn't know"),
    ({"edits": [{"kind": "erase", "parts": [], "strokes": []}]}, "picked or painted"),
    ({"edits": [{"kind": "cutout", "parts": []}]}, "needs a part"),
    ({"edits": [{"kind": "blur"}]}, "needs a part"),
    ({"edits": [{"kind": "blur", "parts": [{"clicks": []}]}]}, "needs a click"),
    (
        {"edits": [{"kind": "blur", "parts": [{"clicks": [{"x": 0.5, "y": 0.5, "keep": False}]}]}]},
        "needs a click",
    ),
    ({"edits": "erase"}, "doesn't know"),
]


@pytest.mark.parametrize(("kept", "says"), _REFUSED)
def test_edits_mado_cant_make_say_why(kept: object, says: str):
    with pytest.raises(EditError, match=says):
        editing_from(kept)


def test_a_new_pictures_name_and_history_say_what_the_edits_did():
    erased = Editing((Erase((BOAT, SKY)),))
    cut = Editing((Subject(behind="nothing"),))
    both = Editing((Erase(strokes=(Stroke(((0.5, 0.5),), 0.1),)), CutOut((BOAT,), "blurred")))

    assert label(erased) == "Erased"
    assert label(cut) == "Cut out"
    assert label(Editing((Blur((BOAT,)),))) == "Blurred"
    assert label(both) == "Edited"
    assert label(None) is None
    assert label(Editing(())) is None
    assert phrase(erased) == "erased 2 parts"
    assert phrase(cut) == "cut out the subject"
    assert phrase(both) == "erased a part, cut out a part over the rest, blurred"
    assert phrase(Editing((CutOut((BOAT, SKY), "colour"),))) == "cut out parts onto a colour"


def test_parts_get_plain_names_never_a_guess_at_what_they_are():
    assert parts_named(3) == ["Part 1", "Part 2", "Part 3"]


def test_only_a_cut_out_with_nothing_behind_it_leaves_see_through_parts():
    assert see_through(Editing((Subject(behind="nothing"),)))
    assert see_through(Editing((CutOut((BOAT,)),)))
    assert not see_through(Editing((CutOut((BOAT,), "colour"),)))
    assert not see_through(Editing((Erase((BOAT,)), Blur((BOAT,)))))
    assert not see_through(None)


def test_what_the_edits_need():
    editing = Editing(
        (
            Erase((BOAT,), quality="best"),
            Subject(None),
            Erase(strokes=(Stroke(((0.1, 0.1),), 0.1),)),
        )
    )

    assert models_for(editing, cut_quality="fast") == {
        "select",
        "erase-best",
        "erase-fast",
        "cut-fast",
    }
    assert models_for(Editing((Subject("best"),)), cut_quality="fast") == {"cut-best"}
    assert models_for(None, cut_quality="best") == set()
