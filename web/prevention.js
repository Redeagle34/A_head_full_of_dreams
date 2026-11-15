/* Prevention: which cells of the area on screen to treat with prescribed burns, so that a wildfire
   spreads as little as possible (server/critical.py, plan in CriticalNode.md).

   Uses the helpers of app.js ($, map, api, viewParams, num). app.js calls Prevention.attach()
   when the map is ready.

   Sections
     1. Panel     budget, wind, number of simulated fires
     2. Search    ask the server, draw the burn probability and the cells to treat
*/
const Prevention = (() => {

const EMPTY = { type: "FeatureCollection", features: [] };
const RAMP = ["#2b1a4a", "#6a1b7a", "#c2185b", "#ff6a1f", "#ffe66d"];      // burn probability, low -> high
const TREAT = "#35e0d0";
const WINDS = [["N", 0], ["NE", 45], ["E", 90], ["SE", 135], ["S", 180], ["SW", 225], ["W", 270], ["NW", 315]];

let open = false, request = null, result = null;
const pct = v => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`;
const box = b => ({ type: "Polygon", coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });

// ---------- 1. Panel ----------

function build() {
  const panel = document.createElement("aside");
  panel.id = "preventPanel"; panel.className = "sat-panel prevent-panel glass"; panel.hidden = true;
  panel.innerHTML = `
    <div class="panel-head"><div><div class="eyebrow">Area on screen</div><h2>Prevention</h2></div>
      <button id="preventClose" type="button" aria-label="Close prevention">Close</button></div>
    <p class="hint">Which cells to treat with prescribed burns so that a wildfire spreads least. Thousands of simulated fires start where fires started in 2000–2025 and spread cell by cell with vegetation, tree cover, wind and slope. The search then removes the cells that cut the most likely spread routes. Cells are 0.1° (about 10 km).</p>
    <div class="step two">
      <label><h3>Area to treat</h3>
        <select id="preventBudget">
          <option value="250">250 km²</option><option value="500">500 km²</option><option value="1000" selected>1,000 km²</option>
          <option value="2000">2,000 km²</option><option value="5000">5,000 km²</option>
        </select></label>
      <label><h3>Simulated fires</h3>
        <select id="preventRuns">
          <option value="2000">2,000</option><option value="5000">5,000</option><option value="10000" selected>10,000</option><option value="20000">20,000</option>
        </select></label>
    </div>
    <div class="step two">
      <label><h3>Wind from</h3>
        <select id="preventWindFrom">${WINDS.map(([n, d]) => `<option value="${d}"${d === 270 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
      <label><h3>Wind, m/s</h3>
        <input id="preventWind" type="number" min="0" max="40" step="0.5" placeholder="Usual here"></label>
    </div>
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
      <p class="hint"><b>Limits.</b> Fires stop at the edge of the screen. Land with no land cover record (never near a VIIRS fire) is treated as land fire cannot cross. Wind is one direction and speed for the whole area; slope comes from the mean height of each cell. Fuel moisture and the season are not in the model. This helps decide where to look first; it is not a treatment plan.</p>
    </details>`;
  document.body.appendChild(panel);
  $("preventClose").onclick = () => toggle(false);
  $("preventRun").onclick = search;
  $("preventClear").onclick = clear;
}

function toggle(show) {
  show = show ?? !open;
  if (show) for (const id of ["fireBtn", "satBtn"])       // they share the left side of the screen
    if ($(id).getAttribute("aria-expanded") === "true") $(id).click();
  open = show;
  $("preventPanel").hidden = !open;
  $("preventBtn").setAttribute("aria-expanded", String(open));
}

// ---------- 2. Search ----------

async function search() {
  request?.abort();
  request = new AbortController();
  const wind = $("preventWind").value;
  const params = { bbox: viewParams().bbox, budget_km2: $("preventBudget").value, runs: $("preventRuns").value,
                   wind_from: $("preventWindFrom").value, ...(wind !== "" ? { wind_ms: wind } : {}) };
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
  $("preventStatus").textContent = `${s.runs.toLocaleString()} fires simulated on ${s.burnable.toLocaleString()} cells that can burn. Wind ${s.wind_ms} m/s from ${WINDS.find(w => w[1] === +s.wind_from)?.[0] ?? s.wind_from + "°"}.`;
  $("preventReduction").textContent = pct(s.reduction);
  $("preventTreated").textContent = Math.round(s.treated_km2).toLocaleString();
  $("preventCount").textContent = result.critical.length;
  $("preventList").innerHTML = result.critical.length ? result.critical.map((c, i) => `
    <button type="button" data-i="${i}"><b>${c.rank}</b><span>${c.vegetation}<small>removes ${pct(c.share)} of the connected routes · burn probability ${pct(c.burn_probability)}</small></span></button>`).join("")
    : `<p class="hint">No cell lowers the spread here: the simulated fires stay where they start.</p>`;
  $("preventList").onclick = e => {
    const c = result.critical[e.target.closest("button")?.dataset.i];
    if (c) map.fitBounds([[c.bounds[0], c.bounds[1]], [c.bounds[2], c.bounds[3]]], { padding: 160, maxZoom: 10 });
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
     <div>${p.vegetation}</div><div>${(+p.ignitions).toLocaleString()} fires started here, ${(+p.fires_seen).toLocaleString()} touched it (2000–2025)</div>`).addTo(map);
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
  for (const id of ["fireBtn", "satBtn"])
    $(id).addEventListener("click", () => { if (open) toggle(false); });   // opening one of them closes this panel
  return { toggle };
}

return { attach };
})();
