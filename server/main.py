"""Web server: the map page and the data it asks for.

Run:  python -m uvicorn server.main:app --port 8765
Then open http://localhost:8765

Routes
  GET /api/meta             period covered by each layer
  GET /api/cells            colored grid cells for a view and date range
  GET /api/calendar         weekly history of an area, with unusual weeks
  GET /api/detections.csv   download of the observations behind the layer
  GET /api/tle              orbit data of the fire-watching satellites
  GET /api/events           fires as single events: dates, duration, area, vegetation
  GET /api/events/{id}      one fire with its ground cells and nearby reported fires
  GET /api/events/{id}/sharp  Landsat pictures before and after, and burn severity
  GET /api/reported         reported wildfires, optionally only those missed
  GET /                     the website in web/
"""
import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import events, queries, satellites
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


Missed = Literal["satellite", "model", "both", "all"]


@app.get("/api/events")
def fire_events(bbox: str, start: datetime.date, end: datetime.date, min_km2: float = Query(2.0, ge=0)):
    check_dates(start, end)
    try:
        return events.list_events(parse_bbox(bbox), start, end, min_km2)
    except events.Missing as e:
        raise HTTPException(503, str(e))


@app.get("/api/events/{event_id}")
def fire_event(event_id: int):
    try:
        info = events.event(event_id)
    except events.Missing as e:
        raise HTTPException(503, str(e))
    if info is None:
        raise HTTPException(404, "no such fire")
    return info


@app.get("/api/events/{event_id}/sharp")
def fire_event_sharp(event_id: int):
    try:
        info = events.event(event_id)
    except events.Missing as e:
        raise HTTPException(503, str(e))
    if info is None:
        raise HTTPException(404, "no such fire")
    try:
        return events.sharp_pictures(info)
    except Exception as e:                      # not signed in to Earth Engine, quota, network
        raise HTTPException(503, f"Earth Engine is not available: {str(e)[:200]}")


@app.get("/api/reported")
def reported_fires(bbox: str, start: datetime.date, end: datetime.date, missed: Missed = Query("satellite")):
    check_dates(start, end)
    try:
        return events.reported(parse_bbox(bbox), start, end, missed)
    except events.Missing as e:
        raise HTTPException(503, str(e))


@app.get("/api/tle")
def tle():
    return satellites.tle()


# Last, so /api/... routes win.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
