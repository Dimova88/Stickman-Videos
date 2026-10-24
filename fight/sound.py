"""The soundtrack: layered foley, a taiko score, and the mix that holds them.

The first version of the audio was one looping drum, one dry impact and a chord
at the end. That is a metronome with a soundtrack, not a fight. This module
builds the three things a fight scene actually needs:

**Foley**, one sound per *thing that happens*, each made of several layers:

    whoosh      a rising band-swept noise, tuned by the weight of the limb: a
                jab is thin and quick, a kick is low and long, a sword is bright
                with a steel edge on top of it
    footstep    dirt: a low thud, gravel hiss, and a couple of stone ticks
    flesh hit   sub drop + meat thud + skin crack, with a bone ring on blocks
    steel       an inharmonic clang (partials at 1, 2.76, 5.40, 8.93, 13.34)
                plus a sizzling high tail, because steel rings, it does not thump
    boom        a sonic burst for the hits the film stops for
    breath      a short non-verbal effort exhale: air and a glottal buzz, no words

**Music** that knows what is happening. A taiko kit (big drum, shime-daiko, rim)
plus an instrumental rock layer (distorted power chords, bass) drives the tempo
of the fight; the score *stops dead* for the blade lock and for the breath before
the last blow, and comes back at full weight on the blow itself.

**A mix**: every sound is panned to where it happened, hits side-chain the music
by ~8 dB, the metal and the booms go through one convolution reverb, and the
whole thing is limited rather than clipped.

Nothing here is sampled, looped or borrowed: every sound is generated from an
envelope, a filter and a noise seed.
"""
from __future__ import annotations

import math

import numpy as np

SR = 44100

# --------------------------------------------------------------- primitives
def _t(seconds: float) -> np.ndarray:
    return np.arange(max(1, int(seconds * SR))) / SR


def _noise(n: int, seed: float) -> np.ndarray:
    return np.random.default_rng(int(seed * 7919) % 2147483647).normal(
        0, 1, n).astype(np.float32)


def _band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Soft band-pass in the frequency domain: cheap, and phase-clean."""
    lo = max(15.0, min(lo, SR * 0.45))
    hi = max(lo * 1.05, min(hi, SR * 0.47))
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    hp = 1.0 / (1.0 + np.exp(np.clip(-(f - lo) / max(8.0, lo * 0.14), -60, 60)))
    lp = 1.0 / (1.0 + np.exp(np.clip((f - hi) / max(8.0, hi * 0.14), -60, 60)))
    return np.fft.irfft(spec * hp * lp, len(x)).astype(np.float32)


def _sweep_band(x, bands, weights):
    """A filter whose centre moves: the sum of fixed bands with time-varying
    weights. Six FFTs of a short buffer cost nothing and give a real sweep."""
    n = len(x)
    out = np.zeros(n, np.float32)
    for (lo, hi), w in zip(bands, weights):
        if np.max(w) < 1e-3:
            continue
        out += _band(x, lo, hi) * w
    return out


def _decay(n: int, rate: float, attack: float = 0.002) -> np.ndarray:
    t = np.arange(n) / SR
    a = max(1, int(attack * SR))
    env = np.exp(-t * rate).astype(np.float32)
    env[:a] *= np.linspace(0, 1, a) ** 1.4
    return env


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def _saw(freq, t):
    return (2.0 * ((freq * t) % 1.0) - 1.0)


# -------------------------------------------------------------------- drums
def taiko(size: float = 1.0, pitch: float = 62.0, seed: float = 1.0,
          length: float = 0.62) -> np.ndarray:
    """The big drum: a skin that drops in pitch, a slap, and the room."""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = pitch * (1.0 + 1.15 * np.exp(-t * 26.0)) * (0.94 + 0.12 * (size - 1))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (5.4 / size))
    body += 0.42 * np.sin(2 * np.pi * np.cumsum(f * 1.53) / SR) * np.exp(-t * 9.0)
    slap = _band(_noise(n, seed), 160.0, 1500.0) * np.exp(-t * 46.0)
    room = _band(_noise(n, seed + 3), 55.0, 260.0) * np.exp(-t * 2.6)
    sig = body * 1.0 + slap * (0.5 + 0.2 * size) + room * 0.35
    return _norm(np.tanh(sig * 1.25), 0.9)


def shime(pitch: float = 520.0, seed: float = 2.0, length: float = 0.16) -> np.ndarray:
    """The small drum that carries the subdivisions."""
    n = int(length * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * pitch * t) * np.exp(-t * 40.0)
    body += 0.5 * np.sin(2 * np.pi * pitch * 1.61 * t) * np.exp(-t * 55.0)
    skin = _band(_noise(n, seed), 900.0, 4600.0) * np.exp(-t * 78.0)
    return _norm(body * 0.8 + skin * 0.9, 0.8)


def rim(seed: float = 4.0, length: float = 0.10) -> np.ndarray:
    """Wood on wood, for the quieter accents."""
    n = int(length * SR)
    t = np.arange(n) / SR
    click = _band(_noise(n, seed), 1200.0, 5200.0) * np.exp(-t * 190.0)
    tone = np.sin(2 * np.pi * 1180.0 * t) * np.exp(-t * 120.0)
    return _norm(click + 0.6 * tone, 0.55)


def crash(seed: float = 5.0, length: float = 1.4) -> np.ndarray:
    """Cymbal, for the moment the score is allowed to open up."""
    n = int(length * SR)
    t = np.arange(n) / SR
    metal = _noise(n, seed) - _band(_noise(n, seed), 0.0, 900.0)
    metal = _band(metal, 2600.0, 12000.0) * np.exp(-t * 2.6)
    ring = sum(0.10 * np.sin(2 * np.pi * f * t + seed) * np.exp(-t * 2.0)
               for f in (2310.0, 3170.0, 4390.0))
    return _norm(metal * 0.8 + ring, 0.6)


# -------------------------------------------------------------------- music
def power_chord(root: float, dur: float, drive: float = 9.0,
                muted: float = 1.0, seed: float = 1.0) -> np.ndarray:
    """Distorted guitar, in the only honest way to fake one: saws into tanh."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (_saw(root, t) * 0.62 + _saw(root * 1.5, t) * 0.48 +
         _saw(root * 2.0, t) * 0.22)
    x = np.tanh(x * drive)
    x = _band(x, 78.0, 4800.0)
    env = np.exp(-t * (11.0 * muted)) * np.minimum(1.0, t / 0.004)
    return _norm((x * env).astype(np.float32), 0.75)


