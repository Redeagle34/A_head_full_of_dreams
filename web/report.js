/* Fire report page.
 *
 * Sections
 *   1. Helpers
 *   2. Builder: places (states, areas), dates, sections
 *   3. Ask the server and draw the report
 *   4. One function per section of the report (RENDER). To change how a section looks, change it there.
 *   5. Start
 *
 * The data of every section comes from POST /api/report (server/report.py).
 * Address parameters: start, end, states=CA,OR, box=Name|west,south,east,north (may repeat).
 */

// ---------- 1. Helpers ----------

const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter(c => c != null));
  return node;
};
const int = v => d3.format(",")(Math.round(v));
const num = v => v == null ? "–" : Math.abs(v) >= 100 ? int(v) : d3.format(",.1f")(v);
const pct = v => v == null ? "–" : `${d3.format(".2~r")(v * 100)}%`;
const day = s => new Date(s + "T00:00:00Z");
const pretty = s => day(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const LEVEL_COLOR = { Low: "#4caf50", Moderate: "#3d8bfd", High: "#ffd23f", "Very High": "#ff8c1a", Extreme: "#e3172d", "Not rated": "#9a9a9a" };
const FIRE = "#d9480f", SOFT = "#fdba74", GREY = "#9aa1aa";
const WIDTH = 780;
let STATE_NAMES = {}, META = {}, boxes = [], lastReport = null;

async function getJson(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : `Server error ${res.status}`);
  }
  return res.json();
}

function figure(chart, caption) {
  return el("figure", {}, chart, el("figcaption", { textContent: caption }));
}

// A table with a "CSV" link under it. columns: [key, heading, format?]
function table(rows, columns, name, footnote = "") {
  const head = el("tr", {}, ...columns.map(([, heading]) => el("th", { textContent: heading })));
  const body = rows.map(r => el("tr", {}, ...columns.map(([key, , format]) => {
    const cell = el("td");
    const value = format ? format(r[key], r) : r[key];
    if (value instanceof Node) cell.append(value); else cell.textContent = value ?? "–";
    return cell;
  })));
  const quote = v => `"${String(v ?? "").replaceAll('"', '""')}"`;
  const csv = [columns.map(([, h]) => quote(h)).join(","), ...rows.map(r => columns.map(([k]) => quote(r[k])).join(","))].join("\n");
  const link = el("a", { textContent: "Download this table (CSV)", download: `${name}.csv`,
                         href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })) });
  return el("div", {}, el("table", {}, el("thead", {}, head), el("tbody", {}, ...body)),
            el("div", { className: "table-foot" }, el("span", { textContent: footnote }), link));
}

const plot = options => Plot.plot({ width: WIDTH, marginLeft: 56, style: { fontSize: "12px", background: "transparent" }, ...options });

// ---------- 2. Builder ----------

function drawStates(chosen) {
  $("states").replaceChildren(...Object.keys(STATE_NAMES).sort().map(code => {
    const box = el("input", { type: "checkbox", value: code, checked: chosen.includes(code) });
    return el("label", { title: STATE_NAMES[code] }, box, code);
  }));
}
const chosenStates = () => [...$("states").querySelectorAll("input:checked")].map(i => i.value);
const setStates = on => $("states").querySelectorAll("input").forEach(i => i.checked = on);

function drawBoxes() {
  $("boxes").replaceChildren(...boxes.map((b, i) => el("li", {},
    el("span", {}, b.name, " ", el("small", { textContent: b.bbox.map(v => v.toFixed(2)).join(", ") })),
    el("button", { type: "button", textContent: "Remove", ariaLabel: `Remove ${b.name}`, onclick: () => { boxes.splice(i, 1); drawBoxes(); } }))));
}

async function addPlace() {
  const query = $("place").value.trim(), note = $("placeNote");
  if (query.length < 2) return;
  note.textContent = "Searching…";
  try {
    const url = `https://nominatim.openstreetmap.org/search?${new URLSearchParams({ q: query, format: "jsonv2", countrycodes: "us", limit: 1 })}`;
    const [found] = await (await fetch(url)).json();
    if (!found) return note.textContent = "Place not found. Try a county, park or city name.";
    const [south, north, west, east] = found.boundingbox.map(Number);
    boxes.push({ name: found.display_name.split(",").slice(0, 2).join(","), bbox: [west, south, east, north] });
    drawBoxes(); $("place").value = "";
    note.textContent = "Added. An area is the box around the place found.";
  } catch (e) { note.textContent = "Place search is not reachable."; }
}

