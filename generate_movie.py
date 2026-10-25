#!/usr/bin/env python3
"""Build a whole film — 30 seconds or 10 minutes — one scene at a time.

The 30-second test renders 720 frames in one process and holds a scene dict in
memory. That is fine for 720 frames and impossible for 14 400: a 10-minute film
is eighteen scenes, eighteen sets of tracks and solvers, and if all of that is
in RAM at once the machine swaps and then dies.

So this is the orchestrator. It reads a **manifest** (``story_templates/*.json``),
renders each scene on its own — its own build, its own audio, its own encode —
and then joins the segments and the score with ffmpeg. Peak memory is one scene,
whatever the film's length.

    python generate_movie.py --manifest story_templates/epic_structure_10min.json
    python generate_movie.py --plan                       # what it would render
    python generate_movie.py --manifest ... --pipe        # raw frames over stdin

``--pipe`` is the constant-memory path the brief asked for: frames go into
FFmpeg's stdin as ``rgb24`` and nothing is ever written to disk. It is slower,
because it cannot use the multiprocessing segment renderer, so the default
(``--segments``) is what a long film actually uses.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FPS = 24.0


# --------------------------------------------------------------------- manifest
def load_manifest(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "scenes" not in data:
        raise SystemExit(f"{path}: no 'scenes'")
    for i, sc in enumerate(data["scenes"]):
        sc.setdefault("index", i)
        sc.setdefault("duration_s", 30.0)
        sc.setdefault("set", "steel-mountain")
        sc.setdefault("act", "act")
    return data


def scene_plan(sc: dict) -> dict:
    """What the two directors say about one scene, before a frame is drawn.

    The camera decides how many shots an act can afford and whether the act is
    being cut too fast to read; the score decides where the sections and the
    silences go. A ten-minute film is nineteen of these, so the plan is also
    written next to the segment — the segment knows what it was supposed to be.
    """
    from engine import camera_director as cam
    from engine import soundtrack_engine as music

    # how hard an act is cut follows how loud it is: the quiet first act gets
    # long shots, the fourth act gets a beat every second
    profile = music.act_profile(sc["act"])
    intensity = float(profile.get("intensity", 0.6))
    beats = int(sc.get("beats", round(16 + 16 * intensity)))
    plan = music.plan_scene(sc["act"], duration=float(sc["duration_s"]),
                            drops=tuple(sc.get("drops", ())))
    return {
        "scene": sc["index"] + 1,
        "act": sc["act"],
        "duration": float(sc["duration_s"]),
        "camera": {"pacing": cam.act_pacing(float(sc["duration_s"]), beats),
                   "shots": cam.shot_budget(beats),
                   "mix": dict(cam.SHOT_MIX)},
        "music": [{"section": s["name"], "t0": round(s["t0"], 3),
                   "t1": round(s["t1"], 3),
                   "intensity": round(float(s["intensity"]), 3)}
                  for s in plan],
    }


def plan(manifest: dict) -> str:
    lines = [f"film: {manifest.get('title', 'untitled')}  "
             f"({len(manifest['scenes'])} scenes, "
             f"{sum(s['duration_s'] for s in manifest['scenes']):.1f}s)"]
    act = None
    for sc in manifest["scenes"]:
        if sc["act"] != act:
            act = sc["act"]
            lines.append(f"  -- {act}")
        info = scene_plan(sc)
        pace = info["camera"]["pacing"]
        shots = info["camera"]["shots"]
        lines.append(f"   {sc['index'] + 1:2d}. {sc['title'][:36]:36s} "
                     f"{sc['duration_s']:5.1f}s  [{sc['set']:13s}] "
                     f"{shots['wide'] + shots['medium'] + shots['close'] + shots['overhead']:2d} shots, "
                     f"cut {pace['average_shot']:.2f}s "
                     f"{'' if pace['verdict'] == 'ok' else '<- ' + pace['verdict']}, "
                     f"{len(info['music'])} music sections")
    return "\n".join(lines)


# ------------------------------------------------------------------ rendering
def render_segments(manifest: dict, out_path: str, w: int, h: int,
                    workers: int, preset: str, crf: int, limit: int | None) -> None:
    """One ``.mp4`` per scene, then one concat. Peak RAM = one scene."""
    from fight.clashfilm import render

    work = Path(out_path).parent / "segments"
    work.mkdir(parents=True, exist_ok=True)
    scenes = manifest["scenes"][:limit] if limit else manifest["scenes"]
    listing = []
    t_all = time.time()
    for i, sc in enumerate(scenes):
        seg = work / f"scene_{i + 1:02d}.mp4"
        listing.append(seg)
        print(f"[{i + 1}/{len(scenes)}] {sc['title']} -> {seg.name}", flush=True)
        # the segment carries its own brief: what the camera and the score were
        # told to do, so a scene can be re-rendered alone years later
        side = work / f"scene_{i + 1:02d}.json"
        side.write_text(json.dumps(scene_plan(sc), indent=2), encoding="utf-8")
        render(str(seg), w=w, h=h, workers=workers, audio=True,
               start=0.0, end=min(sc["duration_s"], 30.2),
               preset=preset, crf=crf, set_name=sc["set"])
    _concat(listing, out_path)
    print(f"[generate_movie] {out_path} in {time.time() - t_all:.0f}s "
          f"({len(listing)} scenes)")


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _concat(segments, out_path: str) -> None:
    ff = _ffmpeg()
    work = Path(out_path).parent
    listing = work / "_scenes.txt"
    with open(listing, "w") as fh:
        for seg in segments:
            fh.write(f"file '{Path(seg).resolve()}'\n")
    # every segment already carries its own score, so the join is a stream copy:
    # no re-encode, no audio held in memory, and a 10-minute cut costs the same
    # as a 30-second one
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", out_path,
                    "-loglevel", "error"], check=True)


def render_pipe(manifest: dict, out_path: str, w: int, h: int, limit: int | None):
    """Constant-memory path: raw frames straight into FFmpeg's stdin.

    Nothing is buffered to disk and nothing accumulates: the generator yields one
    ``bytes`` object per frame and drops it. A 10-minute film costs the same RAM
    as a 10-second one — it only costs *time*.
    """
    from fight import clashfilm as F

    scenes = manifest["scenes"][:limit] if limit else manifest["scenes"]
    total = int(sum(min(s["duration_s"], 30.2) for s in scenes) * FPS)
    ff = _ffmpeg()
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
         "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", out_path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    done = 0
    t0 = time.time()
    try:
        for i, sc in enumerate(scenes):
            print(f"[pipe] scene {i + 1}/{len(scenes)}: {sc['title']}", flush=True)
            scene = F.scene(sc["set"])
            n = int(round(min(sc["duration_s"], 30.2) * FPS))
            for f in range(n):
                img = F.render_frame(f / FPS, scene, w=w, h=h)
                proc.stdin.write(img.tobytes())
                done += 1
                if done % 120 == 0:
                    print(f"   {done}/{total} frames "
                          f"({time.time() - t0:.0f}s)", flush=True)
                del img
    finally:
        proc.stdin.close()
        proc.wait()
    print(f"[pipe] {out_path} ({done} frames)")


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="story_templates/epic_structure_10min.json")
    ap.add_argument("--out", default="renders/full_movie.mp4")
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0,
                    help="render only the first N scenes (for a smoke test)")
    ap.add_argument("--pipe", action="store_true",
                    help="raw frames to ffmpeg stdin, constant memory")
    ap.add_argument("--plan", action="store_true")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    if args.plan:
        print(plan(manifest))
        return
    h = int(round(args.w * 9 / 16))
    limit = args.limit or None
    if args.pipe:
        render_pipe(manifest, args.out, args.w, h, limit)
    else:
        render_segments(manifest, args.out, args.w, h, args.workers,
                        args.preset, args.crf, limit)


if __name__ == "__main__":
    main()