def bass(root: float, dur: float, seed: float = 1.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * root * t) + 0.45 * np.sin(2 * np.pi * root * 2 * t)
    x += 0.22 * _saw(root * 1.0, t) * np.exp(-t * 6.0)
    env = np.exp(-t * 2.6) * np.minimum(1.0, t / 0.006)
    return _norm(_band((x * env).astype(np.float32), 30.0, 900.0), 0.85)


def string_pad(root: float, dur: float, seed: float = 1.0) -> np.ndarray:
    """A wide, detuned saw bed: the 'strings' under the victory card."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    for k, det in enumerate((-7, -3, 0, 3, 7)):
        f = root * (1.0 + det / 1200.0)
        for mult, g in ((1.0, 0.5), (2.0, 0.22), (3.0, 0.12)):
            x += g * _saw(f * mult + k * 0.03, t)
    env = np.minimum(1.0, t / 0.35) * np.exp(-t * 0.10)
    talk = 1.0 + 0.05 * np.sin(2 * np.pi * 0.7 * t)
    return _norm(_band((x * env * talk).astype(np.float32), 90.0, 3600.0), 0.5)


def riser(dur: float, seed: float = 9.0) -> np.ndarray:
    """Noise climbing a filter: the four bars before the blow lands."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = _noise(n, seed)
    bands = [(150, 500), (400, 1100), (900, 2400), (1800, 4200), (3400, 9000)]
    k = np.clip(t / dur, 0, 1)
    weights = [np.exp(-((k - c) ** 2) / 0.10) for c in (0.0, 0.25, 0.5, 0.75, 1.0)]
    y = _sweep_band(x, bands, weights)
    return _norm((y * (k ** 1.6)).astype(np.float32), 0.55)