function drawQuick() {
  const last = META.both.last_day, lastYear = +last.slice(0, 4), options = [["", "Custom dates"]];
  for (let y = lastYear; y >= lastYear - 5; y--) options.push([`${y}-01-01|${y === lastYear ? last : `${y}-12-31`}`, `Year ${y}`]);
  options.push([`${lastYear - 9}-01-01|${last}`, "Last 10 years"], [`${META.both.first_day}|${last}`, "Whole record"]);
  $("quick").replaceChildren(...options.map(([value, text]) => el("option", { value, textContent: text })));
  $("quick").onchange = e => { if (e.target.value) [$("start").value, $("end").value] = e.target.value.split("|"); };
}

function drawSections(list) {
  $("sections").replaceChildren(...list.map(s =>
    el("label", {}, el("input", { type: "checkbox", value: s.key, checked: true }), s.title)));
}
const chosenSections = () => [...$("sections").querySelectorAll("input:checked")].map(i => i.value);

// ---------- 3. Ask and draw ----------

async function build() {
  const request = { states: chosenStates(), boxes, start: $("start").value, end: $("end").value, sections: chosenSections() };
  if (!request.states.length && !boxes.length) return $("status").textContent = "Choose at least one state or area.";
  if (!request.sections.length) return $("status").textContent = "Tick at least one section.";
  if (!request.start || !request.end) return $("status").textContent = "Choose both dates.";
  $("status").textContent = "Building…"; $("build").disabled = true;
  try {
    lastReport = await getJson("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
    draw(lastReport);
    $("status").textContent = "";
    $("print").disabled = $("json").disabled = false;
  } catch (e) { $("status").textContent = e.message; }
  $("build").disabled = false;
}

function placeText(places) {
  const all = places.states.length === Object.keys(STATE_NAMES).length;
  const states = all ? ["all states in the data (contiguous United States, District of Columbia and Hawaii)"] : places.states.map(s => STATE_NAMES[s] ?? s);
  return [...states, ...places.boxes.map(b => b.name)].join("; ");
}

function draw(report) {
  const head = el("header", {},
    el("h1", { textContent: "Fire activity report" }),
    el("p", { className: "meta" }, el("b", { textContent: "Places: " }), placeText(report.places)),
    el("p", { className: "meta" }, el("b", { textContent: "Period: " }), `${pretty(report.start)} to ${pretty(report.end)}`),
    el("p", { className: "meta" }, el("b", { textContent: "Made: " }), `${pretty(report.generated)} · Burning Calendar · satellite data from NASA FIRMS (MODIS and VIIRS)`));
  const parts = report.sections.map(s => {
    const section = el("section", { id: `s-${s.key}` }, el("h2", { textContent: s.title }));
    if (s.data.note) section.append(el("p", { className: "warn", textContent: s.data.note }));
    try { section.append(...[RENDER[s.key](s.data, report)].flat().filter(Boolean)); }
    catch (e) { section.append(el("p", { className: "warn", textContent: `This section could not be drawn: ${e.message}` })); }
    return section;
  });
  $("report").replaceChildren(head, ...parts);
  document.title = `Fire report · ${report.start} to ${report.end}`;
  if (matchMedia("(max-width: 860px)").matches) $("report").scrollIntoView({ behavior: "smooth" });
}

// ---------- 4. Sections ----------

const RENDER = {
  summary(d) {
    const out = [el("div", { className: "tiles" },
      el("div", {}, el("b", { textContent: int(d.fires) }), el("span", { textContent: "fires" })),
      el("div", {}, el("b", { textContent: `${int(d.area_km2)} km²` }), el("span", { textContent: "area with hotspots" })),
      el("div", {}, el("b", { textContent: d.largest_km2 == null ? "–" : `${int(d.largest_km2)} km²` }), el("span", { textContent: "largest fire" })),
      el("div", {}, el("b", { textContent: int(d.cell_days) }), el("span", { textContent: "active cell-days (MODIS-equivalent)" })))];
    if (d.normal) {
      const n = d.normal, ratio = n.median > 0 ? d.cell_days / n.median : null;
      out.push(el("p", { className: "lead", textContent:
        `Fire activity was ${ratio == null ? "above a normal of zero" : `${d3.format(".2~r")(ratio)} times the normal`} for these dates: ` +
        `${int(d.cell_days)} active cell-days against a median of ${int(n.median)} in the ${n.years} other years on record. ` +
        `It was higher than in ${n.years_below} of those ${n.years} years.` }));
    } else out.push(el("p", { className: "note", textContent: "A comparison with normal is given for periods of one year or less." }));
    out.push(el("p", { className: "note", textContent: "Active cell-days: squares of 1.5 km with fire on a day, added over the period, in MODIS-equivalent units so that years before and after VIIRS can be compared." }));
    return out;
  },

  yearly(d) {
    const rows = d.years.filter(y => y.cell_days > 0 || y.complete);
    const chart = plot({ height: 260, x: { label: null, tickFormat: "d" }, y: { label: "active cell-days", grid: true }, marks: [
      Plot.barY(rows, { x: "year", y: "cell_days", fill: r => r.complete ? FIRE : SOFT, title: r => `${r.year}: ${int(r.cell_days)}${r.complete ? "" : " (part of the year)"}` }),
      d.median_full_years ? Plot.ruleY([d.median_full_years], { stroke: "#1b1d21", strokeDasharray: "4 3" }) : null, Plot.ruleY([0])] });
    return [figure(chart, `Fire activity by year, in MODIS-equivalent units. Dashed line: median of the complete years (${num(d.median_full_years)}). Pale bars: years with part of the data.`),
      table(rows, [["year", "Year"], ["cell_days", "Active cell-days", num], ["complete", "Whole year in the data", v => v ? "yes" : "no"]], "fire-activity-by-year")];
  },

  seasonality(d) {
    const season = d.weeks.filter(w => w.season).map(w => w.week);
    const months = { 1: "Jan", 5: "Feb", 9: "Mar", 14: "Apr", 18: "May", 22: "Jun", 27: "Jul", 31: "Aug", 36: "Sep", 40: "Oct", 44: "Nov", 49: "Dec" };
    const chart = plot({ height: 240, x: { label: null, ticks: Object.keys(months).map(Number), tickFormat: w => months[w] }, y: { label: "active cell-days per week", grid: true }, marks: [
      Plot.barY(d.weeks.filter(w => w.season), { x: "week", y: () => d3.max(d.weeks, w => w.p90), fill: "#fde6c8", inset: -0.5 }),
      Plot.areaY(d.weeks, { x: "week", y1: "p50", y2: "p90", fill: SOFT, fillOpacity: 0.7, curve: "step" }),
      Plot.lineY(d.weeks, { x: "week", y: "p50", stroke: FIRE, strokeWidth: 2, curve: "step" }),
      Plot.lineY(d.weeks, { x: "week", y: "mean", stroke: "#1b1d21", strokeDasharray: "3 3", curve: "step" }), Plot.ruleY([0])] });
    const runs = [];
    for (const w of season) { const last = runs.at(-1); if (last && w === last[1] + 1) last[1] = w; else runs.push([w, w]); }
    const text = runs.length ? `Usual fire season (weeks whose long-term mean is at least half of the peak week): ${runs.map(([a, b]) => a === b ? `week ${a}` : `weeks ${a} to ${b}`).join(", ")}.`
                             : "No week stands out as a fire season in these places.";
    return [figure(chart, "A typical year, by week. Line: the middle year (median). Band: up to the 90th percentile. Dashed: the mean. Shaded columns: the usual fire season."),
      el("p", { textContent: text })];
  },

  unusual(d) {
    const rows = d.series.map(r => ({ ...r, date: day(r.week) }));
    const chart = plot({ height: 240, x: { label: null }, y: { label: "active cell-days per week", grid: true }, marks: [
      Plot.areaY(rows, { x: "date", y: "p90", fill: "#e5e7eb", curve: "step" }),
      Plot.lineY(rows, { x: "date", y: "typical", stroke: GREY, curve: "step" }),
      Plot.lineY(rows, { x: "date", y: "cell_days", stroke: FIRE, strokeWidth: 2 }),
      Plot.dot(rows.filter(r => r.flag), { x: "date", y: "cell_days", r: r => r.flag === 2 ? 6 : 4, fill: r => r.flag === 2 ? "#b91c1c" : FIRE, stroke: "#fff" }), Plot.ruleY([0])] });
    const tag = flag => el("span", { className: `tag ${flag === 2 ? "record" : ""}`, textContent: flag === 2 ? "record" : "unusual" });
    const out = [figure(chart, "Each week of the period (red line) against what is typical for that time of year (grey line: median; grey area: up to the 90th percentile). Dots: unusual weeks; large dark dots: records.")];
    out.push(d.flagged.length
      ? table(d.flagged, [["week", "Week of", pretty], ["cell_days", "Active cell-days", num], ["typical", "Typical (median)", num], ["p90", "90th percentile", num], ["flag", "", tag]],
              "unusual-weeks", `${d.flagged.length} of ${d.weeks_in_period} weeks`)
      : el("p", { textContent: `None of the ${d.weeks_in_period} weeks of the period was unusual for its time of year.` }));
    return out;
  },

  fires(d) {
    const dot = level => level ? el("span", {}, el("span", { className: "dot", style: `background:${LEVEL_COLOR[level]}` }), level) : "not rated";
    return [el("h3", { textContent: "By size" }),
      table(d.by_size, [["size", "Size"], ["fires", "Fires", int], ["area_km2", "Area, km²", num], ["mean_days", "Mean duration, days", num]], "fires-by-size"),
      el("h3", { textContent: `The ${d.largest.length} largest` }),
      table(d.largest, [["start", "First day", pretty], ["end", "Last day", pretty], ["state", "State"], ["days", "Days", int],
                        ["area_km2", "Area from hotspots, km²", num], ["burned_km2", "Burned-area map, km²", num], ["level", "Danger level", dot]], "largest-fires",
            "Burned-area map: MODIS MCD64A1, for fires of 10 km² and more."),
      el("p", { className: "note", textContent: "One fire: detections that touch on squares of about 1 km and follow within 5 days. Area is the area of those squares." })];
  },

  danger(d) {
    if (!d.levels.length) return [];
    const chart = plot({ height: 220, marginLeft: 90, x: { label: "fires", grid: true }, y: { label: null, domain: d.levels.map(l => l.level) }, marks: [
      Plot.barX(d.levels, { y: "level", x: "fires", fill: l => LEVEL_COLOR[l.level], title: l => `${l.level}: ${int(l.fires)} fires` }), Plot.ruleX([0])] });
    const name = v => el("span", {}, el("span", { className: "dot", style: `background:${LEVEL_COLOR[v]}` }), v);
    return [figure(chart, "Fires of the period by danger level. The level is the chance of reaching 1,000 acres, judged after two days of VIIRS passes."),
      table(d.levels, [["level", "Level", name], ["fires", "Fires", int], ["area_km2", "Final area, km²", num]], "fires-by-danger-level"),
      el("h3", { textContent: "What the levels meant in 2022–2025, years the model never saw" }),
      table(d.meaning, [["name", "Level", name], ["fires", "Fires rated", int], ["reached_1000", "Reached 1,000 acres", pct], ["median_acres", "Typical final size, acres", int]], "danger-level-meaning",
            "All rated fires in the United States, not only the places of this report."),
      el("p", { className: "note", textContent: "Not rated: fires seen by MODIS only (all fires before 2012) and fires in Hawaii. The level is a help to decide where to look first, not a dispatch order." })];
  },

  vegetation(d) {
    if (!d.classes.length) return d.note ? [] : [el("p", { textContent: "No fire of 10 km² or more with a mapped burn in these places and dates." })];
    const rows = d.classes.filter(c => c.share >= 0.005);
    const chart = plot({ height: 40 + 26 * rows.length, marginLeft: 220, x: { label: "km² burned", grid: true }, y: { label: null, domain: rows.map(c => c.name) }, marks: [
      Plot.barX(rows, { y: "name", x: "km2", fill: "#5f8f4e", title: c => `${c.name}: ${num(c.km2)} km²` }), Plot.ruleX([0])] });
    return [figure(chart, "Land cover the year before the fire (MODIS MCD12Q1), inside the burned-area map (MODIS MCD64A1)."),
      table(d.classes, [["name", "Land cover"], ["km2", "Burned, km²", num], ["share", "Share", pct]], "vegetation-burned"),
      el("p", { className: "note", textContent: `From ${int(d.fires_with_map)} fires of 10 km² or more. The burned-area map gives ${int(d.burned_km2)} km² for them; the hotspot squares give ${int(d.hotspot_km2)} km². The map misses small and low-severity burns, mostly cropland fires.` })];
  },

  missed(d) {
    if (!d.by_size.length) return [];
    const rows = d.by_size.map(r => ({ ...r, missed: 1 - r.seen_either }));
    const chart = plot({ height: 230, marginBottom: 40, x: { label: "final size of the reported fire, acres", domain: rows.map(r => r.size) }, y: { label: "seen by a satellite", grid: true, percent: true, domain: [0, 100] }, marks: [
      Plot.barY(rows, { x: "size", y: "seen_either", fill: FIRE, title: r => `${r.size}: ${pct(r.seen_either)} of ${int(r.reports)} reports` }), Plot.ruleY([0])] });
    return [figure(chart, "Share of agency-reported wildfires that MODIS or VIIRS detected within 2 km, from 1 day before to 3 days after the report."),
      table(rows, [["size", "Final size, acres"], ["reports", "Reports", int], ["seen_viirs", "Seen by VIIRS", pct], ["seen_modis", "Seen by MODIS", pct], ["seen_either", "Seen by either", pct], ["missed", "Missed", pct]], "reported-fires-seen",
            "Reports: NIFC WFIGS, 2014 onward; all fires of 100 acres or more and a random part of the smaller ones."),
      el("p", { className: "note", textContent: "A map without detections does not mean there was no fire: small fires are mostly missed, and part of the misses on large fires is the reported point lying far from where the fire burned." })];
  },

  sensors(d) {
    const rows = d.years.flatMap(y => [{ year: y.year, sensor: "MODIS", detections: y.modis }, { year: y.year, sensor: "VIIRS", detections: y.viirs }]);
    const chart = plot({ height: 250, x: { label: null, tickFormat: "d" }, y: { label: "detections per year", grid: true }, color: { domain: ["MODIS", "VIIRS"], range: ["#2563eb", FIRE], legend: true }, marks: [
      Plot.lineY(rows, { x: "year", y: "detections", stroke: "sensor", strokeWidth: 2, marker: "circle" }), Plot.ruleY([0])] });
    return [figure(chart, "Raw detections of each sensor, in the chosen places, by the year the fire started. VIIRS starts in 2012 (a second satellite joins in 2018) and counts several times more than MODIS for the same fires. This is why the series above are in MODIS-equivalent units."),
      table(d.years, [["year", "Year"], ["modis", "MODIS detections", int], ["viirs", "VIIRS detections", int], ["fires", "Fires", int]], "detections-by-sensor")];
  },

  methods(d) {
    return [el("dl", { className: "methods" }, ...d.items.flatMap(i => [el("dt", { textContent: i.title }), el("dd", { textContent: i.text })]))];
  },

  sources(d) {
    return [el("ol", { className: "sources" }, ...d.items.map(i => el("li", {}, `${i.name}. `, el("a", { href: i.url, textContent: i.url })))),
      el("p", { className: "note", textContent: `Satellite data in this report ends ${pretty(d.data_ends)}.` })];
  },
};

// ---------- 5. Start ----------

(async function start() {
  try {
    const [geo, meta, sections] = await Promise.all([getJson("data/states.geojson"), getJson("/api/meta"), getJson("/api/report/sections")]);
    STATE_NAMES = Object.fromEntries(geo.features.map(f => [f.properties.state, f.properties.name]));
    META = meta;
    drawSections(sections);
  } catch (e) { $("status").textContent = `The data server is not answering: ${e.message}`; return; }
  const params = new URLSearchParams(location.search), last = META.both.last_day;
  drawStates((params.get("states") || "").split(",").filter(Boolean));
  boxes = params.getAll("box").map(text => {
    const [name, coords] = text.split("|"), bbox = (coords || "").split(",").map(Number);
    return bbox.length === 4 && bbox.every(Number.isFinite) ? { name: name || "Area", bbox } : null;
  }).filter(Boolean);
  drawBoxes(); drawQuick();
  for (const id of ["start", "end"]) { $(id).min = META.both.first_day; $(id).max = last; $(id).onchange = () => $("quick").value = ""; }
  $("start").value = params.get("start") || `${last.slice(0, 4)}-01-01`;
  $("end").value = params.get("end") || last;
  $("statesAll").onclick = () => setStates(true);
  $("statesNone").onclick = () => setStates(false);
  $("sectionsAll").onclick = () => $("sections").querySelectorAll("input").forEach(i => i.checked = true);
  $("sectionsNone").onclick = () => $("sections").querySelectorAll("input").forEach(i => i.checked = false);
  $("placeAdd").onclick = addPlace;
  $("place").onkeydown = e => { if (e.key === "Enter") addPlace(); };
  $("build").onclick = build;
  $("print").onclick = () => print();
  $("json").onclick = () => {
    const link = el("a", { download: `fire-report-${lastReport.start}-${lastReport.end}.json`,
                           href: URL.createObjectURL(new Blob([JSON.stringify(lastReport, null, 1)], { type: "application/json" })) });
    link.click();
  };
  if (boxes.length || chosenStates().length) build();          // came from the map with a place: build at once
})();
