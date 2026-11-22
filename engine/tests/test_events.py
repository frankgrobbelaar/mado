"""What the engine tells the app on its standard output, after the ready line."""

import json
import time

import pytest

from mado.events import notify, working


def test_a_notification_is_one_json_line_in_plain_ascii(capsys: pytest.CaptureFixture[str]):
    notify("Your 24 pictures are ready", "4K · all checked · 1.2 GB → 3.4 GB")

    line = capsys.readouterr().out
    assert line.endswith("\n")
    assert line.isascii()  # whatever code page Windows gives the pipe
    assert json.loads(line) == {
        "event": "notify",
        "title": "Your 24 pictures are ready",
        "body": "4K · all checked · 1.2 GB → 3.4 GB",
    }


def test_a_notification_can_lead_somewhere_in_mado(capsys: pytest.CaptureFixture[str]):
    notify("Your 24 pictures are ready", "4K · all checked", link="/settings")

    assert json.loads(capsys.readouterr().out)["link"] == "/settings"


def test_while_it_works_at_starting_the_engine_says_so_every_few_seconds(
    capsys: pytest.CaptureFixture[str],
):
    with working(every=0.02):
        time.sleep(0.2)
    said = capsys.readouterr().out.splitlines()
    time.sleep(0.1)

    assert len(said) >= 2
    assert all(json.loads(line) == {"event": "working"} for line in said)
    assert capsys.readouterr().out == ""  # nothing once it's done
