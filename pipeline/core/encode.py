"""Video encoding: raw frames -> MP4 via bundled FFmpeg."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

FFMPEG = None


def ffmpeg_exe() -> str:
    global FFMPEG
    if FFMPEG:
        return FFMPEG
    cand = os.environ.get("FFMPEG")
    if cand and Path(cand).exists():
        FFMPEG = cand
        return FFMPEG
    try:
        import imageio_ffmpeg
        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        return FFMPEG
    except Exception:
        pass
    for c in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(c).exists():
            FFMPEG = c
            return FFMPEG
    raise RuntimeError("ffmpeg not found; pip install imageio-ffmpeg")


class VideoWriter:
    """Streams RGB24 frames into an H.264 MP4 (BT.709, faststart)."""

    def __init__(self, path: str | Path, w: int, h: int, fps: int = 24, crf: int = 17,
                 preset: str = "slow", audio: str | None = None, tune: str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.w, self.h, self.fps = w, h, fps
        cmd = [
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
            "-i", "pipe:0",
        ]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-movflags", "+faststart"]
        if tune:
            cmd += ["-tune", tune]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "320k", "-shortest"]
        cmd += [str(self.path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
        self.frames = 0

    def write(self, frame: np.ndarray):
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        if frame.shape != (self.h, self.w, 3):
            raise ValueError(f"frame shape {frame.shape} != {(self.h, self.w, 3)}")
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        self.frames += 1

    def close(self):
        if self.proc:
            self.proc.stdin.close()
            err = self.proc.stderr.read().decode("utf-8", "replace")
            code = self.proc.wait()
            if code != 0:
                raise RuntimeError(f"ffmpeg failed ({code}): {err[:2000]}")
            self.proc = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def mux(video: str | Path, audio: str | Path, out: str | Path, crf: int = 17):
    """Attach a soundtrack to an existing video without re-encoding the video."""
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest", str(out)]
    subprocess.run(cmd, check=True)


def probe(path: str | Path) -> dict:
    import json
    out = subprocess.run([ffmpeg_exe().replace("ffmpeg", "ffprobe") if False else "ffprobe",
                          "-v", "error", "-print_format", "json",
                          "-show_format", "-show_streams", str(path)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout)
