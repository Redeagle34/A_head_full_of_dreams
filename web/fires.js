/* Fires: one list of fires with their danger level, on screen or around a point,
   and the reported fires that were missed.

   A fire here is always the same thing: MODIS and VIIRS detections that touch on squares
   of about 1 km and follow within 5 days (pipeline/fire_events.py). Its danger level
   comes from pipeline/danger_model.py, trained on those same fires.

   Uses the helpers of app.js ($, state, map, api, viewParams, pretty, addDays, num, clamp).
   app.js calls Fires.attach() when the map is ready, and refresh() of the object it
   returns (window.fireView) when the view or the dates change.

   Sections
     1. Settings            colors and words of the five danger levels
     2. Panel               where to look, danger and size filters
     3. List and markers    the same fires in the list and on the map
     4. Around a point      choose a point and a distance
     5. One fire            rating, dates, duration, area, vegetation, spread on the map
     6. Before and after    daily NASA pictures (no key) and sharper Landsat pictures
     7. Missed fires        reported wildfires the satellites or the model missed
*/
const Fires = (() => {

// ---------- 1. Settings ----------

// Colors of the U.S. fire danger rating signs: green, blue, yellow, orange, red.
const LEVEL_COLOR = ["#4caf50", "#3d8bfd", "#ffd23f", "#ff8c1a", "#e3172d"];
const UNRATED_COLOR = "#9a9a9a";
const ACRES_PER_KM2 = 247.105;
const SNAPSHOT = "https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&CRS=EPSG:4326&FORMAT=image/jpeg";
const STYLES = { natural: ["MODIS_Terra_CorrectedReflectance_TrueColor", "Natural color"],
                 scar: ["MODIS_Terra_CorrectedReflectance_Bands721", "Burn scars (infrared): burned ground is red-brown, plants green"] };
const SPREAD = ["#ffe66d", "#ff6a1f", "#b0005a", "#4a1486"];      // first day -> last day
const EMPTY = { type: "FeatureCollection", features: [] };

let open = false, current = null, timer = null, missed = "off", request = null, LEVEL_INFO = [];
// What the list shows: fires on screen ("view") or around a point ("near").
const find = { mode: "view", lat: null, lon: null, km: 50, level: 0, minKm2: 2, picking: false };

const range = (a, b) => a === b ? pretty(a) : `${pretty(a)} to ${pretty(b)}`;
const km2 = v => v >= 100 ? Math.round(v).toLocaleString() : (+v.toFixed(1)).toLocaleString();
const acres = v => `${Math.round(v).toLocaleString()} acres`;
const days = n => `${n} ${n === 1 ? "day" : "days"}`;
const percent = v => `${Math.min(99, Math.round(v * 100))}%`;       // used only for shares below 1
const levelColor = d => d?.level == null ? UNRATED_COLOR : LEVEL_COLOR[d.level];
const levelName = d => d?.level_name ?? "Not rated";

// ---------- 2. Panel ----------

function build() {
  const panel = document.createElement("aside");
  panel.id = "firePanel"; panel.className = "sat-panel fire-panel glass"; panel.hidden = true;
  panel.innerHTML = `
    <div class="panel-head"><div><div class="eyebrow">Dates on the time bar</div><h2>Fires</h2></div>
      <button id="fireClose" type="button" aria-label="Close fires">Close</button></div>
    <div id="fireListView">
      <p class="hint">One fire = MODIS and VIIRS detections that touch (squares of about 1 km) and follow within 5 days. The same fires are in the list and on the map, colored by danger level.</p>
      <div class="choices row" id="fireMode">
        <label><input type="radio" name="fireMode" value="view" checked><span><b>On screen</b><small>Largest first.</small></span></label>
        <label><input type="radio" name="fireMode" value="near"><span><b>Around a point</b><small>Most dangerous first, then nearest.</small></span></label>
      </div>
      <div class="steps" id="nearSteps" hidden>
        <div class="row">
          <button id="nearLocate" type="button">My location</button>
          <button id="nearCentre" type="button">Centre of the map</button>
          <button id="nearPick" type="button" aria-pressed="false">Pick on the map</button>
        </div>
        <p id="nearPoint" class="hint">No point chosen yet.</p>
        <label class="step"><h3>How far</h3>
          <select id="nearKm">
            <option value="10">10 km</option><option value="25">25 km</option><option value="50" selected>50 km</option>
            <option value="100">100 km</option><option value="250">250 km</option>
          </select></label>
      </div>
      <div class="step two">
        <label><h3>Danger</h3>
          <select id="fireLevel">
            <option value="0" selected>All fires</option><option value="1">Moderate and above</option>
            <option value="2">High and above</option><option value="3">Very High and above</option>
          </select></label>
        <label><h3>Size</h3>
          <select id="fireSize">
            <option value="0">Any size</option><option value="2" selected>2 km² and up</option>
            <option value="10">10 km² and up</option><option value="100">100 km² and up</option>
          </select></label>
      </div>
      <p id="fireSummary" class="hint"></p>
      <div id="fireList" class="fires"></div>
      <details class="about">
        <summary>What the danger levels mean</summary>
        <p class="hint">The level is the chance that a fire reaches 1,000 acres, judged after VIIRS has watched it for two days. The table shows what happened at each level in 2022–2025, years the model never saw.</p>
        <table id="levelTable"></table>
        <p class="hint">The level uses VIIRS only: its size is the VIIRS footprint on squares of 440 m, while a fire's area counts squares of 1 km from MODIS and VIIRS. Fires seen by MODIS only (all fires before 2012) and fires in Hawaii are not rated.</p>
        <p class="hint">This is a suggestion to help decide where to look first. It is not a dispatch order.</p>
      </details>
      <h3>Reported fires that were missed</h3>
      <p class="hint">Wildfires reported by fire agencies (NIFC), 2014 onward. A ring marks each one on the map.</p>
      <div class="choices" id="missedChoices">
        <label><input type="radio" name="missed" value="off" checked><span><b>Off</b></span></label>
        <label><input type="radio" name="missed" value="satellite"><span><b>Missed by the satellites</b><small>No detection within 2 km, from 1 day before to 3 days after the report.</small></span></label>
        <label><input type="radio" name="missed" value="model"><span><b>Not expected by the prediction model</b><small>The ignition model scored the place and day under 0.5. Only 2022 onward, the years the model never saw.</small></span></label>
        <label><input type="radio" name="missed" value="both"><span><b>Missed by both</b></span></label>
      </div>
      <p class="hint" id="missedNote"></p>
    </div>
    <div id="fireDetail" hidden></div>`;
  document.body.appendChild(panel);
  $("fireClose").onclick = () => toggle(false);
  $("missedChoices").addEventListener("change", e => { missed = e.target.value; loadMissed(); });
  $("fireMode").addEventListener("change", e => setMode(e.target.value));
  $("fireLevel").addEventListener("change", e => { find.level = +e.target.value; load(); });
  $("fireSize").addEventListener("change", e => { find.minKm2 = +e.target.value; load(); });
  $("markers").addEventListener("change", load);
  wireNear();
}

function toggle(show) {
  open = show ?? !open;
  $("firePanel").hidden = !open;
  $("fireBtn")?.setAttribute("aria-expanded", String(open));
  if (open) { window.satelliteView?.toggle(false); load(); }
}

// ---------- 3. List and markers ----------

function refresh() {                  // the view or the dates changed; wait until the map rests
  clearTimeout(timer);
  timer = setTimeout(() => { load(); if (missed !== "off") loadMissed(); }, 300);
}

async function load() {
  const onMap = $("markers").value !== "off";
  request?.abort();
  if (!open && !onMap) return drawMarkers([]);
  if (find.mode === "near" && find.lat == null) return drawList(null, "Choose a point: your location, the centre of the map, or a click on the map.");
  request = new AbortController();
  const common = { start: state.start, end: state.end, min_km2: find.minKm2, min_level: find.level };
  try {
    const data = find.mode === "near"
      ? await api("/api/events/near", { ...common, lat: find.lat, lon: find.lon, km: find.km }, request.signal)
      : await api("/api/events", { ...common, bbox: viewParams().bbox }, request.signal);
    drawList(data);
  } catch (e) { if (e.name !== "AbortError") drawList(null, e.message); }
}

function drawList(data, message) {
  const fires = data?.events ?? [], n = fires.length;
  const where = find.mode === "near" ? `within ${find.km} km` : "on screen";
  const size = find.minKm2 ? ` of ${find.minKm2} km² or more` : "";
  const level = find.level ? `, ${$("fireLevel").selectedOptions[0].text.toLowerCase()}` : "";
  const when = `${pretty(state.start)} – ${pretty(state.end)}`;
  const order = find.mode === "near" ? "Most dangerous first, then nearest." : "Largest first.";
  $("fireSummary").textContent = message ?? ((!n ? `No fire${size} ${where}${level}, ${when}.`
    : `${data.truncated ? `The first ${n}` : n} ${n === 1 ? "fire" : "fires"}${size} ${where}${level}, ${when}. ${order}`) +
    (data.note ? ` ${data.note}` : ""));
  $("fireList").replaceChildren(...fires.map(f => {
    const b = document.createElement("button"), d = f.danger;
    b.type = "button"; b.className = "fire"; b.style.setProperty("--level", levelColor(d));
    const side = f.km == null ? days(f.duration_days) : f.km === 0 ? "you are inside its area" : `${f.km} km ${f.direction}`;
    b.innerHTML = `<span class="badge">${levelName(d)}</span>
      <span class="head"><span>${km2(f.area_km2)} km²</span><span>${side}</span></span>
      <span class="line">${range(f.start, f.end)}${f.state ? ` · ${f.state}` : ""}${d?.exposure ? ` · <b>${d.exposure}</b>` : ""}</span>
      <span class="line">${acres(f.area_km2 * ACRES_PER_KM2)}${d?.conditions.length ? ` · ${d.conditions.join(" · ")}` : ""}</span>`;
    b.onclick = () => show(f.event_id);
    return b;
  }));
  drawMarkers($("markers").value === "off" ? [] : fires);
}

function drawMarkers(fires) {
  map.getSource("fires")?.setData({ type: "FeatureCollection", features: fires.map(f => ({
    type: "Feature", geometry: { type: "Point", coordinates: [f.lon, f.lat] },
    properties: { id: f.event_id, color: levelColor(f.danger), km2: f.area_km2 },
  })).reverse() });           // top of the list drawn last, on top
}

function drawLevelTable() {
  const pct = v => `${d3.format(".2~r")(v * 100)}%`;
  $("levelTable").innerHTML = `<tr><th>Level</th><th>Fires</th><th>Reached 1,000 acres</th><th>Typical size</th></tr>` +
    LEVEL_INFO.map(l => `<tr><td><span class="dot" style="--level:${LEVEL_COLOR[l.level]}"></span>${l.name}</td>
      <td>${d3.format(",")(l.fires)}</td><td>${pct(l.reached_1000)}</td><td>${d3.format(",")(l.median_acres)} acres</td></tr>`).join("");
}

// Fly to a box. The zoom is worked out here (not with fitBounds, which fails on the globe
// view), leaving room for the panel on screens wide enough to afford it.
function flyToBox(west, south, east, north, maxZoom = 12) {
  const { clientWidth: W, clientHeight: H } = map.getCanvas(), roomy = W > 1000 && H > 600;
  const cos = Math.cos((south + north) / 2 * Math.PI / 180);
  const lonSpan = Math.max(east - west, 0.02) * 1.25, latSpan = Math.max(north - south, 0.02) * 1.25;
  const freeW = roomy ? W - 520 : W - 40, freeH = roomy ? H - 300 : H - 40;
  const zoom = Math.min(maxZoom, Math.log2(360 * freeW / (512 * lonSpan)), Math.log2(360 * freeH * cos / (512 * latSpan)));
  const degreesPerPixel = 360 / (512 * 2 ** zoom);
  map.flyTo({ zoom, duration: 1500,
              center: [(west + east) / 2 - (roomy ? 200 * degreesPerPixel : 0),
                       (south + north) / 2 - (roomy ? 20 * degreesPerPixel * cos : 0)] });
}

// ---------- 4. Around a point ----------

function setMode(mode) {
  find.mode = mode;
  $("nearSteps").hidden = mode !== "near";
  if (mode !== "near") setPicking(false);
  drawRing(false);
  load();
}

function setPicking(on) {
  find.picking = on;
  $("nearPick").setAttribute("aria-pressed", String(on));
  map.getCanvas().style.cursor = on ? "crosshair" : "";
}

function setPoint(lat, lon, label) {
  Object.assign(find, { lat, lon });
  setPicking(false);
  $("nearPoint").textContent = `${label} (${lat.toFixed(3)}, ${lon.toFixed(3)})`;
  drawRing(true);
  load();
}

function drawRing(fly) {
  const on = find.mode === "near" && find.lat != null;
  if (!on) return map.getSource("ring").setData(EMPTY);
  const dLat = find.km / 111.32, dLon = dLat / Math.cos(find.lat * Math.PI / 180);
  const ring = d3.range(0, 65).map(i => [find.lon + dLon * Math.cos(i * Math.PI / 32), find.lat + dLat * Math.sin(i * Math.PI / 32)]);
  map.getSource("ring").setData({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] } });
  if (fly) flyToBox(find.lon - dLon, find.lat - dLat, find.lon + dLon, find.lat + dLat);
}

