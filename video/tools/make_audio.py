"""Synthesize the music bed and sound effects for the video, timed to its events (no samples, royalty-free).

Writes audio/music.wav and audio/sfx.wav (48 kHz stereo, 30 s). Event times are written on the film's 'story'
clock and converted to video time with the same REMAP as main.js (keep the two in sync).
Run: python video/tools/make_audio.py
"""
import pathlib

import numpy as np
from scipy import signal

SR = 48000
DUR = 30.0
N = int(SR * DUR)
OUT = pathlib.Path(__file__).resolve().parents[1] / "audio"
rng = np.random.default_rng(7)

# --- same remap as main.js: [video, story]
REMAP = [[0, 0], [3.19, 4.0], [4.46, 6.0], [6.29, 8.0], [7.5, 9.6], [8.6, 11.0], [9.95, 12.6], [11.1, 13.7],
         [13.6, 18.0], [15.0, 19.9], [18.7, 22.8], [21.0, 25.8], [23.75, 29.15], [25.25, 31.95], [27.4, 34.45], [30, 37.8]]


def vt(story):
    """story time -> video time"""
    for (v0, s0), (v1, s1) in zip(REMAP, REMAP[1:]):
        if story <= s1:
            return v0 + (story - s0) / (s1 - s0) * (v1 - v0)
    return REMAP[-1][0]


TF = 18.0
T_DATA, T_ALGO = TF + 1.9, TF + 1.9 + 2.9
T_FEAT = T_ALGO + 3.0
TFS = T_FEAT + 0.45 - 1.9
T_EXIT = TFS + 1.9 + 8.2


# ------------------------------------------------------------------ helpers
def buf():
    return np.zeros((N, 2))


def add(dst, x, t, gain=1.0, pan=0.0):
    """mix mono or stereo x into dst at time t (s)"""
    i = int(t * SR)
    if i >= N or i + len(x) <= 0:
        return
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        x = np.stack([x * l * 1.414, x * r * 1.414], 1)
    a, b = max(0, i), min(N, i + len(x))
    dst[a:b] += x[a - i:b - i] * gain


def env(n, a=0.005, d=0.2, curve=4.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) * curve / max(d, 1e-4))
    return e


def lp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, min(fc, SR / 2 * 0.95), "low", fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(signal.butter(order, [lo, min(hi, SR / 2 * 0.95)], "band", fs=SR, output="sos"), x)


def sweep_lp(x, f0, f1, block=480):
    """low-pass whose cutoff moves exponentially from f0 to f1"""
    out = np.zeros_like(x)
    zi = None
    nb = int(np.ceil(len(x) / block))
    for k in range(nb):
        f = f0 * (f1 / f0) ** (k / max(1, nb - 1))
        sos = signal.butter(2, min(f, SR / 2 * 0.95), "low", fs=SR, output="sos")
        if zi is None:
            zi = signal.sosfilt_zi(sos) * 0
        seg = x[k * block:(k + 1) * block]
        y, zi = signal.sosfilt(sos, seg, zi=zi)
        out[k * block:k * block + len(seg)] = y
    return out


def saw(freq, n, detune=0.0):
    t = np.arange(n) / SR
    ph = (t * freq * (1 + detune)) % 1.0
    return 2 * ph - 1


def reverb(x, secs=1.8, mix=0.3, seed=1):
    r = np.random.default_rng(seed)
    n = int(secs * SR)
    ir = r.standard_normal((n, 2)) * np.exp(-np.arange(n) / SR * 5.0 / secs)[:, None]
    ir = lp(ir.T, 6000).T
    ir /= np.sqrt((ir ** 2).sum(0))
    wet = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)
    return x * (1 - mix) + wet * mix


def note(n):  # midi -> Hz
    return 440 * 2 ** ((n - 69) / 12)


# ------------------------------------------------------------------ music
BEAT = 14.6 / 28            # ~115 BPM: the freeze (13.6 s) and the title slam (28.2 s) both land on a downbeat
T0 = 13.6
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]   # Am F C G
BAR = 4 * BEAT


def beat_times(start, end, step=1.0, offset=0.0):
    k0 = int(np.ceil((start - T0) / (BEAT * step) - offset))
    out = []
    k = k0
    while True:
        t = T0 + (k + offset) * BEAT * step
        if t >= end:
            break
        if t >= start:
            out.append(t)
        k += 1
    return out


