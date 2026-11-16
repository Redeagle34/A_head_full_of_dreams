/* Burning Calendar: the first-visit tour.
 *
 * A welcome card, then one short step per tool. Each step lights up the real control; the
 * visitor can use it (the step then moves on by itself) or press Next. Shown once per browser;
 * the "?" button in the top bar starts it again.
 *
 * Loaded after layout.js; uses only the page's elements, not the other scripts.
 */
(() => {

const KEY = "burning-calendar-tour-done";
const one = s => document.querySelector(s);

// target: what is lit up. try: what to do with it; `on` [selector, event] moves the step on when done.
const STEPS = [
  { target: "#legend", title: "Fire seen from space",
    text: "Each colored square is fire that NASA's MODIS and VIIRS satellites saw. The legend says what the colors mean. Click a square for its numbers.",
    action: ["Show the Park Fire, 2024", () => pick("ex:park")] },
  { target: ".search", title: "Go anywhere in the U.S.",
    text: "Type a city, county or park and press Enter. Or just drag and zoom the map.",
    on: ["#place", "keydown", e => e.key === "Enter"] },
  { target: "#timeline", title: "Choose the dates",
    text: "Drag the bright block to move the period, pull its edges to change its length, or press Play to watch fires through time.",
    on: ["#tlPlay", "click"] },
  { target: "#fireBtn", title: "Fires and their danger",
    text: "The fires on screen, largest first, each rated from low to extreme danger. Open it and click a fire to see how it grew day by day.",
    on: ["#fireBtn", "click"] },
  { target: "#preventBtn", title: "Prevention",
    text: "Simulates thousands of wildfires and finds the places where a prescribed burn would stop the most spread.",
    on: ["#preventBtn", "click"] },
  { target: "#satBtn", title: "The satellites",
    text: "See where the fire-watching satellites are right now and the strip of ground each one is scanning.",
    on: ["#satBtn", "click"] },
  { target: "#filtersBtn", title: "Data and colors",
    text: "Pick MODIS, VIIRS or both, and color by intensity, days with fire, or how unusual the dates are.",
    on: ["#filtersBtn", "click"] },
  { target: "#panelBtn", title: "History and report",
    text: "Area history shows every week since 2000 for what is on screen and flags unusual ones. Report builds a printable scientific report.",
    on: ["#panelBtn", "click"] },
];

let step = -1, card, spot, timer, unhook = null;

function pick(value) {              // an entry of Quick dates, the way a person would choose it
  const s = one("#preset");
  if (![...s.options].some(o => o.value === value)) return;
  s.value = value;
  s.dispatchEvent(new Event("change", { bubbles: true }));
}

function closePanels() {            // what a step opened is closed before the next one
  for (const b of document.querySelectorAll(".actions [aria-expanded='true']")) b.click();
}

function build() {
  spot = Object.assign(document.createElement("div"), { className: "tour-spot" });
  card = Object.assign(document.createElement("div"), { className: "tour-card glass" });
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-live", "polite");
  card.setAttribute("aria-label", "Tour of the page");
  document.body.append(spot, card);
  addEventListener("keydown", e => {
    if (!card.hidden && e.key === "Escape") end();
  });
}

function welcome() {
  step = -1;
  spot.hidden = true;
  card.hidden = false;
  card.className = "tour-card glass welcome";
  card.innerHTML = `
    <div class="eyebrow">Welcome</div>
    <h2>Every wildfire satellites saw in the U.S. since 2000</h2>
    <p>A quick tour of the tools: ${STEPS.length} steps, under a minute. Try each tool as you go.</p>
    <div class="tour-buttons"><button type="button" class="primary" data-go="next">Start the tour</button>
      <button type="button" data-go="end">Skip, I'll explore</button></div>`;
  card.style.left = card.style.top = "";
  wire();
  card.querySelector(".primary").focus();
}

function show(i) {
  unhook?.(); unhook = null;
  closePanels();
  step = i;
  const s = STEPS[i], last = i === STEPS.length - 1;
  card.className = "tour-card glass";
  card.innerHTML = `
    <div class="eyebrow">${i + 1} of ${STEPS.length}</div>
    <h2>${s.title}</h2>
    <p>${s.text}</p>
    ${s.action ? `<button type="button" class="tour-try" data-go="action">${s.action[0]}</button>` : ""}
    <div class="tour-dots" aria-hidden="true">${STEPS.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div>
    <div class="tour-buttons">
      ${i ? `<button type="button" data-go="back">Back</button>` : ""}
      <button type="button" data-go="end" class="quiet-button">Skip</button>
      <button type="button" class="primary" data-go="next">${last ? "Start exploring" : "Next"}</button></div>`;
  wire();
  if (s.on) {                       // used the control: move on, after a moment to see what it did
    const [sel, type, test] = s.on, el = one(sel);
    const h = e => { if (!test || test(e)) { unhook?.(); unhook = null; setTimeout(next, 1200); } };
    el?.addEventListener(type, h);
    unhook = () => el?.removeEventListener(type, h);
  }
  one(s.target)?.scrollIntoView({ block: "nearest", inline: "center" });   // the buttons scroll sideways on a phone
  place();
  card.querySelector(".primary").focus({ preventScroll: true });
}

function wire() {
  card.onclick = e => {
    const go = e.target.closest("[data-go]")?.dataset.go;
    if (go === "next") next();
    else if (go === "back") show(step - 1);
    else if (go === "end") end();
    else if (go === "action") { STEPS[step].action[1](); setTimeout(next, 2200); }
  };
}

function next() {
  if (card.hidden) return;
  step + 1 < STEPS.length ? show(step + 1) : end();
}

// Light up the target and put the card next to it, inside the screen.
function place() {
  if (step < 0 || card.hidden) return;
  const el = one(STEPS[step].target);
  if (!el) return;
  const r = el.getBoundingClientRect(), pad = 6, gap = 12, W = innerWidth, H = innerHeight;
  spot.hidden = false;
  Object.assign(spot.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px` });
  const c = card.getBoundingClientRect();
  const below = r.bottom + pad + gap, above = r.top - pad - gap - c.height;
  const top = below + c.height <= H - gap ? below : above >= gap ? above : Math.max(gap, (H - c.height) / 2);
  const left = Math.min(Math.max(gap, r.left + r.width / 2 - c.width / 2), W - c.width - gap);
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

function start() {
  if (!card) build();
  welcome();
  clearInterval(timer);
  timer = setInterval(place, 250);  // panels and the map move things around
}

function end() {
  unhook?.(); unhook = null;
  clearInterval(timer);
  if (step >= 0) closePanels();
  card.hidden = spot.hidden = true;
  step = -1;
  try { localStorage.setItem(KEY, "1"); } catch (e) { /* private window: the tour shows again next time */ }
  one("#tourBtn")?.focus();
}

one("#tourBtn").onclick = start;
let seen = false;
try { seen = localStorage.getItem(KEY) === "1"; } catch (e) { /* no storage: show it */ }
if (!seen) setTimeout(start, 700);

})();