function wireNear() {
  $("nearKm").addEventListener("change", e => { find.km = +e.target.value; drawRing(true); load(); });
  $("nearCentre").onclick = () => { const c = map.getCenter(); setPoint(c.lat, c.lng, "Centre of the map"); };
  $("nearPick").onclick = () => {
    setPicking(!find.picking);
    if (find.picking) $("nearPoint").textContent = "Click the map where you are.";
  };
  $("nearLocate").onclick = () => {
    if (!navigator.geolocation) return $("nearPoint").textContent = "Location is not available in this browser.";
    $("nearPoint").textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(
      p => setPoint(p.coords.latitude, p.coords.longitude, "My location"),
      () => $("nearPoint").textContent = "Location was not shared. Use the map centre or pick a point.");
  };
}

// ---------- 5. One fire ----------

function chanceText(d) {
  if (d.level == null) return "Not rated: in Hawaii, or weather data missing.";
  if (d.p1000 === 1) return "Already over 1,000 acres after two days.";
  const info = LEVEL_INFO.find(l => l.level === d.level);
  return info ? `${d3.format(".2~r")(info.reached_1000 * 100)} in 100 fires rated ${d.level_name} reached 1,000 acres (2022–2025).` : "";
}

function ratingHtml(f) {
  const d = f.danger;
  if (!d) return `<p class="hint">${f.detections_viirs ? "No danger level is linked to this fire yet."
    : "Not rated. The level is made from VIIRS detections, and only MODIS saw this fire."}</p>`;
  // Say so when the group the model judged is not exactly this fire.
  const part = [];
  if (d.share < 1) part.push(`The level was made for the VIIRS detections of ${range(d.first_day, d.last_day)}, ${percent(d.share)} of this fire's. The model saw the rest as ${d.parts === 2 ? "another fire" : `${d.parts - 1} other fires`}, mostly because of gaps of more than 2 days.`);
  if (d.fire_share < 1) part.push(`The detections the level was made for also reach into a neighbouring fire of this list: ${percent(d.fire_share)} of them are in this one.`);
  return `<b><span class="dot" style="--level:${levelColor(d)}"></span>${levelName(d)}${d.level == null ? "" : " danger"}</b>
    <div class="factors">
      <div><small>Chance of getting large</small>${chanceText(d)}</div>
      <div><small>What is exposed</small>${d.built_ha == null ? "No data." : `${d3.format(",")(d.built_ha)} ha built-up within 5 km of where it started: ${d.exposure}.`}</div>
      <div><small>The first two days, as VIIRS saw them</small>${acres(d.acres_day2)} after two days, ${acres(d.acres)} in the end, on squares of 440 m${d.conditions.length ? `<br>${d.conditions.join(" · ")}` : ""}${d.land_cover ? `<br>Started in ${d.land_cover}.` : ""}</div>
    </div>
    ${part.length ? `<p class="hint">${part.join(" ")}</p>` : ""}`;
}

