"""Procedural soundtrack: music + sound design, synthesised from scratch.

Nothing sampled, nothing licensed — every sound is synthesised with numpy, so
the whole score is 100 % original and safe to monetise.

Layers
------
* ``Pad``      slow detuned-saw chord bed (anime "dark epic")
* ``Braam``    trailer brass hit (stacked detuned saws + slow filter)
* ``Taiko``    deep drum with body + skin noise
* ``Boom``     sub impact with downward pitch sweep
* ``Whoosh``   band-passed noise sweep (movement)
* ``Slash``    bright metallic noise transient
* ``Riser``    accelerating noise + pulse build-up
* ``Chime``    bell/choir shimmer
* ``Heart``    double thump (tension)
* ``Rain``     filtered noise bed
"""
from __future__ import annotations

import math
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

SR = 48000


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def env(t: np.ndarray, attack=0.005, decay=0.2, curve=2.0) -> np.ndarray:
    a = np.clip(t / max(attack, 1e-5), 0, 1)
    d = np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-5)) ** curve
    return (a * d).astype(np.float32)


def adsr(t: np.ndarray, a=0.01, d=0.15, s=0.6, r=0.4, total=None) -> np.ndarray:
    total = total or float(t[-1]) if len(t) else 1.0
    out = np.ones_like(t)
    out = np.where(t < a, t / max(a, 1e-5), out)
    out = np.where((t >= a) & (t < a + d), 1 - (1 - s) * (t - a) / max(d, 1e-5), out)
    out = np.where(t >= a + d, s, out)
    rel_start = total - r
    out = np.where(t > rel_start, out * np.clip((total - t) / max(r, 1e-5), 0, 1), out)
    return out.astype(np.float32)


def lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter, sosfilt
    ny = SR / 2
    c = min(max(cutoff, 20), ny * 0.98)
    sos = butter(order, c / ny, btype="low", output="sos")
    return sosfilt(sos, x).astype(np.float32)


def highpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter, sosfilt
    ny = SR / 2
    c = min(max(cutoff, 20), ny * 0.98)
    sos = butter(order, c / ny, btype="high", output="sos")
    return sosfilt(sos, x).astype(np.float32)


def bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    from scipy.signal import butter, sosfilt
    ny = SR / 2
    sos = butter(order, [min(lo, ny * .9) / ny, min(hi, ny * .95) / ny], btype="band", output="sos")
    return sosfilt(sos, x).astype(np.float32)


def sweep_filter_noise(dur: float, f0: float, f1: float, q=2.0, seed=0) -> np.ndarray:
    """Noise whose band-pass centre sweeps f0 -> f1 (whooshes, risers)."""
    from scipy.signal import butter, sosfilt
    t = _t(dur)
    n = len(t)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    block = 512
    out = np.zeros(n, np.float32)
    zi = None
    for i in range(0, n, block):
        frac = i / max(n - 1, 1)
        fc = f0 * (f1 / f0) ** frac
        ny = SR / 2
        fc = min(max(fc, 30), ny * 0.95)
        bw = max(fc / q, 30)
        lo = max(fc - bw / 2, 20) / ny
        hi = min(fc + bw / 2, ny * 0.98) / ny
        sos = butter(2, [lo, hi], btype="band", output="sos")
        out[i:i + block] = sosfilt(sos, x[i:i + block]).astype(np.float32)
    return out


def saw(freq, t: np.ndarray, phase=0.0) -> np.ndarray:
    return (2.0 * ((freq * t + phase) % 1.0) - 1.0).astype(np.float32)


def sine(freq, t: np.ndarray, phase=0.0) -> np.ndarray:
    return np.sin(2 * np.pi * freq * t + phase).astype(np.float32)


# ---------------------------------------------------------------- instruments
def boom(t0: float, dur=1.6, f0=110, f1=34, amp=1.0, seed=1) -> tuple[float, np.ndarray]:
    t = _t(dur)
    f = f1 + (f0 - f1) * np.exp(-t * 5.0)
    ph = np.cumsum(2 * np.pi * f / SR)
    body = np.sin(ph).astype(np.float32)
    tick = highpass(np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32), 1200) * \
        env(t, 0.001, 0.02, 1.0) * 0.5
    sig = (body * env(t, 0.004, 0.45, 1.6) + tick)
    return t0, (sig * amp).astype(np.float32)


def taiko(t0: float, amp=1.0, pitch=1.0, seed=2, dur=1.1) -> tuple[float, np.ndarray]:
    t = _t(dur)
    f = 62 * pitch * (1 + 0.6 * np.exp(-t * 22))
    ph = np.cumsum(2 * np.pi * f / SR)
    body = np.sin(ph).astype(np.float32) * env(t, 0.002, 0.28, 1.4)
    rng = np.random.default_rng(seed)
    skin = bandpass(rng.standard_normal(len(t)).astype(np.float32), 180, 2600) * env(t, 0.001, 0.055, 1.2)
    wood = sine(210 * pitch, t) * env(t, 0.001, 0.03, 1.0) * 0.35
    return t0, ((body * 0.9 + skin * 0.5 + wood) * amp).astype(np.float32)


