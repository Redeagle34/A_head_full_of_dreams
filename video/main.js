// A Head Full of Dreams: 30 s presentation video, 1920x1080.
// Every frame is a pure function of time: window.seek(t) draws frame t (used for preview and MP4 render).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { geoOrthographic, geoPath, geoGraticule10, geoDistance } from 'https://cdn.jsdelivr.net/npm/d3-geo@3.1.1/+esm';
import { feature } from 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/+esm';

const W = 1920, H = 1080, CX = W / 2, CY = H / 2;
const DURATION = 30;
// The film is authored on a 'story' clock; this remap compresses the intro so the video lasts 30 s.
// [video s, story s] pairs, linear in between (intro x1.9, transition x1.3, team x1.4, satellite x1.7, ending x1).
// Synced to the recorded voice: audio/voice_clean.wav = voice_raw.mp4 with the lead silence cut and the first
// sentence sped up 1.25x (pitch kept). Word times in the final track: "prevent" 3.2 s, "control" 4.5 s,
// "understand" 6.3 s, "A Head Full of Dreams" 8.5-9.9 s, "here's our proposal" 10.0-11.1 s,
// "Our solution is an interactive..." 11.5 s, "MODIS / VIIRS" 15.3-18.1 s.
// After the proposal: "Our solution ... all the fires that are active" over OUR WEBPAGE + the live map (to 15.3 s),
// "detected by MODIS or by VIIRS" over DATASETS (15.3-18.8 s); ALGORITHMS 18.7-21 s; features 21.2-27.4 s; exit to 30 s.
const REMAP = [[0, 0], [3.19, 4.0], [4.46, 6.0], [6.29, 8.0], [7.5, 9.6], [8.6, 11.0], [9.95, 12.6], [11.1, 13.7], [13.6, 18.0], [15.0, 19.9], [18.7, 22.8], [21.0, 25.8], [27.4, 34.45], [30, 37.8]];
function storyTime(v) {
  for (let k = 1; k < REMAP.length; k++) { const [v0, s0] = REMAP[k - 1], [v1, s1] = REMAP[k]; if (v <= v1) return s0 + ((v - v0) / (v1 - v0)) * (s1 - s0); }
  return REMAP[REMAP.length - 1][1];
}
let VT = 0; // video time of the frame being drawn (drives the hand-drawn boil)
window.__duration = DURATION;
const RENDER = new URLSearchParams(location.search).has('render');
const F = CY / Math.tan(THREE.MathUtils.degToRad(15)); // focal length in px for fov 30
const R0 = 280; // chalk globe radius (px)
const T_FREEZE = 18.0; // the picture freezes here (satellite settling into orbit) and becomes a laptop screen
const TF = T_FREEZE;
// ending order: OUR WEBPAGE -> DATASETS -> ALGORITHMS -> three app features -> exit
const T_DATA = TF + 1.9, T_ALGO = T_DATA + 2.9, T_FEAT = T_ALGO + 3.0;
const TFS = T_FEAT + 0.45 - 1.9;          // feature times below are written as TFS + (1.9 ... 10.1)
const T_EXIT = TFS + 1.9 + 8.2;

// ------------------------------------------------------------------ people (placeholders)
// Put photos in assets/people/persona1.png ... persona5.png (or .jpg) and change the names.
const PEOPLE = [ // drawn back to front. Mirrored 2-1-2 layout: everyone points in at the Earth; entrances alternate L/R.
  // img: assets/people/personaN.png (background removed); s: scale so faces match (~75 px wide)
  { img: 3, x: 175, s: 0.42, dy: 28, from: 'left', t: 11.1 },    // outer left, arm up to the right
  { img: 2, x: 1772, s: 0.7, dy: 185, from: 'right', t: 11.3 },   // outer right, points up-left
  { img: 1, x: 480, s: 0.93, dy: 28, from: 'left', t: 11.5 },    // inner left, both hands to the right
  { img: 5, x: 1418, s: 0.2, from: 'right', t: 11.7 },   // inner right, both hands to the left
  { img: 4, x: 960, s: 0.585, from: 'bottom', t: 11.9 }, // centre, arms up holding the Earth
]

// ------------------------------------------------------------------ math
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  inCubic: x => x * x * x,
  outCubic: x => 1 - Math.pow(1 - x, 3),
  inOutCubic: x => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  inOutSine: x => -(Math.cos(Math.PI * x) - 1) / 2,
  outBack: x => { const c1 = 1.5, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
  outExpo: x => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inQuad: x => x * x,
};
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453123; return x - Math.floor(x); };
let BOIL = 0; // hand-drawn "boil": jitter pattern changes 12 times per second
const jit = (i, k = 0) => (hash(i * 12.9898 + BOIL * 78.233 + k * 37.719) - 0.5) * 2;

// ------------------------------------------------------------------ canvases
const $ = id => document.getElementById(id);
function ctx2d(id) { const c = $(id); c.width = W; c.height = H; return c.getContext('2d'); }
const bgx = ctx2d('bg'), mpx = ctx2d('map'), phx = ctx2d('photo'), chx = ctx2d('chalk');
const CH = { white: '#f3f1ea', yellow: '#ffd865', orange: '#ff8f3f', red: '#ff6250', green: '#a6e3b0', blue: '#9cd0ff', pink: '#ff9ec7' };

// ------------------------------------------------------------------ loading
const loadImg = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
const loadJSON = src => fetch(src).then(r => r.json());

async function loadAll() {
  const fontsP = Promise.all(['700 100px "Cabin Sketch"', '400 100px "Cabin Sketch"', '40px "Gochi Hand"', '700 40px "Space Grotesk"', '500 40px "Space Grotesk"', '500 20px "JetBrains Mono"'].map(f => document.fonts.load(f)));
  const [land, firesCA, firesUS, mosaics, patches, weekly] = await Promise.all([
    loadJSON('assets/land-110m.json'), loadJSON('data/fires_ca_20200908.json'), loadJSON('data/fires_us_sep2020.json'),
    loadJSON('data/mosaics.json'), loadJSON('data/patches.json'), loadJSON('data/weekly_ca_2020.json')]);
  const mosImgs = await Promise.all(mosaics.map(m => loadImg(m.src)));
  const featNames = ['f0_open', 'f1_typing', 'f1_result', 'f2_set', ...Array.from({ length: 12 }, (_, i) => `f2_play${i}`), 'f3_fire', 'f3_landsat'];   // real app screens (tools/capture_features.mjs)
  const featImgs = await Promise.all(featNames.map(n => loadImg(`assets/web/${n}.png`)));
  const feat = Object.fromEntries(featNames.map((n, k) => [n, featImgs[k]]));
  const logo = await loadImg('assets/nasa_spaceapps.png');
  const people = await Promise.all(PEOPLE.map(async (_, i) => (await loadImg(`assets/people/persona${i + 1}.png`)) || (await loadImg(`assets/people/persona${i + 1}.jpg`))));
  await fontsP; await document.fonts.ready;
  return { land, firesCA, firesUS, mosaics, mosImgs, patches, weekly, people, feat, logo };
}

