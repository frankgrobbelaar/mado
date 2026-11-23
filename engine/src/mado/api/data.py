"""Settings > Your data: where Mado keeps its data and how big each part is, and the export."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from mado import data
from mado.api.common import ApiModel, Paths
from mado.export import export_data

router = APIRouter()


class DataSizes(ApiModel):
    folder: str  # the data folder
    database: int
    cache: int  # what Mado can always make again
    logs: int
    backups: int
    tools: int
    pasted: int  # pictures pasted from the clipboard, kept till they're saved


class ExportRequest(ApiModel):
    folder: str  # where the zip goes


class Exported(ApiModel):
    path: str
    size: int


@router.get("/data")
def your_data(paths: Paths) -> DataSizes:
    """How big each part of Mado's data is."""
    found = data.sizes(paths)
    return DataSizes(
        folder=str(found.folder),
        database=found.database,
        cache=found.cache,
        logs=found.logs,
        backups=found.backups,
        tools=found.tools,
        pasted=found.pasted,
    )


@router.post("/export")
def export(body: ExportRequest, paths: Paths) -> Exported:
    """Writes the export zip (the database, its settings and a manifest) into a folder, never
    over another file."""
    try:
        written = export_data(paths, Path(body.folder), now=datetime.now().astimezone())
    except OSError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Mado couldn't write the export there: {error.strerror or error}.",
        ) from None
    if written is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mado has no data to export yet.")
    return Exported(path=str(written), size=written.stat().st_size)
