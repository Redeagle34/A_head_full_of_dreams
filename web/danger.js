/* Burning Calendar: rated fires on the map and the "Fires nearby" radius search.
 *
 * Loaded after app.js and uses its helpers ($, api, state, map, pretty, viewParams, setStatus).
 * app.js calls setupFires() when the map is ready and refreshFires() when the view or dates change.
 *
 * Sections
 *   1. Settings: colors and words of the five danger levels
 *   2. Fire markers for the map view
 *   3. One fire in words: the three factors
 *   4. Fires nearby: choose a point, a distance and a level, get a list
 */

// ---------- 1. Settings ----------

// Colors of the U.S. fire danger rating signs: green, blue, yellow, orange, red.
const LEVEL_COLOR = ["#4caf50", "#3d8bfd", "#ffd23f", "#ff8c1a", "#e3172d"];
const UNRATED_COLOR = "#9a9a9a";
const near = { lat: null, lon: null, km: 50, level: 0, picking: false, label: "" };
let LEVEL_INFO = [], firesRequest = null, nearRequest = null;

// Keep the target clear of the top bar and, on wide screens, of the open panel on the right.
const framePadding = () => innerWidth > 760 ? { top: 170, bottom: 60, left: 60, right: 470 } : { top: 60, bottom: 60, left: 30, right: 30 };
const levelColor = f => f.level == null ? UNRATED_COLOR : LEVEL_COLOR[f.level];
const acres = v => `${d3.format(",")(v)} acres`;
const dates = f => f.first_day === f.last_day ? pretty(f.first_day) : `${pretty(f.first_day)} – ${pretty(f.last_day)}`;

// ---------- 2. Fire markers ----------

wireFires();                // the panel works before the map has finished loading

async function setupFires() {
  const empty = { type: "FeatureCollection", features: [] };
  map.addSource("ring", { type: "geojson", data: empty });
  map.addLayer({ id: "ring-fill", type: "fill", source: "ring", paint: { "fill-color": "#ffffff", "fill-opacity": 0.06 } });
  map.addLayer({ id: "ring-line", type: "line", source: "ring", paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [2, 2] } });
  map.addSource("fires", { type: "geojson", data: empty });
  map.addLayer({ id: "fires", type: "circle", source: "fires", paint: {
    "circle-color": ["get", "color"], "circle-stroke-color": "#111", "circle-stroke-width": 1.5, "circle-opacity": 0.92,
    // size by footprint, smaller when the whole country is on screen
    "circle-radius": ["interpolate", ["linear"], ["zoom"],
      3, ["interpolate", ["linear"], ["sqrt", ["get", "acres"]], 0, 2, 30, 3, 300, 6, 700, 9],
      8, ["interpolate", ["linear"], ["sqrt", ["get", "acres"]], 0, 5, 30, 8, 300, 15, 700, 21]],
  } });
  map.on("click", "fires", e => showFire(JSON.parse(e.features[0].properties.fire)));
  map.on("mousemove", "fires", () => map.getCanvas().style.cursor = "pointer");
  map.on("mouseleave", "fires", () => map.getCanvas().style.cursor = "");
  map.on("click", e => { if (near.picking) setNearPoint(e.lngLat.lat, e.lngLat.lng, "Point picked on the map"); });
  try { LEVEL_INFO = await api("/api/danger/levels", {}); drawLevelTable(); }
  catch (e) { $("nearSummary").textContent = e.message; }
  drawRing();
  refreshFires();
}

async function refreshFires() {
  if (!map?.getSource("fires")) return;
  firesRequest?.abort();
  if (!$("near").hidden && near.lat != null) runNear();
  if ($("markers").value === "off") return drawMarkers([]);
  firesRequest = new AbortController();
  try {
    const data = await api("/api/fires", { bbox: viewParams().bbox, start: state.start, end: state.end, min_level: $("markers").value }, firesRequest.signal);
    drawMarkers(data.fires);
  } catch (e) { if (e.name !== "AbortError") drawMarkers([]); }
}

function drawMarkers(fires) {
  map.getSource("fires").setData({ type: "FeatureCollection", features: fires.map(f => ({
    type: "Feature", geometry: { type: "Point", coordinates: [f.lon, f.lat] },
    properties: { color: levelColor(f), acres: f.acres, fire: JSON.stringify(f) },
  })).reverse() });           // most dangerous drawn last, on top
}

// ---------- 3. One fire in words ----------

function chanceText(f) {
  if (f.level == null) return "Not rated: outside the contiguous U.S. or weather data missing.";
  if (f.p1000 === 1) return "Already over 1,000 acres after two days.";
  const info = LEVEL_INFO.find(l => l.level === f.level);
  const share = info ? `${d3.format(".2~r")(info.reached_1000 * 100)} in 100 fires rated ${f.level_name} reached 1,000 acres` : "";
  return `${share} (2022–2025).`;
}

function exposureText(f) {
  return f.built_ha == null ? "No data." : `${d3.format(",")(f.built_ha)} ha built-up within 5 km: ${f.exposure}.`;
}

function behaviourText(f) {
  const power = f.frp_max ? ` · peak ${d3.format(",")(Math.round(f.frp_max))} MW` : "";
  const facts = f.conditions.length ? `<br>${f.conditions.join(" · ")}` : "";
  return `${acres(f.acres)} footprint · ${dates(f)}${power}${facts}`;
}