// ------------------------------------------------------------------ backgrounds
function makeBoard() {
  const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  const grd = g.createRadialGradient(CX, CY * 0.85, 80, CX, CY, 1250);
  grd.addColorStop(0, '#2f3f39'); grd.addColorStop(0.55, '#212e2a'); grd.addColorStop(1, '#121a17');
  g.fillStyle = grd; g.fillRect(0, 0, W, H);
  const r = mulberry32(7);
  for (let i = 0; i < 80; i++) {
    const x = r() * W, y = r() * H, rx = 80 + r() * 420, ry = 20 + r() * 120;
    g.save(); g.translate(x, y); g.rotate((r() - 0.5) * 0.6); g.scale(1, ry / rx);
    const gg = g.createRadialGradient(0, 0, 0, 0, 0, rx);
    gg.addColorStop(0, `rgba(220,235,225,${0.02 + r() * 0.03})`); gg.addColorStop(1, 'rgba(220,235,225,0)');
    g.fillStyle = gg; g.beginPath(); g.arc(0, 0, rx, 0, Math.PI * 2); g.fill(); g.restore();
  }
  for (let i = 0; i < 28; i++) {
    g.strokeStyle = `rgba(230,240,235,${0.012 + r() * 0.02})`; g.lineWidth = 30 + r() * 70; g.lineCap = 'round';
    const x = r() * W - 200, y = r() * H; g.beginPath(); g.moveTo(x, y);
    g.bezierCurveTo(x + r() * 300, y + (r() - 0.5) * 80, x + 300 + r() * 300, y + (r() - 0.5) * 80, x + 400 + r() * 600, y + (r() - 0.5) * 60); g.stroke();
  }
  const id = g.getImageData(0, 0, W, H), d = id.data;
  for (let i = 0; i < d.length; i += 4) { const n = (r() - 0.5) * 12; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
  g.putImageData(id, 0, 0);
  const v = g.createRadialGradient(CX, CY, 450, CX, CY, 1150);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.6)'); g.fillStyle = v; g.fillRect(0, 0, W, H);
  return c;
}
function makeSpace() {
  const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  const grd = g.createRadialGradient(CX, CY, 100, CX, CY, 1300);
  grd.addColorStop(0, '#0b1426'); grd.addColorStop(0.6, '#060a14'); grd.addColorStop(1, '#020308');
  g.fillStyle = grd; g.fillRect(0, 0, W, H);
  const r = mulberry32(11);
  // faint galactic band
  g.save(); g.translate(CX, CY); g.rotate(-0.42);
  for (let i = 0; i < 60; i++) {
    const x = (r() - 0.5) * 2600, y = (r() - 0.5) * 260, rad = 120 + r() * 260;
    const gg = g.createRadialGradient(x, y, 0, x, y, rad);
    gg.addColorStop(0, `rgba(${120 + r() * 60},${130 + r() * 50},${200 + r() * 55},0.035)`); gg.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gg; g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  g.restore();
  for (let i = 0; i < 2600; i++) {
    const x = r() * W, y = r() * H, m = Math.pow(r(), 3);
    const a = 0.25 + m * 0.75, s = 0.5 + m * 1.6;
    const tint = r(); g.fillStyle = tint < 0.1 ? `rgba(255,210,170,${a})` : tint < 0.22 ? `rgba(170,200,255,${a})` : `rgba(255,255,255,${a})`;
    g.beginPath(); g.arc(x, y, s, 0, Math.PI * 2); g.fill();
    if (m > 0.75) { const gg = g.createRadialGradient(x, y, 0, x, y, 7); gg.addColorStop(0, 'rgba(200,220,255,0.35)'); gg.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gg; g.fillRect(x - 7, y - 7, 14, 14); }
  }
  return c;
}
function makeGrain() {
  const c = document.createElement('canvas'); c.width = c.height = 512; const g = c.getContext('2d');
  const id = g.createImageData(512, 512), r = mulberry32(3);
  for (let i = 0; i < id.data.length; i += 4) { id.data[i] = id.data[i + 1] = id.data[i + 2] = 255; id.data[i + 3] = r() < 0.2 ? 30 + r() * 110 : 190 + r() * 65; }
  g.putImageData(id, 0, 0); return c;
}

// ------------------------------------------------------------------ chalk primitives
function circlePts(cx, cy, r, n = 64) { const a = []; for (let i = 0; i < n; i++) { const t = (i / n) * Math.PI * 2; a.push([cx + Math.cos(t) * r, cy + Math.sin(t) * r]); } return a; }
function resample(pts, step) {
  const out = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i]; const d = Math.hypot(x1 - x0, y1 - y0); const n = Math.max(1, Math.round(d / step));
    for (let k = 1; k <= n; k++) out.push([lerp(x0, x1, k / n), lerp(y0, y1, k / n)]);
  }
  return out;
}
function pathOf(c, pts, closed = true) { pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); if (closed) c.closePath(); }
function drawPoly(ctx, pts, { w = 3, color = CH.white, amp = 1.4, closed = false, alpha = 1, seed = 0, upto = 1, passes = 2 } = {}) {
  if (upto <= 0 || alpha <= 0 || pts.length < 2) return;
  const n = pts.length, total = closed ? n + 1 : n;
  const m = Math.max(2, Math.ceil(total * clamp(upto)));
  ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = color;
  for (let p = 0; p < passes; p++) {
    ctx.globalAlpha = alpha * (p ? 0.45 : 0.95); ctx.lineWidth = p ? w * 0.55 : w;
    ctx.beginPath();
    for (let i = 0; i < m; i++) {
      const k = i % n, q = pts[k];
      const x = q[0] + jit(seed + k, p * 2 + 0.3) * amp, y = q[1] + jit(seed + k, p * 2 + 1.7) * amp;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}
function hatch(ctx, clipFn, bbox, { spacing = 8, angle = -0.8, color = CH.white, alpha = 0.5, w = 2, seed = 0 } = {}) {
  if (alpha <= 0) return;
  ctx.save(); ctx.beginPath(); clipFn(ctx); ctx.clip();
  ctx.strokeStyle = color; ctx.lineWidth = w; ctx.globalAlpha = alpha; ctx.lineCap = 'round';
  const [x0, y0, x1, y1] = bbox, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, R = Math.hypot(x1 - x0, y1 - y0) / 2 + 10;
  const ca = Math.cos(angle), sa = Math.sin(angle);
  ctx.beginPath();
  let i = 0;
  for (let k = -R; k <= R; k += spacing, i++) {
    const o = k + jit(seed + i, 9) * spacing * 0.22;
    const px = cx - sa * o, py = cy + ca * o, l = R * (0.8 + 0.2 * hash(seed + i * 3.3));
    ctx.moveTo(px - ca * R, py - sa * R); ctx.lineTo(px + ca * l, py + sa * l);
  }
  ctx.stroke(); ctx.restore();
}
function chalkText(ctx, text, x, y, { font = '"Cabin Sketch"', weight = 700, size = 100, color = CH.white, align = 'center', reveal = 1, seed = 0, alpha = 1, rot = 0 } = {}) {
  if (reveal <= 0 || alpha <= 0) return;
  ctx.save(); ctx.font = `${weight} ${size}px ${font}`; ctx.textAlign = align; ctx.textBaseline = 'middle';
  const w = ctx.measureText(text).width;
  const left = align === 'center' ? x - w / 2 : align === 'left' ? x : x - w;
  ctx.beginPath(); ctx.rect(left - 30, y - size, (w + 60) * clamp(reveal), size * 2); ctx.clip();
  ctx.translate(x + jit(seed, 1) * 1.3, y + jit(seed, 2) * 1.3); ctx.rotate(rot + jit(seed, 3) * 0.003);
  ctx.fillStyle = color; ctx.globalAlpha = alpha; ctx.fillText(text, 0, 0);
  ctx.globalAlpha = alpha * 0.3; ctx.fillText(text, 1.6, 1.2);
  ctx.restore();
  if (reveal > 0 && reveal < 1) { // chalk tip sparkle at the writing edge
    const ex = left + (w + 60) * reveal - 30;
    ctx.save(); ctx.fillStyle = color; ctx.globalAlpha = alpha * 0.8;
    for (let k = 0; k < 6; k++) { ctx.beginPath(); ctx.arc(ex + jit(seed + k, 5) * 10, y + jit(seed + k, 6) * size * 0.35, 1.5 + hash(k + BOIL) * 2, 0, 7); ctx.fill(); }
    ctx.restore();
  }
}

// flame outline in unit space (base at 0,0, tip near y=-1)
function flamePts(t, seed) {
  const pts = [], N = 26;
  const sway = Math.sin(t * 3.1 + seed * 7) * 0.13 + Math.sin(t * 7.3 + seed * 3) * 0.05;
  const Hh = 1 + Math.sin(t * 5.7 + seed * 11) * 0.07;
  const prof = v => (v < 0.38 ? 0.44 * Math.sqrt(Math.max(0, 1 - ((0.38 - v) / 0.38) ** 2)) : 0.44 * Math.pow(1 - (v - 0.38) / 0.62, 1.25));
  for (const side of [1, -1]) for (let k = 0; k <= N; k++) {
    const v = side === 1 ? k / N : 1 - k / N;
    const ripple = Math.sin(v * 10 - t * 9 + seed * 5 + (side > 0 ? 0 : 2)) * 0.05 * v;
    pts.push([sway * v * v + side * (prof(v) + ripple), -v * Hh]);
  }
  return pts;
}
const PALS = [[CH.orange, CH.yellow], [CH.red, CH.orange], [CH.orange, CH.white], [CH.red, CH.yellow]];
function drawFlame(ctx, x, y, s, t, seed, alpha = 1, pal = 0) {
  if (alpha <= 0 || s < 2) return;
  const [c1, c2] = PALS[pal % PALS.length];
  const outer = flamePts(t, seed).map(([u, v]) => [x + u * s, y + v * s]);
  const inner = flamePts(t * 1.3 + 1, seed + 5).map(([u, v]) => [x + u * s * 0.5, y + v * s * 0.55 - 0.03 * s]);
  const w = Math.max(1.6, s * 0.026), bb = [x - s * 0.6, y - s * 1.2, x + s * 0.6, y + 2];
  hatch(ctx, c => pathOf(c, outer), bb, { spacing: Math.max(4, s * 0.06), angle: -0.9, color: c1, alpha: 0.5 * alpha, w: w * 0.7, seed: seed * 7 });
  hatch(ctx, c => pathOf(c, inner), bb, { spacing: Math.max(3, s * 0.032), angle: 0.9, color: c2, alpha: 0.85 * alpha, w: w * 0.8, seed: seed * 11 });
  drawPoly(ctx, outer, { w, color: c1, amp: Math.max(0.8, s * 0.011), closed: true, alpha, seed: seed * 31 });
  drawPoly(ctx, inner, { w: w * 0.8, color: c2, amp: Math.max(0.6, s * 0.009), closed: true, alpha, seed: seed * 41 });
  const ph = (t * 1.6 + seed * 0.37) % 1;
  if (ph < 0.6) {
    const k = 1 - ph / 0.6, ty = y - s * (1.12 + ph * 0.55), tx = x + Math.sin(t * 3.1 + seed * 7) * 0.15 * s + Math.sin(ph * 6) * s * 0.05, ts = s * 0.17 * k;
    drawPoly(ctx, flamePts(t * 2, seed + 9).map(([u, v]) => [tx + u * ts, ty + v * ts]), { w: w * 0.7, color: c2, amp: 0.5, closed: true, alpha: alpha * k, seed: seed * 51 });
  }
}
function drawSparks(ctx, x, y, s, t, seed, alpha) {
  ctx.save(); ctx.fillStyle = CH.yellow;
  for (let i = 0; i < 5; i++) {
    const ph = (t * (0.55 + hash(seed + i) * 0.4) + hash(seed * 3 + i)) % 1;
    const px = x + (hash(seed + i * 7) - 0.5) * s * 0.9 + Math.sin(t * 4 + i) * s * 0.08, py = y - s * (0.9 + ph * 1.1);
    ctx.globalAlpha = alpha * (1 - ph) * 0.9; ctx.beginPath(); ctx.arc(px, py, Math.max(1.2, s * 0.018), 0, 7); ctx.fill();
  }
  ctx.restore();
}

// icons (unit coordinates, drawn with progress)
const ICONS = {
  shield: [
    { pts: resample([[0, -0.52], [0.42, -0.37], [0.39, 0.06], [0.22, 0.34], [0, 0.52], [-0.22, 0.34], [-0.39, 0.06], [-0.42, -0.37], [0, -0.52]], 0.05), closed: false },
    { pts: resample([[-0.2, 0.0], [-0.05, 0.16], [0.22, -0.16]], 0.05) },
  ],
  target: [
    { pts: circlePts(0, 0, 0.38, 48), closed: true },
    { pts: circlePts(0, 0, 0.14, 24), closed: true },
    { pts: resample([[0, -0.58], [0, -0.24]], 0.05) }, { pts: resample([[0, 0.24], [0, 0.58]], 0.05) },
    { pts: resample([[-0.58, 0], [-0.24, 0]], 0.05) }, { pts: resample([[0.24, 0], [0.58, 0]], 0.05) },
  ],
  chart: [
    { pts: resample([[-0.5, -0.48], [-0.5, 0.45], [0.52, 0.45]], 0.05) },
    { pts: resample([[-0.42, 0.3], [-0.22, 0.08], [-0.04, 0.17], [0.04, 0.04]], 0.04), w: 1.1 },
    { pts: resample([[0.1, -0.04], [0.18, -0.15]], 0.04) }, { pts: resample([[0.25, -0.22], [0.33, -0.32]], 0.04) }, { pts: resample([[0.4, -0.38], [0.48, -0.48]], 0.04) },
  ],
  bolt: [
    { pts: resample([[0.1, -0.56], [-0.3, 0.06], [-0.02, 0.06], [-0.13, 0.56], [0.31, -0.1], [0.03, -0.1], [0.1, -0.56]], 0.05) },
  ],
  lens: [
    { pts: circlePts(-0.08, -0.08, 0.32, 48), closed: true },
    { pts: resample([[0.16, 0.16], [0.48, 0.48]], 0.05), w: 2.2 },
    { pts: resample([[-0.24, 0.06], [-0.24, -0.04]], 0.05) }, { pts: resample([[-0.1, 0.06], [-0.1, -0.2]], 0.05) }, { pts: resample([[0.04, 0.06], [0.04, -0.12]], 0.05) },
  ],
};
function drawIcon(ctx, name, x, y, s, p, color, seed) {
  const parts = ICONS[name], n = parts.length;
  parts.forEach((part, i) => {
    const pp = clamp(p * n - i * 0.7);
    if (pp <= 0) return;
    drawPoly(ctx, part.pts.map(([u, v]) => [x + u * s, y + v * s]), { w: 5 * (part.w || 1), color, amp: 1.5, closed: part.closed, upto: pp, seed: seed + i * 50 });
  });
}
function starPts(x, y, r) { const a = []; for (let i = 0; i < 10; i++) { const ang = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r; a.push([x + Math.cos(ang) * rr, y + Math.sin(ang) * rr]); } return a; }

// ------------------------------------------------------------------ chalk globe
function recorder() {
  const segs = []; let cur = null;
  return {
    segs,
    moveTo(x, y) { cur = [[x, y]]; segs.push(cur); }, lineTo(x, y) { if (cur) cur.push([x, y]); },
    closePath() { if (cur) cur.closed = true; }, arc() {}, beginPath() {},
    replay(c) { for (const s of segs) { s.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); if (s.closed) c.closePath(); } },
  };
}
const HOT = [[-121.5, 39.5], [-60, -9], [-116, 57], [22, -12], [24, 39], [118, 62], [104, 18], [-48, -18], [-100, 20], [14, 6]];
const globeLon = t => -60 - (t - 9.6) * 5;
const GLOBE_LAT = 12;
let LAND, GRAT;
function rainbowPoly(ctx, pts, o, hue0, chunk = 10) { // a chalk line whose colour runs through the rainbow
  for (let k = 0; k < pts.length - 1; k += chunk) {
    const seg = pts.slice(k, Math.min(pts.length, k + chunk + 1));
    drawPoly(ctx, seg, { ...o, color: `hsl(${(hue0 + (k / pts.length) * 360) % 360} 90% 72%)`, seed: (o.seed || 0) + k });
  }
}
function chalkGlobe(ctx, t, cx, cy, R, alpha, flameAlpha = 1) {
  if (alpha <= 0) return;
  const lon = globeLon(t), lat = GLOBE_LAT;
  const proj = geoOrthographic().scale(R).translate([cx, cy]).rotate([-lon, -lat]).clipAngle(90).precision(0.6);
  const rec = recorder(); geoPath(proj, rec)(LAND);
  const grat = recorder(); geoPath(proj, grat)(GRAT);
  const bb = [cx - R, cy - R, cx + R, cy + R];
  ctx.save();
  ctx.globalAlpha = alpha; const og = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.1, cx, cy, R); og.addColorStop(0, 'rgba(120,200,255,0.22)'); og.addColorStop(0.6, 'rgba(110,120,255,0.14)'); og.addColorStop(1, 'rgba(190,110,255,0.16)'); ctx.fillStyle = og; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
  hatch(ctx, c => c.arc(cx, cy, R, 0, Math.PI * 2), bb, { spacing: 14, angle: 0.6, color: '#7fd3ff', alpha: 0.22 * alpha, w: 1.7, seed: 3 });
  grat.segs.forEach((s, i) => drawPoly(ctx, s, { w: 1.3, color: i % 2 ? '#c4a7ff' : '#8fe3ff', alpha: 0.3 * alpha, amp: 0.7, seed: 500 + i * 37, passes: 1 }));
  // each landmass takes the rainbow hue of its direction from the centre, slowly cycling (matches the team colours)
  rec.segs.forEach((sg, i) => {
    let mx = 0, my = 0, x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const [x, y] of sg) { mx += x; my += y; x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    mx /= sg.length; my /= sg.length;
    const hue = ((Math.atan2(my - cy, mx - cx) * 180) / Math.PI + 360 + t * 45) % 360, col = `hsl(${hue} 85% 70%)`;
    if (sg.closed && (x1 - x0) * (y1 - y0) > 30) hatch(ctx, c => pathOf(c, sg), [x0, y0, x1, y1], { spacing: 7, angle: -0.7, color: col, alpha: 0.6 * alpha, w: 2, seed: 7 + i });
    drawPoly(ctx, sg, { w: 2.6, color: col, alpha, amp: 1.1, closed: !!sg.closed, seed: 900 + i * 101 });
  });
  const rim = circlePts(cx, cy, R, 140); rim.push(rim[0]);
  rainbowPoly(ctx, rim, { w: 5, amp: 1.6, alpha }, (t * 60) % 360, 6);
  drawPoly(ctx, circlePts(cx, cy, R + 11, 140), { w: 1.6, color: '#fff3d6', closed: true, amp: 2.2, alpha: alpha * 0.4, seed: 17, passes: 1 });
  HOT.forEach(([lo, la], i) => {
    const dist = geoDistance([lo, la], [lon, lat]); const vis = clamp((Math.PI / 2 - 0.2 - dist) / 0.25);
    if (vis <= 0) return;
    const p = proj([lo, la]);
    drawFlame(ctx, p[0], p[1] + R * 0.02, R * 0.11 * (0.7 + 0.3 * vis), t, 100 + i, alpha * vis * flameAlpha, i);
  });
  ctx.restore();
  return proj;
}