async function show(id) {
  const box = $("fireDetail");
  $("fireListView").hidden = true; box.hidden = false; box.textContent = "Loading…";
  let f;
  try { f = await api(`/api/events/${id}`, {}); } catch (e) { box.textContent = e.message; return; }
  current = f;
  const last = Math.max(1, f.duration_days - 1);
  map.getSource("fire-event").setData(f.cells);
  map.setPaintProperty("fire-event", "fill-color", ["interpolate", ["linear"], ["get", "day"],
    0, SPREAD[0], last * 0.33, SPREAD[1], last * 0.66, SPREAD[2], last, SPREAD[3]]);
  flyToBox(f.west, f.south, f.east, f.north);

  const hasMap = f.burned_km2 != null;
  const veg = (f.vegetation || []).filter(v => v.share >= 0.01).slice(0, 6);
  box.innerHTML = `
    <button id="fireBack" type="button">← All fires</button>
    <h2 class="fire-title">${range(f.start, f.end)}</h2>
    <p class="hint">${f.state || ""} · centre ${f.lat.toFixed(2)}, ${f.lon.toFixed(2)}</p>
    <div class="tiles">
      <div><b>${f.duration_days}</b><span>${f.duration_days === 1 ? "day" : "days"}, first to last detection</span></div>
      <div><b>${km2(f.area_km2)}</b><span>km² with hotspots (${acres(f.area_km2 * ACRES_PER_KM2)})</span></div>
      <div><b>${num(f.frp_max)}</b><span>MW, strongest detection</span></div>
    </div>
    <p class="hint">Seen burning on ${f.active_days} of those days. ${f.detections_viirs.toLocaleString()} VIIRS and ${f.detections_modis.toLocaleString()} MODIS detections.</p>
    <div class="fire-legend"><span>Day 1</span><i style="background:linear-gradient(90deg, ${SPREAD.join(",")})"></i><span>Day ${f.duration_days}</span></div>
    <p class="hint">Map colors: the day each square first burned.</p>

    <h3>Danger level</h3>
    ${ratingHtml(f)}

    <h3>How much burned</h3>
    <dl class="sat-facts">
      <dt>From hotspots</dt><dd>${km2(f.area_km2)} km² <small>squares of about 1 km that held a detection; tends to overstate</small></dd>
      <dt>Burned-area map</dt><dd>${hasMap ? km2(f.burned_km2) + " km² <small>MODIS MCD64A1, from the change in the ground</small>"
                                           : "<small>computed for fires of 10 km² and up</small>"}</dd>
      <dt>Burn severity</dt><dd id="fireSevere"><small>press “Sharper pictures” below</small></dd>
    </dl>

    <h3>What burned</h3>
    ${veg.length ? `<div class="veg">${veg.map(v => `<div><span>${v.name}</span><i><b style="width:${Math.round(v.share * 100)}%"></b></i><span>${Math.round(v.share * 100)}% · ${km2(v.km2)} km²</span></div>`).join("")}</div>
                    <p class="hint">Land cover the year before the fire (MODIS MCD12Q1), inside the mapped burned area.</p>`
                 : `<p class="hint">${hasMap ? "The burned-area map shows no burn here, so vegetation is not split. Typical for small or cropland fires."
                                             : "Computed for fires of 10 km² and up."}</p>`}

    <h3>Before and after</h3>
    <div class="choices row" id="pictureStyle">
      <label><input type="radio" name="pstyle" value="natural" checked><span><b>Natural color</b></span></label>
      <label><input type="radio" name="pstyle" value="scar"><span><b>Burn scars</b></span></label>
    </div>
    <div class="pair" id="firePair"></div>
    <p class="hint" id="pictureNote"></p>
    <button id="fireSharp" type="button">Sharper pictures (Landsat, 30 m)</button>
    <div id="fireSharpOut"></div>

    <h3>Reported by fire agencies</h3>
    <div id="fireReported"></div>`;
  $("fireBack").onclick = back;
  $("fireSharp").onclick = () => sharp(f);
  $("pictureStyle").addEventListener("change", e => pictures(f, e.target.value));
  pictures(f, "natural");
  $("fireReported").innerHTML = f.reported.length
    ? f.reported.map(r => `<div class="reported"><b>${pretty(r.date)}</b> · ${r.acres != null ? Math.round(r.acres).toLocaleString() + " acres" : "size unknown"} · ${r.cause || "cause unknown"}
        <small>${r.seen_satellite ? "seen by satellite near its starting point" : "not seen by satellite near its starting point"} ·
        model score ${r.score_ignition.toFixed(2)}${r.split === "test" ? "" : " (a year the model was trained on)"}</small></div>`).join("")
    : `<p class="hint">No reported wildfire starts inside this fire's box. Reports begin in 2014; planned burns and farm fires are not in the list.</p>`;
}