# -------------------------------------------------------------------- foley
def whoosh(weight: float = 0.5, dur: float = 0.20, bright: float = 0.5,
           up: bool = True, seed: float = 3.0) -> np.ndarray:
    """Air moving. ``weight`` 0 is a jab, 1 is a kick or a two-handed swing."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = _noise(n, seed)
    base = 260.0 + 260.0 * weight
    bands = [(base, base * 2.2), (base * 1.7, base * 4.0),
             (base * 3.0, base * 7.5), (base * 5.0, base * 12.0)]
    k = (t / dur) if up else (1.0 - t / dur)
    centres = (0.05, 0.35, 0.65, 0.92)
    weights = [np.exp(-((k - c) ** 2) / 0.055) for c in centres]
    y = _sweep_band(x, bands, weights)
    if bright > 0.5:
        edge = _band(x, 2200.0, 8000.0) * np.exp(-((k - 0.85) ** 2) / 0.02)
        y = y + edge * (bright - 0.5) * 1.6
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.4
    return _norm((y * env).astype(np.float32), 0.55 + 0.25 * weight)


def steel_swing(weight: float = 0.8, dur: float = 0.24, seed: float = 6.0):
    """A katana through air: the whoosh plus the edge singing over it."""
    w = whoosh(0.45 * weight, dur, bright=0.95, up=True, seed=seed)
    n = len(w)
    t = np.arange(n) / SR
    ring = np.zeros(n, np.float32)
    for f, g in ((2680.0, 0.30), (4020.0, 0.20), (6110.0, 0.12)):
        ring += g * np.sin(2 * np.pi * f * t) * np.exp(-t * 22.0)
    ring *= np.linspace(0.0, 1.0, n) ** 2
    return _norm(w + ring * 0.5, 0.7)


def footstep(size: float = 1.0, seed: float = 7.0) -> np.ndarray:
    """Dirt and stone: a soft low thud, gravel, and a couple of ticks."""
    n = int(0.20 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (86.0 * (1 + 0.6 * np.exp(-t * 30))) * t) * np.exp(-t * 26.0)
    gravel = _band(_noise(n, seed), 380.0, 3200.0) * np.exp(-t * 30.0)
    ticks = np.zeros(n, np.float32)
    rng = np.random.default_rng(int(seed * 97) % 99991)
    for _ in range(3):
        i0 = int(rng.uniform(0.012, 0.075) * SR)
        ln = int(rng.uniform(0.004, 0.012) * SR)
        seg = _noise(ln, rng.uniform(1, 99)) * np.exp(-np.arange(ln) / (ln * 0.5))
        ticks[i0:i0 + ln] += seg[:max(0, min(ln, n - i0))][:len(ticks[i0:i0 + ln])]
    sig = body * 0.9 + gravel * 0.55 + _band(ticks, 1800.0, 7000.0) * 0.35
    return _norm(np.tanh(sig * 1.2), 0.32 + 0.35 * min(size, 1.6))


def sub_drop(depth: float = 1.0, length: float = 0.85, seed: float = 8.0) -> np.ndarray:
    """The low end falling out of the room under a heavy hit."""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = 34.0 + 66.0 * np.exp(-t * 6.5)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6)
    x += 0.4 * np.sin(2 * np.pi * np.cumsum(f * 0.5) / SR) * np.exp(-t * 2.0)
    x += 0.15 * _band(_noise(n, seed), 25.0, 140.0) * np.exp(-t * 5.0)
    return _norm(np.tanh(x * 1.6), 0.85 * depth)


def flesh_hit(size: float = 1.0, kind: str = "hit", seed: float = 10.0,
              length: float = 0.55) -> np.ndarray:
    """Knuckle, meat and bone: four layers that a single thud cannot fake."""
    n = int(length * SR)
    t = np.arange(n) / SR
    low = {"hit": 96.0, "body": 80.0, "block": 150.0, "final": 66.0,
           "clash": 170.0}.get(kind, 96.0) * (1.0 - 0.12 * min(size, 2.0))
    sweep = low * (1.0 + 1.3 * np.exp(-t * 44.0))
    body = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.exp(-t * 12.0)
    body += 0.30 * np.sin(2 * np.pi * np.cumsum(sweep * 0.5) / SR) * np.exp(-t * 8.0)
    smack_lo, smack_hi = {"block": (650, 3200), "body": (300, 1400),
                          "final": (480, 3600), "clash": (900, 4600)}.get(
                              kind, (700, 4200))
    smack = _band(_noise(n, seed), smack_lo, smack_hi)
    smack *= (1.0 - np.exp(-t * 1600.0)) * np.exp(-t * 40.0)
    meat = _band(_noise(n, seed + 1), 150.0, 900.0) * np.exp(-t * 17.0)
    ring = np.zeros(n, np.float32)
    if kind in ("block", "clash"):
        for f, g in ((1180.0, 0.20), (1730.0, 0.13), (2640.0, 0.08)):
            ring += g * np.sin(2 * np.pi * f * t + seed) * np.exp(-t * 20.0)
    sig = body * 1.1 + smack * (1.6 if kind == "hit" else 1.2) + meat * 0.9 + ring
    sig *= _decay(n, 0.0, 0.0008)
    return _norm(np.tanh(sig * 1.4), 0.6 + 0.25 * min(size, 1.8))


def metal_clang(size: float = 1.0, pitch: float = 640.0,
                seed: float = 12.0, length: float = 0.9) -> np.ndarray:
    """Steel on steel: inharmonic partials, a bright sizzle and a hard clank."""
    n = int(length * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(int(seed * 131) % 99991)
    sig = np.zeros(n, np.float32)
    for ratio, gain, decay in ((1.0, 0.55, 5.0), (2.76, 0.34, 7.5),
                               (5.40, 0.22, 11.0), (8.93, 0.14, 16.0),
                               (13.34, 0.08, 22.0)):
        f = pitch * ratio * (1.0 + rng.uniform(-0.01, 0.01))
        sig += gain * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t * decay)
    sizzle = _band(_noise(n, seed), 3200.0, 11000.0) * np.exp(-t * 9.0)
    clank = np.sin(2 * np.pi * 132.0 * (1 + np.exp(-t * 40)) * t) * np.exp(-t * 22.0)
    sig = sig * (0.9 + 0.5 * size) + sizzle * 0.55 + clank * 0.7
    return _norm(np.tanh(sig * 1.2), 0.6 + 0.2 * min(size, 1.6))


def steel_grind(dur: float = 0.6, seed: float = 18.0) -> np.ndarray:
    """Two edges sliding against each other: the sound of a lock, not a hit.

    The score stops for this, so it has to carry the moment on its own: a
    friction hiss, a slow beating between close partials, and a low groan.
    """
    n = int(dur * SR)
    t = np.arange(n) / SR
    hiss = _band(_noise(n, seed), 1800.0, 9000.0)
    beat = 0.5 + 0.5 * np.sin(2 * np.pi * 7.5 * t + 1.0)
    hiss *= 0.35 + 0.65 * beat
    ring = np.zeros(n, np.float32)
    for f, g in ((1830.0, 0.22), (1876.0, 0.20), (3120.0, 0.14), (4190.0, 0.10)):
        ring += g * np.sin(2 * np.pi * f * t + seed) * (0.4 + 0.6 * beat)
    groan = np.sin(2 * np.pi * (74.0 + 6.0 * np.sin(2 * np.pi * 2.2 * t)) * t)
    env = np.minimum(1.0, t / 0.05) * np.exp(-np.maximum(0.0, t - dur * 0.55) * 9.0)
    sig = (hiss * 0.55 + ring * 0.9 + groan * 0.35) * env
    return _norm(np.tanh(sig * 1.2), 0.5)


def boom(size: float = 1.0, seed: float = 14.0) -> np.ndarray:
    """The hit the film stops for: air pressure, then the tail of it."""
    n = int(1.5 * SR)
    t = np.arange(n) / SR
    sub = sub_drop(1.0, 1.4, seed)
    sub = np.pad(sub, (0, max(0, n - len(sub))))[:n]
    f = 30.0 + 90.0 * np.exp(-t * 9.0)
    pressure = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    air = _band(_noise(n, seed), 45.0, 700.0) * np.exp(-t * 5.5)
    crack = _band(_noise(n, seed + 2), 800.0, 5200.0) * np.exp(-t * 32.0)
    sig = sub * 0.9 + pressure * 1.0 + air * 1.1 + crack * 0.8
    return _norm(np.tanh(sig * 1.5), 0.7 + 0.25 * min(size, 1.6))


def breath(effort: float = 1.0, seed: float = 15.0, length: float = 0.22,
           pitch: float = 128.0) -> np.ndarray:
    """An effort exhale, not a word: air through a throat, with a little voice.

    The brief is a fight with no narration, so there is no language here —
    only the sound a body makes when it throws something heavy.
    """
    n = int(length * SR)
    t = np.arange(n) / SR
    air = _band(_noise(n, seed), 480.0, 2600.0)
    form = _band(_noise(n, seed + 1), 700.0, 1500.0)
    voice = _saw(pitch * (1.0 + 0.25 * np.exp(-t * 8.0)), t)
    voice = _band(voice, 90.0, 620.0) * 0.55
    env = np.minimum(1.0, t / 0.03) * np.exp(-t * (10.0 + 6.0 * effort))
    sig = (air * 0.55 + form * 0.45 + voice * 0.6) * env
    return _norm(np.tanh(sig * 1.1), 0.16 + 0.16 * min(effort, 2.0))


# --------------------------------------------------------------------- reverb
def _ir(seconds: float = 0.85, seed: float = 21.0) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    x = _noise(n, seed) * np.exp(-t * 5.2)
    x = _band(x, 120.0, 7000.0)
    x[:int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
    # a few early reflections give the tail a room instead of a wash
    for dt, g in ((0.011, 0.5), (0.019, 0.38), (0.031, 0.28), (0.047, 0.2)):
        i = int(dt * SR)
        x[i] += g
    return (x / (np.max(np.abs(x)) or 1.0)).astype(np.float32)


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """FFT convolution of a long bus with a short impulse response."""
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:n]
    return y.astype(np.float32)


# --------------------------------------------------------------------- mixing
class Bus:
    """A stereo bus with constant-power panning and a reverb send."""

    def __init__(self, n: int):
        self.n = n
        self.dry = np.zeros((n, 2), np.float32)
        self.send = np.zeros((n, 2), np.float32)

    def add(self, sig: np.ndarray, t: float, gain: float = 1.0, pan: float = 0.0,
            send: float = 0.0) -> None:
        if sig is None or len(sig) == 0 or t >= self.n / SR:
            return
        i0 = int(round(t * SR))
        if i0 < 0:
            sig = sig[-i0:]
            i0 = 0
        if i0 >= self.n or len(sig) == 0:
            return
        m = min(len(sig), self.n - i0)
        a = (float(np.clip(pan, -1, 1)) + 1.0) * math.pi / 4.0
        gl, gr = math.cos(a) * math.sqrt(2.0), math.sin(a) * math.sqrt(2.0)
        self.dry[i0:i0 + m, 0] += sig[:m] * gain * gl
        self.dry[i0:i0 + m, 1] += sig[:m] * gain * gr
        if send > 0:
            self.send[i0:i0 + m, 0] += sig[:m] * gain * gl * send
            self.send[i0:i0 + m, 1] += sig[:m] * gain * gr * send


def _duck(n: int, events, depth: float = 0.65, hold: float = 0.16) -> np.ndarray:
    """The side-chain that lets a punch be heard instead of drowning."""
    d = np.ones(n, np.float32)
    for t, k in events:
        i0 = int(max(0.0, t - 0.015) * SR)
        i1 = min(n, int((t + hold) * SR))
        if i0 >= i1:
            continue
        seg = np.arange(i1 - i0) / SR
        env = np.minimum(1.0, seg / 0.010) * np.exp(-np.maximum(0.0, seg - 0.02) * 12.0)
        d[i0:i1] = np.minimum(d[i0:i1], 1.0 - depth * k * env)
    return d


def _mask(n: int, windows, fade: float = 0.05) -> np.ndarray:
    """Silence where the score has to get out of the way."""
    m = np.ones(n, np.float32)
    for t0, t1 in windows:
        i0 = max(0, int(t0 * SR))
        i1 = min(n, int(t1 * SR))
        if i0 >= i1:
            continue
        m[i0:i1] = 0.0
        f = min(int(fade * SR), (i1 - i0) // 2)
        if f > 2:
            m[i0:i0 + f] *= np.linspace(1, 0, f)
            m[i1 - f:i1] *= np.linspace(0, 1, f)
    return m


# ----------------------------------------------------------------- the score
GROUND_Y = 590.0
_ROOT_A = 55.0          # A1, the key the fight is in
_ROOT_C = 65.41         # C2, where it lands when the fight is won

#: the riff, as (beat within a two second bar, root in Hz)
RIFF = ((0.00, 55.00), (0.25, 55.00), (0.50, 65.41), (0.75, 55.00),
        (1.00, 73.42), (1.25, 55.00), (1.50, 65.41), (1.75, 49.00))


def _foot_plants(track, t0: float, t1: float, hz: float = 60.0):
    """Where a fighter's foot actually comes down, read off the solved rig.

    The footwork module already decides when a foot lands; this finds the same
    events from the outside by looking for the low point of each foot, so the
    sound cannot disagree with the picture.
    """
    n = max(2, int((t1 - t0) * hz))
    ts = t0 + np.arange(n) / hz
    out = []
    for sid in (8, 10):
        ys = np.empty(n, np.float32)
        xs = np.empty(n, np.float32)
        for i, t in enumerate(ts):
            p = track.skel(float(t)).pts[sid]
            xs[i], ys[i] = p[0], p[1]
        for i in range(1, n - 1):
            if not (ys[i] >= ys[i - 1] and ys[i] > ys[i + 1]):
                continue
            before = ys[max(0, i - 6):i]
            after = ys[i + 1:i + 7]
            if len(before) and len(after):
                lift = min(float(np.min(before)), float(np.min(after)))
                if ys[i] - lift < 4.0:          # a jiggle, not a step
                    continue
            if ys[i] < GROUND_Y - 55.0:          # in the air, not a plant
                continue
            speed = abs(float(xs[min(n - 1, i + 4)] - xs[max(0, i - 4)])) / (8 / hz)
            out.append((float(ts[i]), float(np.clip(speed / 260.0, 0.15, 1.4))))
    out.sort()
    return out


def _limb_of(track, t: float, x: float, y: float):
    """Which limb is at the impact point: a hand (with a sword?) or a foot."""
    if track is None:
        return "hand", 0.5
    try:
        sk = track.skel(t)
    except Exception:
        return "hand", 0.5
    named = ((4, "hand"), (6, "hand"), (8, "foot"), (10, "foot"))
    best, kind = 1e9, "hand"
    for sid, k in named:
        p = sk.pts[sid]
        d = math.hypot(p[0] - x, p[1] - y)
        if d < best:
            best, kind = d, k
    if best > 90.0:
        return "hand", 0.5
    return kind, float(np.clip(1.0 - best / 120.0, 0.25, 1.0))


def score(scene, duration: float = 30.2, parts: bool = False):
    """Build the whole soundtrack for one film, from the film's own events."""
    n = int(duration * SR)
    music = Bus(n)
    foley = Bus(n)
    hits = Bus(n)

    impacts = [e for e in scene["impacts"] if e.get("x") is not None]
    # the duel scene lists its two fighters by name; the blade film carries a
    # tracks list because it has four of them
    if scene.get("tracks"):
        tracks = {tr.name: tr for tr in scene["tracks"]}
    else:
        tracks = {k: v for k, v in scene.items()
                  if hasattr(v, "skel") and hasattr(v, "name")}
    cuts = list(scene.get("cuts", ()))
    ink = list(scene.get("ink", ()))
    texts = scene.get("texts", ())

    def text_time(style, default):
        for txt in texts:
            if txt["style"] == style:
                return float(txt["t0"])
        return default

    fight = text_time("fight", 2.10)
    ko = text_time("ko", duration - 4.6)
    finals = [e for e in impacts if e["kind"] == "final"]
    final_t = float(finals[0]["t"]) if finals else ko - 2.0
    heavy = max(impacts, key=lambda e: (e["kind"] == "clash", e["size"])) if impacts else None
    # a blade lock is a stand-off: two edges held against each other, and the
    # score has to get out of the way. A fist fight has no such moment, so this
    # only applies to a film that actually carries steel.
    has_steel = any(getattr(tr, "weapon", None) for tr in tracks.values())
    lock_t = None
    if has_steel:
        second_half = [e for e in impacts
                       if e["t"] > duration * 0.55 and e["kind"] == "clash"]
        if second_half:
            lock_t = float(max(second_half, key=lambda e: e["size"])["t"])

    # ---------------------------------------------------------- 1. the foley
    ramp_lo = min((e["t"] for e in impacts), default=0.0)
    ramp_hi = max((e["t"] for e in impacts), default=duration)
    for e in impacts:
        pan = ((e["x"] / 960.0) * 2.0 - 1.0) * 0.62
        # every blow hits a little harder than the one before it
        esc = 0.78 + 0.30 * (e["t"] - ramp_lo) / max(0.5, ramp_hi - ramp_lo)
        striker = tracks.get(e.get("by"))
        kind, closeness = _limb_of(striker, e["t"], e["x"], e["y"])
        armed = bool(getattr(striker, "weapon", None))
        weight = float(np.clip(0.25 + 0.55 * closeness + 0.25 * (e["size"] - 0.9),
                               0.2, 1.0))
        seed = e["t"] * 37.0
        # the air the blow moved, just before it lands
        if kind == "foot":
            foley.add(whoosh(0.95, 0.30, bright=0.35, up=pan >= 0, seed=seed),
                      e["t"] - 0.20, 0.42, pan)
        elif armed and e["kind"] in ("clash", "block", "hit"):
            foley.add(steel_swing(0.9, 0.22, seed=seed), e["t"] - 0.16, 0.38, pan)
        else:
            foley.add(whoosh(weight, 0.16 + 0.10 * weight, bright=0.55,
                             up=pan >= 0, seed=seed), e["t"] - 0.13, 0.34, pan)

        is_lock = lock_t is not None and abs(e["t"] - lock_t) < 0.02
        if e["kind"] in ("clash", "block"):
            hits.add(metal_clang(e["size"], 560.0 + 120.0 * e["size"], seed=seed),
                     e["t"], (0.24 if is_lock else 0.44) * esc, pan, send=0.55)
            if not is_lock:
                hits.add(flesh_hit(e["size"], "block", seed=seed), e["t"], 0.26, pan)
        elif e["kind"] == "final":
            hits.add(boom(e["size"], seed=seed), e["t"], 0.78, pan, send=0.7)
            hits.add(flesh_hit(e["size"], "final", seed=seed), e["t"], 0.72, pan)
        else:
            hits.add(flesh_hit(e["size"], e["kind"], seed=seed), e["t"],
                     0.72 * esc, pan, send=0.25)
        # the low end, on everything that lands
        if e["kind"] in ("hit", "final"):
            hits.add(sub_drop(0.75 if e["kind"] == "hit" else 1.25,
                              0.9, seed=seed), e["t"], 0.38, 0.0)
        # effort: the man who threw it, and the man who took it
        if e["kind"] in ("hit", "final"):
            hits.add(breath(1.2, seed=seed, pitch=118.0), e["t"] - 0.10, 0.30, pan * 0.6)
            hits.add(breath(0.8, seed=seed + 5, pitch=96.0, length=0.26),
                     e["t"] + 0.035, 0.22, -pan * 0.6)

    # footsteps, from the rig
    for name, tr in tracks.items():
        base = -0.32 if name in ("red", "hero") else 0.32
        for t, strength in _foot_plants(tr, 0.0, duration - 0.2):
            foley.add(footstep(strength, seed=t * 13.0 + len(name)), t,
                      0.16 + 0.30 * strength, base + 0.1 * (name == "teal"))

    # landings after a knockdown
    for t in scene.get("dust", ()):
        hits.add(footstep(1.4, seed=t * 7.0), t, 0.5, -0.1)
        hits.add(boom(0.5, seed=t * 3.0), t, 0.30, 0.0, send=0.3)

    # the blade lock: the score stops and the two edges keep talking
    if lock_t is not None:
        hits.add(steel_grind(0.62, seed=lock_t), lock_t - 0.03, 0.30,
                 (heavy["x"] / 960.0) * 2.0 - 1.0 if heavy else 0.0, send=0.6)

    # the ink frames: the blow heard from inside the skull — two frames of
    # black and white get a sub drop under the hit that frames them
    for i, start in enumerate(ink):
        hits.add(boom(1.2, seed=71 + i), start, 0.85, 0.0, send=0.8)
        hits.add(metal_clang(1.4, 420.0, seed=71 + i, length=1.4), start,
                 0.35, 0.0, send=0.9)
        hits.add(breath(1.6, seed=90 + i, pitch=88.0, length=0.42), start + 0.04,
                 0.30, 0.0)

    # -------------------------------------------------------- 2. the music
    def drum(t, size=1.0, gain=0.5, pitch=62.0):
        music.add(taiko(size, pitch, seed=t * 11.0), t, gain)

    def small(t, gain=0.30, pitch=520.0):
        music.add(shime(pitch, seed=t * 13.0), t, gain, pan=0.18)

    def tick(t, gain=0.16):
        music.add(rim(seed=t * 17.0), t, gain, pan=-0.22)

    def bar_rock(t0, t1, gain=0.5):
        t = t0
        while t < t1:
            for off, root in RIFF:
                if t + off >= t1:
                    break
                music.add(power_chord(root * 2.0, 0.22, muted=1.0, seed=t + off),
                          t + off, gain * 0.55, pan=-0.18)
            music.add(bass(55.0, 0.42, seed=t), t, gain * 0.9)
            t += 2.0

    # intro: the drum arrives before the fighters do
    music.add(taiko(0.7, 58.0, seed=0.1), 0.10, 0.24)
    for i, t in enumerate((0.60, 1.15, 1.62)):
        drum(t, 0.55 + 0.15 * i, 0.22 + 0.05 * i, 60.0 + 2 * i)
    roll = fight - 0.55
    while roll < fight:
        small(roll, 0.10 + 0.20 * (roll - (fight - 0.55)) / 0.55, 480.0)
        roll += 0.0625
    music.add(riser(fight - 1.4, seed=3.0), 0.60, 0.22, send=0.4)

    # main: quarter notes, a rim on the off-beat, bass under the bar
    t, beat = fight, 0
    accents = (0.62, 0.26, 0.40, 0.30)
    while t < 8.10:
        drum(t, 1.0, accents[beat % 4], 62.0)
        small(t + 0.25, 0.13, 540.0)
        if beat % 4 == 0:
            tick(t + 0.375, 0.14)
            music.add(bass(55.0, 0.5, seed=t), t, 0.30)
        t += 0.5
        beat += 1

    # drive: the rock layer enters, taiko goes to eighths
    music.add(crash(seed=1.0), 8.10, 0.30, send=0.3)
    bar_rock(8.10, 16.90, 0.55)
    t, beat = 8.10, 0
    while t < 16.90:
        drum(t, 0.95, 0.44 if beat % 2 == 0 else 0.24, 62.0)
        small(t + 0.125, 0.10, 560.0)
        small(t + 0.375, 0.09, 500.0)
        t += 0.25
        beat += 1

    # build: the tempo tightens and the filter opens
    b0 = 17.30
    if cuts:
        b0 = max(b0, cuts[0][0] + cuts[0][1] + 0.06)
    t, step = b0, 0.30
    span = max(0.4, (lock_t or 19.4) - b0)
    while t < (lock_t or 19.42) - 0.55:
        drum(t, 0.9, 0.34 + 0.46 * ((t - b0) / span), 63.0)
        t += step
        step = max(0.14, step * 0.94)
    music.add(riser(max(0.4, (lock_t or 19.4) - b0 - 0.2), seed=5.0), b0,
              0.42, send=0.5)

    # climax: double time, full riff, crash on the way in
    c0 = (lock_t or 20.40) + 0.42
    music.add(crash(seed=2.0), c0, 0.42, send=0.35)
    music.add(taiko(1.4, 55.0, seed=c0), c0, 0.85)
    bar_rock(c0, max(c0 + 0.5, final_t - 0.05), 0.95)
    t, beat = c0, 0
    while t < final_t - 0.02:
        drum(t, 1.15, 0.86 if beat % 4 == 0 else 0.46, 61.0)
        if beat % 2:
            small(t + 0.125, 0.16, 600.0)
        t += 0.25
        beat += 1

    # the aftermath: the room after the noise
    a0 = final_t + 0.55
    for i, t in enumerate(np.arange(a0, ko - 0.2, 0.85)):
        drum(float(t), 0.7, 0.26 - 0.02 * i, 58.0)

    # victory: the key lifts to C major and the strings come in
    for i, (semi, off, gain) in enumerate(((0, 0.00, 0.62), (4, 0.0, 0.30),
                                           (7, 0.0, 0.26), (12, 0.0, 0.20))):
        music.add(string_pad(_ROOT_C * 4 * (2 ** (semi / 12.0)), 3.2, seed=i),
                  ko + off, gain, pan=(-0.3 + 0.2 * i), send=0.5)
    music.add(crash(seed=3.0, length=1.8), ko, 0.44, send=0.5)
    drum(ko, 1.6, 0.95, 55.0)
    for i, off in enumerate((0.0, 0.28, 0.56, 0.84, 1.20, 1.56)):
        small(ko + off, 0.16, 620.0 + 30 * i)
    for i, off in enumerate((0.0, 0.5, 1.0, 1.5, 2.0)):
        drum(ko + 0.9 + off, 1.2, 0.62 - 0.05 * i, 57.0)
    music.add(bass(_ROOT_C, 2.6, seed=4.0), ko + 0.02, 0.5)

    # every blow gets its own drum: the score plays the fight, not a click track
    for e in impacts:
        if e["t"] < fight - 0.1:
            continue
        big = e["kind"] in ("clash", "final", "hit") and e["size"] >= 1.0
        music.add(taiko(1.15 if big else 0.85, 60.0 + 6.0 * (e["size"] - 0.9),
                        seed=e["t"] * 3.0), e["t"], 0.55 if big else 0.34,
                  pan=((e["x"] / 960.0) * 2.0 - 1.0) * 0.25)

    # ----------------------------------------------------- 3. the two silences
    stops = []
    if lock_t is not None:
        stops.append((lock_t - 0.52, lock_t + 0.44))
    stops.append((final_t - 0.62, final_t))
    if cuts:
        stops.append((cuts[0][0] - 0.04, cuts[0][0] + cuts[0][1] * 0.92))
    mask = _mask(n, stops, fade=0.06)

    # --------------------------------------------------------------- 4. mix
    duck = _duck(n, [(e["t"], 0.55 if e["kind"] in ("hit", "clash") else 0.75)
                     for e in impacts] + [(final_t, 0.85)], depth=0.55)
    bed = music.dry * mask[:, None] * duck[:, None]
    for ch in (0, 1):
        bed[:, ch] = _band(bed[:, ch], 46.0, 13000.0)

    ir = _ir(0.85)
    wet = np.zeros((n, 2), np.float32)
    for ch in (0, 1):
        src = hits.send[:, ch] * 0.55 + foley.send[:, ch] * 0.5
        wet[:, ch] = convolve(src, ir)[:n][:n]
    if not wet.any():
        wet = np.zeros((n, 2), np.float32)

    mix = (bed * 0.88 + foley.dry * 0.85 + hits.dry * 0.60 + wet * 0.34)

    # a gentle high-pass keeps the sub from eating the headroom
    for ch in (0, 1):
        x = _band(_band(mix[:, ch], 34.0, 17500.0), 34.0, 17500.0)
        # a small tilt: the drums and the bass were sitting on top of everything
        x = x - 0.34 * _band(x, 52.0, 165.0) + 0.28 * _band(x, 1900.0, 7200.0)
        mix[:, ch] = x

    # the fight happens on the right of the frame more often than not, so the
    # stereo field is trimmed back to level rather than left leaning
    rl = float(np.sqrt(np.mean(mix[:, 0] ** 2))) or 1.0
    rr = float(np.sqrt(np.mean(mix[:, 1] ** 2))) or 1.0
    trim = float(np.clip((rr / rl) ** 0.5, 0.7, 1.4))
    mix[:, 0] *= trim
    mix[:, 1] /= trim

    fin, fout = int(0.35 * SR), int(1.2 * SR)
    mix[:fin] *= np.linspace(0, 1, fin)[:, None] ** 1.5
    mix[-fout:] *= np.linspace(1, 0, fout)[:, None]
    # limiter: soft knee, then a hard ceiling
    mix = np.tanh(mix * 0.70) * 1.32
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 0.94
    mix = np.clip(mix, -1.0, 1.0).astype(np.float32)
    if parts:
        return mix, {"music": bed * 0.62, "foley": foley.dry * 0.70,
                     "hits": hits.dry, "wet": wet * 0.30}
    return mix
