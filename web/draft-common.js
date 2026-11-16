/* Design drafts: what the three drafts share in behaviour.

   Loaded after app.js on each draft page, in place of layout.js.

   Sections
     1. Switcher          one button that moves to the next design, keeping place and dates
     2. Small switches    the bits layout.js wires on the main page
     3. Data for a place  history of the area on screen, and fires around its centre
     4. Words             plain-language sentences built from that data
*/
const Draft = (() => {

const PAGES = [["draft-park.html", "Field guide"], ["draft-forecast.html", "Forecast"], ["draft-guide.html", "Guide map"]];
const here = PAGES.findIndex(([file]) => location.pathname.endsWith(file));
const embedded = window.self !== window.top;
if (embedded) document.documentElement.classList.add("embedded");

// ---------- 1. Switcher ----------

function remember() {                            // so the next design opens on the same place and dates
  if (typeof map === "undefined" || !map) return;
  const c = map.getCenter();
  sessionStorage.setItem("draft-view", JSON.stringify({ lng: c.lng, lat: c.lat, zoom: map.getZoom(), start: state.start, end: state.end }));
}

function buildSwitcher() {
  if (embedded || here < 0) return;
  const next = PAGES[(here + 1) % PAGES.length];
  const bar = document.createElement("nav");
  bar.className = "draft-switch"; bar.setAttribute("aria-label", "Design drafts");
  bar.innerHTML = `<span>Design ${here + 1} of ${PAGES.length}: ${PAGES[here][1]}</span>
    <a class="next" href="${next[0]}">Next design: ${next[1]}</a>
    <a href="drafts.html">All three side by side</a><a href="index.html">Current page</a>`;
  bar.addEventListener("click", remember);
  document.body.appendChild(bar);
  addEventListener("keydown", e => {             // D moves to the next design
    if (e.key.toLowerCase() === "d" && !e.target.closest("input, select, textarea")) { remember(); location.href = next[0]; }
  });
}

function restore() {
  let v; try { v = JSON.parse(sessionStorage.getItem("draft-view")); } catch (e) { v = null; }
  if (!v) return;
  map.jumpTo({ center: [v.lng, v.lat], zoom: v.zoom });
  if (v.start && v.end) window.timeline?.apply(v.start, v.end);
}

// ---------- 2. Small switches ----------

function wire() {
  const one = s => document.querySelector(s);
  one("#tlMore")?.addEventListener("click", e => e.target.setAttribute("aria-expanded", String(one("#timeline").classList.toggle("more"))));
  one("#filtersClose")?.addEventListener("click", () => one("#filtersBtn").click());
}

/* Run fn once the map, the satellites and the fires are all attached. */
function ready(fn) {
  const t = setInterval(() => {
    if (typeof map !== "undefined" && map && window.fireView && window.satelliteView) { clearInterval(t); restore(); fn(); }
  }, 120);
}

// ---------- 3. Data for a place ----------

/* History of the area on screen: one row per week of the whole record.
   fn receives { rows: [{date, yr, wk, value, flag}], clim: {p50, p90, critical}, years } */
function watchCalendar(fn) {
  let timer = null, request = 0;
  const load = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (state.layer === "none") return;
      const mine = ++request;
      try {
        const c = await api("/api/calendar", viewParams());
        if (mine !== request) return;
        const rows = c.weeks.map((date, i) => ({ date, ...isoWeek(date), value: c.value[i], flag: c.flag[i] }));
        fn({ rows, clim: c.clim, years: [...new Set(rows.map(r => r.yr))] });
      } catch (e) { /* the draft keeps its last picture */ }
    }, 450);
  };
  map.on("moveend", load);
  document.getElementById("layerChoices")?.addEventListener("change", load);
  load();
}

/* Fires within `km` of the centre of the map, in the dates of the time bar, most dangerous first.
   `km` is a number, or a function that returns the distance chosen now.
   fn receives { fires, km, place: {lat, lon} } */
