"""Camera: the thing that turns a drawing into a film.

World units are "1080p pixels" (y down, origin at animation centre).  A camera
holds a position, zoom, roll, plus a shake layer and a set of one-shot punches.
Depth is expressed per element as a parallax factor: 1.0 = action plane,
0.2 = far background, 1.3 = extreme foreground.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .easing import Shake, Track, clamp, ease, lerp, value_noise


@dataclass
class CameraState:
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0
    rot: float = 0.0


@dataclass
class CameraTrack:
    """Keyed camera move. Every channel is optional and independently eased."""

    xs: Track = field(default_factory=Track)
    ys: Track = field(default_factory=Track)
    zs: Track = field(default_factory=Track)
    rs: Track = field(default_factory=Track)
    _shake: Shake | None = None
    _punches: list[tuple[float, float, float]] = field(default_factory=list)  # t0, amp, decay
    _handheld: float = 0.0
    _seed: int = 3

    def key(self, t: float, x: float | None = None, y: float | None = None,
            zoom: float | None = None, rot: float | None = None, ease_name: str = "smooth") -> "CameraTrack":
        if x is not None:
            self.xs.add(t, x, ease_name)
        if y is not None:
            self.ys.add(t, y, ease_name)
        if zoom is not None:
            self.zs.add(t, zoom, ease_name)
        if rot is not None:
            self.rs.add(t, rot, ease_name)
        return self

    def shake(self, amp: float = 26.0, decay: float = 9.0, freq: float = 34.0,
              rot_amp: float = 0.012) -> "CameraTrack":
        self._shake = Shake(amp=amp, decay=decay, freq=freq, rot_amp=rot_amp, seed=self._seed)
        return self

    def hit(self, t0: float, amp: float = 34.0, decay: float = 11.0) -> "CameraTrack":
        """Register an impact at t0; the strongest active punch wins."""
        if self._shake is None:
            self.shake()
        self._punches.append((t0, amp, decay))
        return self

    def handheld(self, amount: float = 1.0) -> "CameraTrack":
        self._handheld = amount
        return self

    def punch(self, t0: float, amp: float = 0.06, decay: float = 8.0) -> "CameraTrack":
        """Snap zoom-in spike at t0 (dolly punch)."""
        self._punches.append((t0, -amp, decay))
        return self

    def at(self, t: float) -> CameraState:
        x = self.xs.at(t) if self.xs.keys else 0.0
        y = self.ys.at(t) if self.ys.keys else 0.0
        z = self.zs.at(t) if self.zs.keys else 1.0
        r = self.rs.at(t) if self.rs.keys else 0.0

        # Slow drift adds life even on locked-off shots.
        if self._handheld:
            x += self._handheld * 3.2 * value_noise(t * 0.55, self._seed + 1)
            y += self._handheld * 2.4 * value_noise(t * 0.47, self._seed + 2)
            r += self._handheld * 0.0018 * value_noise(t * 0.9, self._seed + 4)

        for t0, amp, decay in self._punches:
            dt = t - t0
            if 0 <= dt < 4.0:
                env = math.exp(-decay * dt)
                z *= 1.0 + amp * env
                x += 0.35 * amp * 20 * env * value_noise(t * 40, self._seed + 9)
                y += 0.35 * amp * 20 * env * value_noise(t * 37, self._seed + 11)

        if self._shake is not None:
            # combine every hit into a single decaying envelope
            best = 0.0
            for t0, amp, decay in self._punches:
                dt = t - t0
                if 0 <= dt < 4.0:
                    best = max(best, amp * math.exp(-decay * dt))
            sx, sy, sr = self._shake.at(t)
            if best:
                sx, sy, sr = sx * best / max(self._shake.amp, 1e-6) * 1.0, sy * best / max(self._shake.amp, 1e-6), sr * best / max(self._shake.amp, 1e-6)
            x += sx
            y += sy
            r += sr

        return CameraState(x=x, y=y, zoom=max(z, 0.05), rot=r)


class Camera:
    """A camera bound to a track plus the projection maths for one frame."""

    def __init__(self, track: CameraTrack, width: int, height: int):
        self.track = track
        self.w = width
        self.h = height
        self.s = height / 1080.0

    def at(self, t: float) -> CameraState:
        return self.track.at(t)

    @staticmethod
    def matrix(st: CameraState, s: float):
        c, sn = math.cos(st.rot), math.sin(st.rot)
        m = st.zoom * s
        return c * m, -sn * m, sn * m, c * m  # a, b, c, d

    def project(self, p: Sequence[float], st: CameraState, depth: float = 1.0) -> tuple[float, float]:
        a, b, c, d = self.matrix(st, self.s)
        k = depth
        dx, dy = (p[0] - st.x) * k, (p[1] - st.y) * k
        return (self.w / 2 + a * dx + b * dy, self.h / 2 + c * dx + d * dy)

    def scale(self, st: CameraState, depth: float = 1.0) -> float:
        return st.zoom * self.s * depth

    def project_pts(self, pts, st: CameraState, depth: float = 1.0):
        return [self.project(p, st, depth) for p in pts]

    def image_coeffs(self, st: CameraState, rect: tuple[float, float, float, float],
                     img_size: tuple[int, int], depth: float = 1.0):
        """Affine coefficients mapping DEST screen px -> SOURCE image px.

        rect = (cx, cy, w, h) of the plate in world units.
        """
        cx, cy, w, h = rect
        iw, ih = img_size
        a, b, c, d = self.matrix(st, self.s)
        det = a * d - b * c
        ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
        # screen -> world
        tx = self.w / 2 - (ia * (a * 0) + ib * 0)
        # world = pos + k^-1 * M^-1 * (screen - centre)
        px = st.x
        py = st.y
        sx = px - (ia * self.w / 2 + ib * self.h / 2)
        sy = py - (ic * self.w / 2 + id_ * self.h / 2)
        # world -> image
        k = iw / w
        return (
            ia / depth * k, ib / depth * k, sx * k + iw / 2 - cx * k,
            ic / depth * k, id_ / depth * k, sy * k + ih / 2 - cy * k,
        )


def fit_rect(img_size: tuple[int, int], cover_w: float = 1920, cover_h: float = 1080,
             center=(0.0, 0.0)) -> tuple[float, float, float, float]:
    """Sized so the plate covers the frame at zoom 1 from its centre."""
    iw, ih = img_size
    k = max(cover_w / iw, cover_h / ih)
    return (center[0], center[1], iw * k, ih * k)


def follow(get_pos: Callable[[float], tuple[float, float]], lag: float = 0.12,
           look: float = 0.35, zoom_key: Track | None = None) -> CameraTrack:
    """Utility: build a camera track that trails a target."""
    raise NotImplementedError("authoring helper: key the camera explicitly for control")
