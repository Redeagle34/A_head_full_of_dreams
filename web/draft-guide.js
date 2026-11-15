/* Draft 3, "Guide map": the lobes and the year wheel.

   Uses Draft (draft-common.js) and the helpers of app.js.

   Sections
     1. Lobes         which lobe is swollen: the map, the fires, the year, or the Earth alone
     2. Satellites    the others stay in orbit; the picked one opens a bubble and the Earth turns under it
     3. Fires lobe    sentence, sign and list for the fires around the red dot
     4. Year wheel    one ring is one year; a petal is a week
*/
Draft.ready(() => {

const el = id => document.getElementById(id);

// ---------- 1. Lobes ----------

function open(which) {
  document.body.dataset.open = which;
  for (const b of document.querySelectorAll(".grow")) b.setAttribute("aria-expanded", String(b.dataset.lobe === which));
  setTimeout(drawWheel, 430);                     // after the swell, at the new size
}
for (const b of document.querySelectorAll(".grow"))
  b.onclick = () => open(document.body.dataset.open === b.dataset.lobe ? "map" : b.dataset.lobe);
addEventListener("keydown", e => {
  if (e.key !== "Escape" || !el("satLightbox")?.hidden) return;      // Escape closes the enlarged picture first
  if (window.satelliteView && !el("satCard").hidden) window.satelliteView.toggle(false);
  else open("map");
});

// A plain click on the Earth (not a drag, not a fire, not a satellite) leaves the Earth alone on screen.
const back = document.createElement("button");
back.type = "button"; back.className = "earth-back"; back.hidden = true; back.textContent = "Back to the guide";
back.onclick = () => open("map");
document.body.appendChild(back);
new MutationObserver(() => { back.hidden = document.body.dataset.open !== "earth"; })
  .observe(document.body, { attributes: true, attributeFilter: ["data-open"] });

function onSatellite(point) {
  return window.satelliteView.sats.some(s => s.screen && Math.hypot(s.screen.x - point.x, s.screen.y - point.y) < 50);
}
map.on("click", e => {
  if (window.fireView.picking() || onSatellite(e.point)) return;
  const layers = ["fire", "fires", "fire-reported"].filter(id => map.getLayer(id));
  if (map.queryRenderedFeatures(e.point, { layers }).length) return;
  if (document.body.dataset.open !== "earth") open("earth");
});

// ---------- 2. Satellites ----------

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

// The others stay in orbit; the Earth turns until the picked satellite looks straight down at it,
// with the satellite set to the right of the bubble.
Satellites.options.keepOthers = true;
Satellites.options.onSelect = sat => {
  if (!sat?.here) return;
  const earthOnly = document.body.dataset.open === "earth";
  map.flyTo({ center: [sat.here.lon, sat.here.lat], zoom: Math.min(map.getZoom(), earthOnly ? 2.3 : 2), duration: 1800,
              offset: earthOnly ? [180, 20] : [230, 40], essential: true });
};

// ---------- 3. Fires lobe ----------

el("sign").innerHTML = Draft.LEVELS.map((name, i) => `<span style="--c:${Draft.LEVEL_COLOR[i]}">${name}</span>`).join("");

Draft.watchNearby(50, near => {
  el("nearHeadline").textContent = Draft.nearbySentence(near).replace("within 50 km", "within 50 km of the red dot");
  const top = Draft.worst(near.fires), sign = el("sign");
  [...sign.children].forEach((s, i) => s.classList.toggle("on", i === top));
  sign.setAttribute("aria-label", top < 0 ? "No rated fire nearby" : `Highest danger level nearby: ${Draft.LEVELS[top]}`);
  const list = el("nearFires");
  list.replaceChildren(...near.fires.slice(0, 14).map(Draft.fireRow));
  if (!near.fires.length) list.innerHTML = `<p class="hint">Nothing to list here. Slide the map or stretch the dates.</p>`;
});

// ---------- 4. Year wheel ----------

let cal = null, year = null, followDates = true;
const TAU = 2 * Math.PI, MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function drawWheel() {
  if (!cal) return;
  if (followDates || year == null) year = +state.end.slice(0, 4);
  const big = document.body.dataset.open === "wheel";
  const S = 400, c = S / 2, r0 = big ? 64 : 58, R = 172, clim = cal.clim;
  const mine = cal.rows.filter(r => r.yr === year);
  const len = d3.scaleSqrt([0, Math.max(1, d3.max(clim.p50), d3.max(mine, r => r.value) || 0)], [0, R - r0]);
  const angle = w => (w - 1) / 52 * TAU;          // 0 = January, at the top
  const petal = d3.arc().innerRadius(r0).cornerRadius(5).padAngle(0.012);
  const at = (w, r) => [c + Math.sin(angle(w) + TAU / 104) * r, c - Math.cos(angle(w) + TAU / 104) * r];
  const inPeriod = r => addDays(r.date, 6) >= state.start && r.date <= state.end;
  const weeks = d3.range(1, 53);
  el("wheel").innerHTML = `<svg viewBox="0 0 ${S} ${S}" role="img" aria-label="The year ${year} here, week by week, against a usual year">
    <g transform="translate(${c} ${c})">
      ${weeks.map(w => `<path class="petal" data-wk="${w}" fill="${clim.critical[w - 1] ? "var(--crimson)" : "var(--marble)"}" stroke="var(--gochujang)" stroke-width="1.5"
          d="${petal({ startAngle: angle(w), endAngle: angle(w + 1), outerRadius: r0 + Math.max(7, len(clim.p50[w - 1])) })}"></path>`).join("")}
    </g>
    ${mine.filter(r => r.value > 0 && r.wk <= 52).map(r => { const [x, y] = at(r.wk, r0 + len(r.value));
        return `<circle cx="${x}" cy="${y}" r="${r.flag ? 6 : 3.4}" fill="${inPeriod(r) ? "var(--crimson)" : "var(--white)"}" stroke="${inPeriod(r) ? "var(--white)" : "var(--cosmos)"}" stroke-width="2" pointer-events="none"></circle>`; }).join("")}
    ${big ? MONTHS.map((m, i) => { const [x, y] = at(1 + i * 52 / 12 + 1.6, R + 16); return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle">${m}</text>`; }).join("") : ""}
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

Draft.watchCalendar(c => { cal = c; el("seasonLine").textContent = Draft.seasonSentence(c, state.end); drawWheel(); });
let seen = "";
setInterval(() => {
  const k = `${state.start}|${state.end}`;
  if (k !== seen && cal) { seen = k; followDates = true; el("seasonLine").textContent = Draft.seasonSentence(cal, state.end); drawWheel(); }
}, 300);

});