function back() {
  current = null;
  map.getSource("fire-event").setData(EMPTY);
  $("fireDetail").hidden = true; $("fireListView").hidden = false;
}

// ---------- 6. Before and after ----------

function pictureBox(f) {
  const padX = Math.max(0.08, (f.east - f.west) * 0.35), padY = Math.max(0.08, (f.north - f.south) * 0.35);
  const box = [f.south - padY, f.west - padX, f.north + padY, f.east + padX];
  const ratio = (box[2] - box[0]) / ((box[3] - box[1]) * Math.cos((f.lat) * Math.PI / 180));
  return { bbox: box.map(v => v.toFixed(4)).join(","), width: 360, height: Math.round(clamp(360 * ratio, 180, 480)) };
}

function pictures(f, style) {
  const pair = $("firePair"), { bbox, width, height } = pictureBox(f);
  pair.innerHTML = "";
  for (const [label, first] of [["Before", addDays(f.start, -1)], ["After", addDays(f.end, 1)]]) {
    const fig = document.createElement("figure"), img = new Image(), cap = document.createElement("figcaption");
    let date = first;
    const draw = () => {
      img.src = `${SNAPSHOT}&TIME=${date}&BBOX=${bbox}&LAYERS=${STYLES[style][0]}&WIDTH=${width}&HEIGHT=${height}`;
      img.alt = `${label} the fire: Terra MODIS picture of ${date}`;
      cap.querySelector("span").textContent = `${label} · ${pretty(date)}`;
    };
    cap.innerHTML = `<button type="button" aria-label="One day earlier">−</button><span></span><button type="button" aria-label="One day later">+</button>`;
    const [minus, plus] = cap.querySelectorAll("button");
    minus.onclick = () => { date = addDays(date, -1); draw(); };
    plus.onclick = () => { date = addDays(date, 1); draw(); };
    img.style.aspectRatio = `${width} / ${height}`;
    fig.append(img, cap); pair.appendChild(fig); draw();
  }
  $("pictureNote").textContent = `${STYLES[style][1]}. Terra MODIS, 250 m, one picture a day (NASA Worldview). ` +
    "Cloud or smoke in the way? Step a day back or forward with − and +.";
}

