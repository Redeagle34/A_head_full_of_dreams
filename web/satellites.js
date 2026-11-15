/* Satellites on the globe.

   Zoom out and the fire-watching satellites appear in orbit, drawn with NASA's
   own 3D models. Pick one: the others step aside, two lines run from it to the
   edges of the strip of ground it is scanning, the strip it covered in the last
   ten minutes is shaded, and a card shows the picture it takes of that ground.

   Sections
     1. Catalogue          which satellites, their instruments and pictures
     2. Orbit maths        position now, edges of the scanned strip, overpasses
     3. 3D layer           models, orbit lines and scan lines on the MapLibre globe
     4. Card               what it sees, the satellite, its numbers, next passes
     5. Picture            NASA Worldview snapshot of the ground under the satellite

   Data
     Orbits    CelesTrak two-line elements via /api/tle (fallback data/tle.json),
               turned into positions with SGP4 (satellite.js).
     Models    NASA 3D Resources (github.com/nasa/NASA-3D-Resources), in models/.
     Pictures  NASA Worldview Snapshots (wvs.earthdata.nasa.gov), no key.
*/
const Satellites = (() => {

// ---------- 1. Catalogue ----------

const CATALOG = [
  { key: "terra", name: "Terra", instrument: "MODIS", swathKm: 2330, color: "#ffb02e", model: "models/terra.glb",
    image: "MODIS_Terra_CorrectedReflectance_TrueColor", fires: "MODIS_Terra_Thermal_Anomalies_All", lookBack: 2, pixel: "250 m",
    note: "Built for a 10:30 morning pass; its orbit has been drifting earlier since 2020. Flying since 1999." },
  { key: "aqua", name: "Aqua", instrument: "MODIS", swathKm: 2330, color: "#4fc3f7", model: "models/aqua.glb",
    image: "MODIS_Aqua_CorrectedReflectance_TrueColor", fires: "MODIS_Aqua_Thermal_Anomalies_All", lookBack: 2, pixel: "250 m",
    note: "Built for a 13:30 afternoon pass; its orbit has been drifting later since 2022. Flying since 2002." },
  { key: "suomi-npp", name: "Suomi NPP", instrument: "VIIRS", swathKm: 3060, color: "#c79bff", model: "models/suomi-npp.glb",
    image: "VIIRS_SNPP_CorrectedReflectance_TrueColor", fires: "VIIRS_SNPP_Thermal_Anomalies_375m_All", lookBack: 2, pixel: "375 m",
    note: "Afternoon pass, about 13:30 local time. Flying since 2011." },
  { key: "noaa-20", name: "NOAA-20", instrument: "VIIRS", swathKm: 3060, color: "#69f0ae", model: "models/suomi-npp.glb",
    image: "VIIRS_NOAA20_CorrectedReflectance_TrueColor", fires: "VIIRS_NOAA20_Thermal_Anomalies_375m_All", lookBack: 2, pixel: "375 m",
    note: "Same orbit as Suomi NPP, half an orbit apart. Flying since 2017. Drawn with the Suomi NPP model: NASA publishes none for NOAA-20." },
  { key: "noaa-21", name: "NOAA-21", instrument: "VIIRS", swathKm: 3060, color: "#ff8a80", model: "models/suomi-npp.glb",
    image: "VIIRS_NOAA21_CorrectedReflectance_TrueColor", fires: "VIIRS_NOAA21_Thermal_Anomalies_375m_All", lookBack: 2, pixel: "375 m",
    note: "Flying since 2022. Drawn with the Suomi NPP model: NASA publishes none for NOAA-21." },
  { key: "landsat-8", name: "Landsat 8", instrument: "OLI / TIRS", swathKm: 185, color: "#fff59d", model: "models/landsat-8.glb",
    image: "HLS_L30_Nadir_BRDF_Adjusted_Reflectance", fires: null, lookBack: 24, pixel: "30 m",
    note: "Sharp 30 m pictures of a narrow strip; returns to the same place every 16 days (8 with its twin, Landsat 9). Flying since 2013." },
];

const SHOW_BELOW_ZOOM = 4.2;      // satellites appear when the map is zoomed out past this
const MODEL_PIXELS = 78;          // size of a model on screen, always the same
const RECENT_MINUTES = 10;        // the shaded strip covers this much flying time
const PASS_HOURS = 24;
const SNAPSHOT = "https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&CRS=EPSG:4326&FORMAT=image/jpeg";
const PLACE_NAMES = "Coastlines_15m,Reference_Features_15m,Reference_Labels_15m";

// ---------- 2. Orbit maths ----------

const RAD = Math.PI / 180, EARTH_KM = 6371;
const clampNum = (v, a, b) => Math.min(b, Math.max(a, v));

function positionAt(satrec, date) {
  const pv = satellite.propagate(satrec, date);
  if (!pv.position) return null;
  const g = satellite.eciToGeodetic(pv.position, satellite.gstime(date));
  return { lat: satellite.degreesLat(g.latitude), lon: satellite.degreesLong(g.longitude), altKm: g.height,
           speed: Math.hypot(pv.velocity.x, pv.velocity.y, pv.velocity.z) };
}

function distanceKm(a, b) {
  const s = Math.sin((b.lat - a.lat) * RAD / 2) ** 2 +
            Math.cos(a.lat * RAD) * Math.cos(b.lat * RAD) * Math.sin((b.lon - a.lon) * RAD / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(s)));
}

function bearing(a, b) {
  const y = Math.sin((b.lon - a.lon) * RAD) * Math.cos(b.lat * RAD);
  const x = Math.cos(a.lat * RAD) * Math.sin(b.lat * RAD) -
            Math.sin(a.lat * RAD) * Math.cos(b.lat * RAD) * Math.cos((b.lon - a.lon) * RAD);
  return Math.atan2(y, x) / RAD;
}

function destination(p, bearingDeg, km) {
  const d = km / EARTH_KM, t = bearingDeg * RAD, la = p.lat * RAD;
  const lat = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(t));
  const lon = p.lon * RAD + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(lat));
  return { lat: lat / RAD, lon: ((lon / RAD + 540) % 360) - 180 };
}

