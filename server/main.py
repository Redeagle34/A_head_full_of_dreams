"""Web server: the map page and the data it asks for.

Run:  python -m uvicorn server.main:app --port 8780
Then open http://localhost:8780

Routes
  GET /api/meta             period covered by each layer
  GET /api/cells            colored grid cells for a view and date range
  GET /api/calendar         weekly history of an area, with unusual weeks
  GET /api/detections.csv   download of the observations behind the layer
  GET /api/events           fires in a map view: dates, duration, area, vegetation, danger rating
  GET /api/events/near      the same within a distance of a point, most dangerous first
  GET /api/events/{id}      one fire with its ground cells and nearby reported fires
  GET /api/danger/levels    what each danger level meant on years the model never saw
  GET /api/tle              orbit data of the fire-watching satellites
  GET /api/events/{id}/sharp  Landsat pictures before and after, and burn severity
  GET /api/reported         reported wildfires, optionally only those missed
  GET /api/report/sections  the sections a report can hold
  POST /api/report          the scientific report for chosen places, dates and sections
  GET /                     the website in web/
"""
import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from . import db, events, fires, queries, report, satellites
from .config import WEB_DIR

Layer = Literal["viirs", "modis", "both"]
Metric = Literal["intensity", "days", "unusual"]

app = FastAPI(title="Burning Calendar")


@app.exception_handler(db.Missing)
def database_missing(request, e):
    return JSONResponse({"detail": str(e)}, status_code=503)


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


@app.get("/api/danger/levels")
def danger_levels():
    try:
        return fires.level_meanings()
    except fires.NotBuilt as e:
        raise HTTPException(503, str(e))


Missed = Literal["satellite", "model", "both", "all"]


def find_events(**arguments):
    try:
        return events.find(**arguments)
    except events.Missing as e:
        raise HTTPException(503, str(e))


@app.get("/api/events")
def fire_events(bbox: str, start: datetime.date, end: datetime.date, min_km2: float = Query(2.0, ge=0),
                min_level: int = Query(0, ge=0, le=4)):
    check_dates(start, end)
    return find_events(start=start, end=end, min_km2=min_km2, bbox=parse_bbox(bbox), min_level=min_level)


@app.get("/api/events/near")                    # before /api/events/{event_id}, or "near" is read as an id
def fire_events_near(start: datetime.date, end: datetime.date,
                     lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                     km: float = Query(50, gt=0, le=events.MAX_RADIUS_KM), min_km2: float = Query(2.0, ge=0),
                     min_level: int = Query(0, ge=0, le=4)):
    check_dates(start, end)
    return find_events(start=start, end=end, min_km2=min_km2, near=(lat, lon, km), min_level=min_level)


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
    except events.Missing as e:                 # Earth Engine is not set up on this server
        raise HTTPException(503, str(e))
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
class Box(BaseModel):
    name: str = "Area"
    bbox: tuple[float, float, float, float]         # west, south, east, north


class ReportRequest(BaseModel):
    states: list[str] = []
    boxes: list[Box] = []
    start: datetime.date
    end: datetime.date
    sections: list[str] = list(report.SECTIONS)


@app.get("/api/report/sections")
def report_sections():
    return [{"key": key, "title": title} for key, title in report.SECTIONS.items()]


@app.post("/api/report")
def make_report(request: ReportRequest):
    try:
        return report.build(request.states, [b.model_dump() for b in request.boxes], request.start, request.end,
                            request.sections)
    except report.BadRequest as e:
        raise HTTPException(400, str(e))


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
