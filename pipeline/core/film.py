"""Film assembly: shots, cameras, transitions, parallel rendering."""
from __future__ import annotations

import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from .camera import Camera, CameraTrack, CameraState
from .easing import ease, lerp, clamp
from .render import Painter, Post, finish, to_uint8


@dataclass
class Shot:
    """A single continuous shot: one camera, one draw function, one mood."""

    name: str
    dur: float
    cam: CameraTrack
    draw: Callable[[Painter, float], None]
    post: Callable[[float], Post] | None = None
    audio: Callable[[object, float], None] | None = None
    bg: tuple = (0.0, 0.0, 0.0)
    fade_in: float = 0.0
    fade_out: float = 0.0
    flash_at: tuple[float, ...] = ()
    whip_in: float = 0.0        # seconds of horizontal motion blur at the head
    whip_out: float = 0.0
    grain_seed: int = 0

    def local_post(self, t: float) -> Post:
        p = self.post(t) if self.post else Post()
        if self.fade_in > 0 and t < self.fade_in:
            p.fade = max(p.fade, 1.0 - ease("out", t / self.fade_in))
        if self.fade_out > 0 and t > self.dur - self.fade_out:
            p.fade = max(p.fade, 1.0 - ease("in", (self.dur - t) / self.fade_out))
        for ft in self.flash_at:
            dt = abs(t - ft)
            if dt < 0.055:
                p.flash = max(p.flash, 0.62 * (1 - dt / 0.055) ** 1.2)
        if self.whip_in > 0 and t < self.whip_in:
            p.motion_blur = max(p.motion_blur, 60 * (1 - ease("out", t / self.whip_in)))
        if self.whip_out > 0 and t > self.dur - self.whip_out:
            p.motion_blur = max(p.motion_blur, 60 * ease("in", (t - (self.dur - self.whip_out)) / self.whip_out))
        return p