/* The two ends of the scan line under the satellite at `date`. */
function scanEdges(sat, date) {
  const here = positionAt(sat.satrec, date), next = positionAt(sat.satrec, new Date(+date + 10000));
  if (!here || !next) return null;
  const heading = bearing(here, next);
  return { here, heading, left: destination(here, heading - 90, sat.swathKm / 2),
           right: destination(here, heading + 90, sat.swathKm / 2) };
}

/* Angle between straight down and the edge of the scanned strip, seen from the satellite. */
function viewAngle(sat, altKm) {
  const ground = sat.swathKm / 2 / EARTH_KM;                 // angle at the Earth's centre
  return Math.atan(Math.sin(ground) / ((EARTH_KM + altKm) / EARTH_KM - Math.cos(ground))) / RAD;
}

/* Height of the sun above the horizon, degrees (good to a fraction of a degree). */
function sunElevation(p, date) {
  const d = (date - Date.UTC(2000, 0, 1, 12)) / 864e5;
  const g = (357.529 + 0.98560028 * d) * RAD;
  const L = (280.459 + 0.98564736 * d + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * RAD;
  const e = (23.439 - 0.00000036 * d) * RAD;
  const dec = Math.asin(Math.sin(e) * Math.sin(L)), ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24;
  const ha = (gmst * 15 + p.lon) * RAD - ra;
  return Math.asin(Math.sin(p.lat * RAD) * Math.sin(dec) + Math.cos(p.lat * RAD) * Math.cos(dec) * Math.cos(ha)) / RAD;
}

/* Times in the next PASS_HOURS when a satellite's scanned strip covers a place. */
function passesOver(place, from, only) {
  const stepMs = 20000, steps = PASS_HOURS * 3600000 / stepMs, out = [];
  for (const sat of only ? [only] : sats) {
    let before = Infinity, last = Infinity, lastTime = null;
    for (let i = 0; i <= steps; i++) {
      const t = new Date(+from + i * stepMs), p = positionAt(sat.satrec, t);
      if (!p) continue;
      const d = distanceKm(p, place);
      if (last < before && last <= d && last < sat.swathKm / 2)
        out.push({ sat, time: lastTime, offKm: last, daylight: sunElevation(place, lastTime) > 0 });
      before = last; last = d; lastTime = t;
    }
  }
  return out.sort((a, b) => a.time - b.time);
}

// ---------- 3. 3D layer ----------

let map, sats = [], selected = null, enabled = true, panelOpen = false;
let scene, camera, renderer, scanLines, scanFan, lastSwath = 0, lastOrbit = 0, repaintTimer = null;
const REPAINT_MS = 250;           // satellites move about a pixel a second here: 4 redraws a second are enough
// Every model is shown from the same three-quarter angle, whatever the globe is doing.
const POSE = new THREE.Matrix4().makeRotationX(0.5).multiply(new THREE.Matrix4().makeRotationY(-0.65));

const lngLat = p => new maplibregl.LngLat(p.lon, p.lat);
function world(p, altM) {                       // a point above the ground, in the globe's own coordinates
  const m = map.transform.getMatrixForModel(lngLat(p), altM);
  return new THREE.Vector3(m[12], m[13], m[14]);
}

function placeholder(color) {                   // shown until the NASA model has loaded
  const g = new THREE.Group(), m = new THREE.MeshLambertMaterial({ color });
  g.add(new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.3, 0.3), m));
  const wing = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.02, 1), new THREE.MeshLambertMaterial({ color: 0x27408b }));
  wing.scale.set(8, 1, 1); g.add(wing);
  return g;
}

