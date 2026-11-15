/* Burning Calendar: keeps the floating parts of the page clear of each other.
 *
 * Loaded after timeline.js; needs nothing from the other scripts.
 *
 *   1. Measure the top bar, the time bar and the legend. style.css places the panels, the
 *      legend and the map buttons from these three numbers.
 *   2. On a phone only one panel is open at a time.
 *   3. Small switches: More on the time bar, the note of the legend, Close in Filters.
 */
(() => {

const PHONE = matchMedia("(max-width: 760px), (max-height: 480px)");     // the same test as in style.css
const SHEETS = ".panel, .sat-panel, .filters";
const root = document.documentElement, one = s => document.querySelector(s);

// ---------- 1. Measure ----------

function measure() {
  const set = (name, px) => root.style.setProperty(name, `${Math.round(px)}px`);
  set("--bar-end", one(".bar").getBoundingClientRect().bottom);
  set("--time-start", root.clientHeight - one("#timeline").getBoundingClientRect().top);
  set("--legend-start", root.clientHeight - one("#legend").getBoundingClientRect().top);   // after the time bar: the legend may stand on it
}
const watch = new ResizeObserver(measure);
for (const s of [".bar", "#timeline", "#legend"]) watch.observe(one(s));
addEventListener("resize", measure);
measure();

// ---------- 2. One sheet at a time ----------

// Each panel is closed the way a person would: with the top bar button that controls it.
function closeOthers(keep) {
  for (const p of document.querySelectorAll(SHEETS))
    if (p !== keep && !p.hidden) one(`[aria-controls="${p.id}"][aria-expanded="true"]`)?.click();
}
new MutationObserver(changes => {
  if (!PHONE.matches) return;
  const opened = changes.map(c => c.target).find(t => !t.hidden && t.matches(SHEETS));
  if (opened) closeOthers(opened);
}).observe(document.body, { attributes: true, attributeFilter: ["hidden"], subtree: true });
PHONE.addEventListener("change", () => { if (PHONE.matches) closeOthers(one(`:is(${SHEETS}):not([hidden])`)); });

// ---------- 3. Small switches ----------

one("#tlMore").onclick = e => e.target.setAttribute("aria-expanded", String(one("#timeline").classList.toggle("more")));
one("#legend").onclick = e => e.currentTarget.classList.toggle("open");
one("#filtersClose").onclick = () => one("#filtersBtn").click();

})();
