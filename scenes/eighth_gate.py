"""THE EIGHTH GATE — Chapter 0 teaser (30 s).

Structure (see docs/screenplay/ for the full 8-minute treatment):
    1  Black, one ember, a bell
    2  Establishing: moon, mountains, fog, a lone figure
    3  Low angle: the gate, lanterns, rain
    4  Macro: a foot on wet stone
    5  Close: the eyes ignite
    6  Whip pan: the gate opens
    7  Reverse: the rival in the light
    8  Face-off, low angle
    9  Clash: dash -> impact -> aftermath
    10 Title
"""
from __future__ import annotations

import math

import numpy as np

from pipeline.core import fx, sets
from pipeline.core.audio import (Mix, braam, boom, chime, choir, chord, cloth, heart, pad, riser,
                           slash, step, taiko, whoosh)
from pipeline.core.camera import Camera, CameraTrack
from pipeline.core.character import POSES, Look, Rig, draw_character, draw_smear, solve
from pipeline.core.easing import clamp, ease, lerp, smoothstep, value_noise
from pipeline.core.film import Film, Shot
from pipeline.core.render import Painter, Post

W, H = 1920, 1080

HERO = Look(color=(0.87, 0.91, 0.98), rim=(0.35, 0.78, 1.0), ink=(0.012, 0.016, 0.026),
            eye=(0.72, 0.95, 1.0), head_style="light", rim_amount=1.0, aura=(0.25, 0.6, 1.0),
            trail=(0.5, 0.8, 1.0), w_scale=1.0)
RIVAL = Look(color=(0.95, 0.90, 0.92), rim=(1.0, 0.36, 0.22), ink=(0.03, 0.012, 0.012),
             eye=(1.0, 0.45, 0.16), head_style="light", rim_amount=1.0, aura=(1.0, 0.3, 0.12),
             trail=(1.0, 0.42, 0.2), w_scale=1.05)
RIG = Rig()

PAL = sets.Palette(sky_top=(0.016, 0.026, 0.058), sky_bottom=(0.20, 0.10, 0.13),
                   haze=(0.36, 0.26, 0.34), far=(0.085, 0.10, 0.17), mid=(0.045, 0.05, 0.09),
                   near=(0.010, 0.011, 0.018), accent=(1.0, 0.58, 0.22), accent2=(0.42, 0.76, 1.0),
                   moon=(0.86, 0.88, 0.96))


# --------------------------------------------------------------------- helpers
def ambient(p: Painter, t: float, rain=False, embers=40, mote=26):
    fx.Embers(count=embers, color=(1.0, 0.5, 0.16), seed=5, speed=20).draw(p, t)
    fx.dust_motes(p, t, count=mote)
    if rain:
        fx.rain(p, t, count=220, alpha=0.20)


def horizon_ground(p, t, y=250.0, pal=PAL, wet=True, reflect_sources=(), light_col=None, light_x=0.0):
    sets.ground(p, pal, y=y, wet=wet, light_col=light_col, light_x=light_x, detail=1.0)
    if reflect_sources:
        sets.wet_reflection(p, reflect_sources, y=y, t=t)


def hero_pose(name, x, y, facing=1, **kw):
    return POSES[name].copy(px=x, py=y, facing=facing, **kw)


# ======================================================================= shots
def _clash_post(t: float) -> Post:
    p = Post(bloom=0.5, vignette=0.42, ca=1.6 if t > 1.0 else 1.0, contrast=1.12,
             flash_color=(1, 0.95, 0.85))
    # two inverted frames at the moment of contact: the classic anime impact frame
    if 1.05 <= t < 1.135:
        p.invert = 0.92
        p.posterize = 0.75
        p.bloom = 0.2
    return p