@dataclass
class Film:
    shots: list[Shot] = field(default_factory=list)
    fps: int = 24
    width: int = 1920
    height: int = 1080
    title: str = ""

    def add(self, shot: Shot) -> Shot:
        self.shots.append(shot)
        return shot

    @property
    def duration(self) -> float:
        return sum(s.dur for s in self.shots)

    def schedule(self) -> list[tuple[Shot, float, float]]:
        out, t = [], 0.0
        for s in self.shots:
            out.append((s, t, t + s.dur))
            t += s.dur
        return out

    def _frame(self, idx: int) -> np.ndarray:
        t = idx / self.fps
        for shot, t0, t1 in self.schedule():
            if t0 <= t < t1 or (shot is self.shots[-1] and t <= t1):
                lt = min(t - t0, shot.dur - 1e-6)
                cam = Camera(shot.cam, self.width, self.height)
                st = cam.at(lt)
                p = Painter(self.width, self.height, cam, st, shot.bg)
                shot.draw(p, lt)
                post = shot.local_post(lt)
                out = finish(p.col, post, lt, p.glow, rng_seed=shot.grain_seed + idx // 37)
                return to_uint8(out)
        return np.zeros((self.height, self.width, 3), np.uint8)

    def render_frame(self, idx: int) -> np.ndarray:
        return self._frame(idx)

    def render(self, out_path: str | Path, start: float = 0.0, end: float | None = None,
               workers: int | None = None, crf: int = 17, audio: str | None = None,
               progress: bool = True, preview_every: int = 0, preview_dir: str | None = None,
               frames_dir: str | Path | None = None, keep_frames: bool = False,
               resume: bool = False):
        """Render to PNG frames (in parallel), then encode. Frame files make the
        render resumable and avoid sharing pipes with worker processes."""
        from .encode import VideoWriter, ffmpeg_exe
        import subprocess

        end = self.duration if end is None else end
        f0 = int(round(start * self.fps))
        f1 = int(round(end * self.fps))
        workers = workers or max(1, (os.cpu_count() or 2))
        fdir = Path(frames_dir or (Path(out_path).parent / f".frames_{Path(out_path).stem}"))
        fdir.mkdir(parents=True, exist_ok=True)
        t_start = time.time()
        total = f1 - f0

        def frame_path(i: int) -> Path:
            return fdir / f"f{i:06d}.png"

        todo = [i for i in range(f0, f1) if not (resume and frame_path(i).exists())]
        if progress:
            print(f"  rendering {len(todo)}/{total} frames on {workers} workers", flush=True)

        if workers <= 1 or len(todo) < 4:
            for k, i in enumerate(todo):
                _save(frame_path(i), self._frame(i))
                if progress and k % 12 == 0:
                    _report(k, len(todo), t_start)
        else:
            with ProcessPoolExecutor(max_workers=workers, initializer=_worker_setup,
                                     initargs=(self,)) as ex:
                jobs = [(i, str(frame_path(i))) for i in todo]
                for k, _ in enumerate(ex.map(_render_to, jobs, chunksize=2)):
                    if progress and k % 12 == 0:
                        _report(k, len(todo), t_start)

        # encode the image sequence
        if progress:
            print(f"  encoding {total} frames -> {out_path}", flush=True)
        pattern = str(fdir / "f%06d.png")
        cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
               "-framerate", str(self.fps), "-start_number", str(f0), "-i", pattern]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-level", "4.2", "-colorspace", "bt709",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart",
                "-r", str(self.fps)]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "320k", "-shortest"]
        cmd += [str(out_path)]
        subprocess.run(cmd, check=True)

        if preview_every and preview_dir:
            _make_previews(fdir, f0, f1, preview_every, preview_dir)
        if not keep_frames:
            for i in range(f0, f1):
                try:
                    frame_path(i).unlink()
                except FileNotFoundError:
                    pass
            try:
                fdir.rmdir()
            except OSError:
                pass
        return out_path

    def render_frames(self, frames_dir: str | Path, start: float = 0.0, end: float | None = None,
                      workers: int | None = None, progress: bool = True, resume: bool = False):
        """Render only the PNG sequence (useful for re-encoding without re-rendering)."""
        end = self.duration if end is None else end
        f0, f1 = int(round(start * self.fps)), int(round(end * self.fps))
        workers = workers or max(1, (os.cpu_count() or 2))
        fdir = Path(frames_dir)
        fdir.mkdir(parents=True, exist_ok=True)
        todo = [i for i in range(f0, f1) if not (resume and (fdir / f"f{i:06d}.png").exists())]
        t0 = time.time()
        if workers <= 1:
            for k, i in enumerate(todo):
                _save(fdir / f"f{i:06d}.png", self._frame(i))
                if progress and k % 12 == 0:
                    _report(k, len(todo), t0)
        else:
            with ProcessPoolExecutor(max_workers=workers, initializer=_worker_setup,
                                     initargs=(self,)) as ex:
                for k, _ in enumerate(ex.map(_render_to, [(i, str(fdir / f"f{i:06d}.png")) for i in todo],
                                             chunksize=2)):
                    if progress and k % 12 == 0:
                        _report(k, len(todo), t0)
        return fdir


def _save(path, arr):
    Image.fromarray(arr).save(path, compress_level=1)


def _render_to(job):
    idx, path = job
    _save(path, _FILM._frame(idx))
    return idx


def _make_previews(fdir: Path, f0: int, f1: int, every: int, out_dir: str):
    import shutil
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for i in range(f0, f1, every):
        src = fdir / f"f{i:06d}.png"
        if src.exists():
            shutil.copyfile(src, Path(out_dir) / f"prev_{i:06d}.jpg") if False else \
                Image.open(src).convert("RGB").save(Path(out_dir) / f"prev_{i:06d}.jpg", quality=88)


_FILM: Film | None = None


def _worker_setup(film: Film):
    global _FILM
    _FILM = film


def _worker_init(film: Film):
    _worker_setup(film)


def _render_one(idx: int) -> np.ndarray:
    return _FILM._frame(idx)


def _report(done: int, total: int, t0: float):
    el = time.time() - t0
    rate = done / el if el > 0 else 0
    eta = (total - done) / rate if rate > 0 else 0
    print(f"  frame {done}/{total}  {rate:.2f} fps  eta {eta/60:.1f} min", flush=True)