let loader = null, models = {};
function gltfLoader() {                         // NASA's files are Draco-compressed
  if (!loader) {
    const draco = new THREE.DRACOLoader();
    draco.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/libs/draco/gltf/");
    loader = new THREE.GLTFLoader(); loader.setDRACOLoader(draco);
  }
  return loader;
}

function loadModel(sat) {
  // One download and one Draco decode per file: NOAA-20 and NOAA-21 share the Suomi NPP model.
  models[sat.model] ??= new Promise((ok, fail) => gltfLoader().load(sat.model, ok, undefined, fail));
  models[sat.model].then(gltf => {
    const scene = gltf.scene.clone();
    const box = new THREE.Box3().setFromObject(scene), size = box.getSize(new THREE.Vector3());
    const inner = new THREE.Group();
    scene.position.copy(box.getCenter(new THREE.Vector3())).multiplyScalar(-1);
    inner.add(scene);
    inner.scale.setScalar(1 / Math.max(size.x, size.y, size.z));     // longest side = 1 unit
    inner.traverse(o => { o.frustumCulled = false; });
    sat.group.clear(); sat.group.add(inner); sat.modelRoot = inner;
    if (sat === selected) showModel(sat);
    map.triggerRepaint();
  }, () => { /* keep the placeholder */ });
}

function makeLine(color, points, opacity) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(points * 3), 3));
  const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  line.frustumCulled = false;
  return line;
}