def chord_at(t):
    return CHORDS[int(np.floor((t - T0) / BAR)) % 4]


def section_gain(t):
    """music energy per section"""
    if t < 7.5: return 0.55
    if t < 13.6: return 0.55 + 0.45 * (t - 7.5) / 6.1
    if t < 27.4: return 1.0
    return 0.0


music = buf()
# pad: detuned saws, filtered, one chord per bar, until the drop
pad = buf()
for bt in beat_times(-BAR * 8, 27.4, 4):
    s, e = max(0, bt), min(27.4, bt + BAR)
    if e <= s:
        continue
    n = int((e - s + 0.6) * SR)
    ch = chord_at(bt + 0.01)
    x = np.zeros((n, 2))
    for m in ch + [ch[0] - 12]:
        for d, side in ((-0.004, 0), (0.0035, 1), (0.0, None)):
            v = saw(note(m), n, d) * 0.09
            if side is None:
                x += v[:, None] * 0.6
            else:
                x[:, side] += v
    x = lp(x.T, 1400 if s > 13.6 else 900).T
    a = np.minimum(1, np.arange(n) / (0.25 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.5 * SR))
    add(pad, x * a[:, None], s, 0.55 * section_gain(s + 0.01))
music += reverb(pad, 2.4, 0.35, 2)

# arpeggio pluck: 8ths in the intro and build, 16ths in the groove
arp = buf()
for t in beat_times(0.0, 27.4, 0.5) + beat_times(13.6, 27.4, 0.5, 0.5):
    ch = chord_at(t + 0.01)
    k = int(round((t - T0) / (BEAT / 2)))
    m = (ch * 2)[k % 6] + 12 + (12 if (k // 6) % 2 else 0)
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * note(m) * tt) + 0.3 * np.sin(4 * np.pi * note(m) * tt)) * env(n, 0.002, 0.25, 5)
    add(arp, x, t, 0.11 * section_gain(t), pan=(-0.4 if k % 2 else 0.4))
music += reverb(arp, 1.6, 0.4, 3)

# kick: half-time in the build, four-on-the-floor in the groove
def kick(n=int(0.45 * SR)):
    tt = np.arange(n) / SR
    f = 45 + 110 * np.exp(-tt * 30)
    return np.tanh(1.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.35, 5))


for t in beat_times(9.95, 13.6, 2) + beat_times(13.6, 27.4, 1):
    add(music, kick(), t, 0.55)
# clap on 2 and 4, hats on the off-beats (groove only)
for t in beat_times(13.6, 27.4, 2, 0.5):
    n = int(0.25 * SR)
    x = bp(rng.standard_normal(n), 900, 5000) * env(n, 0.001, 0.12, 6)
    add(music, x, t, 0.22)
for t in beat_times(13.6, 27.4, 1, 0.5):
    n = int(0.06 * SR)
    add(music, hp(rng.standard_normal(n), 7000) * env(n, 0.001, 0.04, 6), t, 0.08, pan=0.3)
# bass: root 8ths in the groove
bass = buf()
for t in beat_times(13.6, 27.4, 0.5):
    m = chord_at(t + 0.01)[0] - 24
    n = int(BEAT / 2 * SR * 0.95)
    x = lp(saw(note(m), n) * 0.5 + np.sin(2 * np.pi * note(m) * np.arange(n) / SR), 500) * env(n, 0.004, 0.25, 2.5)
    add(bass, x, t, 0.32)
music += bass

# riser into the freeze, drop before the slam, final chord
n = int(2.0 * SR)
rise = sweep_lp(rng.standard_normal(n), 300, 9000) * np.linspace(0, 1, n) ** 2
add(music, rise, 13.6 - 2.0, 0.22)
final = np.zeros((int(1.9 * SR), 2))
for m in [45, 57, 60, 64, 69]:
    v = saw(note(m), len(final), 0.003) * 0.12
    final[:, 0] += v; final[:, 1] += saw(note(m), len(final), -0.003) * 0.12
final = lp(final.T, 2200).T * np.exp(-np.arange(len(final)) / SR * 1.5)[:, None]
add(music, reverb(final, 2.0, 0.4, 4), vt(T_EXIT + 1.3), 0.8)

# ------------------------------------------------------------------ sound effects
sfx = buf()


def whoosh(t, dur, f0=400, f1=4000, gain=0.3, pan=0.0):
    n = int(dur * SR)
    x = sweep_lp(rng.standard_normal(n), f0, f1) * np.sin(np.pi * np.arange(n) / n) ** 1.5
    add(sfx, x, t, gain, pan)