def whoosh(t0: float, dur=0.55, f0=180, f1=1400, amp=0.6, seed=3, reverse=False) -> tuple[float, np.ndarray]:
    if reverse:
        f0, f1 = f1, f0
    x = sweep_filter_noise(dur, f0, f1, q=1.4, seed=seed)
    t = _t(dur)
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.4
    if reverse:
        e = e ** 2
    return t0, (x * e * amp).astype(np.float32)


def slash(t0: float, amp=0.7, seed=4, dur=0.35, pitch=1.0) -> tuple[float, np.ndarray]:
    t = _t(dur)
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(len(t)).astype(np.float32)
    met = bandpass(n, 2600 * pitch, 9000, order=2) * env(t, 0.001, 0.045, 1.0)
    ring = (sine(3100 * pitch, t) + sine(4700 * pitch, t) * 0.6) * env(t, 0.002, 0.12, 1.5) * 0.25
    sw = sweep_filter_noise(dur, 5200, 900, q=1.1, seed=seed + 1) * env(t, 0.004, 0.08, 2.0)
    return t0, ((met * 1.0 + sw * 0.6 + ring) * amp).astype(np.float32)


def riser(t0: float, dur=2.0, amp=0.6, seed=5, f_end=6000) -> tuple[float, np.ndarray]:
    x = sweep_filter_noise(dur, 220, f_end, q=1.1, seed=seed)
    t = _t(dur)
    e = (t / dur) ** 2.2
    pulse = (np.sin(2 * np.pi * (2 + 18 * (t / dur) ** 2) * t) > -0.2).astype(np.float32) * 0.25
    return t0, ((x * e + pulse * e) * amp).astype(np.float32)


def braam(t0: float, dur=3.2, amp=0.9, root=55.0, seed=7) -> tuple[float, np.ndarray]:
    t = _t(dur)
    out = np.zeros(len(t), np.float32)
    for k, det in enumerate((-0.12, -0.04, 0.0, 0.05, 0.13)):
        out += saw(root * (1 + det) * 1.0, t, phase=k * 0.13)
        out += saw(root * 2 * (1 + det * 1.3), t, phase=k * 0.31) * 0.5
    out = lowpass(out, 900, 2)
    e = np.clip(t / 0.09, 0, 1) * np.exp(-np.maximum(t - 0.09, 0) / 1.2) ** 0.8
    rng = np.random.default_rng(seed)
    hit = lowpass(rng.standard_normal(len(t)).astype(np.float32), 400) * env(t, 0.002, 0.12, 1.5)
    return t0, ((out * 0.16 + hit * 0.5) * e * amp).astype(np.float32)


def pad(t0: float, dur: float, freqs: Sequence[float], amp=0.25, detune=0.006, seed=9,
        cutoff=1400) -> tuple[float, np.ndarray]:
    t = _t(dur)
    out = np.zeros(len(t), np.float32)
    for i, f in enumerate(freqs):
        for d in (-detune, 0.0, detune):
            out += saw(f * (1 + d), t, phase=(i * 0.37 + d * 40)) * 0.33
    out = lowpass(out, cutoff, 2)
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.13 * t + seed)
    e = np.minimum(t / max(dur * 0.25, 0.1), 1) * np.minimum((dur - t) / max(dur * 0.3, 0.1), 1)
    return t0, (out * e * lfo * amp / len(freqs)).astype(np.float32)


def choir(t0: float, dur: float, freqs: Sequence[float], amp=0.2, cutoff=2200) -> tuple[float, np.ndarray]:
    t = _t(dur)
    out = np.zeros(len(t), np.float32)
    for i, f in enumerate(freqs):
        vib = 1 + 0.004 * np.sin(2 * np.pi * (4.5 + i * 0.4) * t + i)
        for h, ha in ((1, 1.0), (2, 0.35), (3, 0.18), (4, 0.08), (5, 0.05)):
            out += np.sin(2 * np.pi * f * h * vib * t + i) .astype(np.float32) * ha
    out = lowpass(out, cutoff, 2)
    e = np.minimum(t / max(dur * 0.3, 0.1), 1) * np.minimum((dur - t) / max(dur * 0.35, 0.1), 1)
    return t0, (out * e * amp / (len(freqs) * 2)).astype(np.float32)


