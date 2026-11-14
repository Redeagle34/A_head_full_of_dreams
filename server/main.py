"""Web server: the map page and the data it asks for.

Run:  python -m uvicorn server.main:app --port 8765
Then open http://localhost:8765

Routes
  GET /api/meta             period covered by each layer
  GET /api/cells            colored grid cells for a view and date range
  GET /api/calendar         weekly history of an area, with unusual weeks
  GET /api/detections.csv   download of the observations behind the layer
  GET /                     the website in web/
"""
import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import queries
from .config import WEB_DIR

Layer = Literal["viirs", "modis", "both"]
Metric = Literal["intensity", "days", "unusual"]

app = FastAPI(title="Burning Calendar")


def parse_bbox(bbox: str):
    """'west,south,east,north' in degrees -> four floats, checked."""
    try:
        west, south, east, north = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be west,south,east,north")
    west, east = max(west, -180.0), min(east, 180.0)
    south, north = max(south, -90.0), min(north, 90.0)
    if west >= east or south >= north:
        raise HTTPException(400, "bbox is empty")
    return west, south, east, north


def check_dates(start: datetime.date, end: datetime.date):
    if start > end:
        raise HTTPException(400, "start date is after end date")


@app.get("/api/meta")
def meta():
    return queries.meta()


@app.get("/api/cells")
def cells(layer: Layer, bbox: str, start: datetime.date, end: datetime.date,
          metric: Metric = Query("intensity")):
    check_dates(start, end)
    try:
        return queries.cells(layer, parse_bbox(bbox), start, end, metric)
    except queries.BadRequest as e:
        raise HTTPException(400, str(e))


@app.get("/api/calendar")
def calendar(layer: Layer, bbox: str):
    return queries.calendar(layer, parse_bbox(bbox))


@app.get("/api/detections.csv")
def detections(layer: Layer, bbox: str, start: datetime.date, end: datetime.date):
    check_dates(start, end)
    text = queries.detections_csv(layer, parse_bbox(bbox), start, end)
    name = f"fire_{layer}_{start}_{end}.csv"
    return Response(text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# Last, so /api/... routes win.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
