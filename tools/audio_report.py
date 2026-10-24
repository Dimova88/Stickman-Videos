"""Look at the soundtrack instead of guessing: numbers, waveform, spectrogram.

    .venv/bin/python tools/audio_report.py --set steel-mountain

Prints the level of every section of the film, the spectral centre of gravity of
a steel clash against a flesh hit (they have to be different sounds), and writes
``renders/audio_report.png``: the waveform, a log-frequency spectrogram of the
mix, and the section map underneath, so a dip in the score is visible as a dip.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw

import fight.clashfilm as F
import fight.sound as S

SR = S.SR


def db(x: float) -> float:
    return 20.0 * np.log10(max(x, 1e-6))


def rms(x, t0, t1):
    b = x[int(t0 * SR):int(t1 * SR)]
    return float(np.sqrt((b ** 2).mean())) if len(b) else 0.0


def centroid(x, t0, t1):
    b = x[int(t0 * SR):int(t1 * SR), 0]
    if len(b) < 256:
        return 0.0
    spec = np.abs(np.fft.rfft(b * np.hanning(len(b))))
    f = np.fft.rfftfreq(len(b), 1.0 / SR)
    return float((spec * f).sum() / (spec.sum() or 1.0))


def sections(scene, duration):
    texts = scene.get("texts", ())
    ko = next((t["t0"] for t in texts if t["style"] == "ko"), duration - 4.6)
    impacts = [e for e in scene["impacts"] if e.get("x") is not None]
    clashes = [e for e in impacts if e["kind"] == "clash"]
    second = [e for e in clashes if e["t"] > duration * 0.55]
    lock = max(second, key=lambda e: e["size"])["t"] if second else 19.9
    finals = [e for e in impacts if e["kind"] == "final"]
    final = finals[0]["t"] if finals else ko - 2.0
    return [("intro", 0.15, 2.0), ("main", 2.6, 7.9), ("drive", 8.4, 15.6),
            ("build", 17.5, lock - 0.7), ("lock (music out)", lock - 0.3, lock + 0.4),
            ("climax", lock + 0.75, final - 0.7),
            ("breath (music out)", final - 0.55, final - 0.02),
            ("the blow", final, final + 0.28),
            ("aftermath", final + 0.7, min(ko - 0.2, final + 3.2)),
            ("victory", ko + 0.2, min(duration - 0.6, ko + 2.6))], ko, lock, final


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="steel-mountain")
    ap.add_argument("--out", default="renders/audio_report.png")
    args = ap.parse_args()

    sc = F.scene(args.set)
    duration = float(F.DURATION)
    print(f"[audio] {args.set}")
    mix, parts = S.score(sc, duration, parts=True)

    # ---- A. level is not loudness: check the peak and the crest, not just RMS
    peak = float(np.abs(mix).max())
    crest = db(peak) - db(float(np.sqrt((mix ** 2).mean())))
    at_ceiling = float((np.abs(mix) > 0.93).mean())
    print(f"  peak {peak:.2f}  crest {crest:.1f} dB  samples at ceiling "
          f"{at_ceiling * 100:.3f}%  L/R "
          f"{db(float(np.sqrt((mix[:, 0] ** 2).mean()))):.1f}/"
          f"{db(float(np.sqrt((mix[:, 1] ** 2).mean()))):.1f} dBFS")

    rows, ko, lock, final = sections(sc, duration)
    print(f"  {'section':22s} {'mix':>7s} {'music':>7s} {'foley':>7s} {'hits':>7s}")
    for name, t0, t1 in rows:
        t0, t1 = max(0.0, t0), min(duration, t1)
        if t1 <= t0:
            continue
        print(f"  {name:22s} {rms(mix, t0, t1):7.3f} {rms(parts['music'], t0, t1):7.3f} "
              f"{rms(parts['foley'], t0, t1):7.3f} {rms(parts['hits'], t0, t1):7.3f}")

    # ---- B. the sounds have to be different sounds
    impacts = [e for e in sc["impacts"] if e.get("x") is not None]
    steel = next((e for e in impacts if e["kind"] == "clash"), None)
    flesh = next((e for e in impacts if e["kind"] == "hit"), None)
    for label, e in (("steel clash", steel), ("flesh hit", flesh)):
        if e is None:
            continue
        c = centroid(parts["hits"], e["t"] + 0.004, e["t"] + 0.10)
        print(f"  {label:12s} at {e['t']:5.2f}s  centre of gravity {c:6.0f} Hz")

    # ---- C. the picture
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), (12, 13, 16))
    d = ImageDraw.Draw(img)

    # waveform, one bar per 10 ms
    wx0, wx1, wy0, wy1 = 40, W - 40, 40, 220
    hop = int(0.010 * SR)
    frames = (len(mix) - 1) // hop
    xs = np.arange(frames)
    seg = np.array([np.abs(mix[i * hop:(i + 1) * hop]).max() for i in range(frames)])
    tsec = xs * hop / SR
    px = wx0 + (tsec / duration) * (wx1 - wx0)
    mid = (wy0 + wy1) / 2
    amp = seg * (wy1 - wy0) / 2
    for i in range(frames):
        c = (60, 220, 255) if seg[i] < 0.7 else (255, 140, 60)
        d.line([(px[i], mid - amp[i]), (px[i], mid + amp[i])], fill=c)
    d.text((wx0, wy0 - 16), "waveform (10 ms peaks)", fill=(200, 200, 210))

    # spectrogram, log frequency 40 Hz .. 16 kHz
    sx0, sx1, sy0, sy1 = 40, W - 40, 260, 700
    win, step = 2048, 256
    n_frames = (len(mix) - win) // step
    freqs = np.fft.rfftfreq(win, 1.0 / SR)
    keep = (freqs >= 40) & (freqs <= 16000)
    logf = np.log2(np.clip(freqs[keep], 40, 16000))
    rowsy = np.linspace(logf.min(), logf.max(), sy1 - sy0)
    spec = np.zeros((n_frames, sy1 - sy0), np.float32)
    hann = np.hanning(win)
    for i in range(n_frames):
        chunk = mix[i * step:i * step + win, 0] * hann
        mag = np.abs(np.fft.rfft(chunk))[keep]
        vals = np.interp(rowsy, logf, 20 * np.log10(np.maximum(mag, 1e-9)))
        spec[i] = vals
    # dB relative to the loudest bin in the whole film, floored 75 dB down:
    # an absolute scale would paint the entire frame white
    spec -= spec.max()
    spec = np.clip((spec + 75.0) / 75.0, 0, 1)
    spec = spec.T[::-1]                       # low frequency at the bottom
    tx = np.linspace(0, 1, spec.shape[1])
    cols = np.stack([tx * spec.shape[1], np.zeros_like(tx)], 0)
    lut = np.zeros((256, 3), np.uint8)
    for i in range(256):
        k = i / 255.0
        lut[i] = (int(255 * min(1.0, k ** 0.8 * 1.1)),
                  int(255 * min(1.0, max(0.0, k ** 1.6 * 1.15))),
                  int(70 + 185 * min(1.0, k * 1.5)))
    pic = Image.fromarray((lut[(spec * 255).astype(np.uint8)]), "RGB")
    img.paste(pic.resize((sx1 - sx0, sy1 - sy0), Image.BILINEAR), (sx0, sy0))
    d.text((sx0, sy0 - 16), "spectrogram, log 40 Hz - 16 kHz", fill=(200, 200, 210))

    # section map
    sy = 740
    d.line([(wx0, sy), (wx1, sy)], fill=(90, 90, 100))
    for name, t0, t1 in rows:
        t0, t1 = max(0.0, t0), min(duration, t1)
        if t1 <= t0:
            continue
        x0 = wx0 + t0 / duration * (wx1 - wx0)
        x1 = wx0 + t1 / duration * (wx1 - wx0)
        lvl = rms(mix, t0, t1)
        h = 10 + 70 * min(1.0, lvl / 0.30)
        col = (90, 200, 160) if "out" not in name else (230, 90, 90)
        d.rectangle([x0, sy - h, x1 - 2, sy], fill=col)
        d.text((x0 + 2, sy + 6), name.split(" (")[0], fill=(190, 190, 200))
    for t, lab in ((lock, "lock"), (final, "blow"), (ko, "K.O.")):
        x = wx0 + t / duration * (wx1 - wx0)
        d.line([(x, sy0), (x, sy + 4)], fill=(255, 200, 90), width=2)
        d.text((x + 4, sy0 + 4), lab, fill=(255, 200, 90))
    d.text((wx0, H - 40), "one bar per section: height is its RMS. Red = the score "
                          "is out on purpose.", fill=(170, 170, 180))
    img.save(args.out)
    print(f"[report] {args.out}")


if __name__ == "__main__":
    main()