async function sharp(f) {
  const out = $("fireSharpOut"), btn = $("fireSharp");
  btn.disabled = true; out.innerHTML = `<p class="hint">Asking Google Earth Engine for cloud-free Landsat views… this takes up to a minute.</p>`;
  try {
    const s = await api(`/api/events/${f.event_id}/sharp`, {});
    if (current !== f) return;
    const fig = (title, part) => part.url
      ? `<figure><img src="${part.url}" alt="${title}: Landsat view, ${part.from} to ${part.to}"><figcaption><span>${title} · ${pretty(part.from)} to ${pretty(part.to)} · ${part.scenes} passes</span></figcaption></figure>`
      : `<figure><figcaption><span>${title}: no Landsat pass in ${pretty(part.from)} to ${pretty(part.to)}</span></figcaption></figure>`;
    out.innerHTML = `<div class="pair">${fig("Before", s.before)}${fig("After", s.after)}</div>` +
      (s.severity_url ? `<figure class="wide"><img src="${s.severity_url}" alt="Burn severity map">
         <figcaption><span>Burn severity: green unchanged, yellow light, red severe</span></figcaption></figure>` : "") +
      `<p class="hint">Landsat, 30 m, cloud-free blend of the ${s.days} days before and after, about ${s.width_km} km across. Colors: infrared, so plants are green and burned ground red-brown.</p>`;
    $("fireSevere").innerHTML = s.severe_km2 != null
      ? `${km2(s.severe_km2)} km² <small>moderate or high severity in Landsat (dNBR 0.27 and up), of ${km2(s.valid_km2)} km² seen cloud-free in the picture</small>`
      : "<small>needs a Landsat view both before and after</small>";
  } catch (e) { out.innerHTML = `<p class="hint">${e.message}</p>`; }
  btn.disabled = false;
}

