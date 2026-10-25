"""Render the fight to PNG frames, then encode an MP4 with synthesised sound."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image

from .choreo import FPS, DURATION, GROUND, RED, BLUE, build
from .core import Pose, clamp, smooth
from .draw import Canvas, Cam, INK, draw_background, draw_figure, shadow

W, H = 1920, 1080
SR = 48000


# ------------------------------------------------------------------- camera
def camera_at(keys, t: float) -> Cam:
    if t <= keys[0][0]:
        return Cam(keys[0][1], keys[0][2], keys[0][3])
    if t >= keys[-1][0]:
        return Cam(keys[-1][1], keys[-1][2], keys[-1][3])
    for i in range(len(keys) - 1):
        t0, x0, y0, z0 = keys[i]
        t1, x1, y1, z1 = keys[i + 1]
        if t0 <= t <= t1:
            u = smooth((t - t0) / (t1 - t0))
            return Cam(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u)
    return Cam()


def shake_at(events, t: float):
    """Returns (shake_x, shake_y, zoom_kick) for the frame."""
    sx = sy = zoom = 0.0
    for e in events:
        if e["kind"] != "shake":
            continue
        age = t - e["t"]
        if 0 <= age < e["dur"]:
            k = (1 - age / e["dur"]) ** 2 * e["amp"]
            sx += math.sin(age * 61.0) * 9.0 * k
            sy += math.cos(age * 47.0) * 6.0 * k
            if e.get("kick"):
                zoom += e["kick"] * (1 - age / e["dur"]) ** 1.5
    return sx, sy, zoom


# ------------------------------------------------------------------ effects
def _star_points(cx, cy, r_out, r_in, n=7, rot=0.0):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def draw_effects(cv: Canvas, events, t: float, overlay_flash: list):
    for e in events:
        age = t - e["t"]
        if age < 0:
            continue
        size = e.get("size", 1.0)
        c = cv.wp((e.get("x", 480), e.get("y", 300)))
        u = cv.unit()
        if e["kind"] == "spark":
            life = 0.26
            if age > life:
                continue
            k = age / life
            grow = 1 - (1 - k) ** 2
            r = (13 + 24 * size) * u * (0.6 + 0.7 * grow) * (1 - 0.35 * k)
            alpha = int(255 * (1 - k) ** 0.7)
            rot = 0.4 + e["t"] * 3.0
            # white core with an ink outline: the Pivot-era impact star
            cv.polygon(_star_points(c[0], c[1], r, r * 0.42, 7, rot), (255, 255, 255),
                       alpha=int(alpha * 0.92), width=max(2.0, 5.0 * u), outline=INK)
            cv.disc(c, r * 0.18, (255, 255, 255))
            for i in range(6):
                a = rot + i * math.pi / 3
                L = (15 + 40 * size) * u * grow
                ca, sa_ = math.cos(a), math.sin(a)
                x0, y0 = c[0] + ca * r * 0.78, c[1] + sa_ * r * 0.78
                x1, y1 = x0 + ca * L, y0 + sa_ * L
                w = (2.6 + 1.6 * size) * u
                poly = [(x0 - sa_ * w, y0 + ca * w), (x0 + sa_ * w, y0 - ca * w),
                        (x1 + sa_ * w * 0.12, y1 - ca * w * 0.12),
                        (x1 - sa_ * w * 0.12, y1 + ca * w * 0.12)]
                cv.polygon(poly, INK, alpha=int(175 * (1 - k) ** 1.2))
        elif e["kind"] == "whoosh":
            # a tapered speed streak: a thin filled wedge that trails the limb
            life = e.get("dur", 0.18)
            if age > life or size < 0.8:
                continue
            k = age / life
            d = e.get("dir", 1)
            for i in range(3):
                spread = (i - 1) * 13
                ln = (52 + 26 * i) * u * (0.45 + 0.85 * (1 - k))
                slide = d * 34.0 * u * k
                taper = 0.35 + 0.65 * (1 - k)
                pts = []
                back = []
                for s_ in range(6):
                    f = s_ / 5
                    px = c[0] - d * slide + d * (ln * (f - 0.6))
                    py = c[1] + spread * 0.35 + math.sin(f * 2.4) * 3.4 * u + spread * 0.5 * f
                    w = (1.6 + 3.4 * math.sin(math.pi * f) ** 1.2) * u * taper
                    pts.append((px, py - w))
                    back.append((px, py + w))
                poly = [cv.wp(q) for q in pts + back[::-1]]
                cv.polygon(poly, (120, 116, 108), alpha=int(62 * (1 - k) ** 1.4))
        elif e["kind"] == "dust":
            life = 0.55
            if age > life:
                continue
            k = age / life
            for i in range(5):
                a = math.pi * (0.15 + 0.7 * i / 4)
                rr = (18 + 46 * k) * u * size
                px = c[0] + math.cos(a) * (24 + 70 * k) * u * size
                py = c[1] - abs(math.sin(a)) * (10 + 34 * k) * u * size
                cv.flush()
                cv.disc((px, py), rr * 0.35, (214, 208, 196))
        elif e["kind"] == "flash":
            if age > 0.12:
                continue
            k = age / 0.12
            overlay_flash.append(int(90 * (1 - k) ** 2 * size))


# -------------------------------------------------------------------- frame
def render_frame(t: float, scene, w=W, h=H) -> Image.Image:
    keys = scene["camera"]
    sx, sy, zoom = shake_at(scene["events"], t)
    cam = camera_at(keys, t)
    cam.sx, cam.sy = sx, sy
    cam.zoom *= 1.0 + zoom
    cv = Canvas(w, h, cam)
    draw_background(cv)

    pa = scene["a"].pose_at(t)
    pb = scene["b"].pose_at(t)

    # ground contact shadows, then the figures, far fighter first
    for p in (pb, pa):
        cv.flush()
        shadow(cv, p, alpha=52, squash=0.26)
    cv.flush()

    draw_figure(cv, pb, INK, accent=BLUE)
    draw_figure(cv, pa, INK, accent=RED)
    cv.flush()

    flash = []
    draw_effects(cv, scene["events"], t, flash)
    cv.flush()
    if flash:
        a = min(230, sum(flash))
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (w, h), (255, 253, 245)), a / 255.0), (0, 0))

    # fade up from black, and a slow fade to black on the last beat
    fade = 0.0
    if t < 0.5:
        fade = 1.0 - t / 0.5
    elif t > DURATION - 0.9:
        fade = (t - (DURATION - 0.9)) / 0.9
    if fade > 0.001:
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (w, h), (8, 8, 10)),
                                 min(1.0, fade) ** 1.2), (0, 0))
    return cv.img


# -------------------------------------------------------------------- audio
def _env(n, attack, decay):
    a = max(1, int(attack * SR))
    d = max(1, int(decay * SR))
    e = np.ones(n, np.float32)
    e[:a] = np.linspace(0, 1, a) ** 1.5
    if d < n:
        e[d:] = np.exp(-(np.arange(n - d) / SR) * 9.0)
    return e


def hit_sound(size=1.0):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (90 - 30 * size) * t) * np.exp(-t * 18)
    crack = np.random.default_rng(7).normal(0, 1, n) * np.exp(-t * 70) * 0.7
    s = (body * 0.9 + crack * 0.4) * _env(n, 0.002, 0.2)
    return (s * min(1.0, 0.55 + 0.35 * size)).astype(np.float32)


def whoosh_sound(dur=0.2, up=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, n).astype(np.float32)
    # one-pole low-pass whose cutoff sweeps for the "swipe" character
    out = np.empty(n, np.float32)
    y = 0.0
    for i in range(n):
        k = 0.02 + 0.10 * (i / n if up else 1 - i / n)
        y += k * (noise[i] - y)
        out[i] = y
    w = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return (out * w * 0.5).astype(np.float32)


def synth_audio(events, duration=DURATION) -> np.ndarray:
    n = int(duration * SR)
    mix = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(3)

    def add(sig, t, gain=1.0, pan=0.0):
        i0 = int(t * SR)
        if i0 >= n:
            return
        m = min(len(sig), n - i0)
        l = gain * (1 - max(0.0, pan) * 0.6)
        r = gain * (1 + min(0.0, pan) * 0.6)
        mix[i0:i0 + m, 0] += sig[:m] * l
        mix[i0:i0 + m, 1] += sig[:m] * r

    # slow pulse: a kick every half second, a shaker on the eighths
    t = 0.0
    while t < duration - 0.2:
        beat = np.sin(2 * np.pi * 52 * np.arange(int(0.30 * SR)) / SR) * np.exp(
            -np.arange(int(0.30 * SR)) / SR * 12)
        add(beat.astype(np.float32), t, 0.30 if t % 1.0 < 1e-6 else 0.16)
        t += 0.5
    for i in range(int(duration * 4)):
        tt = i * 0.25
        hsh = rng.normal(0, 1, int(0.05 * SR)).astype(np.float32)
        hsh *= np.exp(-np.arange(len(hsh)) / SR * 90)
        add(hsh, tt, 0.05)

    for e in events:
        pan = (e.get("x", 480) - 480) / 480.0
        if e["kind"] == "spark":
            add(hit_sound(e.get("size", 1.0)), e["t"], 0.85, pan)
        elif e["kind"] == "flash":
            add(hit_sound(1.6), e["t"], 1.0, pan)
        elif e["kind"] == "whoosh":
            add(whoosh_sound(e.get("dur", 0.2) * 1.6, e.get("dir", 1) > 0), e["t"] - 0.06, 0.35, pan)
        elif e["kind"] == "dust":
            add(hit_sound(0.4), e["t"], 0.35, pan)

    # soft limiter and fade-out at the very end
    mix = np.tanh(mix * 1.4) * 0.85
    fade = int(0.6 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return mix


def write_wav(path, stereo):
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())


# -------------------------------------------------------------------- render
def _frame_job(args):
    idx, t, w, h, scene = args
    img = render_frame(t, scene, w, h)
    path = os.path.join(TMP, f"f{idx:05d}.jpg")
    img.save(path, quality=94, subsampling=0)
    return path


TMP = ""


def render(out_path: str, w: int = W, h: int = H, workers: int = 2, audio: bool = True,
           start: float = 0.0, end: float = DURATION, preview_every: int = 0):
    global TMP
    import imageio_ffmpeg
    from multiprocessing import Pool

    TMP = os.path.join(os.path.dirname(out_path) or ".", "tmp", "frames")
    os.makedirs(TMP, exist_ok=True)
    scene = build()
    n0, n1 = int(round(start * FPS)), int(round(end * FPS))
    jobs = [(i, i / FPS, w, h, scene) for i in range(n0, n1)]

    print(f"[render] {len(jobs)} frames at {w}x{h}", flush=True)
    with Pool(workers) as pool:
        for k, _ in enumerate(pool.imap_unordered(_frame_job, jobs, chunksize=4), 1):
            if k % 24 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)}", flush=True)

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    silent = os.path.join(TMP, "_silent.mp4")
    subprocess.run([ff, "-y", "-framerate", str(FPS), "-i", os.path.join(TMP, "f%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    silent, "-loglevel", "error"], check=True)
    if audio:
        wav = os.path.join(TMP, "_audio.wav")
        mix = synth_audio(scene["events"], (n1 - n0) / FPS)
        write_wav(wav, mix)
        subprocess.run([ff, "-y", "-i", silent, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart",
                        "-shortest", out_path, "-loglevel", "error"], check=True)
    else:
        os.replace(silent, out_path)
    for f in os.listdir(TMP):
        if f.startswith("f") and f.endswith(".jpg"):
            os.remove(os.path.join(TMP, f))
    print(f"[done] {out_path}", flush=True)


def stills(times, w=960, h=540, out_dir="renders/preview"):
    os.makedirs(out_dir, exist_ok=True)
    scene = build()
    paths = []
    for t in times:
        p = os.path.join(out_dir, f"t{t:06.2f}.jpg")
        render_frame(t, scene, w, h).save(p, quality=92)
        paths.append(p)
    # contact sheet
    cols = 3
    rows = math.ceil(len(paths) / cols)
    sheet = Image.new("RGB", (w * cols, h * rows), (20, 20, 20))
    for i, p in enumerate(paths):
        sheet.paste(Image.open(p), ((i % cols) * w, (i // cols) * h))
    sheet.save(os.path.join(out_dir, "contact.jpg"), quality=88)
    print("contact:", os.path.join(out_dir, "contact.jpg"))
