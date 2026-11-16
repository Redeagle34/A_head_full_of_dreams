// Render the video page frame by frame and pipe to ffmpeg.
//   node tools/render.mjs                 -> out/video_1080p60.mp4
//   node tools/render.mjs --stills 1,5,9  -> out/stills/t_1.00.png ...
//   node tools/render.mjs --fps 30 --from 10 --to 15
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]] : a), []));
const PAGE = args.url || 'http://localhost:8767/?render';
const FPS = +(args.fps || 60), FROM = +(args.from || 0);
let TO = args.to ? +args.to : null;
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'out');
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=d3d11', '--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
page.on('console', m => { if (m.type() === 'error') console.log('[page]', m.text()); });
await page.goto(PAGE);
await page.waitForFunction(() => window.__ready === true || document.querySelector('pre'), null, { timeout: 120000 });
const err = await page.evaluate(() => document.querySelector('pre')?.textContent);
if (TO === null) TO = await page.evaluate(() => window.__duration || 30);
if (err) { console.error(err); process.exit(1); }
// warm-up: compile shaders / upload textures for every scene
for (const t of [1, 10.5, 12, 15, 16.5, 17.5, 19, 21, 22.5, 24, 26, 28]) await page.evaluate(t => window.seek(t), t);

const cdp = await page.context().newCDPSession(page);
async function grab(format = 'jpeg') {
  const r = await cdp.send('Page.captureScreenshot', { format, quality: format === 'jpeg' ? 95 : undefined, clip: { x: 0, y: 0, width: 1920, height: 1080, scale: 1 }, captureBeyondViewport: false });
  return Buffer.from(r.data, 'base64');
}

if (args.stills) {
  const dir = path.join(OUT, 'stills'); fs.mkdirSync(dir, { recursive: true });
  for (const t of String(args.stills).split(',').map(Number)) {
    await page.evaluate(t => window.seek(t), t);
    fs.writeFileSync(path.join(dir, `t_${t.toFixed(2)}.png`), await grab('png'));
    console.log('still', t);
  }
  await browser.close(); process.exit(0);
}

const name = args.out || `video_1080p${FPS}${FROM > 0 || args.to ? `_${FROM}-${TO}` : ''}.mp4`;
const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-movflags', '+faststart', path.join(OUT, name)], { stdio: ['pipe', 'inherit', 'inherit'] });
const n = Math.round((TO - FROM) * FPS), t0 = Date.now();
for (let f = 0; f < n; f++) {
  const t = FROM + f / FPS;
  await page.evaluate(t => window.seek(t), t);
  const buf = await grab('jpeg');
  if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  if (f % FPS === 0) console.log(`frame ${f}/${n}  t=${t.toFixed(2)}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
ff.stdin.end();
await new Promise(r => ff.on('close', r));
await browser.close();
console.log('done', path.join(OUT, name));
