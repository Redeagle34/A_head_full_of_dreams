/* Draft 3, "Guide map": the stages, the left column, the fires card and the year wheel.

   Uses Draft (draft-common.js) and the helpers of app.js.

   Sections
     1. Stages        the intro (veil and play), the opening, the live Earth, and the exit back
     2. Left column   every card and panel stacks here, so nothing covers anything else
     3. Settings      the tools menu, the map credits, the report builder
     4. Satellites    the others stay in orbit; the picked one opens a card and the Earth turns under it
     5. Fires card    fires around the red dot: where, how far, how dangerous, how large
     6. Year wheel    one ring is one year; a petal is a week
*/
Draft.ready(() => {

const el = id => document.getElementById(id);
const wait = ms => new Promise(r => setTimeout(r, ms));

// ---------- 1. Stages ----------

// The page opens on the name, the Earth under a white veil and a play button. Play sends the
// Earth to the centre, then its blue fills the window and the tools come in around it.
// The middle of the map is the middle of the free space: on the intro, the blue area right of
// the name; live, the space right of the column and above the time bar. The red dot sits there.
function padding(stage = document.body.dataset.stage) {
  if (innerWidth <= 1180) return { left: 0, top: 0, right: 0, bottom: 0 };
  if (stage === "intro") return { left: Math.round(innerWidth * 0.42), top: 0, right: 0, bottom: 0 };
  return { left: el("rail").offsetWidth + 20, top: 70, right: 0, bottom: 140 };
}
function placeDot(p) {
  const box = el("lobeMap");
  el("lobeMap").querySelector(".cross").style.cssText =
    `left:${p.left + (box.clientWidth - p.left - p.right) / 2}px; top:${p.top + (box.clientHeight - p.top - p.bottom) / 2}px`;
}
function frame(duration) { const p = padding(); placeDot(p); map.easeTo({ padding: p, duration }); }
// The intro shows the whole globe; play flies to the United States.
map.jumpTo({ center: [-100, 38], zoom: 1.6, padding: padding("intro") });
addEventListener("resize", () => frame(0));
function toUnitedStates() {
  const p = padding("live"), free = el("lobeMap").clientWidth - p.left - p.right;
  const zoom = Math.max(2.2, Math.min(4.2, Math.log2(360 * free / (512 * 62))));
  placeDot(p);
  map.flyTo({ center: [-97.5, 38.5], zoom, padding: p, duration: 1600, essential: true });
}

async function begin() {
  if (document.body.dataset.stage !== "intro") return;
  document.body.dataset.stage = "opening";
  toUnitedStates();
  await wait(760);
  document.body.dataset.stage = "live";
  await wait(500);
  drawWheel();
}
async function leave() {
  if (document.body.dataset.stage !== "live") return;
  closeAll();
  document.body.dataset.stage = "opening";
  await wait(620);
  document.body.dataset.stage = "intro";
  map.easeTo({ center: [-100, 38], zoom: 1.6, padding: padding("intro"), duration: 900 });
  el("begin").focus({ preventScroll: true });
}
el("veil").onclick = begin;
el("exitMap").onclick = leave;
el("begin").focus({ preventScroll: true });

function closeAll() {
  showTools(false);
  window.satelliteView.toggle(false);
  window.fireView.toggle(false);
  for (const [panel, button] of [["filters", "filtersBtn"], ["panel", "panelBtn"]])
    if (!el(panel).hidden) el(button).click();
}

// ---------- 2. Left column ----------

// The satellite card and the panels of the settings join the column above the two cards, and
// push them down; the column scrolls when it is full.
const rail = el("rail");
for (const id of ["panel", "filters", "firePanel", "satPanel"]) rail.prepend(el(id));

function open(which) {
  document.body.dataset.open = which;
  for (const b of document.querySelectorAll(".grow")) b.setAttribute("aria-expanded", String(b.dataset.lobe === which));
}
for (const b of document.querySelectorAll(".grow"))
  b.onclick = () => open(document.body.dataset.open === b.dataset.lobe ? "map" : b.dataset.lobe);

// Each card folds down to its title and opens again.
const ICON_MINI = { open: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 12h12"/></svg>`,
                    shut: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 12h12M12 6v12"/></svg>` };
for (const b of document.querySelectorAll(".mini")) {
  const lobe = b.closest(".lobe"), name = b.getAttribute("aria-label").replace("Minimize ", "");
  const set = small => {
    lobe.classList.toggle("min", small);
    b.innerHTML = small ? ICON_MINI.shut : ICON_MINI.open;
    b.setAttribute("aria-expanded", String(!small));
    b.setAttribute("aria-label", (small ? "Show " : "Minimize ") + name);
  };
  b.onclick = () => set(!lobe.classList.contains("min"));
  set(false);
}

// ---------- 3. Settings ----------

const toolsBtn = el("toolsBtn"), tools = el("actions");
function showTools(on) { tools.hidden = !on; toolsBtn.setAttribute("aria-expanded", String(on)); }
toolsBtn.onclick = () => showTools(tools.hidden);
tools.addEventListener("click", e => {
  if (!e.target.closest("button")) return;
  showTools(false);
  rail.scrollTo({ top: 0, behavior: "smooth" });                     // the panel just opened is at the top
});
addEventListener("pointerdown", e => { if (!tools.hidden && !e.target.closest(".tools")) showTools(false); });

addEventListener("keydown", e => {
  if (e.key !== "Escape" || !el("satLightbox")?.hidden) return;      // Escape closes the enlarged picture first
  if (!tools.hidden) { showTools(false); toolsBtn.focus(); }
  else if (!el("satPanel").hidden) window.satelliteView.toggle(false);
});

// The map credits leave the map and sit at the foot of the settings.
const credits = () => {
  const text = document.querySelector(".maplibregl-ctrl-attrib-inner")?.textContent.trim();
  el("credits").textContent = text ? `Map credits: ${text.replace(/\s*\|\s*/g, " · ")}` : "";
};
setInterval(credits, 3000); credits();

// The report: tick what to include, then open the report page for the Earth on screen.
fetch("/api/report/sections").then(r => r.json()).then(list => {
  el("introSections").replaceChildren(...list.map(s => {
    const l = document.createElement("label");
    l.innerHTML = `<input type="checkbox" value="${s.key}" checked><span>${s.title}</span>`;
    return l;
  }));
}).catch(() => { el("introSections").innerHTML = `<p class="hint">The list of sections is not available now; the next page has it.</p>`; });
el("introGet").onclick = () => {
  const chosen = [...el("introSections").querySelectorAll("input:checked")].map(i => i.value);
  const name = el("areaName").textContent.trim() || "Area on screen";
  const q = new URLSearchParams({ start: state.start, end: state.end, box: `${name}|${viewParams().bbox}` });
  if (chosen.length) q.set("sections", chosen.join(","));
  location.href = `report.html?${q}`;
};

// ---------- 4. Satellites ----------

const ICON = {
  expand: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
             <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
};
el("satEnlarge").innerHTML = ICON.expand;
el("satEnlarge").setAttribute("aria-label", "Enlarge the picture");
el("satEnlarge").title = "Enlarge the picture";
const shut = document.createElement("button");
shut.type = "button"; shut.className = "sat-close"; shut.innerHTML = ICON.close; shut.setAttribute("aria-label", "Close this satellite");
shut.onclick = () => window.satelliteView.toggle(false);
el("satCard").prepend(shut);

// The others stay in orbit; the Earth turns until the picked satellite looks straight down at
// it, set in the free part of the screen to the right of the column.
Satellites.options.keepOthers = true;
Satellites.options.onSelect = sat => {
  rail.scrollTo({ top: 0, behavior: "smooth" });
  if (!sat?.here) return;
  map.flyTo({ center: [sat.here.lon, sat.here.lat], zoom: Math.min(map.getZoom(), 2.3), duration: 1800, essential: true });
};

// ---------- 5. Fires card ----------

const pick = { on: false };
el("sign").innerHTML = Draft.LEVELS.map((name, i) => `<span style="--c:${Draft.LEVEL_COLOR[i]}"><i></i>${name}</span>`).join("");
let near = { fires: [] }, showAll = false;

function drawNear() {
  const level = +el("nearLevel").value, size = +el("nearSize").value, km = el("nearRadius").value;
  const fires = near.fires.filter(f => (level === 0 || (Draft.levelOf(f) ?? -1) >= level) && f.area_km2 >= size);
  const top = Draft.worst(fires), sign = el("sign");
  [...sign.children].forEach((s, i) => s.classList.toggle("on", i === top));
  sign.setAttribute("aria-label", top < 0 ? "No rated fire nearby" : `Highest danger level nearby: ${Draft.LEVELS[top]}`);
  el("nearCount").textContent = near.error ? near.error
    : !fires.length ? `None within ${km} km in these dates.`
    : `${Draft.plural(fires.length, "fire")} within ${km} km${top < 0 ? ", none rated" : `, the worst rated ${Draft.LEVELS[top]}`}.`;
  el("nearFires").replaceChildren(...(showAll ? fires : fires.slice(0, 4)).map(Draft.fireRow));
  el("nearAll").hidden = fires.length <= 4;
  el("nearAll").textContent = showAll ? "Show fewer" : `Show all ${fires.length}`;
}
Draft.watchNearby(() => +el("nearRadius").value, n => { near = n; drawNear(); });
for (const id of ["nearLevel", "nearSize"]) el(id).onchange = () => { showAll = false; drawNear(); };
el("nearAll").onclick = () => { showAll = !showAll; drawNear(); };

// The red dot is the centre this card counts around; a dashed ring on the Earth shows the distance.
// Both show only while the card is open.
const EMPTY = { type: "FeatureCollection", features: [] };
map.addSource("near-ring", { type: "geojson", data: EMPTY });
map.addLayer({ id: "near-ring", type: "line", source: "near-ring",
               paint: { "line-color": "#ffffff", "line-width": 2.5, "line-dasharray": [2, 1.5], "line-opacity": .95 } });
function drawRing() {
  const on = document.body.dataset.stage === "live" && !el("lobeNear").classList.contains("min");
  if (!on) return map.getSource("near-ring").setData(EMPTY);
  const c = map.getCenter(), km = +el("nearRadius").value;
  const dLat = km / 111.32, dLon = dLat / Math.cos(c.lat * Math.PI / 180);
  const ring = d3.range(0, 65).map(i => [c.lng + dLon * Math.cos(i * Math.PI / 32), c.lat + dLat * Math.sin(i * Math.PI / 32)]);
  map.getSource("near-ring").setData({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] } });
}
map.on("move", drawRing);
el("nearRadius").addEventListener("change", drawRing);
new MutationObserver(drawRing).observe(document.body, { attributes: true, attributeFilter: ["data-stage"] });
new MutationObserver(drawRing).observe(el("lobeNear"), { attributes: true, attributeFilter: ["class"] });

// Where the red dot is: my location, or a point picked on the Earth.
el("nearMine").onclick = () => {
  if (!navigator.geolocation) return el("nearCount").textContent = "Location is not available in this browser.";
  el("nearCount").textContent = "Finding your location…";
  navigator.geolocation.getCurrentPosition(
    p => { el("areaName").textContent = "Around my location"; map.flyTo({ center: [p.coords.longitude, p.coords.latitude], zoom: 8 }); },
    () => el("nearCount").textContent = "Location was not shared. Drag the Earth or pick a point.");
};
function setPick(on) {
  pick.on = on;
  el("nearPickBtn").setAttribute("aria-pressed", String(on));
  el("nearPickBtn").textContent = on ? "Now click the Earth" : "Pick a point";
  map.getCanvas().style.cursor = on ? "crosshair" : "";
}
el("nearPickBtn").onclick = () => setPick(!pick.on);
map.on("click", e => { if (pick.on) { setPick(false); map.flyTo({ center: e.lngLat, zoom: Math.max(map.getZoom(), 7) }); } });
el("nearMore").onclick = () => { window.fireView.toggle(true); rail.scrollTo({ top: 0, behavior: "smooth" }); };

api("/api/danger/levels", {}).then(levels => {
  const pct = v => `${d3.format(".2~r")(v * 100)}%`;
  el("nearLevels").innerHTML = `<tr><th>Level</th><th>Grew past 1,000 acres</th><th>Typical size</th></tr>` +
    levels.map(l => `<tr><td><i class="dot" style="background:${Draft.LEVEL_COLOR[l.level]}"></i>${l.name}</td>
      <td>${pct(l.reached_1000)}</td><td>${d3.format(",")(l.median_acres)} acres</td></tr>`).join("");
}).catch(() => { el("nearLevels").innerHTML = ""; });

// ---------- 6. Year wheel ----------

let cal = null, year = null, followDates = true;
const TAU = 2 * Math.PI, MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function drawWheel() {
  if (!cal) return;
  if (followDates || year == null) year = +state.end.slice(0, 4);
  const S = 400, c = S / 2, r0 = 62, R = 168, clim = cal.clim;
  const mine = cal.rows.filter(r => r.yr === year);
  const len = d3.scaleSqrt([0, Math.max(1, d3.max(clim.p50), d3.max(mine, r => r.value) || 0)], [0, R - r0]);
  const angle = w => (w - 1) / 52 * TAU;          // 0 = January, at the top
  const petal = d3.arc().innerRadius(r0).cornerRadius(3).padAngle(0.012);
  const at = (w, r) => [c + Math.sin(angle(w) + TAU / 104) * r, c - Math.cos(angle(w) + TAU / 104) * r];
  const inPeriod = r => addDays(r.date, 6) >= state.start && r.date <= state.end;
  const weeks = d3.range(1, 53);
  el("wheel").innerHTML = `<svg viewBox="-24 -24 ${S + 48} ${S + 48}" role="img" aria-label="The year ${year} here, week by week, against a usual year">
    <g transform="translate(${c} ${c})">
      ${weeks.map(w => `<path class="petal" data-wk="${w}" fill="${clim.critical[w - 1] ? "var(--crimson)" : "var(--marble)"}"
          d="${petal({ startAngle: angle(w), endAngle: angle(w + 1), outerRadius: r0 + Math.max(7, len(clim.p50[w - 1])) })}"></path>`).join("")}
    </g>
    ${mine.filter(r => r.value > 0 && r.wk <= 52).map(r => { const [x, y] = at(r.wk, r0 + len(r.value));
        return `<circle cx="${x}" cy="${y}" r="${r.flag ? 6 : 3.6}" fill="${inPeriod(r) ? "var(--crimson)" : "var(--cosmos)"}" stroke="var(--white)" stroke-width="1.5" pointer-events="none"></circle>`; }).join("")}
    ${MONTHS.map((m, i) => { const [x, y] = at(1 + i * 52 / 12 + 1.6, R + 20); return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle">${m}</text>`; }).join("")}
    <text class="yr" x="${c}" y="${c}" text-anchor="middle" dominant-baseline="central">${year}</text>
  </svg>`;
  for (const p of el("wheel").querySelectorAll(".petal")) p.onclick = () => {
    const r = mine.find(m => m.wk === +p.dataset.wk);
    if (r) window.timeline.apply(r.date, addDays(r.date, 6));
  };
  el("wheelYear").textContent = year;
  const peak = d3.greatest(mine, r => r.value);
  el("wheelNote").textContent = !peak || peak.value === 0 ? `Nothing burned here in ${year}.`
    : `In ${year} the busiest week here began ${pretty(peak.date).replace(/, \d+$/, "")}` +
      (peak.flag === 2 ? ", a record for that time of year." : peak.flag === 1 ? ", unusually active for that time of year." : ", within the normal range.");
}

function step(by) {
  const years = cal.years, i = years.indexOf(year) + by;
  if (i < 0 || i >= years.length) return;
  year = years[i]; followDates = false; drawWheel();
}
el("wheelPrev").onclick = () => step(-1);
el("wheelNext").onclick = () => step(1);

// The year and the dates at the top of the fires card follow the time bar.
function dates() {
  el("nearYear").textContent = state.end.slice(0, 4);
  const f = d => new Date(d + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  el("nearDates").textContent = `${f(state.start)} to ${f(state.end)}`;
}
Draft.watchCalendar(c => { cal = c; dates(); el("seasonLine").textContent = Draft.seasonSentence(c, state.end); drawWheel(); });
let seen = "";
setInterval(() => {
  const k = `${state.start}|${state.end}`;
  if (k === seen) return;
  seen = k; dates();
  if (cal) { followDates = true; el("seasonLine").textContent = Draft.seasonSentence(cal, state.end); drawWheel(); }
}, 300);

});
