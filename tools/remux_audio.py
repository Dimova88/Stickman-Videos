"""Replace the soundtrack of an already-rendered master, without the pixels.

The video is the expensive part and the audio is a pure function of the scene,
so when only the sound changes there is no reason to draw 720 frames again:

    .venv/bin/python tools/remux_audio.py renders/steel_clash_720p.mp4 --set steel-mountain

The video stream is copied bit for bit; only the AAC track is replaced.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io

import imageio_ffmpeg

import fight.clashfilm as F


def duration_of(path: str) -> float:
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ff, "-i", path, "-hide_banner"], capture_output=True,
                         text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return F.DURATION


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("master")
    ap.add_argument("--set", default="steel-mountain")
    ap.add_argument("--keep", action="store_true", help="keep the .wav next to the master")
    args = ap.parse_args()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    secs = duration_of(args.master)
    sc = F.scene(args.set)
    audio = F.synth_audio(sc, secs)
    wav = os.path.join(os.path.dirname(args.master) or ".",
                       "tmp", "_remux.wav")
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    F.write_wav(wav, audio)
    tmp_out = args.master + ".new.mp4"
    subprocess.run([ff, "-y", "-i", args.master, "-i", wav,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-shortest", tmp_out,
                    "-loglevel", "error"], check=True)
    os.replace(tmp_out, args.master)
    if not args.keep:
        os.remove(wav)
    print(f"[audio] {args.master}  <- {args.set}  ({secs:.2f}s)")


if __name__ == "__main__":
    main()
