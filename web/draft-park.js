/* Draft 1, "Field guide": the words column and the calendar band.

   Uses Draft (draft-common.js) and the helpers of app.js.

   Sections
     1. Words column     sentence, danger sign and list for the fires around the cross
     2. Calendar band    every week of the record as one square; a click goes to that week
*/
Draft.ready(() => {

const el = id => document.getElementById(id);

// ---------- 1. Words column ----------

el("sign").innerHTML = Draft.LEVELS.map((name, i) => `<span style="--c:${Draft.LEVEL_COLOR[i]}">${name}</span>`).join("");

Draft.watchNearby(50, near => {
  el("nearHeadline").textContent = Draft.nearbySentence(near);
  const top = Draft.worst(near.fires), sign = el("sign");
  sign.classList.toggle("none", top < 0);
  [...sign.children].forEach((s, i) => s.classList.toggle("on", i === top));
  sign.setAttribute("aria-label", top < 0 ? "No rated fire nearby" : `Highest danger level nearby: ${Draft.LEVELS[top]}`);
  el("signNote").textContent = top < 0
    ? "No rated fire within 50 km in these dates. Levels exist from 2012, when the sharper VIIRS sensor began."
    : `Highest level among the fires within 50 km: ${Draft.LEVELS[top]}.`;
  const list = el("nearFires");
  list.replaceChildren(...near.fires.slice(0, 8).map(Draft.fireRow));
  if (!near.fires.length) list.innerHTML = `<p class="hint">Nothing to list. Move the map, or widen the dates on the black band below.</p>`;
});

// ---------- 2. Calendar band ----------

let cal = null;
const RAMP = d3.scaleSequentialSqrt(d3.interpolateRgbBasis(["#4a3a12", "#b98a12", "#ffd23f", "#fff6cf"]));
const MONTHS = { 1: "Jan", 5: "Feb", 9: "Mar", 14: "Apr", 18: "May", 22: "Jun", 27: "Jul", 31: "Aug", 36: "Sep", 40: "Oct", 44: "Nov", 49: "Dec" };

function draw() {
  if (!cal) return;
  const box = el("calGrid"), W = Math.max(box.clientWidth, 600), H = Math.max(box.clientHeight, 120);
  const years = cal.years.filter(y => cal.rows.filter(r => r.yr === y).length >= 4).sort((a, b) => b - a);   // newest on top
  const left = 40, top = 22, cw = (W - left) / 53, ch = (H - top) / years.length;
  RAMP.domain([0, d3.quantile(cal.rows.map(r => r.value).filter(v => v > 0).sort(d3.ascending), 0.995) || 1]);
  const svg = d3.create("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("preserveAspectRatio", "none");
  // the usual season, as a bar above the weeks it covers
  svg.append("g").selectAll("rect").data(cal.clim.critical.map((on, k) => ({ on, k })).filter(d => d.on)).join("rect")
     .attr("x", d => left + d.k * cw).attr("y", top - 6).attr("width", cw + 0.5).attr("height", 3).attr("fill", "#ff8c1a");
  svg.append("g").selectAll("text").data(Object.entries(MONTHS)).join("text")
     .attr("x", ([w]) => left + (w - 1) * cw).attr("y", 11).text(([, m]) => m);
  svg.append("g").selectAll("text").data(years.filter((y, i) => ch >= 11 || i % 2 === 0)).join("text")
     .attr("x", left - 6).attr("y", y => top + years.indexOf(y) * ch + ch / 2 + 4).attr("text-anchor", "end").text(y => y);
  const tip = d3.select(box).selectAll(".tip").data([0]).join("div").attr("class", "tip").style("display", "none");
  svg.append("g").selectAll("rect").data(cal.rows.filter(r => years.includes(r.yr))).join("rect").attr("class", "wk")
     .attr("x", r => left + (r.wk - 1) * cw + 0.5).attr("y", r => top + years.indexOf(r.yr) * ch + 0.5)
     .attr("width", Math.max(1, cw - 1)).attr("height", Math.max(1, ch - 1))
     .attr("fill", r => r.value > 0 ? RAMP(r.value) : "#1a1d20")
     .on("click", (e, r) => window.timeline.apply(r.date, addDays(r.date, 6)))
     .on("pointermove", (e, r) => {
       const usual = cal.clim.p50[Math.min(r.wk, 53) - 1];
       tip.style("display", "block").style("left", `${e.offsetX}px`).style("top", `${e.offsetY}px`)
          .html(`<b>Week of ${pretty(r.date)}</b><br>${r.value > 0 ? num(r.value) + " burning squares" : "nothing burning"}, usual ${num(usual)}` +
                (r.flag === 2 ? "<br>A record for this time of year" : r.flag === 1 ? "<br>Unusual for this time of year" : ""));
     })
     .on("pointerleave", () => tip.style("display", "none"));
  // unusual and record weeks: a red corner mark, larger for a record
  svg.append("g").attr("pointer-events", "none").selectAll("rect").data(cal.rows.filter(r => r.flag && years.includes(r.yr))).join("rect")
     .attr("x", r => left + (r.wk - 1) * cw + 0.5).attr("y", r => top + years.indexOf(r.yr) * ch + 0.5)
     .attr("width", Math.max(1, cw - 1)).attr("height", r => r.flag === 2 ? Math.max(1, ch - 1) : Math.max(1, (ch - 1) * 0.34))
     .attr("fill", "none").attr("stroke", "#ff3b47").attr("stroke-width", r => r.flag === 2 ? 1.6 : 0)
     .each(function (r) { if (r.flag === 1) d3.select(this).attr("fill", "#ff3b47"); });
  // the period on the map now
  const g = svg.append("g").attr("pointer-events", "none");
  for (const r of cal.rows) {
    if (addDays(r.date, 6) < state.start || r.date > state.end || !years.includes(r.yr)) continue;
    g.append("rect").attr("x", left + (r.wk - 1) * cw).attr("y", top + years.indexOf(r.yr) * ch)
     .attr("width", cw).attr("height", ch).attr("fill", "none").attr("stroke", "#fff").attr("stroke-width", 1.5);
  }
  box.querySelector("svg")?.remove();
  box.prepend(svg.node());
}

Draft.watchCalendar(c => {
  cal = c;
  el("seasonLine").textContent = Draft.seasonSentence(c, state.end);
  draw();
});
new ResizeObserver(draw).observe(el("calGrid"));
let seen = "";
setInterval(() => {                               // the dates moved: redraw the white outline and the sentence
  const k = `${state.start}|${state.end}`;
  if (k !== seen && cal) { seen = k; el("seasonLine").textContent = Draft.seasonSentence(cal, state.end); draw(); }
}, 300);

});
