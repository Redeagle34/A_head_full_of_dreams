// Screenshot the Guide map design of Burning Calendar (served locally) for the laptop scene, and
// write where each click lands, so the cursor in the video presses the real buttons.
//   node tools/capture_guide.mjs [url]
//   -> assets/web/guide_intro.png, guide_live.png, guide_zoomed.png, guide_satellite.png, guide_settings.png, guide_history.png
//      assets/web/guide_clicks.json   [{ x, y, img }] in 1920x1080 pixels, in click order
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const URL = process.argv[2] || 'http://localhost:8765/draft-guide.html';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'web');
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const wait = ms => new Promise(r => setTimeout(r, ms));
const clicks = [];
const shot = async name => { await page.screenshot({ path: path.join(OUT, `guide_${name}.png`) }); console.log(name); };
const centre = async sel => page.evaluate(s => { const b = document.querySelector(s).getBoundingClientRect(); return { x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2) }; }, sel);

await page.goto(URL, { waitUntil: 'networkidle', timeout: 120000 });
// the design switcher strip at the top is for comparing drafts; the video shows the page alone
await page.addStyleTag({ content: '.draft-switch { display: none !important; } :root, html { --sw: 0px !important; }' });
await page.waitForFunction(() => window.satelliteView && window.fireView, null, { timeout: 120000 });
await wait(7000);
await shot('intro');

// 1. play: the Earth opens and flies to the United States
clicks.push({ ...(await centre('#begin')), img: 1 });
await page.click('#begin');
await wait(9000);
await shot('live');

// 2. zoom out with the − button until the satellites in orbit come into view
const minus = await centre('.maplibregl-ctrl-zoom-out');
for (const n of [1, 2]) { clicks.push({ ...minus, img: n === 2 ? 2 : 1 }); await page.mouse.click(minus.x, minus.y); await wait(700); }
await wait(5000);
await shot('zoomed');

// 3. a satellite: its card opens at the top of the left column
const sat = await page.evaluate(() => {
  const inside = l => { const b = l.getBoundingClientRect(); return !l.hidden && b.width && b.left > 460 && b.right < innerWidth - 300 && b.top > 90 && b.bottom < innerHeight - 170; };
  const l = [...document.querySelectorAll('.sat-label')].find(inside);
  if (!l) return null;
  const b = l.getBoundingClientRect();
  return { x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2), name: l.textContent };
});
if (sat) {
  clicks.push({ x: sat.x, y: sat.y, img: 3 });
  await page.mouse.click(sat.x, sat.y);
  console.log('satellite', sat.name);
} else {                                   // no label on screen: open the first satellite from the list
  await page.evaluate(() => { window.satelliteView.toggle(true); document.querySelector('#satList button').click(); });
  clicks.push({ x: 1200, y: 400, img: 3 });
  console.log('NO SATELLITE LABEL IN VIEW');
}
await wait(9000);
await shot('satellite');

// 4. Settings, then 5. Area numbers: the history of the area on screen
await page.evaluate(() => window.satelliteView.toggle(false));
await wait(1500);
clicks.push({ ...(await centre('#toolsBtn')), img: 4 });
await page.click('#toolsBtn');
await wait(900);
await shot('settings');
clicks.push({ ...(await centre('#panelBtn')), img: 5 });
await page.click('#panelBtn');
await wait(8000);
await shot('history');

fs.writeFileSync(path.join(OUT, 'guide_clicks.json'), JSON.stringify(clicks, null, 1));
console.log(clicks);
await browser.close();
