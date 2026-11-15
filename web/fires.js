/* Fires as single events, and the reported fires that were missed.

   Uses the helpers of app.js ($, state, map, api, viewParams, pretty, addDays, num).

   Sections
     1. Panel               list of fires in view, largest first
     2. One fire            dates, duration, area, vegetation, spread on the map
     3. Before and after    daily NASA pictures (no key) and sharper Landsat pictures
     4. Missed fires        reported wildfires the satellites or the model missed
*/
const Fires = (() => {

let open = false, current = null, listTimer = null, missed = "off";
const SNAPSHOT = "https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&CRS=EPSG:4326&FORMAT=image/jpeg";
const STYLES = { natural: ["MODIS_Terra_CorrectedReflectance_TrueColor", "Natural color"],
                 scar: ["MODIS_Terra_CorrectedReflectance_Bands721", "Burn scars (infrared): burned ground is red-brown, plants green"] };
const SPREAD = ["#ffe66d", "#ff6a1f", "#b0005a", "#4a1486"];      // first day -> last day
const range = (a, b) => a === b ? pretty(a) : `${pretty(a)} to ${pretty(b)}`;
const km2 = v => v >= 100 ? Math.round(v).toLocaleString() : (+v.toFixed(1)).toLocaleString();

// ---------- 1. Panel ----------

function build() {
  const panel = document.createElement("aside");
  panel.id = "firePanel"; panel.className = "sat-panel fire-panel glass"; panel.hidden = true;
  panel.innerHTML = `
    <div class="panel-head"><div><div class="eyebrow">Area and dates on screen</div><h2>Fires, one by one</h2></div>
      <button id="fireClose" type="button" aria-label="Close fires">Close</button></div>
    <div id="fireListView">
      <p class="hint">Detections that touch in space and follow within 5 days are one fire. Largest first, 2 km² and up.</p>
      <div id="fireList" class="sat-passes"></div>
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
}

function toggle(show) {
  open = show ?? !open;
  $("firePanel").hidden = !open;
  $("fireBtn")?.setAttribute("aria-expanded", String(open));
  if (open) { window.satelliteView?.toggle(false); loadList(); }
}

function loadList() {
  if (!open || current) return;
  clearTimeout(listTimer);
  listTimer = setTimeout(async () => {
    const box = $("fireList");
    try {
      const { bbox } = viewParams();
      const data = await api("/api/events", { bbox, start: state.start, end: state.end });
      box.innerHTML = "";
      for (const f of data.events.slice(0, 60)) {
        const b = document.createElement("button"); b.type = "button";
        b.innerHTML = `<span><b>${km2(f.area_km2)} km²</b> · ${f.duration_days} ${f.duration_days === 1 ? "day" : "days"} · ${f.state || ""}` +
                      `<small>${range(f.start, f.end)}</small></span>`;
        b.onclick = () => show(f.event_id);
        box.appendChild(b);
      }
      if (!data.events.length) box.textContent = "No fire of 2 km² or more here in these dates.";
    } catch (e) { box.textContent = e.message; }
  }, 300);
}

// ---------- 2. One fire ----------

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
  // Fly to the fire. The zoom is worked out here (not with fitBounds, which fails on the
  // globe view), leaving room for the panel on screens wide enough to afford it.
  const { clientWidth: W, clientHeight: H } = map.getCanvas(), roomy = W > 1000 && H > 600;
  const lonSpan = Math.max(f.east - f.west, 0.02) * 1.25, latSpan = Math.max(f.north - f.south, 0.02) * 1.25;
  const freeW = roomy ? W - 520 : W - 40, freeH = roomy ? H - 300 : H - 40;
  const zoom = Math.min(12, Math.log2(360 * freeW / (512 * lonSpan)),
                        Math.log2(360 * freeH * Math.cos(f.lat * Math.PI / 180) / (512 * latSpan)));
  const degreesPerPixel = 360 / (512 * 2 ** zoom);
  map.flyTo({ zoom, duration: 1500,
              center: [(f.west + f.east) / 2 - (roomy ? 200 * degreesPerPixel : 0),
                       (f.south + f.north) / 2 - (roomy ? 20 * degreesPerPixel * Math.cos(f.lat * Math.PI / 180) : 0)] });

  const hasMap = f.burned_km2 != null;
  const veg = (f.vegetation || []).filter(v => v.share >= 0.01).slice(0, 6);
  box.innerHTML = `
    <button id="fireBack" type="button">← All fires in view</button>
    <h2 class="fire-title">${range(f.start, f.end)}</h2>
    <p class="hint">${f.state || ""} · centre ${f.lat.toFixed(2)}, ${f.lon.toFixed(2)}</p>
    <div class="tiles">
      <div><b>${f.duration_days}</b><span>${f.duration_days === 1 ? "day" : "days"}, first to last detection</span></div>
      <div><b>${km2(f.area_km2)}</b><span>km² with hotspots</span></div>
      <div><b>${num(f.frp_max)}</b><span>MW, strongest detection</span></div>
    </div>
    <p class="hint">Seen burning on ${f.active_days} of those days. ${f.detections_viirs.toLocaleString()} VIIRS and ${f.detections_modis.toLocaleString()} MODIS detections.</p>
    <div class="fire-legend"><span>Day 1</span><i style="background:linear-gradient(90deg, ${SPREAD.join(",")})"></i><span>Day ${f.duration_days}</span></div>
    <p class="hint">Map colors: the day each square first burned.</p>

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
  map.getSource("fire-event").setData({ type: "FeatureCollection", features: [] });
  $("fireDetail").hidden = true; $("fireListView").hidden = false;
  loadList();
}

// ---------- 3. Before and after ----------

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

// ---------- 4. Missed fires ----------

async function loadMissed() {
  const src = map.getSource("fire-reported"), note = $("missedNote");
  if (missed === "off") { src.setData({ type: "FeatureCollection", features: [] }); note.textContent = ""; return; }
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
  build();
  const empty = { type: "FeatureCollection", features: [] };
  map.addSource("fire-event", { type: "geojson", data: empty });
  map.addLayer({ id: "fire-event", type: "fill", source: "fire-event", paint: { "fill-color": SPREAD[0], "fill-opacity": 0.8 } });
  map.addSource("fire-reported", { type: "geojson", data: empty });
  map.addLayer({ id: "fire-reported", type: "circle", source: "fire-reported",
    paint: { "circle-radius": ["interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "acres"], 1]], 0, 4, 30, 6, 300, 12, 1000, 20],
             "circle-color": "rgba(255,255,255,0.08)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.6 } });
  map.on("click", "fire-reported", reportedPopup);
  map.on("mouseenter", "fire-reported", () => map.getCanvas().style.cursor = "pointer");
  map.on("mouseleave", "fire-reported", () => map.getCanvas().style.cursor = "");
  map.on("moveend", () => { loadList(); if (missed !== "off") loadMissed(); });
  for (const id of ["start", "end", "preset"]) $(id).addEventListener("change", () => setTimeout(() => { loadList(); if (missed !== "off") loadMissed(); }, 50));
  $("fireBtn").onclick = () => toggle();
  return { toggle, show };
}

return { attach };
})();