// ------------------------------------------------------------------ scene 1 data
const TITLE = { text: 'MORE AND MORE FIRES', y: 520, size: 160 };
const titleC = document.createElement('canvas'); titleC.width = W; titleC.height = H; const ttx = titleC.getContext('2d');
let TITLE_W = 1600;
function drawTitle(ctx, reveal, alpha) { // textured chalk letters: warm gradient, hatch texture, chalk outline
  if (reveal <= 0 || alpha <= 0) return;
  const { text, y, size } = TITLE;
  ttx.clearRect(0, 0, W, H);
  ttx.font = `700 ${size}px "Cabin Sketch"`; ttx.textAlign = 'center'; ttx.textBaseline = 'middle';
  TITLE_W = ttx.measureText(text).width;
  ttx.fillStyle = '#fff'; ttx.fillText(text, CX, y);
  ttx.globalCompositeOperation = 'source-in';
  const g = ttx.createLinearGradient(0, y - size * 0.45, 0, y + size * 0.45);
  g.addColorStop(0, CH.yellow); g.addColorStop(0.5, CH.orange); g.addColorStop(1, CH.red);
  ttx.fillStyle = g; ttx.fillRect(0, y - size, W, size * 2);
  ttx.globalCompositeOperation = 'destination-out';
  ttx.strokeStyle = 'rgba(0,0,0,0.42)'; ttx.lineWidth = 2.2; ttx.beginPath();
  for (let k = -200, i = 0; k < W; k += 7, i++) { const o = jit(i, 4) * 1.4; ttx.moveTo(k + o, y + size * 0.6); ttx.lineTo(k + o + size * 1.2, y - size * 0.6); }
  ttx.stroke();
  ttx.fillStyle = 'rgba(0,0,0,0.5)';
  for (let i = 0; i < 450; i++) { ttx.fillRect(CX - TITLE_W / 2 + hash(i * 3.1 + BOIL) * TITLE_W, y - size * 0.5 + hash(i * 7.7 + BOIL) * size, 2, 2); }
  ttx.globalCompositeOperation = 'source-over';
  ttx.lineJoin = 'round'; ttx.strokeStyle = CH.white;
  ttx.globalCompositeOperation = 'destination-over'; ttx.fillStyle = 'rgba(40,10,0,0.55)'; ttx.fillText(text, CX + 5, y + 6);
  ttx.globalCompositeOperation = 'source-over';
  ttx.lineWidth = 1.1; ttx.globalAlpha = 0.55; ttx.strokeText(text, CX + jit(1, 1) * 1.2, y + jit(1, 2) * 1.2);
  ttx.globalAlpha = 1;
  const L = CX - TITLE_W / 2 - 20, Wd = (TITLE_W + 40) * clamp(reveal);
  ctx.save(); ctx.globalAlpha *= alpha; ctx.drawImage(titleC, L, 0, Wd, H, L, 0, Wd, H); ctx.restore();
}
const FL = [ // flames standing on the letters: x, size, tEnter, palette
  [270, 120, 0.15, 0], [640, 150, 0.35, 1], [1045, 185, 0.55, 0], [1290, 150, 0.75, 3], [1650, 125, 0.95, 2],
  [455, 85, 2.25, 2], [770, 95, 2.4, 3], [1120, 100, 2.55, 1], [1470, 90, 2.7, 0], [150, 70, 2.85, 1], [1780, 70, 3.0, 3],
];
const FLAME_BASE = TITLE.y - TITLE.size * 0.36;
const WORDS = [ // text, t, x, color, icon
  ['PREVENT', 4.0, 420, CH.green, 'shield'], ['CONTROL', 6.0, 960, CH.blue, 'target'], ['UNDERSTAND', 8.0, 1500, CH.yellow, 'lens'],
];
function scene1(ctx, t, alpha, titleXf) {
  if (alpha > 0) FL.forEach(([x, s, te, pal], i) => {
    const p = prog(t, te, te + 0.55); if (p <= 0) return;
    const e = E.outBack(p), breathe = 1 + Math.sin(t * 2.3 + i) * 0.04;
    const sc = s * lerp(0.1, 1, e) * breathe;
    const fx = CX + (x - CX) * (TITLE_W / 1790); // flame positions follow the title's width
    drawFlame(ctx, fx, FLAME_BASE + 6, sc, t + i * 0.7, i + 1, alpha, pal);
    drawSparks(ctx, fx, FLAME_BASE + 6, sc, t, i + 1, alpha * clamp(p * 2 - 1));
  });
  ctx.save(); if (titleXf) titleXf(ctx);
  drawTitle(ctx, E.inOutSine(prog(t, 0.6, 2.0)), titleXf ? 1 : alpha);
  ctx.restore();
  if (alpha <= 0) return;
  WORDS.forEach(([word, tw, x, color, icon], i) => {
    const pop = E.outBack(prog(t, tw, tw + 0.25));
    if (pop <= 0) return;
    drawIcon(ctx, icon, x, 790, 130 * lerp(0.4, 1, pop), E.outCubic(prog(t, tw, tw + 0.28)), color, 300 + i * 100);
    chalkText(ctx, word, x, 915, { size: 74, reveal: E.outCubic(prog(t, tw + 0.08, tw + 0.38)), seed: 20 + i, color, alpha });
  });
}

// ------------------------------------------------------------------ people cards
const HALO_PAD = 34;
const HALOS = new Map();
function haloFor(i, img, w, h) { // the person's own silhouette, grown outwards: white sticker edge + rainbow band
  if (HALOS.has(i)) return HALOS.get(i);
  const c = document.createElement('canvas'); c.width = w + HALO_PAD * 2; c.height = h + HALO_PAD * 2; const g = c.getContext('2d');
  const ring = (r, fill) => {
    const t = document.createElement('canvas'); t.width = c.width; t.height = c.height; const x = t.getContext('2d');
    for (let k = 0; k < 32; k++) { const a = (k / 32) * Math.PI * 2; x.drawImage(img, HALO_PAD + Math.cos(a) * r, HALO_PAD + Math.sin(a) * r, w, h); }
    x.globalCompositeOperation = 'source-in'; x.fillStyle = fill(x); x.fillRect(0, 0, t.width, t.height); return t;
  };
  g.drawImage(ring(24, x => { const gr = x.createLinearGradient(0, 0, c.width, c.height); ['#ff5e8a', '#ff9f43', '#ffd93d', '#5ee08f', '#4dabf7', '#a78bfa', '#ff5e8a'].forEach((col, k, a) => gr.addColorStop(k / (a.length - 1), col)); return gr; }), 0, 0);
  g.drawImage(ring(9, () => '#fffaf0'), 0, 0);
  HALOS.set(i, c); return c;
}
function personPos(P, i, t, img) {
  const pin = E.outBack(prog(t, P.t, P.t + 0.7));
  const pout = E.inCubic(prog(t, 14.0 + i * 0.06, 14.5 + i * 0.06));
  const w = img.width * P.s, h = img.height * P.s;
  const y = H + 10 - h / 2 + (P.dy || 0); // dy pushes a figure down (body continues below the frame) so heads line up
  let x0 = P.x, y0 = y;
  if (P.from === 'right') x0 = W + w / 2 + HALO_PAD; else if (P.from === 'left') x0 = -w / 2 - HALO_PAD; else y0 = H + h / 2 + HALO_PAD;
  const k = pin * (1 - pout);
  return { x: lerp(x0, P.x, k), y: lerp(y0, y, k), w, h, vis: pin > 0 && k > 0.001 };
}
function drawPeople(cx, t, imgs) {
  PEOPLE.forEach((P, i) => {
    const img = imgs[P.img - 1]; if (!img) return;
    const { x, y, w, h, vis } = personPos(P, i, t, img);
    if (!vis) return;
    const halo = haloFor(i, img, Math.round(w), Math.round(h));
    phx.save();
    phx.shadowColor = 'rgba(0,0,0,0.4)'; phx.shadowBlur = 24; phx.shadowOffsetX = 6; phx.shadowOffsetY = 12;
    phx.filter = `hue-rotate(${(t * 120 + i * 70) % 360}deg)`;
    phx.drawImage(halo, x - w / 2 - HALO_PAD, y - h / 2 - HALO_PAD);
    phx.restore();
    phx.drawImage(img, x - w / 2, y - h / 2, w, h);
  });
}

// ------------------------------------------------------------------ THREE: globe renderer
const latLonToVec = (lat, lon, r = 1) => {
  const phi = ((lon + 180) / 360) * Math.PI * 2, th = ((90 - lat) / 180) * Math.PI;
  return new THREE.Vector3(-Math.cos(phi) * Math.sin(th) * r, Math.cos(th) * r, Math.sin(phi) * Math.sin(th) * r);
};
const gl = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: true, alpha: true, preserveDrawingBuffer: true });
gl.setPixelRatio(1); gl.setSize(W, H, false); gl.outputColorSpace = THREE.SRGBColorSpace; gl.setClearColor(0x000000, 0);
const glTop = new THREE.WebGLRenderer({ canvas: $('gltop'), antialias: true, alpha: true, preserveDrawingBuffer: true });
glTop.setPixelRatio(1); glTop.setSize(W, H, false); glTop.outputColorSpace = THREE.SRGBColorSpace; glTop.setClearColor(0x000000, 0);
glTop.toneMapping = THREE.ACESFilmicToneMapping; glTop.toneMappingExposure = 1.15;

const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(30, W / H, 0.005, 200);
scene.add(cam);
const G = {}; // globe objects

function glowTexture(inner = 'rgba(255,255,255,1)', mid = 'rgba(255,200,120,0.5)') {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, inner); gr.addColorStop(0.25, mid); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function makeLine(points, color, width, opacity, vertexColors = null) {
  const g = new LineGeometry(); g.setPositions(points.flatMap(p => [p.x, p.y, p.z]));
  if (vertexColors) g.setColors(vertexColors);
  const m = new LineMaterial({ color, linewidth: width, transparent: true, opacity, vertexColors: !!vertexColors, depthWrite: false });
  m.resolution.set(W, H);
  const l = new Line2(g, m); l.computeLineDistances(); return l;
}
function ringBasis(normal) {
  const n = normal.clone().normalize();
  let up = new THREE.Vector3(0, 1, 0); if (Math.abs(n.dot(up)) > 0.95) up = new THREE.Vector3(1, 0, 0);
  const v = up.clone().sub(n.clone().multiplyScalar(up.dot(n))).normalize();
  const u = new THREE.Vector3().crossVectors(v, n).normalize();
  return { u, v, n };
}
const ringPoint = (b, r, th) => b.u.clone().multiplyScalar(Math.cos(th) * r).add(b.v.clone().multiplyScalar(Math.sin(th) * r));