// ---------- 7. Missed fires ----------

async function loadMissed() {
  const src = map.getSource("fire-reported"), note = $("missedNote");
  if (missed === "off") { src.setData(EMPTY); note.textContent = ""; return; }
  try {
    const d = await api("/api/reported", { bbox: viewParams().bbox, start: state.start, end: state.end, missed });
    src.setData({ type: "FeatureCollection", features: d.fires.map(r => ({ type: "Feature",
      geometry: { type: "Point", coordinates: [r.lon, r.lat] }, properties: r })) });
    const big = d.summary?.by_size.find(s => s.size.startsWith("5"));
    note.textContent = `${d.total.toLocaleString()} in view for these dates` + (d.shown < d.total ? `, the ${d.shown.toLocaleString()} largest shown` : "") + "." +
      (big ? ` Across the U.S. since 2022, of fires over 10,000 acres the satellites missed ${Math.round(big.missed_by_satellites * 100)}% near the starting point and the model did not expect ${Math.round(big.missed_by_model * 100)}%.` : "");
  } catch (e) { note.textContent = e.message; }
}

function reportedPopup(e) {
  const r = e.features[0].properties, seen = r.seen_satellite === true || r.seen_satellite === "true";
  new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat).setHTML(
    `<b>Reported ${pretty(r.date)}</b>
     <div>${r.acres != null && r.acres !== "null" ? Math.round(+r.acres).toLocaleString() + " acres" : "Size unknown"} · ${r.cause && r.cause !== "null" ? r.cause : "cause unknown"}</div>
     <div>${seen ? "Seen by satellite" : "Not seen by any satellite within 2 km"}</div>
     <div>Prediction model score ${(+r.score_ignition).toFixed(2)}${r.split === "test" ? "" : " (training year)"}</div>`).addTo(map);
}

