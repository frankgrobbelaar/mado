"""What every API module shares: the payload base class and the dependencies."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from mado import db
from mado.ai import Ai
from mado.config import DataPaths
from mado.jobs import Jobs
from mado.making import Sight
from mado.pc_check import PcCheck
from mado.previews import Previews
from mado.quarantine import Quarantine
from mado.samples import Samples
from mado.scan import Scanner
from mado.tools import Tools
from mado.watch import Watcher


class ApiModel(BaseModel):
    """Base for everything the API sends and receives: snake_case here, camelCase in JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        serialize_by_alias=True,
    )


def _paths(request: Request) -> DataPaths:
    paths: DataPaths = request.app.state.paths
    return paths


def _database(paths: Annotated[DataPaths, Depends(_paths)]) -> Iterator[sqlite3.Connection]:
    with closing(db.connect(paths.database)) as conn:
        yield conn


def _toolbox(request: Request) -> Tools:
    toolbox: Tools = request.app.state.tools
    return toolbox


def _scanner(request: Request) -> Scanner:
    scanner: Scanner = request.app.state.scanner
    return scanner


def _watcher(request: Request) -> Watcher | None:
    watcher: Watcher | None = request.app.state.watcher
    return watcher


def _previews(request: Request) -> Previews:
    previews: Previews = request.app.state.previews
    return previews


def _ai(request: Request) -> Ai:
    found: Ai = request.app.state.ai
    return found


def _sight(request: Request) -> Sight:
    found: Sight = request.app.state.sight
    return found


def _quarantine(request: Request) -> Quarantine:
    found: Quarantine = request.app.state.quarantine
    return found


def _jobs(request: Request) -> Jobs:
    found: Jobs = request.app.state.jobs
    return found


def _samples(request: Request) -> Samples:
    found: Samples = request.app.state.samples
    return found


def _pc(request: Request) -> PcCheck:
    found: PcCheck = request.app.state.pc
    return found


# Use these as parameter types in routes, e.g. `def route(conn: Database) -> ...`.
Paths = Annotated[DataPaths, Depends(_paths)]
Database = Annotated[sqlite3.Connection, Depends(_database)]
Toolbox = Annotated[Tools, Depends(_toolbox)]
Scans = Annotated[Scanner, Depends(_scanner)]
Copies = Annotated[Previews, Depends(_previews)]  # the smaller copies the window shows
Watching = Annotated[Watcher | None, Depends(_watcher)]  # None while the engine doesn't watch
Models = Annotated[Ai, Depends(_ai)]  # the AI models, where they run, their files
Seeing = Annotated[Sight, Depends(_sight)]  # what Mado sees in each picture
SetAside = Annotated[Quarantine, Depends(_quarantine)]
Working = Annotated[Jobs, Depends(_jobs)]  # the jobs that make pictures
ThisPc = Annotated[PcCheck, Depends(_pc)]
FirstLook = Annotated[Samples, Depends(_samples)]  # See it first's pictures