async function buildGlobe(A) {
  const tl = new THREE.TextureLoader();
  const loadTex = src => new Promise(res => tl.load(src, res));
  const [tex, bump, ...pTex] = await Promise.all([loadTex('assets/earth-blue-marble.jpg'), loadTex('assets/earth-topology.png'), ...A.patches.map(p => loadTex(p.src))]);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 16;
  const earthMat = new THREE.MeshPhongMaterial({ map: tex, bumpMap: bump, bumpScale: 0.02, specular: new THREE.Color(0x1a2a3a), shininess: 14, transparent: true });
  G.earth = new THREE.Mesh(new THREE.SphereGeometry(1, 192, 192), earthMat); G.earth.renderOrder = 0; scene.add(G.earth);
  G.patches = A.patches.map((p, i) => {
    const t = pTex[i]; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 16;
    const geo = new THREE.SphereGeometry(1.0006 + i * 0.0006, 128, 96,
      ((p.lon0 + 180) / 360) * Math.PI * 2, ((p.lon1 - p.lon0) / 360) * Math.PI * 2, ((90 - p.lat1) / 180) * Math.PI, ((p.lat1 - p.lat0) / 180) * Math.PI);
    const m = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ map: t, transparent: true, depthWrite: false, shininess: 8, specular: new THREE.Color(0x111111) }));
    m.renderOrder = 1 + i; scene.add(m); return m;
  });
  // atmosphere halo and limb rim
  G.atmo = new THREE.Mesh(new THREE.SphereGeometry(1.045, 96, 96), new THREE.ShaderMaterial({
    uniforms: { uOpacity: { value: 1 }, uColor: { value: new THREE.Color(0x5ab0ff) } },
    vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
    fragmentShader: 'uniform float uOpacity; uniform vec3 uColor; varying vec3 vN; varying vec3 vV; void main(){ float g = smoothstep(0.0, 0.3, -dot(vN, vV)); g = pow(g, 2.2); gl_FragColor = vec4(uColor*g*0.85*uOpacity, g*0.85*uOpacity); }',
    side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }));
  scene.add(G.atmo);
  G.rim = new THREE.Mesh(new THREE.SphereGeometry(1.002, 96, 96), new THREE.ShaderMaterial({
    uniforms: { uOpacity: { value: 1 } },
    vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
    fragmentShader: 'uniform float uOpacity; varying vec3 vN; varying vec3 vV; void main(){ float f = pow(1.0 - max(dot(vN, vV), 0.0), 5.0); gl_FragColor = vec4(vec3(0.45,0.72,1.0)*f*0.55*uOpacity, f*0.55*uOpacity); }',
    blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }));
  G.rim.renderOrder = 4; G.atmo.renderOrder = 6; scene.add(G.rim);
  scene.add(new THREE.AmbientLight(0xffffff, 1.35));
  const sun = new THREE.DirectionalLight(0xfff4e6, 2.2); sun.position.set(-3, 2.5, 4); cam.add(sun);

  // fire points (US, Sep 1-14 2020)
  const pos = [], mag = [], birth = [];
  for (const [lo, la, n] of A.firesUS) {
    const v = latLonToVec(la, lo, 1.003); pos.push(v.x, v.y, v.z);
    mag.push(Math.min(1.1, Math.log10(1 + n) * 0.45));
    birth.push(18.15 + ((lo + 125) / 60) * 0.9 + hash(lo * 13 + la * 7) * 0.5);
  }
  const fg = new THREE.BufferGeometry();
  fg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  fg.setAttribute('aMag', new THREE.Float32BufferAttribute(mag, 1));
  fg.setAttribute('aBirth', new THREE.Float32BufferAttribute(birth, 1));
  G.fireMat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uOpacity: { value: 1 }, uScale: { value: 6 } },
    vertexShader: `attribute float aMag; attribute float aBirth; uniform float uTime; uniform float uScale; varying float vOn; varying float vFlash; varying float vMag;
      void main(){ float age = uTime - aBirth; vOn = smoothstep(0.0, 0.18, age); vFlash = age > 0.0 ? exp(-age*4.0) : 0.0; vMag = aMag;
        vec4 mv = modelViewMatrix*vec4(position,1.0); gl_Position = projectionMatrix*mv;
        gl_PointSize = uScale*(0.55 + aMag)*(vOn + vFlash*1.8); }`,
    fragmentShader: `uniform float uOpacity; varying float vOn; varying float vFlash; varying float vMag;
      void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.0, d); a = a*a;
        vec3 col = mix(vec3(1.0,0.32,0.06), vec3(1.0,0.86,0.45), a*0.8 + vFlash*0.5);
        float k = a*uOpacity*(vOn + vFlash)*0.85; gl_FragColor = vec4(col*k, clamp(k,0.0,1.0)); }`,
    blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  });
  G.fires = new THREE.Points(fg, G.fireMat); G.fires.renderOrder = 5; scene.add(G.fires);

  // orbits, defined relative to the view direction at t = 17
  const dir0 = latLonToVec(GLOBE_LAT, globeLon(17.0)).normalize();
  const camUp = new THREE.Vector3(0, 1, 0).sub(dir0.clone().multiplyScalar(dir0.y)).normalize();
  const right = new THREE.Vector3().crossVectors(camUp, dir0).normalize();
  const nHero = dir0.clone().applyAxisAngle(right, THREE.MathUtils.degToRad(-24)).normalize();
  G.rings = [
    { b: ringBasis(nHero), r: 1.34, color: 0xffd84a, w: 2.6, speed: 0.55, th0: Math.PI / 2, hero: true },
    { b: ringBasis(right.clone().applyAxisAngle(camUp, THREE.MathUtils.degToRad(18))), r: 1.2, color: 0xff7a2f, w: 2.2, speed: -0.7, th0: 2.2 },
    { b: ringBasis(right.clone().add(camUp.clone().multiplyScalar(0.75)).normalize()), r: 1.27, color: 0xff7a2f, w: 2.2, speed: 0.62, th0: 4.0 },
  ];
  const satTex = glowTexture('rgba(255,255,255,1)', 'rgba(255,220,140,0.55)');
  for (const R of G.rings) {
    // the hero ring's "top" must be the top of the screen: make v the projected camera-up
    const pts = []; for (let k = 0; k <= 256; k++) pts.push(ringPoint(R.b, R.r, (k / 256) * Math.PI * 2));
    R.line = makeLine(pts, R.color, R.w, 0.55); scene.add(R.line);
    R.sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: satTex, color: 0xffffff, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, sizeAttenuation: false }));
    R.sprite.scale.set(0.02, 0.02, 1); scene.add(R.sprite);
    const tp = []; const cols = [];
    for (let k = 0; k <= 60; k++) { tp.push(new THREE.Vector3()); const c = new THREE.Color(R.color).multiplyScalar(Math.pow(1 - k / 60, 1.5)); cols.push(c.r, c.g, c.b); }
    R.trail = makeLine(tp, 0xffffff, R.w * 2.2, 1, cols); R.trail.material.blending = THREE.AdditiveBlending; R.trail.frustumCulled = false; R.trail.renderOrder = 8; R.line.renderOrder = 7; scene.add(R.trail);
    // scan beam
    const h = 1;
    const cg = new THREE.ConeGeometry(0.11, h, 48, 1, true); cg.translate(0, -h / 2, 0); cg.rotateX(-Math.PI / 2);
    R.beam = new THREE.Mesh(cg, new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Color(R.color) }, uOpacity: { value: 0 } },
      vertexShader: 'varying float vZ; void main(){ vZ = position.z; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: 'uniform vec3 uColor; uniform float uOpacity; varying float vZ; void main(){ float a = (1.0 - smoothstep(0.0, 1.0, vZ))*0.22 + 0.03; a *= uOpacity; gl_FragColor = vec4(uColor*a, a); }',
      blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    }));
    scene.add(R.beam);
  }
}

// ------------------------------------------------------------------ THREE: satellites (top layer)
const topScene = new THREE.Scene();
const cam2 = new THREE.PerspectiveCamera(30, W / H, 0.1, 100); cam2.position.set(0, 0, 10);
const S = {};
function normalizeModel(gltf) {
  const obj = gltf.scene; const box = new THREE.Box3().setFromObject(obj); const size = box.getSize(new THREE.Vector3()); const c = box.getCenter(new THREE.Vector3());
  obj.position.sub(c); const pivot = new THREE.Group(); pivot.add(obj); pivot.scale.setScalar(1 / Math.max(size.x, size.y, size.z));
  const g = new THREE.Group(); g.add(pivot); return g;
}
async function buildSats() {
  const loader = new GLTFLoader();
  const draco = new DRACOLoader(); draco.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/'); loader.setDRACOLoader(draco);
  const load = src => new Promise((res, rej) => loader.load(src, res, undefined, rej));
  const [terra, aqua, npp] = await Promise.all([load('assets/terra.glb'), load('assets/aqua.glb'), load('assets/suomi-npp.glb')]);
  const cl = g => ({ scene: g.scene.clone(true) });
  G.orbitModels = [cl(npp), cl(terra), cl(aqua)].map(g => { const m = normalizeModel(g); m.scale.setScalar(0.18); m.visible = false; scene.add(m); return m; });
  S.hero = normalizeModel(cl(npp));
  S.terra = normalizeModel(terra); S.aqua = normalizeModel(aqua); S.npp = normalizeModel(cl(npp)); S.n20 = normalizeModel(cl(npp));
  for (const k of ['hero', 'terra', 'aqua', 'npp', 'n20']) { topScene.add(S[k]); S[k].visible = false; }
  topScene.add(new THREE.HemisphereLight(0xcfe2ff, 0x2a1a10, 1.4));
  S.lights = [[new THREE.DirectionalLight(0xffe2c0, 3.2), new THREE.Vector3(5, 6, 8)], [new THREE.DirectionalLight(0x7ab8ff, 2.4), new THREE.Vector3(-6, 2, -5)], [new THREE.DirectionalLight(0xffffff, 0.8), new THREE.Vector3(-4, -3, 6)]];
  for (const [l] of S.lights) { topScene.add(l); topScene.add(l.target); }
}
function screenToWorld2(sx, sy, z = 0) { const d = 10 - z, k = d / F; return new THREE.Vector3((sx - CX) * k, -(sy - CY) * k, z); }