def build() -> Film:
    f = Film(fps=24, width=W, height=H, title="THE EIGHTH GATE — Chapter 0")

    # ------------------------------------------------------------------ S01
    def s01_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.004, 0.005, 0.010), bottom=(0.03, 0.022, 0.045))
        sets.fog_band(p, t, 120, thickness=140, color=(0.09, 0.09, 0.15), alpha=0.35, depth=0.6)
        # one lantern very far away, the only light in the world
        sets.lantern(p, -120, -10, r=16, t=t, glow=1.1, cord=0, depth=0.7)
        fx.Embers(count=22, color=(1.0, 0.45, 0.12), seed=9, speed=14, size=(0.8, 2.0)).draw(p, t)

    s01 = Shot("s01_void", 2.6,
               CameraTrack().key(0, 60, 30, 1.0, 0).key(2.6, 10, -20, 1.32, 0, "soft").handheld(0.4),
               s01_draw,
               post=lambda t: Post(bloom=0.5, vignette=0.62, grain=0.035, saturation=0.95),
               fade_in=0.9)

    # ------------------------------------------------------------------ S02
    def s02_draw(p: Painter, t: float):
        sets.sky(p, PAL)
        sets.stars(p, t, count=190, depth=0.25)
        # warm light pollution on the horizon
        p.blob((180, 120), 780, (1.0, 0.45, 0.18), alpha=0.16, depth=0.2, additive=True, soft=1.2)
        sets.moon(p, (-430, -360), r=104, t=t, halo=0.7, depth=0.28)
        sets.clouds(p, t, PAL, depth=0.34, count=6, alpha=0.38)
        sets.mountains_ridge(p, t, PAL.far, depth=0.42, seed=47, base_y=150, amp=300, freq=0.0016,
                             rim=(0.32, 0.40, 0.62), rim_w=2.2, rim_a=0.30, rim_glow=0.2)
        sets.mountains_ridge(p, t, tuple(np.array(PAL.mid) * 0.9), depth=0.6, seed=51, base_y=235,
                             amp=230, freq=0.0026, rim=(0.22, 0.26, 0.40), rim_w=1.8, rim_a=0.5)
        sets.fog_band(p, t, 215, thickness=170, color=(0.42, 0.30, 0.34), alpha=0.30, depth=0.55)
        horizon_ground(p, t, y=300, wet=False)
        # lone figure on the near ridge
        sk = solve(hero_pose("stand_tall", 210, 205, 1, scale=0.95), RIG)
        draw_character(p, sk, RIG, HERO, depth=0.85, eye_glow=0.0, rim_on=True, light=(-0.7, -1.0))
        ambient(p, t, embers=26, mote=18)

    s02 = Shot("s02_wide", 3.4,
               CameraTrack().key(0, 320, 190, 0.72, -0.012).key(3.4, 130, 110, 0.86, 0.004, "soft")
               .handheld(0.5),
               s02_draw,
               post=lambda t: Post(bloom=0.42, vignette=0.52, contrast=1.16, saturation=1.06),
               fade_in=0.5)

    # ------------------------------------------------------------------ S03
    def s03_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.012, 0.020, 0.048), bottom=(0.22, 0.10, 0.10))
        p.blob((0, 150), 700, (1.0, 0.42, 0.14), alpha=0.20, depth=0.2, additive=True, soft=1.1)
        sets.moon(p, (-720, -470), r=86, t=t, halo=0.55, depth=0.26)
        sets.clouds(p, t, PAL, depth=0.3, count=5, alpha=0.28)
        sets.mountains_ridge(p, t, PAL.far, depth=0.4, base_y=120, amp=210, freq=0.002,
                             rim=(0.34, 0.26, 0.34), rim_w=2.0, rim_a=0.4, rim_glow=0.2)
        # shrine steps + gate
        horizon_ground(p, t, y=300, wet=True, light_col=(1.0, 0.5, 0.2), light_x=0.0)
        sets.stairs(p, t, y=330, steps=7, w0=520, rise=40, run=70, color=(0.030, 0.028, 0.040),
                    light=PAL.accent)
        sets.torii(p, t, PAL, x=0, y=250, scale=1.55, depth=1.0, color=(0.20, 0.055, 0.045),
                   light=(1.0, 0.55, 0.24), open_glow=0.0)
        sets.fog_band(p, t, 320, thickness=140, alpha=0.22, depth=0.9, color=(0.5, 0.3, 0.3))
        for i in range(4):
            sets.lantern(p, -520 + i * 340, 20 + (i % 2) * 40, r=20, t=t, sway=10, seed=i, glow=1.2,
                         depth=0.95, cord=70)
        ambient(p, t, rain=True, embers=20, mote=20)

    s03 = Shot("s03_gate", 4.0,
               CameraTrack().key(0, 70, 250, 0.46, 0.024).key(4.0, 10, 150, 0.55, -0.006, "soft")
               .handheld(0.5),
               s03_draw,
               post=lambda t: Post(bloom=0.44, vignette=0.52, contrast=1.14, ca=1.1),
               whip_in=0.0)

    # ------------------------------------------------------------------ S04
    def s04_draw(p: Painter, t: float):
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.030, 0.036, 0.062), (0.004, 0.005, 0.009)))
        r = np.random.default_rng(77)
        for i in range(14):                       # wet stone, receding slabs
            y = -560 + (i ** 1.5) * 30
            hgt = 16 + (i ** 1.5) * 3.2
            shade = 0.016 + 0.0030 * i
            p.polygon_world([(-4000, y), (4000, y), (4000, y + hgt), (-4000, y + hgt)],
                            (shade, shade * 1.15, shade * 1.9), depth=1.0)
            p.line([(-4000, y), (4000, y)], 0.8 + i * 0.5, (0.20, 0.24, 0.34), alpha=0.35, depth=1.0)
        for i in range(26):                       # cracks
            x0 = r.uniform(-1600, 1600); y0 = r.uniform(-540, 560)
            p.line([(x0, y0), (x0 + r.uniform(-220, 220), y0 + r.uniform(6, 54))], 1.2,
                   (0.18, 0.22, 0.32), alpha=0.22, depth=1.0)

        impact_t = 0.72
        lift = 1.0 - ease("out", clamp(t / impact_t))
        pose = POSES["run"].copy(px=-10, py=60 - 120 * lift, facing=1, scale=1.0)
        draw_character(p, solve(pose, RIG), RIG, HERO, depth=1.0, eye_glow=0.0, light=(0.5, -1.0))
        if t > impact_t:
            u = clamp((t - impact_t) / 1.1)
            for k in range(4):
                uk = clamp(u - k * 0.09)
                rr = 18 + 200 * ease("expo_out", uk)
                p.circle((24, 176), rr, (0.55, 0.74, 1.0), alpha=(1 - uk) ** 1.5 * 0.55,
                         ring=1.4 + 1.6 * k, additive=True, depth=1.0, glow=0.14 * (1 - uk),
                         glow_color=(0.5, 0.72, 1.0))
            fx.Particles(x=24, y=176, t0=impact_t, count=30, speed=(150, 540),
                         angle=(math.pi * 1.06, math.pi * 1.94), gravity=1500, life=(0.2, 0.65),
                         size=(0.9, 2.4), color=(0.80, 0.92, 1.0), color_end=(0.4, 0.6, 1.0),
                         seed=13, glow=0.9).draw(p, t)
            fx.ground_dust(p, 24, 182, t, impact_t, width=460, count=9, dur=0.9)
        fx.dust_motes(p, t, count=26)

    s04 = Shot("s04_foot", 2.0,
               CameraTrack().key(0, -55, 165, 4.4, -0.05).key(2.0, -25, 148, 4.9, -0.015, "soft")
               .handheld(0.8),
               s04_draw,
               post=lambda t: Post(bloom=0.5, vignette=0.5, ca=1.4, exposure=1.12),
               whip_in=0.18)

    # ------------------------------------------------------------------ S05
    def s05_draw(p: Painter, t: float):
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.024, 0.028, 0.05), (0.004, 0.005, 0.009)))
        ign = ease("out", clamp((t - 0.85) / 1.15))
        if ign > 0:
            fx.god_rays(p, t, origin=(-180, 60), count=7, spread=1.6, length=2200,
                        color=(0.55, 0.8, 1.0), alpha=0.030 * ign, depth=0.6, seed=21)
        sk = solve(POSES["stand_tall"].copy(px=0, py=190, facing=1), RIG)
        hx, hy = sk.head_c
        # back-light from behind the head so the rim reads
        p.circle((hx - 30, hy - 20), sk.head_r * 1.5, (0.45, 0.8, 1.0), alpha=0.0, depth=0.9,
                 glow=0.30 * ign, glow_color=(0.5, 0.85, 1.0))
        draw_character(p, sk, RIG, HERO, depth=1.0, eye_glow=0.15 + 0.85 * ign,
                       light=(-0.55, -1.0), aura=0.25 * ign)
        sway = math.sin(t * 2.4) * 7
        p.line([(hx - sk.head_r * 0.5, hy - sk.head_r * 0.55),
                (hx - sk.head_r * 1.9, hy - sk.head_r * 0.25 + sway),
                (hx - sk.head_r * 2.9, hy + sk.head_r * 0.15 + sway)], 3.0,
               tuple(HERO.color), alpha=0.75, taper=0.12, glow=0.3, glow_color=HERO.rim)
        if ign > 0.35:
            fx.speed_lines(p, t, 0.95, dur=0.55, count=30, alpha=0.16 * ign, seed=19)
        fx.dust_motes(p, t, count=24)

    s05 = Shot("s05_eyes", 3.0,
               CameraTrack().key(0, 6, 118, 6.4, 0.02).key(3.0, 12, 112, 7.2, -0.008, "soft")
               .hit(1.15, 10.0, 7.0).handheld(0.7),
               s05_draw,
               post=lambda t: Post(bloom=0.52, vignette=0.55, ca=1.6, contrast=1.14),
               whip_in=0.12)

    # ------------------------------------------------------------------ S06
    def s06_draw(p: Painter, t: float):
        op = ease("in_out", clamp(t / 1.5))
        sets.sky(p, PAL, top=(0.01, 0.012, 0.026), bottom=(0.13, 0.08, 0.12))
        sets.mountains_ridge(p, t, PAL.far, depth=0.4, base_y=140, amp=230, freq=0.002)
        fx.god_rays(p, t, origin=(0, 260), count=8, spread=1.25, length=2600, alpha=0.045 * op,
                    color=(1.0, 0.7, 0.4), seed=17, depth=0.98)
        sets.torii(p, t, PAL, x=0, y=280, scale=1.7, depth=1.0, color=(0.16, 0.05, 0.04),
                   light=(1.0, 0.55, 0.22), open_glow=op)
        sets.stairs(p, t, y=340, steps=6, w0=560, rise=40, run=70, color=(0.018, 0.018, 0.028),
                    light=PAL.accent)
        sets.fog_band(p, t, 336, thickness=60, alpha=0.06, depth=0.96, color=(0.5, 0.32, 0.26),
                      width=6000)
        # dust kicked up by the opening
        for i in range(10):
            ph = i * 1.7
            u = clamp((t - 0.35 - i * 0.05) / 2.2)
            if u <= 0 or u >= 1:
                continue
            side = -1 if i % 2 else 1
            p.blob((side * (34 + i * 16), 296 - 26 * u), 26 + 34 * u, (0.60, 0.44, 0.36),
                   alpha=0.16 * (1 - u) ** 1.4, depth=0.98, soft=1.2)
        ambient(p, t, rain=False, embers=50, mote=30)

    s06 = Shot("s06_open", 3.0,
               CameraTrack().key(0, 120, 150, 0.78, 0.02).key(3.0, 0, 60, 0.60, -0.008, "soft")
               .hit(1.35, 22.0, 6.0).handheld(0.6),
               s06_draw,
               post=lambda t: Post(bloom=0.44, vignette=0.50, contrast=1.14, ca=1.3, streak=0.14),
               whip_in=0.25, flash_at=(1.35,))

    # ------------------------------------------------------------------ S07
    def s07_draw(p: Painter, t: float):
        # over-the-shoulder: rival stands in the doorway light
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.10, 0.06, 0.05), (0.02, 0.015, 0.02)))
        fx.god_rays(p, t, origin=(120, 300), count=9, spread=1.35, length=2200,
                    color=(1.0, 0.62, 0.34), alpha=0.045, depth=0.9, seed=33, flicker=0.5)
        p.blob((120, 210), 460, (1.0, 0.5, 0.26), alpha=0.16, depth=0.95, additive=True, soft=1.5)
        sets.torii(p, t, PAL, x=120, y=250, scale=1.5, depth=1.0, color=(0.03, 0.012, 0.01),
                   light=(1.0, 0.5, 0.2), open_glow=1.0)
        sets.fog_band(p, t, 260, thickness=150, alpha=0.3, depth=0.95, color=(0.45, 0.28, 0.2))
        sk = solve(POSES["cross_arms"].copy(px=120, py=150, facing=-1, scale=1.05), RIG)
        draw_character(p, sk, RIG, RIVAL, depth=1.0, eye_glow=0.85, aura=0.55,
                       light=(-0.2, -1.0))
        # near shoulder in the foreground (out of focus)
        p.circle((-520, 300), 150, (0.02, 0.02, 0.03), alpha=0.9, depth=1.35)
        p.blob((-520, 300), 190, (0.0, 0.0, 0.0), alpha=0.9, depth=1.4, soft=0.7)
        fx.Embers(count=40, color=(1.0, 0.42, 0.12), seed=15, speed=18).draw(p, t)
        fx.wind_streaks(p, t, count=26, alpha=0.10, speed=700, depth=0.7)

    s07 = Shot("s07_rival", 3.5,
               CameraTrack().key(0, -20, 190, 1.30, 0.012).key(3.5, 30, 150, 1.52, -0.006, "soft")
               .handheld(0.5),
               s07_draw,
               post=lambda t: Post(bloom=0.46, vignette=0.52, contrast=1.12, ca=1.4, saturation=1.03,
                                   flash_color=(1.0, 0.85, 0.7)),
               whip_in=0.2)

    # ------------------------------------------------------------------ S08
    def s08_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.008, 0.010, 0.022), bottom=(0.12, 0.06, 0.09))
        sets.moon(p, (420, -460), r=70, t=t, halo=0.5, depth=0.28)
        sets.mountains_ridge(p, t, PAL.far, depth=0.42, base_y=120, amp=200, freq=0.0022)
        sets.fog_band(p, t, 210, thickness=170, alpha=0.32, depth=0.6, color=(0.3, 0.22, 0.3))
        horizon_ground(p, t, y=300, wet=True,
                       reflect_sources=[(-260, 0, 90, (0.4, 0.75, 1.0)), (300, 0, 90, (1.0, 0.4, 0.2))])
        # hero foreground left, rival right
        hx = -180 + 5 * math.sin(t * 1.6)
        rx = 190 - 4 * math.sin(t * 1.4 + 1)
        draw_character(p, solve(hero_pose("guard", hx, 175, 1, scale=1.02), RIG), RIG, HERO,
                       depth=1.0, eye_glow=0.9, aura=0.35, light=(0.4, -1.0))
        draw_character(p, solve(hero_pose("guard_low", rx, 180, -1, scale=1.05), RIG), RIG, RIVAL,
                       depth=1.0, eye_glow=0.85, aura=0.4, light=(-0.4, -1.0))
        sets.stairs(p, t, y=330, steps=5, w0=700, rise=30, run=60, color=(0.014, 0.014, 0.022),
                    light=None, alpha=0.85)
        ambient(p, t, embers=70, mote=34)
        fx.wind_streaks(p, t, count=34, alpha=0.12, speed=820, depth=0.8)

    s08 = Shot("s08_faceoff", 3.0,
               CameraTrack().key(0, 0, 210, 1.30, 0.02).key(3.0, 0, 190, 1.45, -0.004, "soft")
               .handheld(0.8),
               s08_draw,
               post=lambda t: Post(bloom=0.42, vignette=0.46, contrast=1.16, ca=1.0),
               whip_in=0.16)

    # ------------------------------------------------------------------ S09
    def s09_draw(p: Painter, t: float):
        # dash -> clash -> debris, all in one continuous camera
        sets.sky(p, PAL, top=(0.006, 0.008, 0.018), bottom=(0.10, 0.05, 0.08))
        sets.moon(p, (520, -430), r=64, t=t, halo=0.4, depth=0.3)
        sets.mountains_ridge(p, t, PAL.far, depth=0.42, base_y=110, amp=190, freq=0.0024)
        sets.torii(p, t, PAL, x=0, y=300, scale=1.35, depth=0.55, color=(0.03, 0.014, 0.012),
                   light=(1.0, 0.5, 0.2), open_glow=0.7)
        horizon_ground(p, t, y=300, wet=True,
                       reflect_sources=[(0, 0, 160, (1.0, 0.5, 0.25))])

        clash = 1.05
        # hero dashes in
        if t < clash:
            u = clamp(t / clash)
            hx = lerp(-980, -120, ease("whip", u) ** 0.85)
            pose = POSES["dash"] if u < 0.85 else POSES["punch"]
            draw_character(p, solve(pose.copy(px=hx, py=178, facing=1), RIG), RIG, HERO, depth=1.0,
                           eye_glow=1.0, aura=0.5 + 0.5 * u)
            # speed trails
            for k in range(3):
                gx = hx - 34 - k * 32
                alpha = 0.18 - k * 0.045
                sk_g = solve(pose.copy(px=gx, py=178, facing=1), RIG)
                for a, b, wd in ((sk_g.pelvis, sk_g.chest, RIG.w_spine),
                                 (sk_g.shoulder, sk_g.elbow_f, RIG.w_arm),
                                 (sk_g.elbow_f, sk_g.hand_f, RIG.w_fore),
                                 (sk_g.hip, sk_g.knee_f, RIG.w_leg),
                                 (sk_g.knee_f, sk_g.foot_f, RIG.w_shin)):
                    p.line([a, b], wd * 1.6, (0.45, 0.75, 1.0), alpha=alpha, depth=1.0,
                           additive=True, glow=alpha * 3.0, glow_color=(0.4, 0.7, 1.0))
                p.circle(sk_g.head_c, RIG.head_r * 0.9, (0.45, 0.75, 1.0), alpha=alpha * 0.8,
                         depth=1.0, additive=True, glow=alpha * 2.0, glow_color=(0.4, 0.7, 1.0))
            fx.dash_lines(p, t, 0.0, dur=clash, count=24, alpha=0.28, seed=41)
        else:
            draw_character(p, solve(POSES["punch"].copy(px=-120, py=178, facing=1), RIG), RIG, HERO,
                           depth=1.0, eye_glow=1.0, aura=0.9)

        # rival
        if t < clash:
            draw_character(p, solve(hero_pose("guard_low", 150, 180, -1), RIG), RIG, RIVAL, depth=1.0,
                           eye_glow=0.9, aura=0.4)
        else:
            u = (t - clash) / 1.6
            rx = 150 + 420 * ease("out", clamp(u))
            draw_character(p, solve(POSES["hit_hard"].copy(px=rx, py=180 - 60 * u, facing=-1), RIG),
                           RIG, RIVAL, depth=1.0, eye_glow=0.7)

        # clash fx
        if t >= clash:
            u = t - clash
            fx.impact_flash(p, (30, 130), t, clash, size=120, color=(1.0, 0.9, 0.78), seed=5,
                            core_size=0.20)
            fx.shockwave(p, (30, 130), t, clash, r1=420, dur=0.55, width=6)
            fx.speed_lines(p, t, clash, dur=0.36, count=80, alpha=0.34, seed=11)
            fx.Particles(x=30, y=130, t0=clash, count=95, speed=(380, 1600), angle=(0, 6.28),
                         gravity=700, drag=1.6, life=(0.25, 0.85), size=(0.7, 2.2),
                         color=(1.0, 0.88, 0.55), color_end=(1.0, 0.25, 0.06), seed=7,
                         glow=0.85, streak=1.6).draw(p, t)
            fx.ground_dust(p, 30, 300, t, clash, width=1400, count=30, dur=1.6)
        ambient(p, t, embers=60, mote=30)

    s09 = Shot("s09_clash", 3.5,
               CameraTrack().key(0, 120, 250, 0.78, 0.03).key(0.7, 60, 220, 0.92, 0.012, "soft")
               .key(1.35, 10, 175, 1.06, -0.03, "impact").key(3.5, -60, 205, 0.98, -0.01, "soft")
               .hit(1.05, 34.0, 9.0).handheld(0.7),
               s09_draw,
               post=lambda t: _clash_post(t),
               whip_in=0.1, flash_at=(1.05,))

    # ------------------------------------------------------------------ S10
    def s10_draw(p: Painter, t: float):
        W, H = p.w, p.h
        k = H / 1080.0
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.004, 0.005, 0.008), (0.004, 0.005, 0.008)))
        a = ease("out", clamp((t - 0.12) / 0.7))
        b = ease("out", clamp((t - 0.8) / 0.6))
        # a shaft of light behind the type
        fx.god_rays(p, t, origin=(W / 2, H * 0.30), count=5, spread=0.85, length=1500 * k,
                    color=(1.0, 0.62, 0.30), alpha=0.030 * a, depth=0.9, seed=51)
        p.blob((W / 2, H * 0.42), 520 * k, (1.0, 0.55, 0.26), alpha=0.06 * a, depth=0.95,
               additive=True, soft=1.6)
        fx.Embers(count=34, color=(1.0, 0.5, 0.15), seed=5, speed=16).draw(p, t)
        if a > 0:
            p.text("THE EIGHTH GATE", (W / 2, H / 2 - 16 * k), 104 * k, (1, 1, 1), alpha=a, bold=True,
                   glow=1.3 * a, tracking=12 * k)
            p.line([(W / 2 - 340 * k * a, H / 2 + 74 * k), (W / 2 + 340 * k * a, H / 2 + 74 * k)],
                   2.4 * k, (1.0, 0.72, 0.4), alpha=0.85 * a, glow=0.6 * a, glow_color=(1.0, 0.7, 0.35))
        if b > 0:
            p.text("C H A P T E R   Z E R O   ·   T H E   D O O R", (W / 2, H / 2 + 134 * k), 24 * k,
                   (0.85, 0.86, 0.92), alpha=0.8 * b, bold=False)
        fx.dust_motes(p, t, count=20)

    s10 = Shot("s10_title", 2.0,
               CameraTrack().key(0, 0, 0, 1.06, 0).key(2.0, 0, 0, 1.0, 0, "soft"),
               s10_draw,
               post=lambda t: Post(bloom=0.45, vignette=0.5, grain=0.032),
               fade_in=0.0, fade_out=0.25)

    for s in (s01, s02, s03, s04, s05, s06, s07, s08, s09, s10):
        f.add(s)
    return f