def pop(t, f=900, gain=0.35, pan=0.0):
    n = int(0.18 * SR)
    tt = np.arange(n) / SR
    x = np.sin(2 * np.pi * np.cumsum(f * (0.35 + 0.65 * np.exp(-tt * 40))) / SR) * env(n, 0.001, 0.1, 5)
    add(sfx, x + 0.2 * hp(rng.standard_normal(n), 3000) * env(n, 0.0005, 0.01, 6), t, gain, pan)


def chime(t, f, gain=0.12, pan=0.0):
    n = int(0.9 * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.76 * tt)) * env(n, 0.002, 0.6, 5)
    add(sfx, x, t, gain, pan)


def tick(t, gain=0.12, f=3200, pan=0.0):
    n = int(0.04 * SR)
    x = np.sin(2 * np.pi * f * np.arange(n) / SR) * env(n, 0.0005, 0.015, 6)
    add(sfx, x, t, gain, pan)


def click(t, gain=0.3):
    for dt in (0.0, 0.035):
        n = int(0.02 * SR)
        add(sfx, bp(rng.standard_normal(n), 1500, 6000) * env(n, 0.0003, 0.006, 6), t + dt, gain)


def key(t, gain=0.15):
    n = int(0.03 * SR)
    add(sfx, bp(rng.standard_normal(n), 1800, 7000) * env(n, 0.0003, 0.012, 6), t, gain, pan=rng.uniform(-0.3, 0.3))


def boom(t, gain=0.8, dur=1.8):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    low = np.tanh(2 * np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-tt * 12)) / SR)) * env(n, 0.002, dur * 0.6, 4)
    burst = lp(rng.standard_normal(n), 2500) * env(n, 0.001, 0.25, 6)
    x = np.stack([low + 0.5 * burst] * 2, 1)
    add(sfx, reverb(np.pad(x, ((0, 0), (0, 0))), 2.2, 0.35, 9), t, gain)


def chalk(t, dur, gain=0.06):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    am = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * (22 + 10 * np.sin(tt * 3)) * tt))
    add(sfx, bp(rng.standard_normal(n), 2500, 7000) * am * np.sin(np.pi * tt / dur), t, gain)


# intro: chalk writing, icon pops
chalk(vt(0.6), vt(2.0) - vt(0.6), 0.07)
for k, ts in enumerate((4.0, 6.0, 8.0)):
    pop(vt(ts), 700 + 150 * k, 0.4, pan=(-0.5, 0, 0.5)[k])
# letters -> line -> circle
whoosh(vt(9.6), vt(10.3) - vt(9.6), 2000, 300, 0.22)
whoosh(vt(10.25), vt(11.0) - vt(10.25), 300, 5000, 0.18)
for k, f in enumerate([1318, 1568, 1976, 2637]):
    chime(vt(11.0) + k * 0.05, f, 0.1, pan=(-0.6 + 0.4 * k))
# teammates land (pop) and the stars twinkle
for k, ts in enumerate((11.1, 11.3, 11.5, 11.7, 11.9)):
    whoosh(vt(ts), 0.28, 600, 3000, 0.12, pan=(-0.7, 0.7, -0.4, 0.4, 0)[k])
    pop(vt(ts + 0.35), 520 + 60 * k, 0.28, pan=(-0.7, 0.7, -0.4, 0.4, 0)[k])
penta = [1760, 1976, 2349, 2637, 2960, 3520]
for k in range(26):
    chime(vt(11.0) + k * (vt(13.9) - vt(11.0)) / 26 + rng.uniform(0, 0.05), penta[k % 6], 0.05, pan=rng.uniform(-0.9, 0.9))
whoosh(vt(14.0), 0.5, 3000, 400, 0.18)                         # team slides out
# satellite rises, the board opens into space, it locks into orbit
n = int((vt(16.3) - vt(14.3)) * SR)
add(sfx, lp(rng.standard_normal(n), 300) * np.linspace(0.2, 1, n), vt(14.3), 0.25)
whoosh(vt(15.2), vt(16.4) - vt(15.2), 200, 2500, 0.2)
chime(vt(17.4), 880, 0.12); chime(vt(17.4) + 0.06, 1320, 0.08)
# freeze: OUR WEBPAGE
boom(vt(TF), 0.75)
whoosh(vt(TF + 0.45), vt(TF + 1.9) - vt(TF + 0.45), 3500, 300, 0.18)
# DATASETS / ALGORITHMS panels and their rows
whoosh(vt(T_DATA + 0.3), 0.5, 500, 4000, 0.22, pan=-0.6)
for i in range(9):
    tick(vt(T_DATA + 0.6 + i * 0.2), 0.1, 2600 + 120 * i, pan=-0.5)