def chime(t0: float, base=880.0, dur=2.4, amp=0.25) -> tuple[float, np.ndarray]:
    t = _t(dur)
    out = np.zeros(len(t), np.float32)
    for k, r in enumerate((1.0, 2.01, 2.99, 4.02, 5.4)):
        out += np.sin(2 * np.pi * base * r * t) * np.exp(-t * (1.6 + k * 0.7)) / (k + 1.4)
    return t0, (out * amp).astype(np.float32)


def heart(t0: float, amp=0.5, pitch=1.0) -> tuple[float, np.ndarray]:
    dur = 1.2
    t = _t(dur)
    b1 = sine(48 * pitch, t) * env(t, 0.004, 0.075, 2.2)
    b2 = sine(42 * pitch, t - 0.22) * env(np.clip(t - 0.22, 0, None), 0.004, 0.09, 2.2) * 0.7
    return t0, ((b1 + b2) * amp).astype(np.float32)


def cloth(t0: float, dur=0.3, amp=0.15, seed=11) -> tuple[float, np.ndarray]:
    t = _t(dur)
    rng = np.random.default_rng(seed)
    x = bandpass(rng.standard_normal(len(t)).astype(np.float32), 900, 6000)
    return t0, (x * env(t, 0.01, 0.09, 1.5) * amp).astype(np.float32)


def step(t0: float, amp=0.28, pitch=1.0, seed=12) -> tuple[float, np.ndarray]:
    t = _t(0.5)
    rng = np.random.default_rng(seed)
    n = bandpass(rng.standard_normal(len(t)).astype(np.float32), 120, 1400) * env(t, 0.002, 0.05, 1.4)
    th = sine(70 * pitch, t) * env(t, 0.002, 0.06, 2.0) * 0.7
    return t0, ((n * 0.6 + th) * amp).astype(np.float32)


# ------------------------------------------------------------------- mixing
@dataclass
class Cue:
    t0: float
    sig: np.ndarray
    gain: float = 1.0
    pan: float = 0.0      # -1 left .. 1 right


class Mix:
    def __init__(self, duration: float, sr: int = SR):
        self.dur = duration
        self.sr = sr
        self.n = int(duration * sr) + sr
        self.left = np.zeros(self.n, np.float32)
        self.right = np.zeros(self.n, np.float32)

    def add(self, t0: float, sig: np.ndarray, gain=1.0, pan=0.0):
        i = int(t0 * self.sr)
        if i >= self.n or i < 0:
            return
        seg = sig[: self.n - i]
        gl = gain * math.sqrt(max(0.0, 0.5 * (1 - pan)))
        gr = gain * math.sqrt(max(0.0, 0.5 * (1 + pan)))
        self.left[i:i + len(seg)] += seg * gl
        self.right[i:i + len(seg)] += seg * gr

    def add_cue(self, c: Cue):
        self.add(c.t0, c.sig, c.gain, c.pan)

    def reverb(self, amount=0.22, decay=2.2, predelay=0.02, seed=3):
        """Convolution with a synthetic IR (smooth exponential noise tail)."""
        n = int(decay * 1.6 * self.sr)
        t = np.arange(n) / self.sr
        rng = np.random.default_rng(seed)
        ir_l = rng.standard_normal(n).astype(np.float32) * np.exp(-t / decay)
        ir_r = rng.standard_normal(n).astype(np.float32) * np.exp(-t / decay)
        ir_l = lowpass(ir_l, 6500)
        ir_r = lowpass(ir_r, 6500)
        ir_l[: int(predelay * self.sr)] = 0
        ir_r[: int(predelay * self.sr)] = 0
        ir_l /= np.sqrt((ir_l ** 2).sum())
        ir_r /= np.sqrt((ir_r ** 2).sum())
        from scipy.signal import fftconvolve
        wl = fftconvolve(self.left, ir_l)[: self.n].astype(np.float32)
        wr = fftconvolve(self.right, ir_r)[: self.n].astype(np.float32)
        self.left = self.left * (1 - amount * 0.35) + wl * amount * 1.6
        self.right = self.right * (1 - amount * 0.35) + wr * amount * 1.6

    def master(self, peak=0.95, target_rms_db=-16.0, drive=None):
        """Limiter/saturator: drive is solved so the output lands on the target.

        A high drive squashes peaks into tanh saturation, which raises the
        perceived loudness of the music beds relative to the hits — exactly how
        trailer mixes are glued.
        """
        l = self.left[: int(self.dur * self.sr)].astype(np.float64)
        r = self.right[: int(self.dur * self.sr)].astype(np.float64)
        big = max(float(np.abs(l).max()), float(np.abs(r).max()), 1e-9)
        l /= big
        r /= big
        target = 10 ** (target_rms_db / 20.0)

        def shaped(d):
            yl = np.tanh(l * d)
            yr = np.tanh(r * d)
            m = max(float(np.abs(yl).max()), float(np.abs(yr).max()), 1e-9)
            return yl / m, yr / m

        if drive is None:
            lo, hi = 0.2, 60.0
            for _ in range(28):
                d = math.sqrt(lo * hi)
                yl, yr = shaped(d)
                rms = float(np.sqrt(((yl + yr) ** 2).mean() / 4.0))
                if rms < target:
                    lo = d
                else:
                    hi = d
            drive = math.sqrt(lo * hi)
        yl, yr = shaped(drive)
        return (yl * peak).astype(np.float32), (yr * peak).astype(np.float32)

    def write_wav(self, path: str | Path, peak=0.95, drive=None, fade_in=0.0, fade_out=0.35,
                  target_rms_db=-16.0):
        l, r = self.master(peak, target_rms_db, drive)
        if fade_in > 0:
            n = int(fade_in * self.sr)
            f = np.linspace(0, 1, n, dtype=np.float32)
            l[:n] *= f
            r[:n] *= f
        if fade_out > 0:
            n = int(fade_out * self.sr)
            f = np.linspace(1, 0, n, dtype=np.float32)
            l[-n:] *= f
            r[-n:] *= f
        pcm = np.stack([l, r], axis=1)
        pcm = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(pcm.tobytes())


