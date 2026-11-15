/* Burning Calendar map page.
 *
 * Sections
 *   1. State and small helpers
 *   2. Map and basemap
 *   3. Fire layer: load cells for the view, color them, explain them in the legend
 *   4. Area history panel: calendar of the area on screen
 *   5. Top bar: place search, dates, buttons
 *   6. Start
 *
 * The fires list, the fire markers and the search around a point are in fires.js.
 */

// ---------- 1. State and helpers ----------

const $ = id => document.getElementById(id);
const state = { layer: "both", metric: "intensity", start: null, end: null, opacity: 0.8, base: "satellite" };
let META = {}, map, baseLayers = [], cellsRequest = null, calendarData = null;

const LAYER_NAME = { both: "MODIS + VIIRS combined", viirs: "VIIRS", modis: "MODIS" };
const EXAMPLES = {
  park:   { name: "Park Fire, California", bounds: [[-122.35, 39.55], [-121.25, 40.55]], start: "2024-07-24", end: "2024-08-15" },
  maui:   { name: "Lahaina, Maui", bounds: [[-156.75, 20.75], [-156.2, 21.05]], start: "2023-08-08", end: "2023-08-12" },
  kansas: { name: "Flint Hills spring burning, Kansas", bounds: [[-97.6, 37.2], [-95.6, 39.4]], start: "2024-04-01", end: "2024-04-30" },
};

