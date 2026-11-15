/* The time bar: the dates of the map as a strip you can type into, drag, stretch and play.

   Uses the helpers of app.js ($, state, META, setDates, refresh, addDays, day, iso, pretty).

   The bar shows a span of the record (the "view"). The bright block on it is the period
   the map is showing (the "window").
     Type      the From and To boxes
     Drag      the block to move the period; its two edges to make it longer or shorter
     Period    Shorter / Longer halve or double the period around its middle
     Bar       Zoom in / Zoom out stretch or squeeze the bar itself; Whole record resets it
     Play      slides the period forward step by step, so the map shows change over time
*/
const Timeline = (() => {

const DAY = 864e5;
const days = (a, b) => Math.round((day(b) - day(a)) / DAY);        // from a to b
let first, last, view, drag = null, timer = null, shown = "";

const clampDate = d => d < first ? first : d > last ? last : d;

function apply(a, b) {                           // set the period of the map
  a = clampDate(a); b = clampDate(b);
  if (a > b) [a, b] = [b, a];
  setDates(a, b); $("preset").value = "custom"; refresh();
  draw();
}

function draw() {
  const a = drag ? drag.a : state.start, b = drag ? drag.b : state.end;
  if (!a || !b) return;
  // The bar always contains the period.
  if (a < view[0]) view[0] = a;
  if (b > view[1]) view[1] = b;
  const span = Math.max(1, days(view[0], view[1]));
  const win = $("tlWindow");
  win.style.left = `${days(view[0], a) / span * 100}%`;
  win.style.width = `max(10px, ${(days(a, b) + 1) / span * 100}%)`;
  const n = days(a, b) + 1;
  $("tlLength").textContent = n >= 730 ? `${(n / 365.25).toFixed(1)} years` : n >= 90 ? `${Math.round(n / 30.44)} months` : `${n} ${n === 1 ? "day" : "days"}`;
  if (drag) { $("start").value = a; $("end").value = b; }
  const key = view.join();
  if (key !== shown) { shown = key; ticks(span); }
}

function ticks(span) {
  const box = $("tlTicks"); box.innerHTML = "";
  const y0 = +view[0].slice(0, 4), y1 = +view[1].slice(0, 4);
  const add = (date, text) => {
    const pos = days(view[0], date) / span;
    if (pos < 0 || pos > 1) return;
    const t = document.createElement("span"); t.style.left = `${pos * 100}%`; t.textContent = text; box.appendChild(t);
  };
  if (span > 800) {
    const step = Math.ceil((y1 - y0 + 1) / 13);
    for (let y = y0; y <= y1 + 1; y++) if (y % step === 0) add(`${y}-01-01`, String(y));
  } else {
    const step = span > 400 ? 3 : span > 150 ? 2 : 1;
    for (let y = y0; y <= y1; y++) for (let m = 0; m < 12; m += step) {
      const d = `${y}-${String(m + 1).padStart(2, "0")}-01`;
      add(d, new Date(d + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", year: m === 0 || span < 150 ? "2-digit" : undefined, timeZone: "UTC" }));
    }
  }
}

function resizePeriod(factor) {                  // around its middle
  const n = days(state.start, state.end) + 1, want = Math.max(1, Math.round(n * factor));
  const mid = addDays(state.start, Math.floor(n / 2));
  let a = clampDate(addDays(mid, -Math.floor(want / 2))), b = clampDate(addDays(a, want - 1));
  if (days(a, b) + 1 < want) a = clampDate(addDays(b, 1 - want));
  apply(a, b);
}

function zoomBar(factor) {                       // around the period
  const mid = addDays(state.start, Math.floor(days(state.start, state.end) / 2));
  const half = Math.max(days(state.start, state.end) / 2 + 3, days(view[0], view[1]) * factor / 2);
  view = [clampDate(addDays(mid, -Math.round(half))), clampDate(addDays(mid, Math.round(half)))];
  draw();
}

function play(on) {
  clearInterval(timer); timer = null;
  const btn = $("tlPlay");
  btn.textContent = on ? "Pause" : "Play"; btn.setAttribute("aria-pressed", String(on));
  if (!on) return;
  if (state.end >= last) apply(first, addDays(first, days(state.start, state.end)));    // at the end: start over
  timer = setInterval(() => {
    const n = days(state.start, state.end) + 1, step = Math.max(1, Math.round(n / 4));
    if (state.end >= last) return play(false);
    const b = clampDate(addDays(state.end, step));
    apply(addDays(b, 1 - n), b);
  }, +$("tlSpeed").value);
}

function pointer() {
  const track = $("tlTrack");
  track.addEventListener("pointerdown", e => {
    const edge = e.target.dataset.edge, onWindow = e.target.closest("#tlWindow");
    const span = days(view[0], view[1]), rect = track.getBoundingClientRect();
    const at = x => addDays(view[0], Math.round(clampNumber((x - rect.left) / rect.width, 0, 1) * span));
    play(false);
    if (!onWindow) {                             // a click on the bar moves the period there
      const n = days(state.start, state.end), mid = at(e.clientX);
      const a = clampDate(addDays(mid, -Math.floor(n / 2)));
      return apply(a, addDays(a, n));
    }
    drag = { mode: edge || "move", x: e.clientX, a: state.start, b: state.end, a0: state.start, b0: state.end, perPx: span / rect.width };
    track.setPointerCapture(e.pointerId);
  });
  track.addEventListener("pointermove", e => {
    if (!drag) return;
    const shift = Math.round((e.clientX - drag.x) * drag.perPx), n = days(drag.a0, drag.b0);
    if (drag.mode === "move") {
      const a = clampDate(addDays(drag.a0, Math.max(shift, -days(first, drag.a0))));
      drag.a = days(a, last) < n ? addDays(last, -n) : a; drag.b = addDays(drag.a, n);
    } else if (drag.mode === "left") {
      drag.a = clampDate(addDays(drag.a0, shift)); if (drag.a > drag.b0) drag.a = drag.b0;
    } else {
      drag.b = clampDate(addDays(drag.b0, shift)); if (drag.b < drag.a0) drag.b = drag.a0;
    }
    draw();
  });
  const end = () => { if (!drag) return; const { a, b } = drag; drag = null; apply(a, b); };
  track.addEventListener("pointerup", end);
  track.addEventListener("pointercancel", end);
}

const clampNumber = (v, a, b) => Math.min(b, Math.max(a, v));

function attach() {
  first = META.modis.first_day; last = META.both.last_day;
  view = [first, last];
  pointer();
  $("tlPlay").onclick = () => play(!timer);
  $("tlSpeed").onchange = () => { if (timer) play(true); };
  $("tlShorter").onclick = () => resizePeriod(0.5);
  $("tlLonger").onclick = () => resizePeriod(2);
  $("tlZoomIn").onclick = () => zoomBar(0.5);
  $("tlZoomOut").onclick = () => zoomBar(2);
  $("tlAll").onclick = () => { view = [first, last]; draw(); };
  $("tlWindow").addEventListener("keydown", e => {            // arrow keys move the period by a quarter of its length
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const n = days(state.start, state.end), step = Math.max(1, Math.round((n + 1) / 4)) * (e.key === "ArrowLeft" ? -1 : 1);
    const a = clampDate(addDays(state.start, step));
    apply(days(a, last) < n ? addDays(last, -n) : a, days(a, last) < n ? last : addDays(a, n));
    e.preventDefault();
  });
  // Dates also change from the boxes, the quick dates and the panels: follow them.
  let seen = "";
  setInterval(() => { const k = `${state.start}|${state.end}`; if (k !== seen && !drag) { seen = k; draw(); } }, 200);
  draw();
  return { play, apply };
}

return { attach };
})();
