/* Draft 2, "Forecast": the answer, the dial, and the two pictures of time.

   Uses Draft (draft-common.js) and the helpers of app.js.

   Sections
     1. Answer          sentence, page color and dial from the fires around the centre
     2. Twelve months   one bar a week, with what is usual marked on each
     3. A usual year    normal range, median, and the year of the chosen dates
     4. Satellites      the next passes over the centre of the map
*/
Draft.ready(() => {

const el = id => document.getElementById(id);
const DAY = 864e5;

// ---------- 1. Answer ----------

// The dial: five arcs in the colors of the danger signs, and a needle.
const arc = d3.arc().innerRadius(62).outerRadius(96).cornerRadius(3).padAngle(0.02);
const turn = Math.PI / 5;
el("dial").innerHTML =
  `<g transform="translate(120 120)">${Draft.LEVEL_COLOR.map((c, i) =>
      `<path fill="${c}" d="${arc({ startAngle: -Math.PI / 2 + i * turn, endAngle: -Math.PI / 2 + (i + 1) * turn })}"></path>`).join("")}</g>
   <g class="needle" style="transform: rotate(-100deg)"><path d="M120 120 L116 112 L120 34 L124 112 Z" fill="#fff"></path></g>
   <circle cx="120" cy="120" r="9" fill="#fff"></circle>
   <text x="24" y="136" text-anchor="middle">Low</text><text x="216" y="136" text-anchor="middle">Extreme</text>`;

function where() {
  const name = el("areaName").textContent.trim(), c = map.getCenter();
  const known = name && !/^(Area on screen|United States)$/.test(name);
  return known ? `Within 50 km of the circle, ${name}`
               : `Within 50 km of the circle at ${Math.abs(c.lat).toFixed(2)}° ${c.lat >= 0 ? "N" : "S"}, ${Math.abs(c.lng).toFixed(2)}° W`;
}

Draft.watchNearby(50, near => {
  const top = Draft.worst(near.fires);
  document.body.dataset.level = top < 0 ? "none" : String(top);
  el("whereLine").textContent = where();
  el("nearHeadline").textContent = Draft.nearbySentence(near);
  el("dial").querySelector(".needle").style.transform = `rotate(${top < 0 ? -100 : -72 + top * 36}deg)`;
  el("dial").setAttribute("aria-label", top < 0 ? "Danger dial: nothing rated" : `Danger dial: ${Draft.LEVELS[top]}`);
  el("dialNote").textContent = top < 0
    ? "Nothing rated nearby. The page turns green, blue, yellow, orange or red with the highest danger level around you."
    : `Highest level nearby: ${Draft.LEVELS[top]}. The whole page takes that color, as on the fire danger signs by the road.`;
  const list = el("nearFires");
  list.replaceChildren(...near.fires.slice(0, 12).map(Draft.fireRow));
  if (!near.fires.length) list.innerHTML = `<p class="hint">No fire to list within 50 km in these dates. Try a longer period, or move the map.</p>`;
});

// ---------- 2. Twelve months ----------

let cal = null;

function drawWeeks() {
  const from = addDays(state.end, -370), rows = cal.rows.filter(r => r.date > from && r.date <= state.end).slice(-53);
  const usualOf = r => cal.clim.p50[Math.min(r.wk, 53) - 1];
  const top = Math.sqrt(Math.max(1, ...rows.map(r => r.value), ...rows.map(usualOf)));
  const strip = el("weekStrip");
  strip.replaceChildren(...rows.map((r, i) => {
    const b = document.createElement("button"), usual = usualOf(r), month = day(r.date);
    b.type = "button";
    b.className = (r.flag ? "flag " : "") + (addDays(r.date, 6) >= state.start && r.date <= state.end ? "in" : "");
    b.setAttribute("aria-label", `Week of ${pretty(r.date)}: ${r.value > 0 ? num(r.value) + " burning squares" : "nothing burning"}, usual ${num(usual)}`);
    b.innerHTML = `<i style="height:${Math.sqrt(r.value) / top * 100}%"></i><u style="bottom:${Math.sqrt(usual) / top * 100}%"></u>` +
      (month.getUTCDate() <= 7 ? `<span>${month.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}</span>` : "") +
      `<span class="tip"><b>Week of ${pretty(r.date)}</b><br>${r.value > 0 ? num(r.value) + " burning squares" : "nothing burning"} · usual ${num(usual)}` +
      (r.flag === 2 ? "<br>A record for this time of year" : r.flag === 1 ? "<br>Unusual for this time of year" : "") + `</span>`;
    b.onclick = () => window.timeline.apply(r.date, addDays(r.date, 6));
    return b;
  }));
  el("weeksTitle").textContent = `The twelve months up to ${pretty(state.end)}, week by week`;
}

// ---------- 3. A usual year ----------

function drawYear() {
  const W = 1200, H = 300, m = { l: 8, r: 8, t: 30, b: 34 }, yr = +state.end.slice(0, 4);
  const mine = cal.rows.filter(r => r.yr === yr), c = cal.clim;
  const x = d3.scaleLinear([1, 53], [m.l, W - m.r]);
  const y = d3.scaleSqrt([0, Math.max(1, d3.max(c.p90), d3.max(mine, r => r.value) || 0)], [H - m.b, m.t]);
  const weeks = d3.range(1, 54);
  const band = d3.area().x(w => x(w)).y0(w => y(c.p10[w - 1])).y1(w => y(c.p90[w - 1])).curve(d3.curveMonotoneX);
  const line = d3.line().x(d => x(d[0])).y(d => y(d[1])).curve(d3.curveMonotoneX);
  const season = weeks.filter(w => c.critical[w - 1]);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const peak = mine.length ? d3.greatest(mine, r => r.value) : null;
  el("yearCurve").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Fire activity through a usual year here, and in ${yr}">
    ${season.map(w => `<rect class="season" x="${x(w - 0.5)}" y="${H - m.b + 6}" width="${x(w + 0.5) - x(w - 0.5) + 0.5}" height="5"></rect>`).join("")}
    <path class="band" d="${band(weeks)}"></path>
    <path class="usual" d="${line(weeks.map(w => [w, c.p50[w - 1]]))}"></path>
    <path class="this" d="${line(mine.map(r => [r.wk, r.value]))}"></path>
    ${months.map((mn, i) => `<text x="${x(1 + i * 53 / 12)}" y="${H - 6}">${mn}</text>`).join("")}
    ${season.length ? `<text class="label" x="${x(season[0] - 0.5)}" y="${H - m.b + 2}" dy="-4">usual fire season</text>` : ""}
    ${peak && peak.value > 0 ? `<text class="label" x="${Math.min(x(peak.wk) + 8, W - 190)}" y="${Math.max(y(peak.value) - 8, 16)}">${yr}: peak in the week of ${pretty(peak.date).replace(/, \d+$/, "")}</text>` : `<text class="label" x="${m.l}" y="18">${yr}: nothing burned here</text>`}
  </svg>`;
}

Draft.watchCalendar(c => { cal = c; redraw(); });
function redraw() {
  if (!cal) return;
  el("seasonLine").textContent = Draft.seasonSentence(cal, state.end);
  drawWeeks(); drawYear();
}
let seen = "";
setInterval(() => { const k = `${state.start}|${state.end}`; if (k !== seen) { seen = k; redraw(); } }, 300);

// ---------- 4. Satellites ----------

function drawPasses() {
  const c = map.getCenter(), now = new Date();
  const rows = window.satelliteView.passesOver({ lat: c.lat, lon: c.lng }, now).slice(0, 8);
  el("passList").innerHTML = rows.map(r => {
    const mins = Math.round((r.time - now) / 60000);
    return `<div><i style="background:${r.sat.color}"></i><b>${r.time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</b>
      <small>${r.sat.name}, ${mins < 60 ? `in ${mins} min` : `in ${Math.floor(mins / 60)} h ${mins % 60} min`}, ${r.daylight ? "in daylight" : "at night"}</small></div>`;
  }).join("") || `<p class="hint">No pass in the next 24 hours.</p>`;
}
map.on("moveend", drawPasses);
setInterval(drawPasses, 60000);
drawPasses();
el("skyOpen").onclick = () => { window.satelliteView.toggle(true); el("top").scrollIntoView(); };

});
