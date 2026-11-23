"""Mado's preferences, chosen during setup and changed later in Settings."""

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import ValidationError

from mado.api.common import ApiModel, Database, Searching

router = APIRouter()


class Settings(ApiModel):
    set_up: bool = False  # the first-run steps are done
    # Saving (Settings > General): what Save offers first, where new pictures go (beside their
    # original, or into one folder), and whether they keep where a picture was taken.
    save_first: Literal["new", "replace"] = "new"
    new_pictures: Literal["beside", "folder"] = "beside"
    new_folder: str | None = None
    keep_location: bool = False
    # Many at once: a watch folder's batch of more than 20 pictures waits for the night.
    big_batches_at_night: bool = False
    # Search: which reader reads the words in pictures (Settings › General › Search): as this PC
    # suits, Windows' own (Fast) or PP-OCRv6 (Best).
    words_reader: Literal["auto", "fast", "best"] = "auto"


@router.get("/settings")
def settings(conn: Database) -> Settings:
    stored = {
        row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM settings")
    }
    chosen = Settings()
    for key in Settings.model_fields:
        if key in stored:
            try:
                values = {**chosen.model_dump(by_alias=False), key: stored[key]}
                chosen = Settings.model_validate(values)
            except ValidationError:
                pass  # a value this Mado doesn't know: keep the default
    return chosen


@router.put("/settings")
def save_settings(body: Settings, conn: Database, finding: Searching) -> Settings:
    """Keeps the owner's choices. Search reads the words again with a reader of words chosen,
    PP-OCRv6 fetched for Best the first time it's chosen."""
    before = settings(conn).words_reader
    with conn:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [(key, json.dumps(value)) for key, value in body.model_dump(by_alias=False).items()],
        )
    if body.words_reader != before:
        if body.words_reader == "best" and not finding.best.ready():
            finding.best.fetch()
        finding.wake(again=True)
    return settings(conn)
