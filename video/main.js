// A Head Full of Dreams: 30 s presentation video, 1920x1080.
// Every frame is a pure function of time: window.seek(t) draws frame t (used for preview and MP4 render).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { geoOrthographic, geoPath, geoGraticule10, geoDistance } from 'https://cdn.jsdelivr.net/npm/d3-geo@3.1.1/+esm';
import { feature } from 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/+esm';

const W = 1920, H = 1080, CX = W / 2, CY = H / 2;
const DURATION = 30;
const RENDER = new URLSearchParams(location.search).has('render');
const F = CY / Math.tan(THREE.MathUtils.degToRad(15)); // focal length in px for fov 30
const R0 = 280; // chalk globe radius (px)

// ------------------------------------------------------------------ people (placeholders)
// Put photos in assets/people/persona1.png ... persona5.png (or .jpg) and change the names.
const PEOPLE = [
  { name: 'Integrante 1', x: 1560, y: 790, w: 250, h: 310, rot: 0.05, from: 'right', t: 10.25, back: false },
  { name: 'Integrante 2', x: 1735, y: 510, w: 200, h: 250, rot: -0.07, from: 'right', t: 10.55, back: true },
  { name: 'Integrante 3', x: 360, y: 790, w: 250, h: 310, rot: -0.05, from: 'left', t: 10.85, back: false },
  { name: 'Integrante 4', x: 185, y: 510, w: 200, h: 250, rot: 0.07, from: 'left', t: 11.15, back: true },
  { name: 'Integrante 5', x: 960, y: 935, w: 230, h: 280, rot: -0.02, from: 'bottom', t: 11.45, back: false },
];

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
  const people = await Promise.all(PEOPLE.map(async (_, i) => (await loadImg(`assets/people/persona${i + 1}.png`)) || (await loadImg(`assets/people/persona${i + 1}.jpg`))));
  await fontsP; await document.fonts.ready;
  return { land, firesCA, firesUS, mosaics, mosImgs, patches, weekly, people };
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
function chalkGlobe(ctx, t, cx, cy, R, alpha, flameAlpha = 1) {
  if (alpha <= 0) return;
  const lon = globeLon(t), lat = GLOBE_LAT;
  const proj = geoOrthographic().scale(R).translate([cx, cy]).rotate([-lon, -lat]).clipAngle(90).precision(0.6);
  const rec = recorder(); geoPath(proj, rec)(LAND);
  const grat = recorder(); geoPath(proj, grat)(GRAT);
  const bb = [cx - R, cy - R, cx + R, cy + R];
  ctx.save();
  ctx.globalAlpha = alpha; ctx.fillStyle = 'rgba(156,208,255,0.07)'; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
  hatch(ctx, c => c.arc(cx, cy, R, 0, Math.PI * 2), bb, { spacing: 15, angle: 0.6, color: CH.blue, alpha: 0.13 * alpha, w: 1.6, seed: 3 });
  grat.segs.forEach((s, i) => drawPoly(ctx, s, { w: 1.2, color: CH.blue, alpha: 0.22 * alpha, amp: 0.7, seed: 500 + i * 37, passes: 1 }));
  hatch(ctx, c => rec.replay(c), bb, { spacing: 7, angle: -0.7, color: CH.green, alpha: 0.5 * alpha, w: 2, seed: 7 });
  rec.segs.forEach((s, i) => drawPoly(ctx, s, { w: 2.6, color: CH.green, alpha, amp: 1.1, closed: !!s.closed, seed: 900 + i * 101 }));
  drawPoly(ctx, circlePts(cx, cy, R, 140), { w: 4.5, color: CH.white, closed: true, amp: 1.6, alpha, seed: 13 });
  drawPoly(ctx, circlePts(cx, cy, R + 10, 140), { w: 1.6, color: CH.white, closed: true, amp: 2.2, alpha: alpha * 0.35, seed: 17, passes: 1 });
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
const FL = [ // x, baseY, size, tEnter, from, palette
  [520, 650, 175, 0.08, 'bottom', 0], [1400, 650, 195, 0.28, 'bottom', 1], [960, 668, 240, 0.5, 'bottom', 0],
  [200, 640, 145, 0.78, 'left', 2], [1720, 640, 155, 0.98, 'right', 3],
  [745, 640, 120, 2.3, 'bottom', 1], [1180, 642, 132, 2.42, 'bottom', 2], [360, 662, 100, 2.56, 'left', 3], [1570, 662, 108, 2.7, 'right', 0],
  [62, 672, 92, 2.84, 'left', 0], [1862, 672, 92, 2.98, 'right', 1], [635, 676, 78, 3.12, 'bottom', 2], [1290, 676, 84, 3.24, 'bottom', 3],
];
const WORDS = [ // text, t, x, color, icon
  ['PREVENIR', 4.0, 400, CH.green, 'shield'], ['CONTROLAR', 6.0, 960, CH.blue, 'target'], ['ANALIZAR', 8.0, 1520, CH.yellow, 'lens'],
];
function scene1(ctx, t, alpha) {
  if (alpha <= 0) return;
  // flames
  FL.forEach(([x, y, s, te, from, pal], i) => {
    const p = prog(t, te, te + 0.65); if (p <= 0) return;
    const e = E.outBack(p);
    let dx = 0, dy = 0;
    if (from === 'bottom') dy = (1 - e) * 560; else if (from === 'left') dx = -(1 - e) * (x + 260); else dx = (1 - e) * (W - x + 260);
    const breathe = 1 + Math.sin(t * 2.3 + i) * 0.035;
    const sc = s * lerp(0.35, 1, clamp(p * 1.6)) * breathe;
    drawFlame(ctx, x + dx, y + dy, sc, t + i * 0.7, i + 1, alpha, pal);
    drawSparks(ctx, x + dx, y + dy, sc, t, i + 1, alpha * clamp(p * 2 - 1));
  });
  // ground line under the fire row
  drawPoly(ctx, resample([[40, 690], [1880, 690]], 24), { w: 3, color: CH.white, amp: 1.6, alpha: alpha * 0.55, upto: E.outCubic(prog(t, 0.2, 1.3)), seed: 70 });
  // title
  chalkText(ctx, 'CADA VEZ MÁS INCENDIOS', CX - 40, 200, { size: 116, reveal: E.inOutSine(prog(t, 0.7, 2.0)), seed: 1, alpha });
  drawPoly(ctx, resample([[380, 280], [960, 286], [1460, 278]], 20), { w: 5, color: CH.orange, amp: 2, alpha, upto: E.outCubic(prog(t, 1.95, 2.45)), seed: 90 });
  // up-arrow next to the title ("more and more")
  const ap = E.outCubic(prog(t, 2.2, 2.8));
  drawPoly(ctx, resample([[1690, 250], [1745, 195], [1780, 218], [1850, 135]], 10), { w: 6, color: CH.red, amp: 1.5, alpha, upto: ap, seed: 95 });
  drawPoly(ctx, resample([[1810, 133], [1852, 133], [1852, 177]], 8), { w: 6, color: CH.red, amp: 1.5, alpha: alpha * clamp(ap * 3 - 2), seed: 99 });
  // three keywords with icons
  WORDS.forEach(([word, tw, x, color, icon], i) => {
    const pIcon = E.outCubic(prog(t, tw, tw + 0.6));
    const pop = E.outBack(prog(t, tw, tw + 0.35));
    drawIcon(ctx, icon, x, 790, 120 * lerp(0.6, 1, pop), pIcon, color, 300 + i * 100);
    chalkText(ctx, word, x, 918, { size: 76, reveal: E.inOutSine(prog(t, tw + 0.25, tw + 0.9)), seed: 20 + i, color, alpha });
  });
}

// ------------------------------------------------------------------ people cards
function personPos(P, i, t) {
  const pin = E.outBack(prog(t, P.t, P.t + 0.75));
  const pout = E.inCubic(prog(t, 14.0 + i * 0.06, 14.55 + i * 0.06));
  let x0 = P.x, y0 = P.y;
  if (P.from === 'right') x0 = W + P.w; else if (P.from === 'left') x0 = -P.w; else y0 = H + P.h;
  const k = pin * (1 - pout);
  return { x: lerp(x0, P.x, k), y: lerp(y0, P.y, k), rot: P.rot + (1 - k) * (P.from === 'left' ? -0.35 : P.from === 'right' ? 0.35 : 0.1), vis: pin > 0 && k > 0.001 };
}
function drawPeople(cx, t, imgs) {
  PEOPLE.forEach((P, i) => {
    const { x, y, rot, vis } = personPos(P, i, t);
    if (!vis) return;
    const a = P.back ? 0.88 : 1, w = P.w, h = P.h, pad = 14, lab = 54;
    const corners = [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2], [-w / 2, -h / 2]];
    const inner = [[-w / 2 + pad, -h / 2 + pad], [w / 2 - pad, -h / 2 + pad], [w / 2 - pad, h / 2 - lab], [-w / 2 + pad, h / 2 - lab], [-w / 2 + pad, -h / 2 + pad]];
    // photo layer
    phx.save(); phx.translate(x, y); phx.rotate(rot);
    phx.fillStyle = 'rgba(14,22,19,0.92)'; phx.fillRect(-w / 2, -h / 2, w, h);
    const iw = w - pad * 2, ih = h - pad - lab;
    if (imgs[i]) {
      const im = imgs[i], sc = Math.max(iw / im.width, ih / im.height);
      phx.save(); phx.beginPath(); phx.rect(-w / 2 + pad, -h / 2 + pad, iw, ih); phx.clip();
      phx.drawImage(im, -w / 2 + pad + (iw - im.width * sc) / 2, -h / 2 + pad + (ih - im.height * sc) / 2, im.width * sc, im.height * sc);
      phx.restore();
    }
    phx.restore();
    // chalk layer
    cx.save(); cx.translate(x, y); cx.rotate(rot);
    drawPoly(cx, resample(corners, 14), { w: 4, color: CH.white, amp: 1.5, alpha: a, seed: 700 + i * 60 });
    drawPoly(cx, resample(inner, 14), { w: 2, color: CH.white, amp: 1.2, alpha: a * 0.6, seed: 760 + i * 60, passes: 1 });
    if (!imgs[i]) { // placeholder silhouette
      const top = -h / 2 + pad, cxp = 0, hr = iw * 0.17;
      drawPoly(cx, circlePts(cxp, top + ih * 0.38, hr, 36), { w: 3.5, color: CH.white, amp: 1.2, alpha: a * 0.85, closed: true, seed: 800 + i * 50 });
      const sh = []; for (let k = 0; k <= 24; k++) { const an = Math.PI + (k / 24) * Math.PI; sh.push([cxp + Math.cos(an) * iw * 0.36, top + ih + Math.sin(an) * ih * 0.32]); }
      drawPoly(cx, sh, { w: 3.5, color: CH.white, amp: 1.2, alpha: a * 0.85, seed: 840 + i * 50 });
      hatch(cx, c => c.arc(cxp, top + ih * 0.38, hr, 0, 7), [-hr, top + ih * 0.38 - hr, hr, top + ih * 0.38 + hr], { spacing: 6, color: CH.white, alpha: 0.22 * a, w: 1.5, seed: 860 + i });
    }
    chalkText(cx, P.name, 0, h / 2 - lab / 2 + 2, { font: '"Gochi Hand"', weight: 400, size: Math.round(w * 0.13), seed: 40 + i, alpha: a });
    cx.restore();
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
    R.sprite.scale.set(0.045, 0.045, 1); scene.add(R.sprite);
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
  S.hero = normalizeModel(cl(npp));
  S.terra = normalizeModel(terra); S.aqua = normalizeModel(aqua); S.npp = normalizeModel(cl(npp)); S.n20 = normalizeModel(cl(npp));
  for (const k of ['hero', 'terra', 'aqua', 'npp', 'n20']) { topScene.add(S[k]); S[k].visible = false; }
  topScene.add(new THREE.HemisphereLight(0xcfe2ff, 0x2a1a10, 1.4));
  S.lights = [[new THREE.DirectionalLight(0xffe2c0, 3.2), new THREE.Vector3(5, 6, 8)], [new THREE.DirectionalLight(0x7ab8ff, 2.4), new THREE.Vector3(-6, 2, -5)], [new THREE.DirectionalLight(0xffffff, 0.8), new THREE.Vector3(-4, -3, 6)]];
  for (const [l] of S.lights) { topScene.add(l); topScene.add(l.target); }
}
function screenToWorld2(sx, sy, z = 0) { const d = 10 - z, k = d / F; return new THREE.Vector3((sx - CX) * k, -(sy - CY) * k, z); }

// ------------------------------------------------------------------ camera path (globe + map share one zoom)
const ZG0 = Math.log2((R0 * Math.cos(THREE.MathUtils.degToRad(GLOBE_LAT)) * 2 * Math.PI) / 256);
const TARGET = { lon: -122.99, lat: 39.92 };
const merc = (lon, lat) => { const lr = (lat * Math.PI) / 180; return [(lon + 180) / 360, (1 - Math.log(Math.tan(lr) + 1 / Math.cos(lr)) / Math.PI) / 2]; };
const unmerc = (x, y) => [x * 360 - 180, (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI];
function camPath(t) {
  if (t <= 17.4) return { lon: globeLon(t), lat: GLOBE_LAT, Z: ZG0 };
  if (t <= 19.6) {
    const e = E.inOutSine(prog(t, 17.4, 19.6));
    return { lon: lerp(globeLon(17.4), -112, e), lat: lerp(GLOBE_LAT, 37, e), Z: lerp(ZG0, 3.7, e) };
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

function seek(t) {
  t = clamp(t, 0, DURATION - 1e-4);
  BOIL = Math.floor(t * 12);
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
    // zoom-out camera between scene 1 and the globe
    const zp = E.inOutCubic(prog(t, 9.6, 10.75));
    const Zc = lerp(5.5, 1, zp);
    const lonNow = globeLon(t);
    const projW = geoOrthographic().scale(R0).translate([CX, CY]).rotate([-lonNow, -GLOBE_LAT]);
    const P1 = projW([-121.5, 39.5]);
    const Fx = lerp(P1[0], CX, zp), Fy = lerp(P1[1], CY, zp);
    // scene 1 (drawn into a box around California that fills the screen at Zc = 5.5)
    if (t < 10.8) {
      stx.save();
      const punch = WORDS.reduce((s, w) => s + 0.025 * Math.exp(-(((t - w[1]) / 0.13) ** 2)), 0) + 0.02 * Math.exp(-(((t - 2.3) / 0.15) ** 2));
      const drift = 1 + 0.045 * prog(t, 0, 9.6) + punch;
      stx.translate(CX, CY); stx.scale(Zc, Zc); stx.translate(-Fx, -Fy);
      stx.translate(P1[0], P1[1]); stx.scale(1 / 5.5, 1 / 5.5);
      stx.translate(0, 0); stx.scale(drift, drift); stx.rotate(Math.sin(t * 0.5) * 0.006);
      stx.translate(-CX, -CY);
      scene1(stx, t, 1 - E.inQuad(prog(t, 9.75, 10.5)));
      stx.restore();
    }
    // chalk globe
    if (t >= 9.6) {
      const gx = CX + (CX - Fx) * Zc, gy = CY + (CY - Fy) * Zc;
      const ga = prog(t, 9.6, 9.95) * (1 - prog(t, 15.85, 16.6));
      chalkGlobe(stx, t, gx, gy, R0 * Zc, ga);
    }
    // team title + people
    if (t >= 10 && t < 14.8) {
      const out = 1 - prog(t, 14.0, 14.45);
      chalkText(stx, 'A HEAD FULL OF DREAMS', CX, 112, { size: 104, reveal: E.inOutSine(prog(t, 11.0, 12.2)), seed: 3, alpha: out });
      chalkText(stx, 'esta es nuestra propuesta', CX, 198, { font: '"Gochi Hand"', weight: 400, size: 54, color: CH.orange, reveal: E.inOutSine(prog(t, 12.9, 13.6)), seed: 4, alpha: out });
      [[330, 92, 16, 11.9], [1590, 86, 20, 12.05], [420, 168, 10, 12.2], [1500, 170, 12, 12.3], [250, 150, 9, 12.4], [1680, 150, 9, 12.5]].forEach(([x, y, r, ts], i) => {
        const p = E.outBack(prog(t, ts, ts + 0.4)); if (p <= 0) return;
        const tw = 1 + Math.sin(t * 6 + i) * 0.12;
        drawPoly(stx, starPts(x, y, r * p * tw), { w: 2.5, color: i % 2 ? CH.yellow : CH.white, amp: 0.8, closed: true, alpha: out, seed: 600 + i * 20 });
      });
      drawPeopleOn(stx, t);
    }
    // hero satellite chalk speed lines
    const ra = prog(t, 14.3, 14.6) * (1 - prog(t, 16.0, 16.5));
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
    const orbA = prog(t, 16.6, 16.9) * (1 - prog(t, 19.4, 20.1)) * gA;
    G.rings.forEach((R, i) => {
      const draw = E.inOutCubic(prog(t, 16.6 + i * 0.18, 17.7 + i * 0.18));
      R.line.geometry.instanceCount = Math.floor(256 * draw);
      R.line.material.opacity = 0.5 * orbA; R.line.visible = draw > 0 && orbA > 0;
      const th = R.th0 + R.speed * (t - 17.4);
      const sp = ringPoint(R.b, R.r, th);
      const vis = (R.hero ? prog(t, 17.3, 17.45) : prog(t, 17.2 + i * 0.2, 17.6 + i * 0.2)) * orbA;
      R.sprite.position.copy(sp); R.sprite.material.opacity = vis; R.sprite.visible = vis > 0;
      const tp = []; for (let k = 0; k <= 60; k++) tp.push(ringPoint(R.b, R.r, th - Math.sign(R.speed) * k * 0.012 * Math.min(1, Math.max(0, t - 17.2) * 2)));
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

function drawPeopleOn(ctx, t) { drawPeople(ctx, t, A.people); }

// hero satellite: rises from the bottom, then flies into orbit (shares the globe camera)
function heroOffsetY(t) { const e = E.outCubic(prog(t, 14.3, 16.3)); return lerp(-1.25, 0, e) + Math.sin(t * 1.7) * 0.015; }
function heroScreenY(t) { return CY - (heroOffsetY(t) / (2.2 * Math.tan(THREE.MathUtils.degToRad(15)))) * CY; }
function heroSat(t) {
  const on = t >= 14.3 && t < 17.45;
  S.hero.visible = on;
  if (!on) return;
  const c = camPath(t), d = globeDistance(c.Z, c.lat);
  cam.position.copy(latLonToVec(c.lat, c.lon, d)); cam.up.set(0, 1, 0); cam.lookAt(0, 0, 0); cam.updateMatrixWorld();
  const near = cam.localToWorld(new THREE.Vector3(0, heroOffsetY(t), -2.2));
  const R = G.rings[0], th = R.th0 + R.speed * (t - 17.4), orbitP = ringPoint(R.b, R.r, th);
  const pB = E.inOutCubic(prog(t, 16.3, 17.4));
  S.hero.position.copy(near.lerp(orbitP, pB));
  S.hero.scale.setScalar(lerp(0.62, 0.014, E.inOutSine(pB)));
  S.hero.quaternion.copy(cam.quaternion);
  S.hero.rotateY(0.6 + t * 0.55); S.hero.rotateX(-0.35 + Math.sin(t * 0.8) * 0.1); S.hero.rotateZ(0.25);
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

// ------------------------------------------------------------------ boot
async function boot() {
  A = await loadAll();
  LAND = feature(A.land, A.land.objects.land); GRAT = geoGraticule10();
  WEEKLY = A.weekly;
  BOARD = makeBoard(); SPACE = makeSpace(); GRAIN = makeGrain(); grainPat = stx.createPattern(GRAIN, 'repeat');
  prepMap(A);
  await buildGlobe(A); await buildSats();
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