const layer = {
  id: "satellites-3d", type: "custom", renderingMode: "3d",

  onAdd(m, gl) {
    scene = new THREE.Scene();
    camera = new THREE.Camera();
    scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.3); sun.position.set(1, 0.6, 0.8); scene.add(sun);
    renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
    renderer.autoClear = false;
    renderer.outputEncoding = THREE.sRGBEncoding;
    for (const sat of sats) {
      sat.group = new THREE.Group(); sat.group.matrixAutoUpdate = false; sat.group.add(placeholder(sat.color));
      sat.track = makeLine(sat.color, 121, 0.75); sat.trackPoints = [];
      scene.add(sat.group, sat.track);
      loadModel(sat);
    }
    const geo = makeLine("#ffffff", 3, 1).geometry;                         // satellite, left edge, right edge
    geo.setIndex([0, 1, 0, 2, 1, 2]);
    scanLines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: "#ffffff" }));
    scanLines.frustumCulled = false;
    const fanGeo = new THREE.BufferGeometry();
    fanGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3));
    scanFan = new THREE.Mesh(fanGeo, new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.16,
                                                                    side: THREE.DoubleSide, depthWrite: false }));
    scanFan.frustumCulled = false;
    scene.add(scanLines, scanFan);
  },

  render(gl, args) {
    const show = enabled && map.getZoom() < SHOW_BELOW_ZOOM;
    for (const sat of sats) { sat.label.hidden = true; sat.screen = null; }
    scanLines.visible = scanFan.visible = false;
    if (!show) return;

    const main = new THREE.Matrix4().fromArray(args.defaultProjectionData.mainMatrix);
    const inverse = main.clone().invert();
    camera.projectionMatrix.copy(main); camera.projectionMatrixInverse.copy(inverse);
    const canvas = map.getCanvas(), W = canvas.clientWidth, H = canvas.clientHeight;
    const clip = v => new THREE.Vector4(v.x, v.y, v.z, 1).applyMatrix4(main);
    const back = (x, y, z) => new THREE.Vector3(x, y, z).applyMatrix4(inverse);
    // The eye, found as the point where two lines of sight cross; and the globe as a sphere.
    const sight = (x, y) => [back(x, y, -1), back(x, y, 1)];
    const eye = crossing(sight(-0.5, 0.1), sight(0.5, -0.1));
    const c = map.getCenter(), g0 = world({ lat: c.lat, lon: c.lng }, 0), g1 = world({ lat: -c.lat, lon: c.lng + 180 }, 0);
    const centre = g0.clone().add(g1).multiplyScalar(0.5), radius = g0.distanceTo(g1) / 2;
    const hidden = p => blocked(eye, p, centre, radius * 0.998);

    const now = new Date(), refreshOrbit = now - lastOrbit > 15000;
    if (refreshOrbit) lastOrbit = +now;
    for (const sat of sats) {
      const here = positionAt(sat.satrec, now);
      const alone = selected && sat !== selected;              // a picked satellite is shown alone
      if (!here || alone) { sat.group.visible = sat.track.visible = false; continue; }
      sat.here = here;
      const P = world(here, here.altKm * 1000), q = clip(P);
      const visible = q.w > 0 && !hidden(P);
      sat.group.visible = visible;
      if (visible) {
        // Face the screen: build the model's axes from the screen's own right and up directions,
        // so size and angle never change with the globe.
        const nx = q.x / q.w, ny = q.y / q.w, nz = q.z / q.w, o = back(nx, ny, nz);
        const right = back(nx + 0.02, ny, nz).sub(o), unitsPerPixel = right.length() / (0.01 * W);
        right.normalize();
        const up = back(nx, ny + 0.02, nz).sub(o);
        up.addScaledVector(right, -up.dot(right)).normalize();
        const toEye = new THREE.Vector3().crossVectors(right, up);
        const scale = MODEL_PIXELS * unitsPerPixel * (sat === selected ? 1.3 : 1);
        sat.group.matrix.makeBasis(right, up, toEye).multiply(POSE)
           .scale(new THREE.Vector3(scale, scale, scale)).setPosition(P);
        sat.screen = { x: (nx * 0.5 + 0.5) * W, y: (0.5 - ny * 0.5) * H };
        sat.label.hidden = false;
        sat.label.style.transform = `translate(${Math.round(sat.screen.x + 16)}px, ${Math.round(sat.screen.y - 34)}px)`;
      }
      // Orbit line: the whole next orbit for the picked satellite, a short tail for the others.
      if (refreshOrbit || sat.trackFor !== (sat === selected)) {
        sat.trackFor = sat === selected;
        const [from, to] = sat.trackFor ? [-20, 100] : [-12, 6];
        sat.trackPoints = [];
        for (let i = 0; i <= 120; i++) {
          const p = positionAt(sat.satrec, new Date(+now + (from + (to - from) * i / 120) * 60000));
          if (p) sat.trackPoints.push(p);
        }
      }
      const pos = sat.track.geometry.attributes.position;
      sat.trackPoints.forEach((p, i) => { const v = world(p, p.altKm * 1000); pos.setXYZ(i, v.x, v.y, v.z); });
      sat.track.geometry.setDrawRange(0, sat.trackPoints.length);
      pos.needsUpdate = true; sat.track.visible = true;
      sat.track.material.opacity = sat === selected ? 0.95 : 0.5;

      if (sat === selected) {
        const e = scanEdges(sat, now);
        const L = world(e.left, 0), R = world(e.right, 0);
        for (const obj of [scanLines, scanFan]) {
          const a = obj.geometry.attributes.position;
          a.setXYZ(0, P.x, P.y, P.z); a.setXYZ(1, L.x, L.y, L.z); a.setXYZ(2, R.x, R.y, R.z);
          a.needsUpdate = true; obj.material.color.set(sat.color); obj.visible = true;
        }
      }
    }
    if (selected && now - lastSwath > 2000) { lastSwath = +now; drawRecentStrip(now); updateFacts(now); }
    renderer.resetState();
    renderer.render(scene, camera);
    // Keep moving, but not at the screen's frame rate: each repaint redraws the whole map.
    clearTimeout(repaintTimer);
    repaintTimer = setTimeout(() => map.triggerRepaint(), REPAINT_MS);
  },
};

/* Point closest to two lines, each given as [point, point]. */
function crossing([a0, a1], [b0, b1]) {
  const u = a1.clone().sub(a0), v = b1.clone().sub(b0), w = a0.clone().sub(b0);
  const a = u.dot(u), b = u.dot(v), c = v.dot(v), d = u.dot(w), e = v.dot(w), den = a * c - b * b || 1e-30;
  const s = (b * e - c * d) / den, t = (a * e - b * d) / den;
  return a0.clone().addScaledVector(u, s).add(b0.clone().addScaledVector(v, t)).multiplyScalar(0.5);
}

/* Does the globe stand between the eye and a point? */
function blocked(eye, p, centre, radius) {
  const d = p.clone().sub(eye), len = d.length(); d.divideScalar(len);
  const t = centre.clone().sub(eye).dot(d);
  if (t <= 0 || t >= len) return false;
  return eye.clone().addScaledVector(d, t).distanceTo(centre) < radius;
}

/* Ground covered in the last RECENT_MINUTES, as a polygon draped on the map. */
function drawRecentStrip(now) {
  const left = [], right = [];
  for (let s = -RECENT_MINUTES * 60; s <= 0; s += 30) {
    const e = scanEdges(selected, new Date(+now + s * 1000));
    if (e) { left.push([e.left.lon, e.left.lat]); right.push([e.right.lon, e.right.lat]); }
  }
  const ring = [...left, ...right.reverse()]; ring.push(ring[0]);
  for (let i = 1; i < ring.length; i++) {         // no jumps across the date line
    while (ring[i][0] - ring[i - 1][0] > 180) ring[i][0] -= 360;
    while (ring[i][0] - ring[i - 1][0] < -180) ring[i][0] += 360;
  }
  map.getSource("sat-strip")?.setData({ type: "Feature", properties: { color: selected.color },
                                         geometry: { type: "Polygon", coordinates: [ring] } });
}

