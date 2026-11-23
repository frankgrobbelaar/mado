"""Recipes and watch folders: steps kept by name, run on any batch or on every new picture put in
a watch folder (mado/recipes.py, mado/watching.py)."""

import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import Field

from mado import recipes, watching
from mado.api.batches import BatchSaving, Step, Words, saves_see_through, steps_of, words_of
from mado.api.common import ApiModel, Database
from mado.batches import BatchError, recipe_from_steps
from mado.recipes import RecipeError
from mado.watching import WatchError, WatchFolders

router = APIRouter()


class NewRecipe(ApiModel):
    name: str = Field(max_length=200)
    steps: list[Step]
    saving: BatchSaving


class KeptRecipe(ApiModel):
    id: int
    name: str
    steps: list[Step]
    saving: BatchSaving
    words: list[Words]  # its steps, then its save, as its line says them
    used: int  # batches made from it
    used_at: str | None
    tonight: bool  # a batch of it waits for tonight


class WatchIn(ApiModel):
    path: str = Field(max_length=1000)
    recipe: int
    results: str = Field(
        max_length=1000
    )  # where its new pictures go: a folder, or a name inside it
    watching: bool = True


class WatchOut(ApiModel):
    id: int
    path: str
    recipe: int
    recipe_name: str
    results: str
    watching: bool
    connected: bool  # its drive is there
    ran_at: str | None  # when it last took pictures
    ran_on: int  # how many its latest batch holds
    problem: str | None  # why its pictures couldn't go in the queue, lately


@router.get("/recipes")
def listed(conn: Database) -> list[KeptRecipe]:
    """The owner's recipes, each with its steps in words and how often and when it was used."""
    return [_recipe(conn, each) for each in recipes.listed(conn)]


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
def keep(body: NewRecipe, conn: Database) -> KeptRecipe:
    """Keeps steps and how they save as a recipe."""
    steps, saving = _checked(conn, body)
    try:
        found = recipes.kept(conn, body.name, steps, saving, _now())
    except RecipeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _recipe(conn, found)


@router.put("/recipes/{recipe_id}")
def change(recipe_id: int, body: NewRecipe, conn: Database) -> KeptRecipe:
    """Changes a recipe: batches in the queue make what they were asked for."""
    steps, saving = _checked(conn, body)
    try:
        found = recipes.changed(conn, recipe_id, body.name, steps, saving)
    except RecipeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That recipe isn't there any more.")
    return _recipe(conn, found)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(recipe_id: int, conn: Database) -> Response:
    """Deletes a recipe; batches made from it keep their steps."""
    try:
        gone = recipes.deleted(conn, recipe_id)
    except RecipeError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    if not gone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That recipe isn't there any more.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watch-folders")
def watch_folders(conn: Database) -> list[WatchOut]:
    """The watch folders: each one's recipe, where its new pictures go, on or off, and when it
    last made pictures."""
    return [_watch(conn, each) for each in watching.listed(conn)]


@router.post("/watch-folders", status_code=status.HTTP_201_CREATED)
def watch(body: WatchIn, conn: Database, request: Request) -> WatchOut:
    """Watches a folder from now: what's in it already is left alone."""
    try:
        found = watching.added(conn, Path(body.path), body.recipe, Path(body.results), _now())
        if not body.watching:
            found = (
                watching.changed(
                    conn,
                    found.id,
                    path=found.path,
                    recipe_id=found.recipe_id,
                    results=found.results,
                    watching=False,
                    now=_now(),
                )
                or found
            )
    except WatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    _poke(request)
    return _watch(conn, found)


@router.put("/watch-folders/{watch_id}")
def change_watch(watch_id: int, body: WatchIn, conn: Database, request: Request) -> WatchOut:
    """Changes a watch folder, or turns it on or off: on again, it takes what arrives from now."""
    try:
        found = watching.changed(
            conn,
            watch_id,
            path=Path(body.path),
            recipe_id=body.recipe,
            results=Path(body.results),
            watching=body.watching,
            now=_now(),
        )
    except WatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That watch folder isn't there any more.")
    _poke(request)
    return _watch(conn, found)


@router.delete("/watch-folders/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def stop_watching(watch_id: int, conn: Database) -> Response:
    """Stops watching a folder: its pictures, and what it made, stay as they are."""
    if not watching.deleted(conn, watch_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That watch folder isn't there any more.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _checked(
    conn: sqlite3.Connection, body: NewRecipe
) -> tuple[list[dict[str, object]], dict[str, object]]:
    steps = steps_of(body.steps)
    saves_see_through(steps, body.saving.model_dump(by_alias=True))
    try:
        recipe_from_steps(conn, steps)
    except BatchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return steps, body.saving.model_dump(by_alias=True)


def _recipe(conn: sqlite3.Connection, found: recipes.Kept) -> KeptRecipe:
    tonight = conn.execute(
        """SELECT 1 FROM batches AS b WHERE b.recipe_id = ? AND b.starts = 'tonight'
           AND EXISTS (SELECT 1 FROM jobs WHERE batch_id = b.id AND state = 'queued')""",
        (found.id,),
    ).fetchone()
    return KeptRecipe.model_validate(
        {
            "id": found.id,
            "name": found.name,
            "steps": found.steps,
            "saving": found.saving,
            "words": [each.model_dump() for each in words_of(conn, found.steps, found.saving)],
            "used": found.used,
            "used_at": found.used_at,
            "tonight": tonight is not None,
        }
    )


def _watch(conn: sqlite3.Connection, found: watching.Watch) -> WatchOut:
    ran = conn.execute(
        """SELECT MAX(j.queued_at) AS at, COUNT(j.id) AS pictures FROM batches AS b
           JOIN jobs AS j ON j.batch_id = b.id AND j.state <> 'cancelled'
           WHERE b.watch_id = ? GROUP BY b.id ORDER BY b.id DESC LIMIT 1""",
        (found.id,),
    ).fetchone()
    anchor = found.path.anchor
    return WatchOut(
        id=found.id,
        path=str(found.path),
        recipe=found.recipe_id,
        recipe_name=found.recipe,
        results=str(found.results),
        watching=found.watching,
        connected=not anchor or Path(anchor).exists(),
        ran_at=ran["at"] if ran else None,
        ran_on=ran["pictures"] if ran else 0,
        problem=found.problem,
    )


def _poke(request: Request) -> None:
    folders: WatchFolders | None = request.app.state.watch_folders
    if folders is not None:
        folders.poke()


def _now() -> datetime:
    return datetime.now().astimezone()