// ------------------------------------------------------------------ camera path (globe + map share one zoom)
const RG1 = 205; // globe radius after it shrinks for the satellite
const globeR = t => lerp(R0, RG1, E.inOutCubic(prog(t, 14.2, 15.9)));
const ZofR = R => Math.log2((R * Math.cos(THREE.MathUtils.degToRad(GLOBE_LAT)) * 2 * Math.PI) / 256);
const ZG0 = ZofR(R0);
const TARGET = { lon: -122.99, lat: 39.92 };
const merc = (lon, lat) => { const lr = (lat * Math.PI) / 180; return [(lon + 180) / 360, (1 - Math.log(Math.tan(lr) + 1 / Math.cos(lr)) / Math.PI) / 2]; };
const unmerc = (x, y) => [x * 360 - 180, (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI];
function camPath(t) {
  if (t <= 17.4) return { lon: globeLon(t), lat: GLOBE_LAT, Z: ZofR(globeR(t)) };
  if (t <= 19.6) {
    const e = E.inOutSine(prog(t, 17.4, 19.6));
    return { lon: lerp(globeLon(17.4), -112, e), lat: lerp(GLOBE_LAT, 37, e), Z: lerp(ZofR(RG1), 3.7, e) };
  }
  const p = prog(t, 19.6, 23.6), e = E.inOutCubic(p);
  const Z1 = 3.7, Z2 = 10.55, Z = lerp(Z1, Z2, e);
  const w = (1 - Math.pow(2, -(Z - Z1))) / (1 - Math.pow(2, -(Z2 - Z1)));
  const a = merc(-112, 37), b = merc(TARGET.lon, TARGET.lat);
  const [lon, lat] = unmerc(lerp(a[0], b[0], w), lerp(a[1], b[1], w));
  const drift = Math.max(0, t - 23.6) * 0.022;
  return { lon, lat, Z: Z + drift + E.inOutCubic(prog(t, 25.0, 27.2)) * 0.5 };
}
function globeDistance(Z, lat) { const r = (Math.pow(2, Z) * 256) / (2 * Math.PI * Math.cos((lat * Math.PI) / 180)); return Math.sqrt((F / r) ** 2 + 1); }

// ------------------------------------------------------------------ map (flat, mercator)
let MOS = [], DET = [];
function prepMap(A) {
  MOS = A.mosaics.map((m, i) => {
    const img = A.mosImgs[i]; const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d');
    g.filter = 'saturate(0.88) brightness(0.8) contrast(1.06)'; g.drawImage(img, 0, 0); g.filter = 'none';
    if (i > 0) { // feather edges so finer levels blend into coarser ones
      g.globalCompositeOperation = 'destination-out';
      const f = Math.round(Math.min(c.width, c.height) * 0.07);
      const lg = (x0, y0, x1, y1) => { const gr = g.createLinearGradient(x0, y0, x1, y1); gr.addColorStop(0, 'rgba(0,0,0,1)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); return gr; };
      g.fillStyle = lg(0, 0, f, 0); g.fillRect(0, 0, f, c.height); g.fillStyle = lg(c.width, 0, c.width - f, 0); g.fillRect(c.width - f, 0, f, c.height);
      g.fillStyle = lg(0, 0, 0, f); g.fillRect(0, 0, c.width, f); g.fillStyle = lg(0, c.height, 0, c.height - f); g.fillRect(0, c.height - f, c.width, f);
      g.globalCompositeOperation = 'source-over';
    }
    return { ...m, img: c };
  });
  DET = A.firesCA.map(([lo, la, scan, track, frp, s, sat]) => { const [x, y] = merc(lo, la); return { x, y, lat: la, scan, track, frp, s, sat, h: hash(lo * 91 + la * 37) }; });
}
const GS = 2; const glowC = document.createElement('canvas'); glowC.width = W / GS; glowC.height = H / GS; const glowX = glowC.getContext('2d');
function drawMap(ctx, c, vp, sensorAlpha, sweepY, t) {
  const ws = 256 * Math.pow(2, c.Z); const [mx, my] = merc(c.lon, c.lat); const cxw = mx * ws, cyw = my * ws;
  ctx.save(); ctx.beginPath(); ctx.rect(vp.x0, 0, vp.x1 - vp.x0, H); ctx.clip();
  ctx.fillStyle = '#081320'; ctx.fillRect(vp.x0, 0, vp.x1 - vp.x0, H);
  MOS.forEach((m, i) => {
    const a = i === 0 ? 1 : clamp((c.Z - (m.z - 1.3)) / 0.55);
    if (a <= 0) return;
    const sc = Math.pow(2, c.Z - m.z), ox = vp.cx + m.x0 * 256 * sc - cxw, oy = CY + m.y0 * 256 * sc - cyw;
    const sx0 = Math.max(0, (vp.x0 - ox) / sc), sy0 = Math.max(0, -oy / sc), sx1 = Math.min(m.img.width, (vp.x1 - ox) / sc), sy1 = Math.min(m.img.height, (H - oy) / sc);
    if (sx1 <= sx0 || sy1 <= sy0) return;
    ctx.globalAlpha = a; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(m.img, sx0, sy0, sx1 - sx0, sy1 - sy0, ox + sx0 * sc, oy + sy0 * sc, (sx1 - sx0) * sc, (sy1 - sy0) * sc);
  });
  ctx.globalAlpha = 1;
  // detections
  const ppm0 = ws / 40075016.686;
  glowX.clearRect(0, 0, glowC.width, glowC.height);
  glowX.globalCompositeOperation = 'source-over';
  const rects = [[], []];
  const dotR = clamp(1.8 * Math.pow(2, (c.Z - 6) * 0.3), 1.8, 3.6);
  for (const d of DET) {
    const sa = sensorAlpha[d.s]; if (sa <= 0) continue;
    const sx = vp.cx + d.x * ws - cxw, sy = CY + d.y * ws - cyw;
    if (sx < vp.x0 - 60 || sx > vp.x1 + 60 || sy < -60 || sy > H + 60) continue;
    const revealed = sy < sweepY;
    const col = d.s === 0 ? [255, 110, 40] : [255, 214, 74];
    const intensity = clamp(0.45 + Math.log10(1 + d.frp) * 0.3, 0.3, 1.2);
    // glow (both modes)
    glowX.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${(revealed ? 0.22 : 0.3) * sa * Math.min(1, intensity)})`;
    const gr = revealed ? 5 : 3 + dotR; glowX.fillRect(sx / GS - gr / 2, sy / GS - gr / 2, gr, gr);
    if (revealed) {
      const ppm = ppm0 / Math.cos((d.lat * Math.PI) / 180);
      rects[d.s].push([sx, sy, Math.max(2, d.scan * 1000 * ppm), Math.max(2, d.track * 1000 * ppm), sa, intensity, (sweepY - sy) / 900]);
    } else {
      ctx.fillStyle = `rgba(${col[0]},${col[1] + 20},${col[2] + 40},${0.9 * sa})`;
      ctx.fillRect(sx - dotR / 2, sy - dotR / 2, dotR, dotR);
    }
  }
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.filter = 'blur(9px)'; ctx.drawImage(glowC, 0, 0, W, H); ctx.globalAlpha = 0.6; ctx.filter = 'blur(3px)'; ctx.drawImage(glowC, 0, 0, W, H); ctx.filter = 'none'; ctx.restore();
  // MODIS footprints: outlined; VIIRS: filled
  for (const [x, y, w, h, sa, it, age] of rects[0]) {
    const flash = clamp(1 - age * 6);
    ctx.fillStyle = `rgba(255,112,40,${(0.07 + 0.06 * it) * sa})`; ctx.fillRect(x - w / 2, y - h / 2, w, h);
    ctx.strokeStyle = `rgba(255,138,64,${0.95 * sa})`; ctx.lineWidth = 1.8; ctx.strokeRect(x - w / 2, y - h / 2, w, h);
    if (flash > 0) { ctx.fillStyle = `rgba(255,240,220,${0.6 * flash * sa})`; ctx.fillRect(x - w / 2, y - h / 2, w, h); }
  }
  for (const [x, y, w, h, sa, it, age] of rects[1]) {
    const flash = clamp(1 - age * 6);
    ctx.fillStyle = `rgba(255,212,70,${(0.1 + 0.1 * it) * sa})`; ctx.fillRect(x - w / 2, y - h / 2, w, h);
    ctx.strokeStyle = `rgba(255,236,140,${0.85 * sa})`; ctx.lineWidth = 1.1; ctx.strokeRect(x - w / 2, y - h / 2, w, h);
    if (flash > 0) { ctx.fillStyle = `rgba(255,255,240,${0.7 * flash * sa})`; ctx.fillRect(x - w / 2, y - h / 2, w, h); }
  }
  // sweep line
  if (sweepY > -40 && sweepY < H + 40) {
    const g = ctx.createLinearGradient(0, sweepY - 140, 0, sweepY);
    g.addColorStop(0, 'rgba(255,220,150,0)'); g.addColorStop(1, 'rgba(255,220,150,0.22)');
    ctx.fillStyle = g; ctx.fillRect(vp.x0, sweepY - 140, vp.x1 - vp.x0, 140);
    ctx.fillStyle = 'rgba(255,245,220,0.95)'; ctx.fillRect(vp.x0, sweepY - 1.5, vp.x1 - vp.x0, 3);
  }
  // vignette for legibility
  const v = ctx.createLinearGradient(0, 0, 0, H);
  v.addColorStop(0, 'rgba(3,7,12,0.55)'); v.addColorStop(0.18, 'rgba(3,7,12,0)'); v.addColorStop(0.78, 'rgba(3,7,12,0)'); v.addColorStop(1, 'rgba(3,7,12,0.6)');
  ctx.fillStyle = v; ctx.fillRect(vp.x0, 0, vp.x1 - vp.x0, H);
  ctx.restore();
}

// ------------------------------------------------------------------ UI (DOM)
const ui = { root: $('ui'), count: $('count'), search: $('searchText'), divider: $('divider'), labL: $('labL'), labR: $('labR'), tb: $('tb').getContext('2d') };
let WEEKLY = [];
function drawTimebar(t) {
  const g = ui.tb, w = 1530, h = 76; g.clearRect(0, 0, w, h);
  const max = Math.max(...WEEKLY.map(d => d[1])); const n = WEEKLY.length, bw = w / n;
  const grow = E.outCubic(prog(t, 21.5, 22.6));
  WEEKLY.forEach(([wk, v], i) => {
    const bh = Math.max(2, (Math.sqrt(v / max) * (h - 22)) * grow);
    const hot = wk === 37;
    g.fillStyle = hot ? '#ffd84a' : v > 20000 ? 'rgba(255,122,47,0.95)' : 'rgba(255,255,255,0.32)';
    g.fillRect(i * bw + 2, h - 18 - bh, bw - 4, bh);
  });
  g.fillStyle = 'rgba(255,255,255,0.5)'; g.font = '500 13px "JetBrains Mono"'; g.textBaseline = 'bottom';
  ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'].forEach((m, i) => g.fillText(m, (i / 12) * w + 4, h));
  const hx = (WEEKLY.findIndex(d => d[0] === 37) + 0.5) * bw;
  g.fillStyle = '#fff'; g.fillRect(hx - 1.5, 0, 3, h - 16);
}
function updateUI(t) {
  const a = E.outCubic(prog(t, 21.4, 22.2));
  ui.root.style.opacity = a;
  ui.root.style.transform = `translateY(${(1 - a) * 18}px)`;
  const total = 26349; ui.count.textContent = Math.round(total * E.outExpo(prog(t, 21.6, 23.8))).toLocaleString('es-MX');
  const q = 'August Complex · California, EE. UU.'; ui.search.textContent = q.slice(0, Math.round(q.length * prog(t, 21.7, 22.7)));
  drawTimebar(t);
  ui.divider.style.transform = `scaleY(${E.outCubic(prog(t, 25.0, 25.5))})`;
  const lp = E.outCubic(prog(t, 25.5, 26.1)), rp = E.outCubic(prog(t, 27.0, 27.6));
  ui.labL.style.opacity = lp; ui.labL.style.transform = `translateX(${(1 - lp) * -40}px)`;
  ui.labR.style.opacity = rp; ui.labR.style.transform = `translateX(${(1 - rp) * 40}px)`;
}

// ------------------------------------------------------------------ assets ready → frame function
let A, BOARD, SPACE, GRAIN, grainPat;
const strokeC = document.createElement('canvas'); strokeC.width = W; strokeC.height = H; const stx = strokeC.getContext('2d');

function seek(tv) {
  VT = clamp(tv, 0, DURATION - 1e-4); BOIL = Math.floor(VT * 12);
  const t = storyTime(VT);
  if (t >= T_FREEZE) { finalScene(t); return; }
  seekScene(t);
}
function seekScene(t) {
  const chalkScene = t < 17.6;

  // ---------- background
  const iris = E.inOutCubic(prog(t, 15.2, 16.4)) * 1250;
  bgx.globalAlpha = 1;
  if (t < 16.4) bgx.drawImage(BOARD, 0, 0); else bgx.drawImage(SPACE, 0, 0);
  if (iris > 0 && t < 16.4) { bgx.save(); bgx.beginPath(); bgx.arc(CX, CY, iris, 0, 7); bgx.clip(); bgx.drawImage(SPACE, 0, 0); bgx.restore(); }
  if (t < 0.35) { bgx.fillStyle = `rgba(0,0,0,${1 - prog(t, 0, 0.35)})`; bgx.fillRect(0, 0, W, H); }

  // ---------- chalk layer
  stx.clearRect(0, 0, W, H); phx.clearRect(0, 0, W, H);
  if (chalkScene) {
    const Rg = globeR(t);
    const fade = 1 - E.inQuad(prog(t, 9.55, 10.0));
    if (A.logo && fade > 0) { // NASA Space Apps Challenge logo, top of the first page
      const lw = 430, lh = (lw * A.logo.height) / A.logo.width, pop = E.outBack(prog(t, 0.0, 0.55));
      phx.save(); phx.globalAlpha = fade * clamp(prog(t, 0, 0.3)); phx.translate(CX, 150); phx.scale(pop, pop);
      phx.drawImage(A.logo, -lw / 2, -lh / 2, lw, lh); phx.restore();
    }
    if (t < 10.3) {
      const punch = WORDS.reduce((s, w) => s + 0.02 * Math.exp(-(((t - w[1]) / 0.12) ** 2)), 0);
      const drift = 1 + 0.04 * prog(t, 0, 9.6) + punch - 0.04 * E.inOutCubic(prog(t, 9.5, 10.2));
      stx.save(); stx.translate(CX, CY); stx.scale(drift, drift); stx.translate(-CX, -CY);
      // the title flattens into one line, as long as the globe's circumference, at the globe's top
      const fp = E.inOutCubic(prog(t, 9.6, 10.25));
      const titleXf = fp > 0 ? c => {
        const L = 2 * Math.PI * R0, sx = lerp(1, L / TITLE_W, fp), sy = lerp(1, 0.02, fp);
        c.setTransform(1, 0, 0, 1, 0, 0);
        c.translate(CX, lerp(TITLE.y, CY - R0, fp)); c.scale(lerp(drift, 1, fp) * sx, lerp(drift, 1, fp) * sy); c.translate(-CX, -TITLE.y);
      } : null;
      scene1(stx, t, fade, titleXf);
      stx.restore();
    }
    // line -> both ends curl down -> circle (the globe outline)
    const lineA = prog(t, 10.05, 10.25) * (1 - prog(t, 11.2, 11.5));
    if (lineA > 0) {
      const k = E.inOutCubic(prog(t, 10.25, 11.0)), L = 2 * Math.PI * R0, top = CY - R0, pts = [];
      for (let i = 0; i <= 160; i++) {
        const sN = i / 160 - 0.5;
        if (k < 1e-3) pts.push([CX + sN * L, top]);
        else { const th = k * 2 * Math.PI, r = L / th, ph = sN * th; pts.push([CX + r * Math.sin(ph), top + r * (1 - Math.cos(ph))]); }
      }
      rainbowPoly(stx, pts, { w: 6, amp: 1.6, alpha: lineA, seed: 1500 }, (t * 60) % 360, 6);
      drawPoly(stx, pts, { w: 2, color: '#fff3d6', amp: 2.4, alpha: lineA * 0.5, seed: 1600, passes: 1 });
    }
    if (t >= 10.85) {
      const ga = prog(t, 10.85, 11.4) * (1 - prog(t, 15.85, 16.6));
      chalkGlobe(stx, t, CX, CY, Rg, ga);
    }
    if (t >= 11 && t < 14.8) {
      const out = 1 - prog(t, 14.0, 14.45);
      rainbowTitle(stx, 'A HEAD FULL OF DREAMS', CX, 112, 104, E.inOutSine(prog(t, 11.6, 12.6)), t, out);
      chalkText(stx, "here's our proposal", CX, 198, { font: '"Gochi Hand"', weight: 400, size: 54, color: CH.orange, reveal: E.inOutSine(prog(t, 13.0, 13.6)), seed: 4, alpha: out });
      [[330, 92, 16, 12.3], [1590, 86, 20, 12.4], [420, 168, 10, 12.5], [1500, 170, 12, 12.6], [250, 150, 9, 12.7], [1680, 150, 9, 12.8]].forEach(([x, y, r, ts], i) => {
        const p = E.outBack(prog(t, ts, ts + 0.4)); if (p <= 0) return;
        const tw = 1 + Math.sin(t * 6 + i) * 0.12;
        drawPoly(stx, starPts(x, y, r * p * tw), { w: 2.5, color: `hsl(${(i * 60 + t * 160) % 360} 90% 72%)`, amp: 0.8, closed: true, alpha: out, seed: 600 + i * 20 });
      });
      // vibrating rainbow stars around the Earth and around each teammate
      TEAM_STARS.forEach(([x, y, r, ts], i) => {
        const p = E.outBack(prog(t, ts, ts + 0.35)); if (p <= 0) return;
        const vib = 1 + Math.sin(t * 15 + i * 1.7) * 0.25, dx = Math.sin(t * 9 + i) * 3.5, dy = Math.cos(t * 11 + i * 2) * 3.5;
        const col = `hsl(${(i * 47 + t * 220) % 360} 95% 70%)`;
        drawPoly(stx, starPts(x + dx, y + dy, r * p * vib), { w: 3.4, color: col, amp: 0.8, closed: true, alpha: out, seed: 1700 + i * 13 });
        if (i % 2 === 0) { stx.save(); stx.globalAlpha = out * (0.5 + 0.5 * Math.sin(t * 20 + i)); stx.fillStyle = col; stx.beginPath(); stx.arc(x + dx, y + dy, r * 0.22 * p, 0, 7); stx.fill(); stx.restore(); }
      });
      drawPeopleOn(stx, t);
    }
    // hero satellite chalk speed lines
    const ra = prog(t, 14.3, 14.6) * (1 - prog(t, 15.0, 15.5));
    if (ra > 0) {
      const sy = heroScreenY(t);
      for (let i = 0; i < 7; i++) {
        const x = CX + (i - 3) * 46 + jit(i, 1) * 6, len = 160 + hash(i) * 180, y0 = sy + 170 + hash(i * 3) * 60;
        drawPoly(stx, resample([[x, y0], [x + jit(i, 2) * 4, y0 + len]], 18), { w: 3, color: i % 2 ? CH.yellow : CH.white, amp: 1.5, alpha: ra * 0.7, seed: 1200 + i * 30 });
      }
    }
    // chalk grain (texture of real chalk)
    grainPat.setTransform(new DOMMatrix().translateSelf((BOIL * 37) % 512, (BOIL * 91) % 512));
    stx.globalCompositeOperation = 'destination-in'; stx.fillStyle = grainPat; stx.fillRect(0, 0, W, H); stx.globalCompositeOperation = 'source-over';
  }

  // ---------- globe (three)
  const c = camPath(t);
  const globeOn = t >= 15.8 && t < 21.5;
  const zMapIn = prog(c.Z, 4.75, 5.5);
  if (globeOn) {
    const gA = prog(t, 15.85, 16.6) * (1 - zMapIn);
    const d = globeDistance(c.Z, c.lat);
    cam.position.copy(latLonToVec(c.lat, c.lon, d)); cam.up.set(0, 1, 0); cam.lookAt(0, 0, 0); cam.updateMatrixWorld();
    G.earth.material.opacity = gA; G.patches.forEach((m, i) => (m.material.opacity = gA * (i === 0 ? prog(c.Z, 3.3, 4.2) : prog(c.Z, 4.0, 4.7))));
    G.atmo.material.uniforms.uOpacity.value = gA * (1 - prog(c.Z, 3.6, 4.6));
    G.rim.material.uniforms.uOpacity.value = gA;
    G.fireMat.uniforms.uTime.value = t; G.fireMat.uniforms.uOpacity.value = gA; G.fireMat.uniforms.uScale.value = 3.4 * Math.pow(2, (c.Z - ZG0) * 0.3);
    const orbA = prog(t, 16.6, 16.9) * (1 - prog(c.Z, 3.9, 4.4)) * gA;
    G.rings.forEach((R, i) => {
      const draw = E.inOutCubic(prog(t, 16.6 + i * 0.18, 17.7 + i * 0.18));
      R.line.geometry.instanceCount = Math.floor(256 * draw);
      R.line.material.opacity = 0.5 * orbA; R.line.visible = draw > 0 && orbA > 0;
      const th = R.th0 + R.speed * (t - 17.4);
      const sp = ringPoint(R.b, R.r, th);
      const vis = (R.hero ? prog(t, 17.15, 17.6) : prog(t, 17.2 + i * 0.2, 17.6 + i * 0.2)) * orbA;
      R.sprite.position.copy(sp); R.sprite.material.opacity = vis * 0.6; R.sprite.visible = vis > 0 && !R.hero;
      const om = G.orbitModels[i]; om.visible = vis > 0.02 && !R.hero; om.position.copy(sp);
      om.lookAt(ringPoint(R.b, R.r, th + Math.sign(R.speed) * 0.05)); om.rotateY(Math.PI / 2); om.rotateX(t * 0.4 + i);
      om.scale.setScalar(0.18 * Math.min(1, vis * 1.5));
      const tp = []; for (let k = 0; k <= 60; k++) tp.push(ringPoint(R.b, R.r, th - Math.sign(R.speed) * k * 0.012 * Math.min(1, Math.max(0, t - (R.hero ? 17.3 : 17.2)) * 1.2)));
      R.trail.geometry.setPositions(tp.flatMap(p => [p.x, p.y, p.z])); R.trail.material.opacity = vis; R.trail.visible = vis > 0;
      const len = sp.length() - 1; R.beam.position.copy(sp); R.beam.lookAt(0, 0, 0); R.beam.scale.set(1, 1, len);
      R.beam.material.uniforms.uOpacity.value = vis * prog(t, 17.5 + i * 0.15, 17.9 + i * 0.15);
      R.beam.visible = vis > 0;
    });
    gl.render(scene, cam);
    $('gl').style.opacity = 1;
  } else { gl.clear(); }

  // ---------- map
  const mapOn = t >= 20.6;
  if (mapOn && c.Z > 4.55) {
    mpx.clearRect(0, 0, W, H);
    const sp = E.inOutCubic(prog(t, 25.0, 25.9));
    const sweepY = lerp(-60, H + 200, prog(t, 23.15, 24.45));
    if (sp <= 0) {
      drawMap(mpx, c, { x0: 0, x1: W, cx: CX }, [1, 1], sweepY, t);
    } else {
      drawMap(mpx, c, { x0: 0, x1: CX, cx: lerp(CX, 590, sp) }, [1, 1 - sp], sweepY, t);
      drawMap(mpx, c, { x0: CX, x1: W, cx: lerp(CX, 1330, sp) }, [1 - sp, 1], sweepY, t);
    }
    $('map').style.opacity = prog(c.Z, 4.55, 4.75);
  } else { $('map').style.opacity = 0; }

  // ---------- satellites on the top layer
  heroSat(t);
  splitSats(t);
  if (!chalkScene && t >= 25.2) splitBeams(stx, t);

  // ---------- compose chalk canvas
  chx.clearRect(0, 0, W, H); chx.drawImage(strokeC, 0, 0);
  $('photo').style.opacity = chalkScene ? 1 : 0;
  updateUI(t);
}

const TEAM_STARS = (() => { // [x, y, size, appear time]: a ring around the globe, then a cluster around each person
  const r = mulberry32(77), out = [];
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * Math.PI * 2 + r() * 0.2, d = R0 + 34 + r() * 120;
    const x = CX + Math.cos(a) * d, y = CY + Math.sin(a) * d * 0.95;
    if (y < 235) continue; // keep the title clear
    out.push([x, y, 13 + r() * 16, 11.0 + (i / 24) * 0.9]);
  }
  PEOPLE.forEach((P, k) => {
    for (let j = 0; j < 6; j++) {
      const side = j % 2 ? 1 : -1, x = P.x + side * (110 + r() * 120), y = 500 + r() * 300;
      out.push([clamp(x, 30, W - 30), y, 12 + r() * 15, P.t + 0.35 + j * 0.07]);
    }
  });
  return out;
})();
function drawPeopleOn(ctx, t) { drawPeople(ctx, t, A.people); }
function rainbowTitle(ctx, text, x, y, size, reveal, t, alpha) {
  ctx.save(); ctx.font = `700 ${size}px "Cabin Sketch"`; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const total = ctx.measureText(text).width; let cx = x - total / 2;
  const n = Math.ceil(text.length * clamp(reveal));
  for (let i = 0; i < n; i++) {
    const ch = text[i], w = ctx.measureText(ch).width;
    const hue = (i * 26 + t * 160) % 360, bob = Math.sin(t * 5 + i * 0.6) * 4;
    ctx.fillStyle = `hsl(${hue} 92% 72%)`; ctx.globalAlpha = alpha;
    ctx.fillText(ch, cx + jit(i, 1) * 1.2, y + bob + jit(i, 2) * 1.2);
    ctx.globalAlpha = alpha * 0.35; ctx.fillText(ch, cx + 2, y + bob + 1.5);
    cx += w;
  }
  ctx.restore();
}

// hero satellite: rises from the bottom and glides into orbit without ever stopping (shares the globe camera)
function heroOffsetY(t) { // rising speed decays smoothly but never reaches zero
  const u = Math.max(0, (t - 14.3) / 2.0), k = 1.6;
  return -1.25 + 1.25 * (1 - Math.exp(-k * u)) / (1 - Math.exp(-k)) + Math.sin(t * 1.7) * 0.012;
}
function heroScreenY(t) { return CY - (heroOffsetY(t) / (2.2 * Math.tan(THREE.MathUtils.degToRad(15)))) * CY; }
const smoother = x => x * x * x * (x * (x * 6 - 15) + 10);
let heroMats = null;
function heroOpacity(a) {
  if (!heroMats) { heroMats = []; S.hero.traverse(o => { if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.transparent = true; heroMats.push(m); }); }); }
  heroMats.forEach(m => (m.opacity = a));
}
function heroSat(t) {
  const on = t >= 14.3 && t < T_FREEZE;
  S.hero.visible = on;
  if (!on) return;
  const c = camPath(t), d = globeDistance(c.Z, c.lat);
  cam.position.copy(latLonToVec(c.lat, c.lon, d)); cam.up.set(0, 1, 0); cam.lookAt(0, 0, 0); cam.updateMatrixWorld();
  const near = cam.localToWorld(new THREE.Vector3(0, heroOffsetY(t), -2.2));
  const R = G.rings[0], th = R.th0 + R.speed * (t - 17.4), orbitP = ringPoint(R.b, R.r, th);
  const w = smoother(prog(t, 15.3, 17.4));
  S.hero.position.copy(near.lerp(orbitP, w));
  S.hero.scale.setScalar(lerp(0.62, 0.18, w));
  S.hero.quaternion.copy(cam.quaternion);
  S.hero.rotateY(0.6 + t * 0.55); S.hero.rotateX(-0.35 + Math.sin(t * 0.8) * 0.1); S.hero.rotateZ(0.25);
  // fade only while the Earth hides it (closest approach of the view ray to the Earth's centre)
  const toS = S.hero.position.clone().sub(cam.position), L = toS.length(); toS.normalize();
  const tc = -cam.position.dot(toS), closest = cam.position.clone().add(toS.clone().multiplyScalar(tc)).length();
  heroOpacity(tc > 0 && tc < L ? smoother(clamp((closest - 0.95) / 0.12)) : 1);
  topRender(cam);
}
const SPLIT = [
  { k: 'terra', x: 640, y: 215, s: 175, from: -1, t: 25.35 },
  { k: 'aqua', x: 845, y: 330, s: 140, from: -1, t: 25.55 },
  { k: 'npp', x: 1280, y: 215, s: 175, from: 1, t: 26.85 },
  { k: 'n20', x: 1075, y: 330, s: 140, from: 1, t: 27.05 },
];
function splitSats(t) {
  let any = false;
  SPLIT.forEach((s, i) => {
    const p = E.outCubic(prog(t, s.t, s.t + 0.9)); const m = S[s.k];
    m.visible = p > 0; if (!m.visible) return; any = true;
    const x = s.x + s.from * (1 - p) * 700, y = s.y - (1 - p) * 260 + Math.sin(t * 1.3 + i) * 6;
    m.position.copy(screenToWorld2(x, y)); m.scale.setScalar((s.s * 10) / F);
    m.rotation.set(0.45 + Math.sin(t * 0.7 + i) * 0.08, (s.from < 0 ? 0.9 : -0.9) + t * 0.35 * s.from, 0.18 * s.from);
  });
  if (any) topRender(cam2);
}
let topDirty = false;
function topRender(camera) {
  // lights follow the camera so the model is always lit from the front-top
  for (const [l, off] of S.lights) { l.position.copy(camera.localToWorld(off.clone().multiplyScalar(0.3)).sub(camera.position).add(camera.position)); l.target.position.copy(camera.localToWorld(new THREE.Vector3(0, 0, -3))); }
  glTop.render(topScene, camera); topDirty = true;
}
function splitBeams(ctx, t) {
  SPLIT.forEach((s, i) => {
    const p = prog(t, s.t + 0.6, s.t + 1.1); if (p <= 0) return;
    const col = s.from < 0 ? '255,122,47' : '255,216,74';
    const tx = s.from < 0 ? 590 : 1330, ty = 600, spread = 150 * (i % 2 ? 0.8 : 1);
    const g = ctx.createLinearGradient(s.x, s.y, tx, ty);
    g.addColorStop(0, `rgba(${col},${0.32 * p})`); g.addColorStop(1, `rgba(${col},0)`);
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = g;
    ctx.beginPath(); ctx.moveTo(s.x - 8, s.y + 30); ctx.lineTo(s.x + 8, s.y + 30); ctx.lineTo(tx + spread, ty + 120); ctx.lineTo(tx - spread, ty + 120); ctx.closePath(); ctx.fill();
    const sc = ((t * 0.9 + i * 0.3) % 1);
    const yy = lerp(s.y + 30, ty + 120, sc), half = lerp(8, spread, sc), xx = lerp(s.x, tx, sc);
    ctx.strokeStyle = `rgba(${col},${0.8 * p * (1 - sc)})`; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(xx - half, yy); ctx.lineTo(xx + half, yy); ctx.stroke();
    ctx.restore();
  });
}

// ------------------------------------------------------------------ ending: laptop
const lapScene = new THREE.Scene();
const lapCam = new THREE.PerspectiveCamera(30, W / H, 0.05, 100);
const LAP = {};
const screenC = document.createElement('canvas'); screenC.width = W; screenC.height = H; const scx = screenC.getContext('2d');
let FREEZE = null, STUDIO = null;
function keyboardTexture() {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 1400; const g = c.getContext('2d');
  g.fillStyle = '#b9bdc4'; g.fillRect(0, 0, c.width, c.height);
  const kx = 150, ky = 120, kw = 1748, kh = 720, cols = 14, rows = 6, gap = 14, w = (kw - gap * (cols - 1)) / cols, h = (kh - gap * (rows - 1)) / rows;
  g.fillStyle = '#16181c';
  g.beginPath(); g.roundRect(kx - 26, ky - 26, kw + 52, kh + 52, 26); g.fillStyle = '#9fa3aa'; g.fill();
  g.fillStyle = '#121418';
  for (let r = 0; r < rows; r++) for (let k = 0; k < cols; k++) {
    let x = kx + k * (w + gap), ww = w;
    if (r === 5) { if (k === 5) { ww = w * 5 + gap * 4; } else if (k > 5 && k < 10) continue; else if (k >= 10) x -= 0; }
    g.beginPath(); g.roundRect(x, ky + r * (h + gap), ww, h, 12); g.fill();
  }
  g.beginPath(); g.roundRect(724, 930, 600, 380, 28); g.fillStyle = '#aeb2b9'; g.fill(); g.strokeStyle = '#9a9ea5'; g.lineWidth = 4; g.stroke();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 16; return t;
}
function makeStudio() {
  const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 0, H); grd.addColorStop(0, '#0b0f17'); grd.addColorStop(1, '#05070b'); g.fillStyle = grd; g.fillRect(0, 0, W, H);
  const glow = g.createRadialGradient(CX, CY * 0.9, 50, CX, CY * 0.9, 1000);
  glow.addColorStop(0, 'rgba(255,120,40,0.32)'); glow.addColorStop(0.45, 'rgba(255,80,30,0.10)'); glow.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = glow; g.fillRect(0, 0, W, H);
  const r = mulberry32(5); g.fillStyle = 'rgba(255,190,120,0.5)';
  for (let i = 0; i < 160; i++) { const x = r() * W, y = r() * H * 0.8, s = r() * 2.2; g.globalAlpha = 0.15 + r() * 0.4; g.beginPath(); g.arc(x, y, s, 0, 7); g.fill(); }
  return c;
}
function buildLaptop() {
  const pm = new THREE.PMREMGenerator(gl); lapScene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  const alu = new THREE.MeshStandardMaterial({ color: 0x9ea3ab, metalness: 0.7, roughness: 0.38, envMapIntensity: 0.45 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x0a0b0d, metalness: 0.2, roughness: 0.25 });
  const BW = 3.2, BD = 2.2, BT = 0.1;
  const base = new THREE.Mesh(new RoundedBoxGeometry(BW, BT, BD, 4, 0.05), alu); base.position.y = BT / 2; lapScene.add(base);
  const kb = new THREE.Mesh(new THREE.PlaneGeometry(BW * 0.96, BD * 0.94), new THREE.MeshStandardMaterial({ map: keyboardTexture(), metalness: 0.4, roughness: 0.5, envMapIntensity: 0.4 }));
  kb.rotation.x = -Math.PI / 2; kb.position.set(0, BT + 0.001, 0.02); lapScene.add(kb);
  const lid = new THREE.Group(); lid.position.set(0, BT, -BD / 2 + 0.03); lid.rotation.x = THREE.MathUtils.degToRad(-14); lapScene.add(lid);
  const LH = 2.06, LT = 0.06;
  const shell = new THREE.Mesh(new RoundedBoxGeometry(BW, LH, LT, 4, 0.03), alu); shell.position.set(0, LH / 2, -LT / 2); lid.add(shell);
  const bezel = new THREE.Mesh(new THREE.PlaneGeometry(BW - 0.04, LH - 0.04), dark); bezel.position.set(0, LH / 2, 0.001); lid.add(bezel);
  const SW = 2.98, SH = (SW * 9) / 16;
  LAP.tex = new THREE.CanvasTexture(screenC); LAP.tex.colorSpace = THREE.SRGBColorSpace; LAP.tex.anisotropy = 16;
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(SW, SH), new THREE.MeshBasicMaterial({ map: LAP.tex, toneMapped: false }));
  screen.position.set(0, LH / 2 + 0.05, 0.003); lid.add(screen);
  const shadowC = document.createElement('canvas'); shadowC.width = shadowC.height = 256; const sg = shadowC.getContext('2d');
  const gr = sg.createRadialGradient(128, 128, 10, 128, 128, 128); gr.addColorStop(0, 'rgba(0,0,0,0.75)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); sg.fillStyle = gr; sg.fillRect(0, 0, 256, 256);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(BW * 1.9, BD * 2.2), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(shadowC), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.002; lapScene.add(shadow);
  lapScene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xfff1e0, 1.5); key.position.set(4, 6, 5); lapScene.add(key);
  const rim = new THREE.DirectionalLight(0xff8a3d, 1.1); rim.position.set(-5, 3, -6); lapScene.add(rim);
  lapScene.updateMatrixWorld(true);
  LAP.screen = screen; LAP.SH = SH;
  LAP.center = screen.getWorldPosition(new THREE.Vector3());
  const q = screen.getWorldQuaternion(new THREE.Quaternion());
  LAP.normal = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
  LAP.up = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
  STUDIO = makeStudio();
}
function captureFreeze() {
  seekScene(T_FREEZE - 1e-3);
  FREEZE = document.createElement('canvas'); FREEZE.width = W; FREEZE.height = H; const f = FREEZE.getContext('2d');
  for (const id of ['bg', 'map', 'gl', 'photo', 'chalk', 'gltop']) {
    const el = $(id), a = +(el.style.opacity || 1);
    if (a > 0) { f.globalAlpha = a; f.drawImage(el, 0, 0); }
  }
  f.globalAlpha = 1;
}
const SHOTS = [ // what the laptop screen shows: start time, screenshot, optional zoom keyframes [t, zoom, focusX, focusY]
  { t: TF + 1.9, img: 'f0_open' },                                     // the map, while DATASETS / ALGORITHMS play
  { t: TFS + 1.9, img: 'f1_typing' },                                   // search a city
  { t: TFS + 3.2, img: 'f1_result', zoom: [[TFS + 3.45, 1, CX, CY], [TFS + 3.95, 2.0, 330, 600], [TFS + 4.55, 2.0, 330, 600], [TFS + 4.8, 1, CX, CY]] },
  { t: TFS + 4.8, img: 'f2_set' },                                      // a period, then Play
  ...Array.from({ length: 12 }, (_, i) => ({ t: TFS + 5.3 + i * 0.19, img: `f2_play${i}`, cut: true })),
  { t: TFS + 7.6, img: 'f3_fire' },                                     // one fire, then its Landsat pictures
  { t: TFS + 8.4, img: 'f3_landsat', zoom: [[TFS + 8.6, 1, CX, CY], [TFS + 9.1, 2.4, 400, 790], [TFS + 10.6, 2.55, 400, 790]] },
];
const CURSOR = [ // [t, x, y, click] in screenshot pixels
  [TFS + 2.0, 980, 640], [TFS + 2.5, 300, 34, true], [TFS + 3.3, 760, 560],
  [TFS + 4.95, 476, 982, true], [TFS + 7.0, 900, 700], [TFS + 8.15, 207, 544, true], [TFS + 9.0, 600, 760],
];
function zoomOf(shot, t) {
  const k = shot.zoom; if (!k) return [1, CX, CY];
  if (t <= k[0][0]) return k[0].slice(1);
  for (let i = 1; i < k.length; i++) if (t <= k[i][0]) { const e = E.inOutCubic(prog(t, k[i - 1][0], k[i][0])); return [1, 2, 3].map(j => lerp(k[i - 1][j], k[i][j], e)); }
  return k[k.length - 1].slice(1);
}
function drawShot(g, shot, t, alpha) {
  const img = A.feat[shot.img]; if (!img || alpha <= 0) return null;
  let [z, fx, fy] = zoomOf(shot, t);
  fx = clamp(fx, CX / z, W - CX / z); fy = clamp(fy, CY / z, H - CY / z);
  g.save(); g.globalAlpha = alpha; g.translate(CX, CY); g.scale(z, z); g.translate(-fx, -fy);
  g.drawImage(img, 0, 0, W, H); g.restore();
  return [z, fx, fy];
}
function drawCursor(g, x, y, s, a) {
  g.save(); g.translate(x, y); g.scale(s, s); g.globalAlpha = a;
  g.beginPath(); g.moveTo(0, 0); g.lineTo(0, 22); g.lineTo(5.5, 17); g.lineTo(9.5, 26); g.lineTo(13, 24.5); g.lineTo(9, 16); g.lineTo(16, 16); g.closePath();
  g.fillStyle = '#fff'; g.fill(); g.lineWidth = 1.6; g.strokeStyle = '#111'; g.stroke(); g.restore();
}
function drawScreen(t) {
  const g = scx; g.clearRect(0, 0, W, H);
  const swap = prog(t, TF + 1.9, TF + 2.5);
  if (swap < 1) { // the frozen frame, darkened under the title, zooms away into the site
    const z = 1 + 0.35 * E.inCubic(swap);
    g.save(); g.globalAlpha = 1 - E.inQuad(swap); g.translate(CX, CY); g.scale(z, z); g.drawImage(FREEZE, -CX, -CY); g.restore();
    g.fillStyle = `rgba(0,0,0,${0.38 * E.outCubic(prog(t, TF, TF + 0.4)) * (1 - swap)})`; g.fillRect(0, 0, W, H);
  }
  if (swap > 0) {
    let k = 0; SHOTS.forEach((sh, i) => { if (t >= sh.t) k = i; });
    const cur = SHOTS[k], prev = SHOTS[k - 1];
    const a = cur.cut ? 1 : E.inOutSine(prog(t, cur.t, cur.t + 0.22));
    if (prev && a < 1) drawShot(g, prev, t, swap);
    const view = drawShot(g, cur, t, a * swap) || [1, CX, CY];
    // cursor and clicks, in the same zoom as the screen
    const ca = prog(t, CURSOR[0][0], CURSOR[0][0] + 0.25) * (1 - prog(t, TFS + 9.6, TFS + 9.9));
    if (ca > 0) {
      let px = CURSOR[0][1], py = CURSOR[0][2];
      for (let i = 1; i < CURSOR.length; i++) { const [t0] = CURSOR[i - 1], [t1, x1, y1] = CURSOR[i]; if (t >= t0) { const e = E.inOutCubic(prog(t, t0 + 0.05, t1)); px = lerp(CURSOR[i - 1][1], x1, e); py = lerp(CURSOR[i - 1][2], y1, e); } }
      const [z, fx, fy] = view;
      g.save(); g.translate(CX, CY); g.scale(z, z); g.translate(-fx, -fy);
      let press = 0;
      CURSOR.forEach(([tc, x, y, click]) => { if (!click) return; press += Math.exp(-(((t - tc) / 0.07) ** 2)); const r = prog(t, tc, tc + 0.5); if (r > 0 && r < 1) { g.strokeStyle = `rgba(255,170,60,${1 - r})`; g.lineWidth = 4 / z; g.beginPath(); g.arc(x, y, (10 + r * 46) / z, 0, 7); g.stroke(); } });
      drawCursor(g, px, py, (2.1 / z) * (1 - 0.18 * press), ca);
      g.restore();
    }
  }
  const sh = prog(t, TF + 0.8, TF + 1.9) * 0.9; // glass sheen once it is a real screen
  if (sh > 0) { const gr = g.createLinearGradient(0, 0, W, H); gr.addColorStop(0, `rgba(255,255,255,${0.10 * sh})`); gr.addColorStop(0.35, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, W, H); }
  LAP.tex.needsUpdate = true;
}
function finalScene(t) {
  if (!FREEZE) captureFreeze();
  // hide every layer of the main film
  for (const id of ['map', 'photo']) $(id).style.opacity = 0;
  ui.root.style.opacity = 0; $('gl').style.opacity = 1;
  stx.clearRect(0, 0, W, H); phx.clearRect(0, 0, W, H); mpx.clearRect(0, 0, W, H);
  S.hero.visible = false; ['terra', 'aqua', 'npp', 'n20'].forEach(k => (S[k].visible = false));
  topDirty = false; glTop.clear();
  bgx.drawImage(STUDIO, 0, 0);
  drawScreen(t);
  // camera: starts exactly framing the screen (invisible cut), then dollies straight back along the screen's
  // normal, so the screen stays parallel to the frame; ends with the screen ~2/3 of the frame, slightly low for the title
  const d0 = LAP.SH / 2 / Math.tan(THREE.MathUtils.degToRad(15));
  const e = E.inOutCubic(prog(t, TF + 0.45, TF + 1.9));
  const push = E.inOutSine(prog(t, TF + 1.9, TF + 7.0));
  const back = E.inOutCubic(prog(t, T_DATA, T_DATA + 0.8)) * (1 - E.inOutCubic(prog(t, T_FEAT, T_FEAT + 0.75)));           // step back to make room for the panels
  const dist = lerp(lerp(d0, lerp(4.45, 4.05, push), e), 6.1, back);
  const lift = lerp(0, 0.15, e) - 0.12 * back;
  // laptop slides right for DATASETS, then left (past the centre) for ALGORITHMS
  const shiftPx = 370 * E.inOutCubic(prog(t, T_DATA, T_DATA + 0.8)) - 1000 * E.inOutCubic(prog(t, T_ALGO, T_ALGO + 1.2)) + 630 * E.inOutCubic(prog(t, T_FEAT, T_FEAT + 0.75));
  const right = new THREE.Vector3().crossVectors(LAP.up, LAP.normal).normalize();
  const worldPerPx = (2 * dist * Math.tan(THREE.MathUtils.degToRad(15))) / H;
  const look = LAP.center.clone().add(LAP.up.clone().multiplyScalar(lift)).add(right.clone().multiplyScalar(-shiftPx * worldPerPx));
  lapCam.position.copy(look.clone().add(LAP.normal.clone().multiplyScalar(dist)));
  lapCam.up.copy(LAP.up);
  lapCam.lookAt(look);
  const ex = E.inCubic(prog(t, T_EXIT, T_EXIT + 1.0)); // exit: the laptop is flung back and away
  lapScene.rotation.set(-0.7 * ex, 2.6 * ex, 0.6 * ex); lapScene.position.set(0, -2.2 * ex, -7 * ex);
  if (t < T_EXIT + 1.0) gl.render(lapScene, lapCam); else gl.clear();
  // captions: OUR WEBPAGE, then one line per feature
  const capOut = 1 - E.inCubic(prog(t, T_EXIT, T_EXIT + 0.3)), webOut = 1 - E.inCubic(prog(t, T_DATA, T_DATA + 0.45));
  const pop = E.outBack(prog(t, TF, TF + 0.45)), mv = E.inOutCubic(prog(t, TF + 0.55, TF + 1.9));
  CAPS.forEach(([t0, text], i) => {
    const t1 = CAPS[i + 1] ? CAPS[i + 1][0] : 1e9;
    const leave = E.inCubic(prog(t, t1, t1 + 0.3));
    if (t < t0 || leave >= 1) return;
    if (i === 0) caption(text, lerp(CY, 70, mv) - 40 * (1 - webOut), lerp(176, 80, mv), pop, webOut);
    else { const e = E.outBack(prog(t, t0, t0 + 0.4)); caption(text, 70 + (1 - e) * -60 - 40 * leave, 66, 1, clamp(prog(t, t0, t0 + 0.25)) * (1 - leave) * capOut); }
  });
  // DATASETS: in from the left, out the same way
  const dIn = E.outBack(prog(t, T_DATA + 0.3, T_DATA + 1.0)), dOut = E.inCubic(prog(t, T_ALGO, T_ALGO + 0.7));
  if (dIn > 0 && dOut < 1) drawPanel(stx, lerp(-900, 60, dIn) - 1000 * dOut, 70, 800, 940, 'DATASETS', DATASETS, T_DATA + 0.6, t, 0.2);
  // ALGORITHMS: in from the right, to the centre
  const aIn = E.outBack(prog(t, T_ALGO + 0.45, T_ALGO + 1.3));
  const aOut = E.inCubic(prog(t, T_FEAT, T_FEAT + 0.6));
  if (aIn > 0 && aOut < 1) drawPanel(stx, lerp(W + 100, CX - 470, aIn) + 1500 * aOut, 110, 940, 860, 'ALGORITHMS', ALGORITHMS, T_ALGO + 0.9, t, 0.22);
  drawExit(t);
  chx.clearRect(0, 0, W, H); chx.drawImage(strokeC, 0, 0);
}
const CAPS = [[TF, 'OUR WEBPAGE'], [TFS + 1.9, 'ANALYSING FIRES IN A GIVEN AREA'], [TFS + 4.8, 'ANALYSING FIRES ACROSS A PERIOD'], [TFS + 7.6, 'BEFORE AND AFTER A FIRE PICTURES']];
function caption(text, y, size, scale, alpha) {
  if (alpha <= 0.001) return;
  stx.save(); stx.globalAlpha = alpha; stx.translate(CX, y); stx.scale(scale, scale);
  stx.font = `700 ${size}px "Space Grotesk"`; stx.textAlign = 'center'; stx.textBaseline = 'middle';
  if ('letterSpacing' in stx) stx.letterSpacing = `${size * 0.04}px`;
  const gr = stx.createLinearGradient(0, -size / 2, 0, size / 2); gr.addColorStop(0, '#ffe08a'); gr.addColorStop(0.55, '#ff9a3d'); gr.addColorStop(1, '#ff5a3a');
  stx.shadowColor = 'rgba(0,0,0,0.6)'; stx.shadowBlur = 30; stx.shadowOffsetY = 8;
  stx.fillStyle = gr; stx.fillText(text, 0, 0);
  stx.restore();
}
// ---- the exit: the laptop is flung away, a wall of fire rises, white flash, the title slams in
function drawExit(t) {
  const u = t - T_EXIT; if (u < 0) return;
  const g = stx, fw = E.inCubic(prog(u, 0.1, 1.0));
  if (u < 1.05) {
    g.save();
    const shake = 16 * fw; g.translate(jit(1, 3) * shake, jit(2, 4) * shake);
    g.fillStyle = `rgba(28,4,2,${0.75 * fw})`; g.fillRect(-40, -40, W + 80, H + 80);   // the room goes dark red
    const glow = g.createLinearGradient(0, H, 0, H - H * 1.35 * fw);
    glow.addColorStop(0, 'rgba(255,120,20,1)'); glow.addColorStop(0.35, 'rgba(230,40,10,0.85)'); glow.addColorStop(0.75, 'rgba(120,10,5,0.5)'); glow.addColorStop(1, 'rgba(60,0,0,0)');
    g.fillStyle = glow; g.fillRect(-40, -40, W + 80, H + 80);
    g.globalCompositeOperation = 'lighter';                                                // flames add light
    for (let i = 0; i < 17; i++) {
      const x = -60 + (i / 16) * (W + 120) + Math.sin(t * 3 + i) * 20, sz = (180 + hash(i * 7) * 260) * (0.25 + fw * 3.4);
      drawFlame(g, x, H + 80, sz, t * 1.7 + i, 60 + i, clamp(prog(u, i * 0.02, i * 0.02 + 0.2)), i % 4);
    }
    g.globalCompositeOperation = 'source-over';
    g.restore();
  }
  const fl = clamp(prog(u, 0.85, 1.0)) * (1 - prog(u, 1.0, 1.45)); // white flash
  if (u >= 1.0) { // end card
    const card = prog(u, 1.0, 1.1);
    g.save(); g.globalAlpha = card;
    const bgG = g.createRadialGradient(CX, CY, 60, CX, CY, 1100); bgG.addColorStop(0, '#2a0e06'); bgG.addColorStop(0.55, '#0c0507'); bgG.addColorStop(1, '#030205');
    g.fillStyle = bgG; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 170; i++) { // embers
      const ph = (u * (0.25 + hash(i) * 0.35) + hash(i * 3.3)) % 1, x = hash(i * 7.1) * W + Math.sin(u * 2 + i) * 30, y = H + 20 - ph * (H + 80);
      g.globalAlpha = card * (1 - ph) * (0.4 + hash(i * 2.2) * 0.6); g.fillStyle = i % 3 ? '#ffb347' : '#ff6a2b';
      g.beginPath(); g.arc(x, y, 1.2 + hash(i * 5.5) * 3.2, 0, 7); g.fill();
    }
    g.globalAlpha = 1; g.restore();
    const slam = E.outBack(prog(u, 1.05, 1.45)), impact = Math.exp(-Math.max(0, u - 1.3) * 7) * (u > 1.3 ? 1 : 0);
    g.save(); g.translate(jit(5, 1) * 22 * impact, jit(6, 2) * 22 * impact);
    const ring = prog(u, 1.3, 1.9); // shockwave
    if (ring > 0 && ring < 1) { g.strokeStyle = `rgba(255,200,120,${0.8 * (1 - ring)})`; g.lineWidth = 10 * (1 - ring) + 1; g.beginPath(); g.arc(CX, 560, 80 + ring * 1100, 0, 7); g.stroke(); }
    if (A.logo) { const lw = 430, lh = (lw * A.logo.height) / A.logo.width, la = clamp(prog(u, 1.4, 1.75)); g.globalAlpha = la; g.drawImage(A.logo, CX - lw / 2, 210 - lh / 2 + (1 - la) * -30, lw, lh); g.globalAlpha = 1; }
    g.save(); g.translate(CX, 560); const sc = lerp(3.2, 1, slam); g.scale(sc, sc); g.translate(-CX, -560);
    rainbowTitle(g, 'A HEAD FULL OF DREAMS', CX, 560, 150, 1, t, clamp(prog(u, 1.05, 1.15)));
    g.restore();
    const sa = clamp(prog(u, 1.6, 2.0));
    g.globalAlpha = sa; g.font = '600 36px "Space Grotesk"'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#ffd9b0';
    if ('letterSpacing' in g) g.letterSpacing = '6px';
    g.fillText('BURNING CALENDAR', CX, 690 + (1 - sa) * 20);
    if ('letterSpacing' in g) g.letterSpacing = '0px';
    g.globalAlpha = 1; g.restore();
    const fade = prog(u, 3.05, 3.3); if (fade > 0) { g.fillStyle = `rgba(0,0,0,${fade})`; g.fillRect(0, 0, W, H); }
  }
  if (fl > 0) { g.fillStyle = `rgba(255,248,235,${fl})`; g.fillRect(0, 0, W, H); }
}
const DATASETS = [ // name, detail (what each one is used for in the project)
  ['NASA FIRMS · MODIS C6.1', 'Terra + Aqua fire detections, 2000–2025'],
  ['NASA FIRMS · VIIRS 375 m', 'Suomi NPP + NOAA-20 detections, 2012–2025'],
  ['gridMET', 'daily weather and fuel dryness'],
  ['LANDFIRE', 'fire regime: frequency and severity'],
  ['MODIS MCD64A1 · MCD12Q1 · MOD44B', 'burned area, land cover, tree cover'],
  ['SRTM · GPW v4.11 · GHSL', 'terrain, population, built-up surface'],
  ['Landsat 5 – 9', 'before / after pictures, burn severity'],
  ['NIFC WFIGS', 'agency-reported wildfires'],
  ['CelesTrak · U.S. Census', 'satellite orbits, state borders'],
];
const ALGORITHMS = [
  ['Active cell-days on a 0.1° grid', 'one fire counts once per cell per day'],
  ['FRP observation operator (IS4FIRES)', 'VIIRS → MODIS-equivalent: error 0.27 vs 3.06 raw'],
  ['Graph connected components', 'detections → 2.0 M individual fires'],
  ['LightGBM gradient-boosted trees', 'chance a fire reaches 1,000 acres · AUC 0.936'],
  ['Isotonic calibration', 'five danger levels, from low to extreme'],
  ['Climatology percentiles', 'unusual (> p90) and record weeks, usual season'],
  ['SGP4 orbit propagation', 'where each satellite is and when it passes'],
  ['Normalized Burn Ratio (Landsat)', 'burn severity before vs after'],
];
function drawPanel(g, x, y, w, h, title, items, tItems, t, step) {
  g.save();
  g.shadowColor = 'rgba(0,0,0,0.55)'; g.shadowBlur = 50; g.shadowOffsetY = 18;
  g.beginPath(); g.roundRect(x, y, w, h, 30); g.fillStyle = 'rgba(9,12,20,0.86)'; g.fill();
  g.shadowColor = 'transparent';
  const bd = g.createLinearGradient(x, y, x + w, y + h);
  ['#ff5e8a', '#ff9f43', '#ffd93d', '#5ee08f', '#4dabf7', '#a78bfa'].forEach((c, k, a) => bd.addColorStop(k / (a.length - 1), c));
  g.lineWidth = 3; g.strokeStyle = bd; g.stroke();
  g.font = '700 68px "Space Grotesk"'; g.textBaseline = 'middle'; g.textAlign = 'left';
  if ('letterSpacing' in g) g.letterSpacing = '3px';
  const tg = g.createLinearGradient(0, y + 50, 0, y + 120); tg.addColorStop(0, '#ffe08a'); tg.addColorStop(0.55, '#ff9a3d'); tg.addColorStop(1, '#ff5a3a');
  g.fillStyle = tg; g.fillText(title, x + 48, y + 86);
  if ('letterSpacing' in g) g.letterSpacing = '0px';
  g.fillStyle = bd; g.fillRect(x + 48, y + 132, 120, 5);
  const top = y + 178, rowH = (h - 210) / items.length;
  items.forEach(([name, detail], i) => {
    const a = E.outCubic(prog(t, tItems + i * step, tItems + i * step + 0.35));
    if (a <= 0) return;
    const ry = top + i * rowH, dx = (1 - a) * 40;
    g.globalAlpha = a;
    g.fillStyle = `hsl(${(i * 360) / items.length + 10} 85% 66%)`;
    g.beginPath(); g.roundRect(x + 50 + dx, ry + 8, 14, 14, 4); g.fill();
    g.fillStyle = '#f4f6fa'; g.font = '600 31px "Space Grotesk"'; g.fillText(name, x + 84 + dx, ry + 15);
    g.fillStyle = 'rgba(222,230,240,0.66)'; g.font = '400 22px "Space Grotesk"'; g.fillText(detail, x + 84 + dx, ry + 52);
    g.globalAlpha = 1;
  });
  g.restore();
}

// ------------------------------------------------------------------ boot
async function boot() {
  A = await loadAll();
  LAND = feature(A.land, A.land.objects.land); GRAT = geoGraticule10();
  ttx.font = `700 ${TITLE.size}px "Cabin Sketch"`; TITLE_W = ttx.measureText(TITLE.text).width;
  WEEKLY = A.weekly;
  BOARD = makeBoard(); SPACE = makeSpace(); GRAIN = makeGrain(); grainPat = stx.createPattern(GRAIN, 'repeat');
  prepMap(A);
  await buildGlobe(A); await buildSats(); buildLaptop();
  // patch: per-frame clear of the top layer when nothing is drawn there
  const origSeek = seek;
  window.seek = t => { topDirty = false; origSeek(t); if (!topDirty) glTop.clear(); };
  window.__ready = true;
  window.seek(0);
  if (!RENDER) setupPreview();
}
function setupPreview() {
  const stage = $('stage'), scrub = $('scrub'), time = $('time'), btn = $('play');
  const fit = () => { const s = Math.min(innerWidth / W, (innerHeight - 60) / H); stage.style.transform = `scale(${s})`; };
  fit(); addEventListener('resize', fit);
  let playing = false, t0 = 0, start = 0;
  const show = t => { window.seek(t); scrub.value = t; time.textContent = `${t.toFixed(2)} s`; };
  const loop = now => { if (!playing) return; const t = t0 + (now - start) / 1000; if (t >= DURATION) { playing = false; btn.textContent = '▶ Play'; show(DURATION - 0.01); return; } show(t); requestAnimationFrame(loop); };
  btn.onclick = () => { playing = !playing; btn.textContent = playing ? '❚❚ Pause' : '▶ Play'; if (playing) { t0 = +scrub.value >= DURATION - 0.05 ? 0 : +scrub.value; start = performance.now(); requestAnimationFrame(loop); } };
  scrub.oninput = () => { playing = false; btn.textContent = '▶ Play'; show(+scrub.value); };
  const q = new URLSearchParams(location.search).get('t'); if (q) show(+q);
}
if (RENDER) document.body.classList.add('render');
boot().catch(e => { console.error(e); document.body.insertAdjacentHTML('beforeend', `<pre style="position:fixed;top:0;left:0;color:#f66;z-index:99">${e.stack}</pre>`); });