const iso = d => d.toISOString().slice(0, 10);
const day = s => new Date(s + "T00:00:00Z");
const addDays = (s, n) => { const d = day(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
const pretty = s => day(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const km = m => m >= 1000 ? `${+(m / 1000).toFixed(1)} km` : `${m} m`;
const num = v => v >= 1000 ? d3.format(".3~s")(v) : d3.format(".3~r")(v);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function isoWeek(dateStr) {                       // ISO year and week of a Monday
  const th = day(dateStr); th.setUTCDate(th.getUTCDate() + 3);
  return { yr: th.getUTCFullYear(), wk: Math.floor((th - Date.UTC(th.getUTCFullYear(), 0, 1)) / 864e5 / 7) + 1 };
}

async function api(path, params, signal) {
  const res = await fetch(`${path}?${new URLSearchParams(params)}`, { signal });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Server error ${res.status}`);
  return res.json();
}

function viewParams() {
  const b = map.getBounds();
  const bbox = [clamp(b.getWest(), -180, 180), clamp(b.getSouth(), -85, 85), clamp(b.getEast(), -180, 180), clamp(b.getNorth(), -85, 85)];
  return { layer: state.layer, bbox: bbox.map(v => v.toFixed(4)).join(",") };
}

// ---------- 2. Map and basemap ----------

function createMap() {
  map = new maplibregl.Map({
    container: "map", style: "https://tiles.openfreemap.org/styles/dark",
    center: [-98, 39], zoom: 3.6, maxZoom: 15, attributionControl: { compact: true }, dragRotate: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.on("style.load", () => { try { map.setProjection({ type: "globe" }); } catch (e) { /* flat map is fine */ } });
  // Start when the map has loaded, or 4 s after its style has: a slow background tile
  // service must not keep the whole page waiting.
  let started = false;
  const begin = () => {
    if (started) return;
    started = true;
    baseLayers = map.getStyle().layers.map(l => ({ id: l.id, type: l.type }));
    const firstLabel = baseLayers.find(l => l.type === "symbol")?.id;
    map.addSource("satellite", { type: "raster", tileSize: 256, maxzoom: 18,
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
    map.addLayer({ id: "satellite", type: "raster", source: "satellite" }, baseLayers[1]?.id);
    map.addSource("fire", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({ id: "fire", type: "fill", source: "fire", paint: { "fill-antialias": false } }, firstLabel);
    setBasemap();
    map.on("click", "fire", showPopup);
    map.on("mousemove", "fire", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "fire", () => map.getCanvas().style.cursor = "");
    map.on("moveend", e => {
      if (e.originalEvent) $("areaName").textContent = "Area on screen";   // moved by hand, not by search
      refresh();
    });
    refresh();
    Satellites.attach(map).then(api => { window.satelliteView = api; });   // see satellites.js
    window.fireView = Fires.attach();                                       // see fires.js
  };
  map.on("load", begin);
  map.on("style.load", () => setTimeout(begin, 4000));
}

function setBasemap() {
  const sat = state.base === "satellite";
  map.setLayoutProperty("satellite", "visibility", sat ? "visible" : "none");
  for (const l of baseLayers) {
    // Over imagery keep only labels and borders of the vector map.
    const keep = !sat || l.type === "symbol" || (l.type === "line" && /boundary|admin/.test(l.id));
    map.setLayoutProperty(l.id, "visibility", keep ? "visible" : "none");
  }
}

// ---------- 3. Fire layer ----------

const RAMP = ["#ffe66d", "#ffb02e", "#ff6a1f", "#e3172d", "#b0005a"];
const DIVERGING = ["#1d6fe0", "#f5f5f5", "#e3172d"];

function setStatus(text) { $("status").textContent = text || ""; }

async function refresh() {
  if (!map?.getSource("fire")) return;
  cellsRequest?.abort();
  window.fireView?.refresh();                       // fires.js
  updateDownload();
  if (state.layer === "none") { drawCells(null); if (!$("panel").hidden) loadCalendar(); return; }
  const m = META[state.layer];
  if (state.end < m.first_day) { drawCells(null); setStatus(`${LAYER_NAME[state.layer]} data starts ${pretty(m.first_day)}.`); return; }
  cellsRequest = new AbortController();
  setStatus("Loading…");
  try {
    const data = await api("/api/cells", { ...viewParams(), start: state.start, end: state.end, metric: state.metric }, cellsRequest.signal);
    drawCells(data);
  } catch (e) {
    if (e.name === "AbortError") return;
    drawCells(null); setStatus(e.message);
  }
  if (!$("panel").hidden) loadCalendar();
}

// Each cell from the server: [west, south, east, north, days, intensity, normal_days]
function drawCells(data) {
  const cells = data?.cells ?? [];
  const value = c => state.metric === "intensity" ? c[5] : state.metric === "days" ? c[4] : c[4] - c[6];
  let scale;
  if (state.metric === "unusual") {
    const top = Math.max(0.5, d3.quantile(cells.map(c => Math.abs(value(c))).sort(d3.ascending), 0.95) || 0.5);
    scale = { top, t: v => clamp(v / top, -1, 1) };
  } else {
    const sorted = cells.map(value).filter(v => v > 0).sort(d3.ascending);
    const lo = d3.quantile(sorted, 0.05) ?? 1, hi = d3.quantile(sorted, 0.98) ?? 1;
    const log = state.metric === "intensity";
    scale = { lo, hi, t: v => hi <= lo ? 1 : clamp(log ? Math.log(Math.max(v, lo) / lo) / Math.log(hi / lo) : (v - lo) / (hi - lo), 0, 1) };
  }
  map.getSource("fire").setData({ type: "FeatureCollection", features: cells.map(c => ({
    type: "Feature",
    properties: { t: scale.t(value(c)), days: c[4], frp: c[5], normal: c[6] },
    geometry: { type: "Polygon", coordinates: [[[c[0], c[1]], [c[2], c[1]], [c[2], c[3]], [c[0], c[3]], [c[0], c[1]]]] },
  })) });
  paintLayer();
  drawLegend(data, scale);
  $("tileCells").textContent = data ? d3.format(",")(cells.length) : "–";
  $("tileDays").textContent = data ? num(data.total_days) : "–";
  $("tileFrp").textContent = data ? num(data.total_frp) : "–";
  if (!data) return setStatus("");
  setStatus(!cells.length ? "No fire seen here in these dates."
    : data.truncated ? "Showing the strongest squares only. Zoom in to see all." : "");
}

function paintLayer() {
  const t = ["get", "t"], o = state.opacity;
  if (state.metric === "unusual") {
    map.setPaintProperty("fire", "fill-color", ["interpolate", ["linear"], t, -1, DIVERGING[0], 0, DIVERGING[1], 1, DIVERGING[2]]);
    map.setPaintProperty("fire", "fill-opacity", ["*", o, ["+", 0.15, ["*", 0.85, ["abs", t]]]]);
  } else {
    map.setPaintProperty("fire", "fill-color", ["interpolate", ["linear"], t, 0, RAMP[0], 0.35, RAMP[1], 0.6, RAMP[2], 0.85, RAMP[3], 1, RAMP[4]]);
    map.setPaintProperty("fire", "fill-opacity", ["*", o, ["+", 0.55, ["*", 0.45, t]]]);
  }
}

function drawLegend(data, scale) {
  const dates = `${pretty(state.start)} – ${pretty(state.end)}`;
  if (state.layer === "none") {
    $("legendTitle").textContent = "No satellite data selected";
    $("legendBar").style.background = "none"; $("legendLow").textContent = $("legendHigh").textContent = "";
    $("legendNote").textContent = "Open Filters to choose MODIS, VIIRS or both.";
    return;
  }
  const title = { intensity: "Fire intensity", days: "Days with fire", unusual: "Fire days compared with normal" }[state.metric];
  $("legendTitle").textContent = `${title} · ${LAYER_NAME[state.layer]}`;
  const colors = state.metric === "unusual" ? DIVERGING : RAMP;
  $("legendBar").style.background = `linear-gradient(90deg, ${colors.join(",")})`;
  if (state.metric === "unusual") {
    $("legendLow").textContent = "fewer than normal"; $("legendHigh").textContent = "more than normal";
  } else if (data?.cells.length) {
    const unit = state.metric === "intensity" ? " MW" : scale.hi === 1 ? " day" : " days";
    $("legendLow").textContent = `${num(scale.lo)}${state.metric === "intensity" ? " MW" : ""}`;
    $("legendHigh").textContent = `${num(scale.hi)}${unit} or more`;
  } else { $("legendLow").textContent = "low"; $("legendHigh").textContent = "high"; }
  const size = data ? `Each square is about ${km(data.size_m)} wide. ` : "";
  const more = data && data.size_m > { viirs: 375, modis: 1000, both: 1500 }[state.layer] ? "Zoom in for more detail. " : "";
  const normal = state.metric === "unusual" && data ? `Normal = the same dates in ${data.reference_years} other years. ` : "";
  $("legendNote").textContent = `${dates}. ${size}${more}${normal}Data ends ${pretty(META[state.layer].last_day)}.`;
}

function showPopup(e) {
  if (window.fireView?.picking() || map.queryRenderedFeatures(e.point, { layers: ["fires"] }).length) return;   // a fire marker wins
  const p = e.features[0].properties;
  const days = +p.days, rows = [`<b>${days >= 0.95 ? Math.round(days) : days.toFixed(1)} fire ${Math.round(days) === 1 ? "day" : "days"}</b>`,
    `<div>Intensity: ${num(+p.frp)} MW</div>`];
  if (p.normal != null && p.normal !== "null") rows.push(`<div>Normal for these dates: ${(+p.normal).toFixed(1)} days</div>`);
  if (state.layer === "both") rows.push("<div>In MODIS-equivalent units</div>");
  new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat).setHTML(rows.join("")).addTo(map);
}

function updateDownload() {
  const a = $("download");
  if (state.layer === "none" || !map) { a.removeAttribute("href"); return; }
  a.href = `/api/detections.csv?${new URLSearchParams({ ...viewParams(), start: state.start, end: state.end })}`;
}

// ---------- 4. Area history panel ----------

let calendarTimer = null;
function loadCalendar() {
  clearTimeout(calendarTimer);
  calendarTimer = setTimeout(async () => {
    if (state.layer === "none") { $("heat").textContent = "Choose satellite data in Filters to see history."; $("periods").replaceChildren(); return; }
    try {
      calendarData = await api("/api/calendar", viewParams());
      drawCalendar(); drawPeriods();
    } catch (e) { $("heat").textContent = e.message; }
  }, 400);
}

function calendarRows() {
  const c = calendarData;
  return c.weeks.map((date, i) => ({ date, ...isoWeek(date), value: c.value[i], flag: c.flag[i] }));
}

function drawCalendar() {
  const rows = calendarRows(), c = calendarData;
  const years = [...d3.rollup(rows, v => v.length, r => r.yr)].filter(([, n]) => n >= 4).map(([y]) => y);
  const data = rows.filter(r => years.includes(r.yr));
  const months = { 1: "Jan", 5: "Feb", 9: "Mar", 14: "Apr", 18: "May", 22: "Jun", 27: "Jul", 31: "Aug", 36: "Sep", 40: "Oct", 44: "Nov", 49: "Dec" };
  const season = c.clim.critical.map((on, k) => ({ wk: k + 1, on })).filter(d => d.on);
  const tip = r => `Week of ${pretty(r.date)}\n${r.value} active squares × days\ntypical ${c.clim.p50[r.wk - 1]} (up to ${c.clim.p90[r.wk - 1]})` +
    (r.flag === 2 ? "\nRECORD for this time of year" : r.flag === 1 ? "\nunusual for this time of year" : "");
  const chart = Plot.plot({
    width: 388, height: 54 + 11 * years.length, marginLeft: 34, marginRight: 4, marginTop: 34, marginBottom: 4, padding: 0.08,
    style: { background: "transparent", color: "#cfcac0", fontSize: "10px" },
    x: { domain: d3.range(1, 54), axis: "top", label: null, tickSize: 0, tickFormat: w => months[w] ?? "" },
    y: { domain: years, label: null, tickSize: 0, tickFormat: y => y % 2 ? "" : String(y) },
    color: { type: "sqrt", range: ["#3a2a1c", "#ffb02e", "#ff6a1f", "#e3172d"], interpolate: "rgb" },
    marks: [
      Plot.cell(data, { x: "wk", y: "yr", fill: d => d.value > 0 ? d.value : NaN, title: tip }),
      Plot.cell(data.filter(d => !(d.value > 0)), { x: "wk", y: "yr", fill: "#23262b", title: tip }),
      Plot.cell(data.filter(d => d.flag), { x: "wk", y: "yr", fill: "none", stroke: "#fff", strokeWidth: d => d.flag === 2 ? 1.8 : 0.8, inset: 0.3 }),
      Plot.tickX(season, { x: "wk", y: years[0], stroke: "#4d9de0", strokeWidth: 7, dy: -11, title: () => "usual fire season" }),
    ],
  });
  $("heat").replaceChildren(chart);
}

function drawPeriods() {
  const c = calendarData, periods = [];
  let cur = null;
  for (const r of calendarRows()) {
    if (r.flag) {
      if (!cur) periods.push(cur = { start: r.date, end: r.date, peak: r.value, record: false });
      cur.end = r.date; cur.peak = Math.max(cur.peak, r.value); cur.record ||= r.flag === 2;
    } else cur = null;
  }
  const last = META[state.layer].last_day;
  const buttons = periods.reverse().slice(0, 12).map(p => {
    const b = document.createElement("button");
    const end = addDays(p.end, 6) > last ? last : addDays(p.end, 6);
    b.type = "button";
    b.innerHTML = `<span>${pretty(p.start)} – ${pretty(end)}</span><span class="tag ${p.record ? "record" : ""}">${p.record ? "record" : "unusual"}</span>`;
    b.onclick = () => { setDates(p.start, end); $("preset").value = "custom"; refresh(); };
    return b;
  });
  $("periods").replaceChildren(...(buttons.length ? buttons : [Object.assign(document.createElement("p"), { className: "hint", textContent: "No unusual weeks found for this area." })]));
}

// ---------- 5. Top bar ----------

function setDates(start, end) {
  state.start = start; state.end = end;
  $("start").value = start; $("end").value = end;
}

function buildPresets() {
  const last = META.both.last_day, lastYear = +last.slice(0, 4);
  const options = [["custom", "Custom dates"], ["d7", "Last 7 days of data"], ["d30", "Last 30 days of data"], ["d365", "Last 12 months of data"]];
  for (let y = lastYear; y > lastYear - 3; y--) options.push([`y${y}`, `Year ${y}`]);
  options.push(["all", "All years"]);
  $("preset").innerHTML = options.map(([v, t]) => `<option value="${v}">${t}</option>`).join("") +
    `<optgroup label="Examples">${Object.entries(EXAMPLES).map(([k, e]) => `<option value="ex:${k}">${e.name}</option>`).join("")}</optgroup>`;
  $("preset").value = `y${lastYear}`;
  setDates(`${lastYear}-01-01`, last);
}

function applyPreset(v) {
  const last = META.both.last_day;
  if (v.startsWith("ex:")) {
    const e = EXAMPLES[v.slice(3)];
    setDates(e.start, e.end); $("areaName").textContent = e.name;
    map.fitBounds(e.bounds, { padding: 60, duration: 1800 });            // moveend triggers refresh
    return;
  }
  if (v.startsWith("d")) setDates(addDays(last, 1 - +v.slice(1)), last);
  else if (v.startsWith("y")) setDates(`${v.slice(1)}-01-01`, `${v.slice(1)}-12-31` > last ? last : `${v.slice(1)}-12-31`);
  else if (v === "all") setDates(META[state.layer === "none" ? "both" : state.layer].first_day, last);
  refresh();
}

async function searchPlace(query) {
  const list = $("results");
  list.hidden = true;
  if (query.trim().length < 2) return;
  setStatus("Searching…");
  let found = [];
  try {
    const url = `https://nominatim.openstreetmap.org/search?${new URLSearchParams({ q: query, format: "jsonv2", countrycodes: "us", limit: 5 })}`;
    found = await (await fetch(url)).json();
  } catch (e) { return setStatus("Place search is not reachable."); }
  if (!found.length) return setStatus("Place not found. Try a city, county or park name.");
  setStatus("");
  const go = p => {
    const [s, n, w, e] = p.boundingbox.map(Number);
    $("areaName").textContent = p.display_name.split(",").slice(0, 2).join(",");
    map.fitBounds([[w, s], [e, n]], { padding: 60, maxZoom: 12, duration: 1800 });
    list.hidden = true;
  };
  go(found[0]);
  if (found.length > 1) {
    list.replaceChildren(...found.map(p => {
      const li = document.createElement("li");
      li.tabIndex = 0;
      li.innerHTML = `${p.display_name.split(",")[0]}<small>${p.display_name.split(",").slice(1, 4).join(",")}</small>`;
      li.onclick = () => go(p);
      li.onkeydown = e => { if (e.key === "Enter") go(p); };
      return li;
    }));
    list.hidden = false;
  }
}

const PANELS = { filters: "filtersBtn", panel: "panelBtn" };
function togglePanel(id, open) {
  const show = open ?? $(id).hidden;
  if (show && innerWidth <= 760) { window.fireView?.toggle(false); window.satelliteView?.toggle(false); }   // one sheet on a phone
  for (const [other, button] of Object.entries(PANELS)) {       // one panel at a time
    const on = other === id && show;
    $(other).hidden = !on; $(button).setAttribute("aria-expanded", String(on));
  }
  if (id === "panel" && show) loadCalendar();
}

function wireControls() {
  $("place").addEventListener("keydown", e => { if (e.key === "Enter") searchPlace(e.target.value); if (e.key === "Escape") $("results").hidden = true; });
  document.addEventListener("click", e => { if (!e.target.closest(".search")) $("results").hidden = true; });
  for (const id of ["start", "end"]) $(id).addEventListener("change", () => {
    if (!$("start").value || !$("end").value) return;
    let [a, b] = [$("start").value, $("end").value];
    if (a > b) [a, b] = [b, a];
    setDates(a, b); $("preset").value = "custom"; refresh();
  });
  $("preset").addEventListener("change", e => applyPreset(e.target.value));
  $("locate").onclick = () => navigator.geolocation?.getCurrentPosition(
    p => { $("areaName").textContent = "Around my location"; map.flyTo({ center: [p.coords.longitude, p.coords.latitude], zoom: 9 }); },
    () => setStatus("Location is not available in this browser."));
  for (const [id, button] of Object.entries(PANELS)) $(button).onclick = () => togglePanel(id);
  $("panelClose").onclick = () => togglePanel("panel", false);
  $("layerChoices").addEventListener("change", e => { state.layer = e.target.value; refresh(); });
  $("metricChoices").addEventListener("change", e => { state.metric = e.target.value; refresh(); });
  $("baseChoices").addEventListener("change", e => { state.base = e.target.value; setBasemap(); });
  $("opacity").addEventListener("input", e => { state.opacity = +e.target.value; paintLayer(); });
}

// ---------- 6. Start ----------

(async function start() {
  try { META = await api("/api/meta", {}); }
  catch (e) { $("status").textContent = "The data server is not running. Start it with: python -m uvicorn server.main:app --port 8780"; return; }
  $("start").min = $("end").min = META.modis.first_day;
  $("start").max = $("end").max = META.both.last_day;
  buildPresets();
  wireControls();
  window.timeline = Timeline.attach();          // see timeline.js
  createMap();
})();