function attach() {
  map.addSource("ring", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "ring-fill", type: "fill", source: "ring", paint: { "fill-color": "#ffffff", "fill-opacity": 0.06 } });
  map.addLayer({ id: "ring-line", type: "line", source: "ring", paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [2, 2] } });
  map.addSource("fire-event", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "fire-event", type: "fill", source: "fire-event", paint: { "fill-color": SPREAD[0], "fill-opacity": 0.8 } });
  map.addSource("fire-reported", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "fire-reported", type: "circle", source: "fire-reported",
    paint: { "circle-radius": ["interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "acres"], 1]], 0, 4, 30, 6, 300, 12, 1000, 20],
             "circle-color": "rgba(255,255,255,0.08)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.6 } });
  map.addSource("fires", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "fires", type: "circle", source: "fires", paint: {
    "circle-color": ["get", "color"], "circle-stroke-color": "#111", "circle-stroke-width": 1.5, "circle-opacity": 0.92,
    // size by area, smaller when the whole country is on screen
    "circle-radius": ["interpolate", ["linear"], ["zoom"],
      3, ["interpolate", ["linear"], ["sqrt", ["get", "km2"]], 0, 2, 2, 3, 20, 6, 45, 9],
      8, ["interpolate", ["linear"], ["sqrt", ["get", "km2"]], 0, 5, 2, 8, 20, 15, 45, 21]],
  } });
  build();
  map.on("click", "fire-reported", reportedPopup);
  map.on("click", "fires", e => { if (!find.picking) { toggle(true); show(e.features[0].properties.id); } });
  for (const layer of ["fire-reported", "fires"]) {
    map.on("mouseenter", layer, () => { if (!find.picking) map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", layer, () => { if (!find.picking) map.getCanvas().style.cursor = ""; });
  }
  map.on("click", e => { if (find.picking) setPoint(e.lngLat.lat, e.lngLat.lng, "Point picked on the map"); });
  $("fireBtn").onclick = () => toggle();
  api("/api/danger/levels", {}).then(levels => { LEVEL_INFO = levels; drawLevelTable(); })
    .catch(e => { $("levelTable").innerHTML = `<tr><td>${e.message}</td></tr>`; });
  load();
  return { toggle, show, refresh, picking: () => find.picking };
}

return { attach };
})();