whoosh(vt(T_ALGO), 0.5, 4000, 500, 0.2, pan=-0.6)
whoosh(vt(T_ALGO + 0.45), 0.5, 500, 4000, 0.22, pan=0.6)
for i in range(8):
    tick(vt(T_ALGO + 0.9 + i * 0.22), 0.1, 2600 + 120 * i, pan=0.3)
whoosh(vt(T_FEAT), 0.55, 3000, 400, 0.2, pan=0.6)
# features: caption swishes, typing, clicks, zooms, Play
for ts in (TFS + 1.9, TFS + 4.8, TFS + 7.6):
    whoosh(vt(ts), 0.35, 1500, 6000, 0.12)
ks = vt(TFS + 2.15); ke = vt(TFS + 2.8)
for k in range(14):                                   # typing "Paradise, California"
    key(ks + k * (ke - ks) / 14 + rng.uniform(0, 0.008))
key(vt(TFS + 2.9), 0.3)                               # Enter
for ts in (TFS + 2.08, TFS + 4.95, TFS + 8.15):
    click(vt(ts), 0.28)
whoosh(vt(TFS + 3.0), vt(TFS + 3.45) - vt(TFS + 3.0), 300, 5000, 0.22)   # fly to Paradise
for ts, d in ((TFS + 3.6, 0.45), (TFS + 8.6, 0.5)):
    whoosh(vt(ts), vt(ts + d) - vt(ts), 400, 3000, 0.14)
pop(vt(TFS + 3.85), 1100, 0.18)                       # card highlight
for i in range(12):
    tick(vt(TFS + 5.3 + i * 0.19), 0.07, 1800, pan=0.2)
# exit: fling, fire roar with crackle, flash, slam, embers
whoosh(vt(T_EXIT), 0.6, 4000, 200, 0.35)
n = int((vt(T_EXIT + 1.05) - vt(T_EXIT)) * SR)
roar = lp(np.cumsum(rng.standard_normal(n)) * 0.02, 900) * np.linspace(0, 1, n) ** 1.5
add(sfx, roar / (np.abs(roar).max() + 1e-9), vt(T_EXIT), 0.45)
for k in range(70):
    tt = vt(T_EXIT) + rng.uniform(0, vt(T_EXIT + 3.2) - vt(T_EXIT))
    m = int(0.012 * SR)
    add(sfx, bp(rng.standard_normal(m), 1500, 8000) * env(m, 0.0003, 0.004, 6), tt, rng.uniform(0.05, 0.18), pan=rng.uniform(-0.8, 0.8))
n = int(0.8 * SR)                                              # reverse swell into the flash
add(sfx, hp(rng.standard_normal(n), 3000) * np.linspace(0, 1, n) ** 3, vt(T_EXIT + 1.0) - 0.8, 0.25)
boom(vt(T_EXIT + 1.0), 0.9, 2.2)
boom(vt(T_EXIT + 1.3), 0.7, 1.6)
whoosh(vt(T_EXIT + 1.3), 0.9, 3000, 150, 0.25)                 # shockwave

# ------------------------------------------------------------------ write
def save(name, x, peak=0.89):
    fade = np.ones(N); f = int(0.25 * SR); fade[-f:] = np.linspace(1, 0, f)
    x = x * fade[:, None]
    x = x / (np.abs(x).max() + 1e-9) * peak
    from scipy.io import wavfile
    wavfile.write(OUT / name, SR, (x * 32767).astype(np.int16))
    print(name, f"{x.shape[0] / SR:.2f}s")


save("music.wav", music)
save("sfx.wav", sfx)
print("events: freeze", round(vt(TF), 2), "datasets", round(vt(T_DATA + 0.3), 2), "algorithms", round(vt(T_ALGO + 0.45), 2),
      "features", round(vt(TFS + 1.9), 2), "exit", round(vt(T_EXIT), 2), "flash", round(vt(T_EXIT + 1.0), 2), "slam", round(vt(T_EXIT + 1.3), 2))
