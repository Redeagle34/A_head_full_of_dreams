// Screenshot the real Burning Calendar page (served locally) for the video ending.
//   node tools/capture_web.mjs [url]   -> assets/web/main.png, satellites.png, history.png
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const URL = process.argv[2] || 'http://localhost:8766/';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'web');
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await page.goto(URL, { waitUntil: 'networkidle', timeout: 120000 });
await wait(6000);
await page.screenshot({ path: path.join(OUT, 'main.png') });
console.log('main');
for (const [label, file] of [['Satellites', 'satellites.png'], ['Area history', 'history.png']]) {
  try {
    await page.getByRole('button', { name: label, exact: true }).first().click();
    await wait(7000);
    await page.screenshot({ path: path.join(OUT, file) });
    console.log(file);
    await page.keyboard.press('Escape'); await wait(800);
    await page.getByRole('button', { name: label, exact: true }).first().click().catch(() => {}); await wait(1500);
  } catch (e) { console.log('skip', label, e.message.split('\n')[0]); }
}
await browser.close();