function fireHtml(f) {
  return `<b><span class="dot" style="--level:${levelColor(f)}"></span>${f.level_name ?? "Not rated"}${f.level == null ? "" : " danger"}</b>
    <div class="factors">
      <div><small>Chance of getting large</small>${chanceText(f)}</div>
      <div><small>What is exposed</small>${exposureText(f)}</div>
      <div><small>What the satellites saw</small>${behaviourText(f)}${f.land_cover ? `<br>In ${f.land_cover}.` : ""}</div>
    </div>`;
}

function showFire(f, fly) {
  if (fly) map.fitBounds([[f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]]], { padding: framePadding(), maxZoom: 11, duration: 1200 });
  new maplibregl.Popup({ closeButton: true }).setLngLat([f.lon, f.lat]).setHTML(fireHtml(f)).addTo(map);
}

// ---------- 4. Fires nearby ----------

function setNearPoint(lat, lon, label) {
  Object.assign(near, { lat, lon, label, picking: false });
  $("nearPick").setAttribute("aria-pressed", "false");
  map.getCanvas().style.cursor = "";
  $("nearPoint").textContent = `${label} (${lat.toFixed(3)}, ${lon.toFixed(3)})`;
  drawRing();
  runNear();
}

function drawRing() {
  if (near.lat == null || !map.getSource("ring")) return;      // drawn by setupFires once the map is ready
  const dLat = near.km / 111.32, dLon = dLat / Math.cos(near.lat * Math.PI / 180);
  const ring = d3.range(0, 65).map(i => [near.lon + dLon * Math.cos(i * Math.PI / 32), near.lat + dLat * Math.sin(i * Math.PI / 32)]);
  map.getSource("ring").setData({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] } });
  map.fitBounds([[near.lon - dLon, near.lat - dLat], [near.lon + dLon, near.lat + dLat]], { padding: framePadding(), duration: 1000 });
}

async function runNear() {
  if (near.lat == null) return;
  nearRequest?.abort();
  nearRequest = new AbortController();
  $("nearSummary").textContent = "Searching…";
  try {
    const data = await api("/api/fires/near", { lat: near.lat, lon: near.lon, km: near.km, min_level: near.level, start: state.start, end: state.end }, nearRequest.signal);
    drawNearList(data);
  } catch (e) {
    if (e.name !== "AbortError") { $("nearSummary").textContent = e.message; $("nearList").replaceChildren(); }
  }
}

function drawNearList(data) {
  const n = data.fires.length;
  $("nearSummary").textContent = !n ? `No fire seen within ${near.km} km between ${pretty(state.start)} and ${pretty(state.end)}.`
    : `${data.truncated ? `First ${n}` : n} ${n === 1 ? "fire" : "fires"} within ${near.km} km, ${pretty(state.start)} – ${pretty(state.end)}. Most dangerous first, then nearest.`;
  $("nearList").replaceChildren(...data.fires.map(f => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "fire"; b.style.setProperty("--level", levelColor(f));
    const where = f.km === 0 ? "you are inside its area" : `${f.km} km ${f.direction}`;
    b.innerHTML = `<span class="badge">${f.level_name ?? "Not rated"}</span>
      <span class="head"><span>${acres(f.acres)}</span><span>${where}</span></span>
      <span class="line">${dates(f)}${f.state ? ` · ${f.state}` : ""}${f.exposure ? ` · <b>${f.exposure}</b>` : ""}</span>
      <span class="line">${f.conditions.join(" · ")}</span>`;
    b.onclick = () => showFire(f, true);
    return b;
  }));
}

function drawLevelTable() {
  const pct = v => `${d3.format(".2~r")(v * 100)}%`;
  $("levelTable").innerHTML = `<tr><th>Level</th><th>Fires</th><th>Reached 1,000 acres</th><th>Typical size</th></tr>` +
    LEVEL_INFO.map(l => `<tr><td><span class="dot" style="--level:${LEVEL_COLOR[l.level]}"></span>${l.name}</td>
      <td>${d3.format(",")(l.fires)}</td><td>${pct(l.reached_1000)}</td><td>${d3.format(",")(l.median_acres)} acres</td></tr>`).join("");
}

function wireFires() {
  $("markers").addEventListener("change", refreshFires);
  $("nearKm").addEventListener("change", e => { near.km = +e.target.value; drawRing(); runNear(); });
  $("nearLevel").addEventListener("change", e => { near.level = +e.target.value; runNear(); });
  $("nearCentre").onclick = () => { const c = map.getCenter(); setNearPoint(c.lat, c.lng, "Centre of the map"); };
  $("nearPick").onclick = () => {
    near.picking = !near.picking;
    $("nearPick").setAttribute("aria-pressed", String(near.picking));
    map.getCanvas().style.cursor = near.picking ? "crosshair" : "";
    if (near.picking) $("nearPoint").textContent = "Click the map where you are.";
  };
  $("nearLocate").onclick = () => {
    if (!navigator.geolocation) return $("nearPoint").textContent = "Location is not available in this browser.";
    $("nearPoint").textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(
      p => setNearPoint(p.coords.latitude, p.coords.longitude, "My location"),
      () => $("nearPoint").textContent = "Location was not shared. Use the map centre or pick a point.");
  };
}