def db_to_gain(db: float) -> float:
    return 10 ** (db / 20.0)


# ------------------------------------------------------------------- music
NOTE = {n: 440.0 * 2 ** ((i - 9) / 12.0) for i, n in enumerate(
    ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def freq(name: str) -> float:
    """'D3', 'F#4', 'Bb2' -> Hz."""
    name = name.strip()
    letter = name[0].upper()
    i = 1
    acc = ""
    while i < len(name) and name[i] in "#b":
        acc += name[i]
        i += 1
    octave = int(name[i:])
    base = NOTE[letter]
    if acc == "#":
        base *= 2 ** (1 / 12)
    elif acc == "b":
        base *= 2 ** (-1 / 12)
    return base * 2 ** (octave - 4)


def chord(names: Sequence[str]) -> list[float]:
    return [freq(n) for n in names]


def wood_hit(t0: float, amp=0.7, pitch=1.0, seed=15) -> tuple[float, np.ndarray]:
    """Bokken striking bokken: sharp transient + wooden body."""
    t = _t(0.55)
    rng = np.random.default_rng(seed)
    n = bandpass(rng.standard_normal(len(t)).astype(np.float32), 900 * pitch, 7000, order=2)
    crack = n * env(t, 0.0008, 0.022, 1.0)
    body = (sine(330 * pitch, t) * 0.5 + sine(520 * pitch, t) * 0.35 +
            sine(870 * pitch, t) * 0.2) * env(t, 0.001, 0.075, 1.7)
    thud = sine(120 * pitch, t) * env(t, 0.002, 0.05, 2.0) * 0.6
    return t0, ((crack * 1.1 + body + thud) * amp).astype(np.float32)


def cloth_rustle(t0: float, dur=0.45, amp=0.16, seed=17) -> tuple[float, np.ndarray]:
    t = _t(dur)
    rng = np.random.default_rng(seed)
    x = bandpass(rng.standard_normal(len(t)).astype(np.float32), 700, 5200)
    e = env(t, 0.02, dur * 0.35, 1.2)
    return t0, (x * e * amp).astype(np.float32)


def freeze_sting(t0: float, amp=0.55, base=1560.0) -> tuple[float, np.ndarray]:
    """Time stops: reversed riser into a single bell + sub."""
    dur = 2.2
    t = _t(dur)
    ping = (sine(base, t) * 0.6 + sine(base * 2.01, t) * 0.25 + sine(base * 3.02, t) * 0.12) * \
        env(t, 0.001, 0.9, 1.6)
    sub = sine(46, t) * env(t, 0.004, 0.7, 1.8) * 0.8
    return t0, ((ping + sub) * amp).astype(np.float32)


def breath(t0: float, dur=0.9, amp=0.22, seed=19, pitch=1.0) -> tuple[float, np.ndarray]:
    """A held exhale — the sound that ends a scene."""
    t = _t(dur)
    rng = np.random.default_rng(seed)
    x = bandpass(rng.standard_normal(len(t)).astype(np.float32), 300 * pitch, 2600 * pitch)
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
    return t0, (x * e * amp).astype(np.float32)


def rain_bed(dur: float, amp=0.5, seed=3) -> tuple[float, np.ndarray]:
    t = _t(dur)
    x = np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32)
    x = bandpass(x, 900, 9000)
    e = np.minimum(t / 0.4, 1) * np.minimum((dur - t) / 0.5, 1)
    return 0.0, (x * e * amp).astype(np.float32)