function watchNearby(distance, fn) {
  let timer = null, request = 0, lastKey = "";
  const load = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const km = typeof distance === "function" ? distance() : distance;
      const c = map.getCenter(), key = `${c.lat.toFixed(3)},${c.lng.toFixed(3)},${km},${state.start},${state.end}`;
      if (key === lastKey) return;
      lastKey = key;
      const mine = ++request;
      try {
        const d = await api("/api/events/near", { lat: c.lat.toFixed(4), lon: c.lng.toFixed(4), km, start: state.start, end: state.end, min_km2: 0 });
        if (mine === request) fn({ fires: d.events ?? [], km, place: { lat: c.lat, lon: c.lng } });
      } catch (e) { if (mine === request) fn({ fires: [], km, place: { lat: c.lat, lon: c.lng }, error: e.message }); }
    }, 450);
  };
  map.on("moveend", load);
  setInterval(load, 700);                        // the dates change without a map event
  load();
}

// ---------- 4. Words ----------

const LEVELS = ["Low", "Moderate", "High", "Very High", "Extreme"];
const LEVEL_COLOR = ["#4caf50", "#3d8bfd", "#ffd23f", "#ff8c1a", "#e3172d"];     // the U.S. fire danger sign colors, as in fires.js
const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

/* The highest danger level among fires, or -1 when none is rated. */
const levelOf = f => f.danger?.level ?? null;
const worst = fires => fires.reduce((m, f) => levelOf(f) == null ? m : Math.max(m, levelOf(f)), -1);

/* What the fires around a place amount to, in one sentence. */
function nearbySentence({ fires, km, error }) {
  if (error) return error;
  if (!fires.length) return `No fire was seen within ${km} km in these dates.`;
  const top = worst(fires), big = fires.filter(f => levelOf(f) != null && levelOf(f) >= 2).length;
  if (top < 0) return `${plural(fires.length, "fire")} seen within ${km} km in these dates. None could be rated.`;
  if (top < 2) return `${plural(fires.length, "fire")} seen within ${km} km in these dates, none rated above ${LEVELS[top]}.`;
  return `${plural(fires.length, "fire")} seen within ${km} km in these dates. ${big === 1 ? "One is" : big + " are"} rated High or above.`;
}

/* How the last week of the chosen dates compares with the same week in other years. */
function seasonSentence(cal, endDate) {
  const wk = isoWeek(endDate).wk, k = Math.min(wk, 52) - 1;
  const usual = cal.clim.p50[k], high = cal.clim.p90[k], inSeason = cal.clim.critical[k];
  const row = cal.rows.findLast(r => r.date <= endDate);
  const month = new Date(endDate + "T00:00:00Z").toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
  const season = inSeason ? `${month} is inside the usual fire season here.` : `${month} is outside the usual fire season here.`;
  if (!row || row.value === 0) return `${season} Nothing burned in this area that week.`;
  if (row.flag === 2) return `${season} That week set a record for this time of year.`;
  if (row.flag === 1) return `${season} That week was unusually active.`;
  return row.value > usual ? `${season} That week was a little busier than usual, within the normal range.`
                           : `${season} That week was normal or quieter than usual.`;
}

buildSwitcher();
wire();
/* One row of a fire list: level badge, where it is from the centre, when, how large. */
function fireRow(f) {
  const b = document.createElement("button"), lv = levelOf(f);
  b.type = "button"; b.className = "fire";
  b.style.setProperty("--level", lv == null ? "#9a9a9a" : LEVEL_COLOR[lv]);
  const where = f.km != null ? (f.km < 1 ? "at the centre" : `${Math.round(f.km)} km ${f.direction}`) : (f.state || "");
  b.innerHTML = `<span class="badge">${lv == null ? "Not rated" : LEVELS[lv]}</span>
    <span class="head"><span>${where}</span><span>${Math.round(f.area_km2 * 247.105).toLocaleString()} acres</span></span>
    <span class="line">${f.start === f.end ? pretty(f.start) : pretty(f.start) + " to " + pretty(f.end)} · ${plural(f.duration_days, "day")}</span>
    <span class="line">${f.danger?.conditions?.length ? f.danger.conditions.slice(0, 2).join("; ") : (f.danger ? "near " + f.danger.exposure : "seen by MODIS only, so not rated")}</span>`;
  b.onclick = () => { window.fireView.toggle(true); window.fireView.show(f.event_id); };
  return b;
}

return { ready, watchCalendar, watchNearby, nearbySentence, seasonSentence, worst, levelOf, fireRow, plural, LEVELS, LEVEL_COLOR, embedded };
})();
