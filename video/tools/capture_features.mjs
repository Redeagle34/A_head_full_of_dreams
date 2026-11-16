// Screenshots of three real features of the Burning Calendar page, for the video's laptop screen.
//   node tools/capture_features.mjs [url]  -> assets/web/f1_*.png (area), f2_*.png (period + Play), f3_*.png (Landsat)
// Needs the app server running (python -m uvicorn server.main:app) and Earth Engine set up for the Landsat step.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const URL = process.argv[2] || 'http://127.0.0.1:8766/';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'web');
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const wait = ms => new Promise(r => setTimeout(r, ms));
const shot = async name => { await page.screenshot({ path: path.join(OUT, `${name}.png`) }); console.log('shot', name); };
const idle = async (ms = 1500) => { await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {}); await wait(ms); };
const step = process.argv[3] || 'all';

await page.goto(URL, { waitUntil: 'networkidle', timeout: 120000 });
await wait(2000);
// landing page: press play to open the Earth
for (const sel of ['#veil', '#begin']) { const b = page.locator(sel); if (await b.isVisible().catch(() => false)) { await b.click().catch(() => {}); break; } }
await idle(9000);
const skip = page.locator('button[data-go="end"]').first();
if (await skip.isVisible().catch(() => false)) { await skip.click(); await wait(1200); }
await shot('f0_open');

let typingName = 'f1';
async function search(text, partial) {
  const box = page.locator('#place');
  await box.click(); await box.fill('');
  await box.type(partial, { delay: 60 }); await wait(1800);
  await shot(`${typingName}_typing`);
  await box.type(text.slice(partial.length), { delay: 40 }); await wait(1500);
  const first = page.locator('#results li').first();
  if (await first.isVisible().catch(() => false)) await first.click(); else await box.press('Enter');
  await idle(7000);
}
async function setDates(a, b) { // the app's own timeline API, so both ends are set together
  await page.evaluate(([a, b]) => window.timeline.apply(a, b), [a, b]);
  await idle(4000);
}
async function closeResults() { await page.keyboard.press('Escape'); await page.evaluate(() => { const r = document.getElementById('results'); if (r) r.hidden = true; document.activeElement?.blur(); }); await wait(500); }
async function zoomOut(n) { for (let i = 0; i < n; i++) { await page.locator('.maplibregl-ctrl-zoom-out').first().click().catch(() => {}); await wait(900); } await idle(3500); }

if (step === 'f1b') { // the search, step by step: empty box, typing, suggestions, the map flying there, the result
  await setDates('2018-01-01', '2018-12-31');
  const box = page.locator('#place');
  await box.click(); await box.fill(''); await wait(600);
  const rect = async sel => page.locator(sel).first().boundingBox().catch(() => null);
  const boxes = { place: await rect('#place') };
  await shot('f1_empty');
  const text = 'Paradise, California';
  let typed = 0;
  for (const [k, n] of [[1, 2], [2, 5], [3, 8], [4, 12], [5, 16], [6, text.length]]) {
    await box.type(text.slice(typed, n), { delay: 45 }); typed = n; await wait(k === 6 ? 700 : 500);
    await shot(`f1_t${k}`);
  }
  await box.press('Enter'); await page.locator('#results li').first().waitFor({ state: 'visible', timeout: 20000 }).catch(() => {}); await wait(800);
  boxes.first = await rect('#results li');
  await shot('f1_suggest');
  await page.locator('#results li').first().click();
  await wait(350); await shot('f1_fly1');
  await wait(700); await shot('f1_fly2');
  await idle(6000); await closeResults(); await zoomOut(2);
  boxes.card = await rect('#nearFires .fire');
  await shot('f1_result');
  fs.writeFileSync(path.join(OUT, 'f1_boxes.json'), JSON.stringify(boxes, null, 1));
  console.log(JSON.stringify(boxes));
}
if (step === 'all' || step === 'f1') {
  typingName = 'f1';
  await setDates('2018-01-01', '2018-12-31');
  await search('Paradise, California', 'Paradis');
  await closeResults(); await zoomOut(2);
  await shot('f1_result');
}
if (step === 'all' || step === 'f2') {
  typingName = 'f2';
  await search('California', 'Califor');
  await closeResults();
  await setDates('2020-07-01', '2020-07-31');
  await shot('f2_set');
  await page.locator('#tlPlay').click();
  for (let i = 0; i < 12; i++) { await wait(650); await shot(`f2_play${i}`); }
  await page.locator('#tlPlay').click().catch(() => {});
}
if (step === 'all' || step === 'f3') {
  typingName = 'f3';
  await search('Paradise, California', 'Paradis');
  await closeResults();
  await setDates('2018-11-01', '2018-11-30');
  await page.evaluate(() => { window.fireView.toggle(true); window.fireView.show(1564960); }); // Camp Fire, Nov 2018
  await idle(6000);
  await shot('f3_fire');
  await page.locator('#fireSharp').click();
  await page.waitForFunction(() => [...document.querySelectorAll('#fireSharpOut img')].length >= 2 && [...document.querySelectorAll('#fireSharpOut img')].every(i => i.complete && i.naturalWidth > 0), null, { timeout: 120000 }).catch(e => console.log('landsat wait', e.message));
  await wait(2000);
  await page.locator('#fireSharpOut').scrollIntoViewIfNeeded().catch(() => {});
  await wait(800);
  await shot('f3_landsat');
}
await browser.close();