# ======================================================================= audio
def soundtrack(duration: float) -> Mix:
    m = Mix(duration)
    T = 0.0
    # ---- 01 void
    m.add(*chime(0.05, base=520, dur=3.4, amp=0.22))
    m.add(*boom(0.05, amp=0.45, f0=90, f1=32))
    m.add(*pad(0.0, 4.2, chord(["D2", "A2", "D3"]), amp=0.55, cutoff=700))
    # ---- 02 wide
    t = 2.6
    m.add(*braam(t + 0.15, amp=0.55, root=36.7))
    m.add(*pad(t, 3.6, chord(["D2", "F2", "A2", "D3"]), amp=0.5, cutoff=900))
    m.add(*whoosh(t + 0.1, dur=1.4, f0=120, f1=900, amp=0.28))
    # ---- 03 gate
    t = 6.0
    m.add(*whoosh(t, dur=0.8, f0=900, f1=160, amp=0.3, reverse=True))
    m.add(*pad(t, 4.0, chord(["Bb1", "F2", "Bb2", "D3"]), amp=0.6, cutoff=800))
    m.add(*taiko(t + 0.5, amp=0.45, pitch=0.85))
    m.add(*boom(t + 0.5, amp=0.4, f0=80, f1=30))
    # rain bed
    m.add(t, _rain_bed(4.2, seed=3), gain=0.10)
    # ---- 04 foot
    t = 10.0
    m.add(*step(t + 0.72, amp=0.55, pitch=0.8))
    m.add(*whoosh(t + 0.6, dur=0.35, f0=300, f1=2200, amp=0.22))
    m.add(t + 0.78, _splash(0.7, seed=5), gain=0.25)
    m.add(*pad(t, 2.0, chord(["D2", "A2"]), amp=0.3, cutoff=600))
    # ---- 05 eyes
    t = 12.0
    m.add(*heart(t + 0.2, amp=0.5, pitch=0.9))
    m.add(*heart(t + 1.0, amp=0.42, pitch=0.9))
    m.add(*riser(t + 0.7, dur=1.9, amp=0.4, f_end=4200))
    m.add(*chime(t + 1.05, base=880, dur=3.0, amp=0.30))
    m.add(*pad(t, 3.2, chord(["D2", "F2", "A2"]), amp=0.45, cutoff=1100))
    # ---- 06 gate opens
    t = 15.0
    m.add(*braam(t + 1.3, amp=1.0, root=36.7))
    m.add(*boom(t + 1.35, amp=0.9, f0=130, f1=28))
    m.add(*taiko(t + 1.35, amp=0.7, pitch=0.7))
    m.add(*whoosh(t + 1.1, dur=1.2, f0=200, f1=3200, amp=0.35))
    m.add(t, _rumble(3.0), gain=0.18)
    # ---- 07 rival
    t = 18.0
    m.add(*whoosh(t, dur=0.5, f0=1800, f1=200, amp=0.28, reverse=True))
    m.add(*pad(t, 3.6, chord(["Bb1", "F2", "Bb2", "Db3"]), amp=0.55, cutoff=900))
    m.add(*choir(t + 0.2, 3.2, chord(["Bb3", "F4", "Bb4"]), amp=0.30))
    m.add(*heart(t + 0.6, amp=0.45, pitch=0.8))
    m.add(*heart(t + 1.35, amp=0.38, pitch=0.8))
    # ---- 08 faceoff
    t = 21.5
    m.add(*taiko(t + 0.05, amp=0.6, pitch=0.75))
    m.add(*taiko(t + 0.9, amp=0.45, pitch=0.75))
    m.add(*pad(t, 3.2, chord(["D2", "A2", "D3", "F3"]), amp=0.6, cutoff=1000))
    m.add(*riser(t + 1.4, dur=1.6, amp=0.45, f_end=5200))
    m.add(*whoosh(t + 1.2, dur=1.0, f0=120, f1=1400, amp=0.25))
    # ---- 09 clash
    t = 24.5
    m.add(*whoosh(t, dur=1.0, f0=200, f1=4200, amp=0.42))
    m.add(*step(t + 0.25, amp=0.3), )
    m.add(*slash(t + 1.05, amp=0.85, pitch=0.9))
    m.add(*boom(t + 1.05, amp=1.0, f0=150, f1=26))
    m.add(*taiko(t + 1.05, amp=0.9, pitch=0.62))
    m.add(*braam(t + 1.05, amp=0.8, root=36.7))
    m.add(*whoosh(t + 1.6, dur=1.6, f0=2600, f1=180, amp=0.3, reverse=True))
    m.add(t, _rumble(3.5), gain=0.2)
    m.add(*pad(t + 1.2, 2.3, chord(["D2", "F2", "A2"]), amp=0.5, cutoff=1400))
    # ---- 10 title
    t = 28.0
    m.add(*braam(t + 0.12, amp=1.0, root=36.7, dur=2.6))
    m.add(*boom(t + 0.14, amp=0.85, f0=120, f1=30))
    m.add(*taiko(t + 0.14, amp=0.75, pitch=0.7))
    m.add(*choir(t + 0.3, 1.6, chord(["D3", "A3", "D4"]), amp=0.4))
    m.add(*chime(t + 0.5, base=1320, dur=1.6, amp=0.16))
    m.reverb(0.30, decay=2.4)
    return m


def _rain_bed(dur, seed=3):
    from pipeline.core.audio import _t, bandpass
    t = _t(dur)
    x = np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32)
    x = bandpass(x, 900, 9000)
    e = np.minimum(t / 0.4, 1) * np.minimum((dur - t) / 0.4, 1)
    return (x * e * 0.5).astype(np.float32)


def _splash(dur, seed=5):
    from pipeline.core.audio import _t, bandpass, env
    t = _t(dur)
    x = np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32)
    x = bandpass(x, 700, 7000)
    return (x * env(t, 0.002, 0.09, 1.6) * 0.9).astype(np.float32)


def _rumble(dur, seed=7):
    from pipeline.core.audio import _t, lowpass
    t = _t(dur)
    x = np.random.default_rng(seed).standard_normal(len(t)).astype(np.float32)
    x = lowpass(x, 130, 2)
    e = np.minimum(t / 0.3, 1) * np.minimum((dur - t) / 0.3, 1)
    return (x * e * 0.9).astype(np.float32)


if __name__ == "__main__":
    film = build()
    print(f"duration {film.duration:.2f}s  shots {len(film.shots)}")
