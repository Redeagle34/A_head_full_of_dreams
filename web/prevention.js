/* Prevention: which cells of the area on screen to treat with prescribed burns, so that a wildfire
   spreads as little as possible (server/critical.py, plan in CriticalNode.md).

   Uses the helpers of app.js ($, map, api, viewParams, num). app.js calls Prevention.attach()
   when the map is ready.

   Sections
     1. Panel     cell size for the view, cells to treat, wind, number of simulated fires
     2. Search    ask the server, draw the burn probability and the cells to treat
*/
const Prevention = (() => {

const EMPTY = { type: "FeatureCollection", features: [] };
const RAMP = ["#2b1a4a", "#6a1b7a", "#c2185b", "#ff6a1f", "#ffe66d"];      // burn probability, low -> high
const TREAT = "#35e0d0";
const WINDS = [["N", 0], ["NE", 45], ["E", 90], ["SE", 135], ["S", 180], ["SW", 225], ["W", 270], ["NW", 315]];

const COUNTS = [5, 10, 20, 40, 60];          // cells to treat offered in the panel (the server allows up to 60)
const SIZE_NAME = { 1: "about 1 km", 2: "about 2 km", 4: "about 4 km", 10: "about 10 km" };

let open = false, request = null, result = null, sizeRequest = null, sizeTimer = null, cellKm2 = null;
const pct = v => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`;
const box = b => ({ type: "Polygon", coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });

// ---------- 1. Panel ----------

function build() {
  const panel = document.createElement("aside");
  panel.id = "preventPanel"; panel.className = "sat-panel prevent-panel glass"; panel.hidden = true;
  panel.innerHTML = `
    <div class="panel-head"><div><div class="eyebrow">Area on screen</div><h2>Prevention</h2></div>
      <button id="preventClose" type="button" aria-label="Close prevention">Close</button></div>
    <p class="hint">Which cells to treat with prescribed burns so that a wildfire spreads least. Thousands of simulated fires start where fires started in 2000–2025 and spread cell by cell with vegetation, tree cover, wind and slope. The search then removes the cells that cut the most likely spread routes.</p>
    <p class="prevent-size"><b id="preventSize">–</b><small>Cell size follows the zoom: about 1 km when zoomed in, up to 10 km for a large area.</small></p>
    <div class="step two">
      <label><h3>Cells to treat</h3>
        <select id="preventBudget">${COUNTS.map(n => `<option value="${n}"${n === 10 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
      <label><h3>Simulated fires</h3>
        <select id="preventRuns">
          <option value="2000">2,000</option><option value="5000">5,000</option><option value="10000" selected>10,000</option><option value="20000">20,000</option>
        </select></label>
    </div>
    <div class="step two">
      <label><h3>Wind from</h3>
        <select id="preventWindFrom"><option value="" selected>Usual in each cell</option>${WINDS.map(([n, d]) => `<option value="${d}">${n}</option>`).join("")}</select></label>
      <label><h3>Wind, m/s</h3>
        <input id="preventWind" type="number" min="0" max="40" step="0.5" placeholder="Usual in each cell"></label>
    </div>
    <p class="hint">Usual wind: each cell's mean wind on its high fire-danger days, 2012–2025 (gridMET, 4 km; days when the energy release component is in its top 10%). Pick a direction or speed to use one wind for the whole area instead.</p>
    <button id="preventRun" type="button" class="primary">Find cells to treat</button>
    <p id="preventStatus" class="hint" aria-live="polite"></p>
    <div id="preventResult" hidden>
      <div class="tiles">
        <div><b id="preventReduction">–</b><span>fewer connected fire routes</span></div>
        <div><b id="preventTreated">–</b><span>km² treated</span></div>
        <div><b id="preventCount">–</b><span>cells</span></div>
      </div>
      <div class="fire-legend"><span>Burn probability: low</span><i style="background:linear-gradient(90deg,${RAMP.join(",")})"></i><span>high</span></div>
      <div class="fire-legend"><span><i class="swatch" style="border-color:${TREAT}"></i> cell to treat, in order</span></div>
      <h3>Cells to treat, best first</h3>
      <div id="preventList" class="prevent-list"></div>
      <p id="preventCheck" class="hint"></p>
      <button id="preventClear" type="button">Clear from the map</button>
    </div>
    <details class="about">
      <summary>How it works, and its limits</summary>
      <p class="hint"><b>Weights.</b> p<sub>ij</sub> is the share of simulated fires that started in cell i and reached cell j (Yemshanov et al. 2021). The jump between two cells follows Alexandridis et al. (2008): p<sub>h</sub> × (1 + vegetation) × (1 + density) × wind × slope. p<sub>h</sub> is set so the simulated fires have the mean size of the real fires that started in this area.</p>
      <p class="hint"><b>Search.</b> Remove, one at a time, the cell that lowers the sum of p<sub>ij</sub> over pairs still connected the most per km², until the area is used. Good, not necessarily the best possible choice.</p>
      <p class="hint"><b>Limits.</b> Fires stop at the edge of the screen. Built-up land, water, snow and barren land do not burn. The usual wind is an average: on the day of a fire it can blow from elsewhere. Hawaii has no gridMET wind; there the chosen wind, or 3 m/s from the west, is used. Slope comes from the mean height of each cell. Fuel moisture and the season are not in the model. The finest cells are about 1 km, the grid the fires are recorded on. This helps decide where to look first; it is not a treatment plan.</p>
    </details>`;
  document.body.appendChild(panel);
  $("preventClose").onclick = () => toggle(false);
  $("preventRun").onclick = search;
  $("preventBudget").onchange = budgetLabels;
  $("preventClear").onclick = clear;
}

function toggle(show) {
  show = show ?? !open;
  if (show) for (const id of ["fireBtn", "satBtn"])       // they share the left side of the screen
    if ($(id).getAttribute("aria-expanded") === "true") $(id).click();
  open = show;
  $("preventPanel").hidden = !open;
  $("preventBtn").setAttribute("aria-expanded", String(open));
  if (open) loadSize();
}

// The cell size the search would use for the view on screen.
async function loadSize() {
  sizeRequest?.abort();
  sizeRequest = new AbortController();
  try {
    const info = await api("/api/critical/size", { bbox: viewParams().bbox }, sizeRequest.signal);
    cellKm2 = info.cell_km2;
    $("preventSize").textContent = `Cells here: ${SIZE_NAME[info.size]} (${info.burnable.toLocaleString()} that can burn)`;
    $("preventRun").disabled = false;
  } catch (e) {
    if (e.name === "AbortError") return;
    cellKm2 = null;
    $("preventSize").textContent = e.message;
    $("preventRun").disabled = true;
  }
  budgetLabels();
}

function budgetLabels() {
  for (const o of $("preventBudget").options)
    o.textContent = cellKm2 ? `${o.value} (about ${Math.round(o.value * cellKm2).toLocaleString()} km²)` : o.value;
}

// ---------- 2. Search ----------

async function search() {
  request?.abort();
  request = new AbortController();
  const wind = $("preventWind").value;
  const from = $("preventWindFrom").value;
  // A little more than n cells of the centre's size: cells further north are a little smaller.
  const params = { bbox: viewParams().bbox, budget_km2: (+$("preventBudget").value * cellKm2 * 1.005).toFixed(2),
                   runs: $("preventRuns").value, ...(wind !== "" ? { wind_ms: wind } : {}), ...(from !== "" ? { wind_from: from } : {}) };
  $("preventStatus").textContent = "Simulating fires and searching… (a few seconds)";
  $("preventRun").disabled = true;
  try {
    result = await api("/api/critical", params, request.signal);
    draw();
  } catch (e) {
    if (e.name !== "AbortError") $("preventStatus").textContent = e.message;
  } finally {
    $("preventRun").disabled = false;
  }
}

function draw() {
  const s = result.summary, max = Math.max(...result.cells.map(c => c.burn_probability), 1e-9);
  map.getSource("prevent-cells").setData({ type: "FeatureCollection", features: result.cells.map(c => ({
    type: "Feature", geometry: box(c.bounds), properties: { ...c, t: Math.sqrt(c.burn_probability / max) } })) });
  map.getSource("prevent-critical").setData({ type: "FeatureCollection", features: result.critical.map(c => ({
    type: "Feature", geometry: box(c.bounds), properties: c })) });
  $("preventStatus").textContent = `${s.runs.toLocaleString()} fires simulated on ${s.burnable.toLocaleString()} cells of ${SIZE_NAME[s.size]} that can burn. `
    + (s.wind_per_cell ? `Wind: usual in each cell, on average ${s.wind_ms} m/s from ${s.wind_from} where fires start.` : `Wind: ${s.wind_ms} m/s from ${s.wind_from} everywhere.`)
    + (s.wind_fallback_cells ? ` ${s.wind_fallback_cells.toLocaleString()} cells have no gridMET wind and use 3 m/s from the west.` : "");
  $("preventReduction").textContent = pct(s.reduction);
  $("preventTreated").textContent = Math.round(s.treated_km2).toLocaleString();
  $("preventCount").textContent = result.critical.length;
  $("preventList").innerHTML = result.critical.length ? result.critical.map((c, i) => `
    <button type="button" data-i="${i}"><b>${c.rank}</b><span>${c.vegetation}<small>removes ${pct(c.share)} of the connected routes · burn probability ${pct(c.burn_probability)}</small></span></button>`).join("")
    : `<p class="hint">No cell lowers the spread here: the simulated fires stay where they start.</p>`;
  $("preventList").onclick = e => {
    const c = result.critical[e.target.closest("button")?.dataset.i];
    if (c) map.flyTo({ center: [(c.bounds[0] + c.bounds[2]) / 2, (c.bounds[1] + c.bounds[3]) / 2] });   // keeps the zoom, so the cell size stays
  };
  $("preventCheck").textContent = `Check: simulated mean fire size ${s.mean_size_simulated} cells against ${s.mean_size_target} in the record (p_h ${s.p_h}). `
    + (s.check_spearman == null ? "" : `Cells the simulation burns most against cells real fires touched most: rank correlation ${s.check_spearman}. Part of this agreement comes from fires starting where fires started before.`);
  $("preventResult").hidden = false;
}

function clear() {
  result = null;
  map.getSource("prevent-cells").setData(EMPTY);
  map.getSource("prevent-critical").setData(EMPTY);
  $("preventResult").hidden = true;
  $("preventStatus").textContent = "";
}

function popup(e) {
  const p = e.features[0].properties;
  const treat = map.queryRenderedFeatures(e.point, { layers: ["prevent-critical-line"] })[0]?.properties;
  new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat).setHTML(
    `<b>${treat ? `Treat, number ${treat.rank}` : "Burn probability " + pct(+p.burn_probability)}</b>
     ${treat ? `<div>Removes ${pct(+treat.share)} of the connected fire routes</div><div>Burn probability ${pct(+p.burn_probability)}</div>` : ""}
     <div>${p.vegetation}</div><div>Wind ${p.wind_ms} m/s from ${p.wind_from}</div><div>${(+p.ignitions).toLocaleString()} fires started here, ${(+p.fires_seen).toLocaleString()} touched it (2000–2025)</div>`).addTo(map);
}

function attach() {
  map.addSource("prevent-cells", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "prevent-cells", type: "fill", source: "prevent-cells", paint: {
    "fill-color": ["interpolate", ["linear"], ["get", "t"], 0, RAMP[0], 0.25, RAMP[1], 0.5, RAMP[2], 0.75, RAMP[3], 1, RAMP[4]],
    "fill-opacity": ["interpolate", ["linear"], ["get", "t"], 0, 0.04, 0.2, 0.3, 1, 0.75], "fill-outline-color": "rgba(0,0,0,0.25)" } });
  map.addSource("prevent-critical", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "prevent-critical-line", type: "line", source: "prevent-critical",
    paint: { "line-color": TREAT, "line-width": 3 } });
  build();
  map.on("click", "prevent-cells", popup);
  map.on("mouseenter", "prevent-cells", () => map.getCanvas().style.cursor = "pointer");
  map.on("mouseleave", "prevent-cells", () => map.getCanvas().style.cursor = "");
  $("preventBtn").onclick = () => toggle();
  map.on("moveend", () => { if (open) { clearTimeout(sizeTimer); sizeTimer = setTimeout(loadSize, 300); } });
  for (const id of ["fireBtn", "satBtn"])
    $(id).addEventListener("click", () => { if (open) toggle(false); });   // opening one of them closes this panel
  return { toggle };
}

return { attach };
})();