// ---------- 4. Card ----------

const el = id => document.getElementById(id);
const fmtTime = d => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const fmtDay = s => new Date(s + "T00:00:00Z").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const fmtPlace = p => `${Math.abs(p.lat).toFixed(1)}° ${p.lat >= 0 ? "N" : "S"}, ${Math.abs(p.lon).toFixed(1)}° ${p.lon >= 0 ? "E" : "W"}`;
const fmtKm = v => Math.round(v).toLocaleString();
function fmtIn(ms) { const m = Math.round(ms / 60000); return m < 60 ? `in ${m} min` : `in ${Math.floor(m / 60)} h ${m % 60} min`; }

function buildPanel() {
  const panel = document.createElement("aside");
  panel.id = "satPanel"; panel.className = "sat-panel glass"; panel.hidden = true;
  panel.innerHTML = `
    <div id="satHome">
      <div class="panel-head"><div><div class="eyebrow">In orbit now</div><h2>Satellites</h2></div>
        <button id="satClose" type="button" aria-label="Close satellites">Close</button></div>
      <p class="hint" id="satHint"></p>
      <div id="satList" class="sat-list"></div>
      <h3>Next passes over the centre of the screen</h3>
      <p class="hint" id="satPassPlace"></p>
      <div id="satPasses" class="sat-passes"></div>
    </div>
    <div id="satCard" hidden>
      <div class="sat-hero">
        <button id="satImage" type="button" class="sat-image" aria-label="Enlarge the picture"></button>
        <button id="satBack" type="button" class="sat-back">← All satellites</button>
        <button id="satEnlarge" type="button" class="sat-enlarge">Enlarge</button>
      </div>
      <div class="sat-what"><div class="eyebrow">What it is looking at</div><b id="satViewTitle"></b>
        <p class="hint" id="satCaption"></p></div>
      <div class="sat-id">
        <canvas id="satModel" width="220" height="150" aria-label="3D model of the satellite"></canvas>
        <div><h2 id="satName"></h2><p class="hint" id="satSub"></p></div>
      </div>
      <dl class="sat-facts" id="satFacts"></dl>
      <p class="hint" id="satNote"></p>
      <h3>Its next passes over the centre of the screen</h3>
      <div id="satPassesOne" class="sat-passes"></div>
    </div>`;
  document.body.appendChild(panel);
  const box = document.createElement("div");
  box.id = "satLightbox"; box.className = "lightbox"; box.hidden = true;
  box.innerHTML = `<div class="lightbox-inner glass"><div class="panel-head"><div><div class="eyebrow">What it is looking at</div>
    <h2 id="satBigTitle"></h2></div><button id="satBigClose" type="button">Close</button></div>
    <div id="satBigHolder" class="lightbox-picture"></div><p class="hint" id="satBigCaption"></p></div>`;
  document.body.appendChild(box);
  box.addEventListener("click", e => { if (e.target === box) box.hidden = true; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") box.hidden = true; });
  el("satBigClose").onclick = () => { box.hidden = true; };
  el("satClose").onclick = () => toggle(false);
  el("satBack").onclick = () => select(null);
  el("satImage").onclick = el("satEnlarge").onclick = enlarge;
  for (const sat of sats) {
    const b = document.createElement("button");
    b.type = "button"; b.innerHTML = `<i style="background:${sat.color}"></i>${sat.name}<small>${sat.instrument}</small>`;
    b.onclick = () => select(sat);
    el("satList").appendChild(b);
    sat.label = document.createElement("button");
    sat.label.type = "button"; sat.label.className = "sat-label"; sat.label.hidden = true;
    sat.label.textContent = sat.name; sat.label.style.borderColor = sat.color;
    sat.label.onclick = () => { toggle(true); select(sat); };
    document.body.appendChild(sat.label);
  }
}

function toggle(open) {
  panelOpen = open ?? !panelOpen;
  el("satPanel").hidden = !panelOpen;
  el("satBtn")?.setAttribute("aria-expanded", panelOpen);
  if (panelOpen) {
    window.fireView?.toggle(false);
    if (map.getZoom() >= SHOW_BELOW_ZOOM) map.flyTo({ zoom: 1.7, duration: 1800 });
    updateHint(); updatePasses();
  } else if (selected) select(null);
}

function updateHint() {
  el("satHint").textContent = map.getZoom() < SHOW_BELOW_ZOOM
    ? "Pick a satellite, here or on the globe, to see the strip of ground it is scanning right now."
    : "Zoom out to see the satellites in orbit.";
}

function select(sat) {
  selected = sat;
  el("satHome").hidden = !!sat; el("satCard").hidden = !sat;
  el("satPanel").scrollTop = 0;
  map.getSource("sat-strip")?.setData({ type: "FeatureCollection", features: [] });
  lastSwath = 0; picture = null;
  if (sat) {
    el("satName").textContent = sat.name;
    el("satSub").textContent = `${sat.instrument} instrument · sharpest detail ${sat.pixel}`;
    el("satNote").textContent = sat.note;
    showModel(sat);
    loadPicture(sat);
  } else stopModel();
  updatePasses();
  map.triggerRepaint();
}

function updateFacts(now) {
  const p = selected.here; if (!p) return;
  const sun = sunElevation(p, now), solar = new Date(+now + p.lon / 15 * 3600000);
  const angle = viewAngle(selected, p.altKm);
  const groundSpeed = p.speed * EARTH_KM / (EARTH_KM + p.altKm);
  el("satFacts").innerHTML = [
    ["Location", `over ${fmtPlace(p)}`],
    ["There it is", `${String(solar.getUTCHours()).padStart(2, "0")}:${String(solar.getUTCMinutes()).padStart(2, "0")} solar time, ${sun > 0 ? "daylight" : "night"}`],
    ["Height", `${fmtKm(p.altKm)} km`],
    ["Speed", `${p.speed.toFixed(1)} km/s (${fmtKm(p.speed * 3600)} km/h)`],
    ["Viewing angle", `${angle.toFixed(1)}° to each side of straight down (${(2 * angle).toFixed(0)}° in all)`],
    ["Strip it sees", `${fmtKm(selected.swathKm)} km wide, edge to edge`],
    ["Area seen", `${fmtKm(selected.swathKm * groundSpeed * 60)} km² every minute; ` +
                  `${fmtKm(selected.swathKm * groundSpeed * 60 * RECENT_MINUTES)} km² in the last ${RECENT_MINUTES} minutes (shaded on the globe)`],
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  if (picture && !picture.loading && distanceKm(picture.centre, p) > Math.max(400, selected.swathKm / 3)) loadPicture(selected);
}

/* The satellite itself, turning slowly, in the card. */
let viewer = null;
function showModel(sat) {
  if (!viewer) {
    const r = new THREE.WebGLRenderer({ canvas: el("satModel"), alpha: true, antialias: true });
    r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); r.setSize(220, 150, false);
    r.outputEncoding = THREE.sRGBEncoding;
    const s = new THREE.Scene(), cam = new THREE.PerspectiveCamera(32, 220 / 150, 0.1, 10);
    cam.position.set(0, 0.3, 1.75); cam.lookAt(0, 0, 0);
    s.add(new THREE.AmbientLight(0xffffff, 1.1));
    const light = new THREE.DirectionalLight(0xffffff, 1.4); light.position.set(1, 1, 1.2); s.add(light);
    viewer = { r, s, cam, holder: new THREE.Group(), frame: 0 };
    s.add(viewer.holder);
  }
  viewer.holder.clear();
  viewer.holder.add(sat.modelRoot ? sat.modelRoot.clone() : placeholder(sat.color));
  cancelAnimationFrame(viewer.frame);
  const spin = () => {
    viewer.holder.rotation.y += 0.008;
    viewer.r.render(viewer.s, viewer.cam);
    viewer.frame = requestAnimationFrame(spin);
  };
  spin();
}
function stopModel() { if (viewer) cancelAnimationFrame(viewer.frame); }

let passTimer = null;
function updatePasses() {
  if (!panelOpen) return;
  clearTimeout(passTimer);
  passTimer = setTimeout(() => {
    const c = map.getCenter(), place = { lat: c.lat, lon: c.lng }, now = new Date();
    const box = el(selected ? "satPassesOne" : "satPasses");
    el("satPassPlace").textContent = `${fmtPlace(place)}, next ${PASS_HOURS} hours. Times are in your clock.`;
    const rows = passesOver(place, now, selected).slice(0, selected ? 6 : 14);
    box.innerHTML = "";
    for (const r of rows) {
      const b = document.createElement("button"); b.type = "button";
      b.innerHTML = `<i style="background:${r.sat.color}"></i><span><b>${fmtTime(r.time)}</b> ${selected ? fmtIn(r.time - now) : r.sat.name}` +
        `<small>${selected ? "" : fmtIn(r.time - now) + " · "}${r.daylight ? "daylight" : "night"} · ${fmtKm(r.offKm)} km from the centre of its strip</small></span>`;
      if (!selected) b.onclick = () => select(r.sat);
      box.appendChild(b);
    }
    if (!rows.length) box.textContent = `No pass over ${fmtPlace(place)} in the next ${PASS_HOURS} hours.`;
  }, 250);
}

// ---------- 5. Picture ----------

let picture = null;      // { sat, centre, loading, day, title, caption, url(width) }

function pictureArea(sat, p) {
  // A box as wide as the scanned strip, centred under the satellite.
  const halfKm = Math.max(sat.swathKm / 2, 60), tallKm = sat.swathKm > 500 ? halfKm * 0.72 : halfKm;
  const cos = Math.max(0.15, Math.cos(p.lat * RAD));
  const lat0 = Math.max(-89.5, p.lat - tallKm / 111), lat1 = Math.min(89.5, p.lat + tallKm / 111);
  const halfLon = Math.min(70, halfKm / 111 / cos);
  const lon0 = Math.max(-180, p.lon - halfLon), lon1 = Math.min(180, p.lon + halfLon);
  return { bbox: [lat0, lon0, lat1, lon1].map(v => v.toFixed(3)).join(","),
           ratio: (lat1 - lat0) / ((lon1 - lon0) * cos),
           widthKm: (lon1 - lon0) * 111 * cos, heightKm: (lat1 - lat0) * 111 };
}

/* Share of a picture that is not black, that is, that the satellite actually saw. */
async function coverage(url) {
  try {
    const bitmap = await createImageBitmap(await (await fetch(url)).blob());
    const c = document.createElement("canvas"); c.width = c.height = 32;
    const g = c.getContext("2d"); g.drawImage(bitmap, 0, 0, 32, 32);
    const d = g.getImageData(0, 0, 32, 32).data;
    let lit = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 45) lit++;
    return lit / 1024;
  } catch (e) { return 0; }
}

async function loadPicture(sat) {
  const img = el("satImage"), cap = el("satCaption"), title = el("satViewTitle");
  const p = positionAt(sat.satrec, new Date()); if (!p) return;
  const area = pictureArea(sat, p), night = sunElevation(p, new Date()) <= 0;
  picture = { sat, centre: p, loading: true };
  title.textContent = `Ground under ${sat.name}: ${fmtKm(area.widthKm)} × ${fmtKm(area.heightKm)} km around ${fmtPlace(p)}`;
  cap.textContent = "Looking for its latest picture of this ground…";
  // Which is the latest day with a picture here? Small test pictures, all days at once.
  const days = Array.from({ length: sat.lookBack + 1 }, (_, i) => new Date(Date.now() - i * 864e5).toISOString().slice(0, 10));
  const probe = day => `${SNAPSHOT}&TIME=${day}&BBOX=${area.bbox}&LAYERS=${sat.image}&WIDTH=160&HEIGHT=${Math.round(clampNum(160 * area.ratio, 60, 240))}`;
  const seen = await Promise.all(days.map(d => coverage(probe(d))));
  if (sat !== selected) return;
  const hit = seen.findIndex(share => share > 0.08);
  if (hit < 0) return contextPicture(sat, p);
  const day = days[hit], layers = [sat.image, sat.fires, PLACE_NAMES].filter(Boolean).join(",");
  const url = width => `${SNAPSHOT}&TIME=${day}&BBOX=${area.bbox}&LAYERS=${layers}&WIDTH=${width}&HEIGHT=${Math.round(width * clampNum(area.ratio, 0.35, 1.4))}`;
  const kind = sat.swathKm < 500 ? "Natural-color picture from Landsat 8 and 9 (30 m detail)" : `Natural-color picture taken by ${sat.name}`;
  const when = hit === 0 ? `today, ${fmtDay(day)}` : `${fmtDay(day)}, ${hit === 1 ? "yesterday" : hit + " days ago"}`;
  picture = { sat, centre: p, loading: false, day, url, title: title.textContent,
    caption: `${kind} on ${when} (UTC), its most recent ${sat.swathKm < 500 ? "" : "daytime "}pass with data here. ` +
      (night ? `It is night under ${sat.name} right now, so this is how the same ground looked in its last daylight pass. ` : "") +
      (sat.fires ? "Red dots: fires it detected that day. " : "") +
      "Black: outside what it saw that day. Coastlines, borders and place names are added so you can tell where it is." };
  img.classList.remove("empty"); el("satEnlarge").hidden = false;
  img.style.aspectRatio = `1 / ${clampNum(area.ratio, 0.35, 1.4)}`;
  img.style.backgroundImage = `url("${url(720)}")`;
  cap.textContent = picture.caption + " Click the picture to enlarge it.";
}

/* No picture of its own here (Landsat away from its recent strips): show the same ground
   as seen by a satellite that covers the whole Earth every day, and say so. */
async function contextPicture(sat, p) {
  const img = el("satImage"), cap = el("satCaption"), title = el("satViewTitle");
  const helper = CATALOG.find(s => s.key === "noaa-20"), wide = { ...sat, swathKm: Math.max(sat.swathKm, 900) };
  const area = pictureArea(wide, p);
  const days = [0, 1, 2].map(i => new Date(Date.now() - i * 864e5).toISOString().slice(0, 10));
  const probe = day => `${SNAPSHOT}&TIME=${day}&BBOX=${area.bbox}&LAYERS=${helper.image}&WIDTH=160&HEIGHT=${Math.round(clampNum(160 * area.ratio, 60, 240))}`;
  const seen = await Promise.all(days.map(d => coverage(probe(d))));
  if (sat !== selected) return;
  const hit = seen.findIndex(share => share > 0.08);
  const why = `${sat.name} has published no picture of its own here in the last ${sat.lookBack} days` +
    (sat.swathKm < 500 ? ": it photographs a narrow strip, in daylight only, and returns every 16 days." : ".");
  if (hit < 0) {
    img.style.backgroundImage = ""; img.classList.add("empty"); el("satEnlarge").hidden = true;
    cap.textContent = why;
    picture = { sat, centre: p, loading: false };
    return;
  }
  const day = days[hit];
  const url = width => `${SNAPSHOT}&TIME=${day}&BBOX=${area.bbox}&LAYERS=${helper.image},${helper.fires},${PLACE_NAMES}&WIDTH=${width}&HEIGHT=${Math.round(width * clampNum(area.ratio, 0.35, 1.4))}`;
  title.textContent = `Ground under ${sat.name}: ${fmtKm(area.widthKm)} × ${fmtKm(area.heightKm)} km around ${fmtPlace(p)}, seen by ${helper.name}`;
  picture = { sat, centre: p, loading: false, day, url, title: title.textContent,
    caption: `${why} This wider picture of the same ground was taken by ${helper.name} on ${fmtDay(day)} (UTC); ` +
      `${sat.name} sees only the middle ${fmtKm(sat.swathKm)} km of it, in much sharper detail. Red dots: fires ${helper.name} detected.` };
  img.classList.remove("empty"); el("satEnlarge").hidden = false;
  img.style.aspectRatio = `1 / ${clampNum(area.ratio, 0.35, 1.4)}`;
  img.style.backgroundImage = `url("${url(720)}")`;
  cap.textContent = picture.caption + " Click the picture to enlarge it.";
}

function enlarge() {
  if (!picture || !picture.url) return;
  const holder = el("satBigHolder"), big = new Image();
  big.alt = picture.title; big.src = picture.url(1600);
  holder.innerHTML = ""; holder.appendChild(big);
  el("satBigTitle").textContent = picture.title;
  el("satBigCaption").textContent = picture.caption + " Source: NASA Worldview.";
  el("satLightbox").hidden = false;
}

async function attach(theMap) {
  map = theMap;
  let data;
  try { data = await (await fetch("/api/tle")).json(); if (!Object.keys(data.satellites).length) throw 0; }
  catch (e) { data = await (await fetch("data/tle.json")).json(); }
  sats = CATALOG.filter(s => data.satellites[s.key]).map(s => {
    const t = data.satellites[s.key];
    return { ...s, satrec: satellite.twoline2satrec(t.line1, t.line2) };
  });
  buildPanel();
  map.addSource("sat-strip", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: "sat-strip", type: "fill", source: "sat-strip",
                 paint: { "fill-color": ["get", "color"], "fill-opacity": 0.22 } });
  map.addLayer({ id: "sat-strip-edge", type: "line", source: "sat-strip",
                 paint: { "line-color": ["get", "color"], "line-width": 1.5 } });
  map.addLayer(layer);
  map.on("click", e => {                          // a click on a model picks that satellite
    const hit = sats.filter(s => s.screen).map(s => ({ s, d: Math.hypot(s.screen.x - e.point.x, s.screen.y - e.point.y) }))
                    .sort((a, b) => a.d - b.d)[0];
    if (hit && hit.d < MODEL_PIXELS * 0.6 && hit.s !== selected) { toggle(true); select(hit.s); }
  });
  map.on("zoom", updateHint);
  map.on("moveend", updatePasses);
  el("satBtn")?.addEventListener("click", () => toggle());
  if (data.fetched) el("satHint").title = `Orbit data: ${data.source}, ${data.fetched}`;
  // For tests and the console.
  return { sats, select, toggle, passesOver, get picture() { return picture; } };
}

return { attach, CATALOG };
})();
