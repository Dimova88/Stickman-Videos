"""THE EIGHTH GATE — Chapter One preview (30 s).

CHAPTER ONE · "THE BOY WHO WAS TOLD NO"

    1  Village at the foot of the mountain, rain, lit windows.     (0.0 – 4.2)
    2  Wide: the boy trains alone in the shrine yard.               (4.2 – 8.0)
    3  Macro: feet pivoting on wet stone, water thrown.             (8.0 – 10.0)
    4  Close: his face, rain, eyes closed — then open.              (10.0 – 13.2)
    5  The master steps out of the shadow (orange rim light).       (13.2 – 16.6)
    6  The lesson: three slow beats — wind, cut, follow.            (16.6 – 21.0)
    7  Faster: three strikes in four seconds, smears.               (21.0 – 24.6)
    8  His palm stops one inch from the boy's throat. Time stops.   (24.6 – 28.2)
    9  Black. Chapter title.                                        (28.2 – 30.0)
"""
from __future__ import annotations

import math

import numpy as np

from pipeline.core import fx, sets
from pipeline.core.audio import (Mix, boom, braam, breath, chime, choir, chord, cloth_rustle,
                                 freeze_sting, heart, pad, rain_bed, riser, step, taiko, whoosh,
                                 wood_hit)
from pipeline.core.camera import Camera, CameraTrack
from pipeline.core.character import (POSES, Look, Rig, draw_character, draw_sash, draw_staff,
                                     solve, staff_line)
from pipeline.core.easing import clamp, ease, lerp, smoothstep, value_noise
from pipeline.core.audio import SR
from pipeline.core.film import Film, Shot
from pipeline.core.render import Painter, Post

W, H = 1920, 1080

BOY = Look(color=(0.88, 0.92, 0.99), rim=(0.38, 0.80, 1.0), ink=(0.012, 0.016, 0.026),
           eye=(0.75, 0.96, 1.0), head_style="light", rim_amount=1.0, aura=(0.25, 0.6, 1.0),
           trail=(0.5, 0.8, 1.0), w_scale=0.94, head_fill=(0.07, 0.09, 0.14))
MASTER = Look(color=(0.97, 0.91, 0.84), rim=(1.0, 0.55, 0.26), ink=(0.026, 0.014, 0.010),
              eye=(1.0, 0.72, 0.32), head_style="light", rim_amount=1.05,
              aura=(1.0, 0.45, 0.15), trail=(1.0, 0.55, 0.25), w_scale=1.10,
              head_fill=(0.09, 0.055, 0.035))
RIG = Rig()
RIG_MASTER = Rig(spine=84.0, head_r=27.0, w_spine=11.6, w_arm=8.6, w_leg=10.0)

PAL = sets.Palette(sky_top=(0.018, 0.026, 0.052), sky_bottom=(0.13, 0.09, 0.13),
                   haze=(0.34, 0.30, 0.40), far=(0.070, 0.085, 0.140), mid=(0.038, 0.044, 0.078),
                   near=(0.008, 0.009, 0.015), accent=(1.0, 0.60, 0.24), accent2=(0.42, 0.76, 1.0),
                   moon=(0.86, 0.89, 0.97))


def pose_of(name, x, y, facing=1, **kw):
    return POSES[name].copy(px=x, py=y, facing=facing, **kw)


def man(p, sk, look, rig=RIG, **kw):
    draw_character(p, sk, rig, look, **kw)
    draw_sash(p, sk, look, color=(0.46, 0.15, 0.11) if look is BOY else (0.34, 0.18, 0.09),
              w=1.05 + 0.12 * (look is MASTER), alpha=kw.get("alpha", 1.0))


def wet_yard(p, t, y=300.0, pal=PAL, light=0.0, light_col=(1.0, 0.55, 0.24)):
    sets.ground(p, pal, y=y, wet=True, detail=1.1,
                light_col=light_col if light > 0 else None, light_x=0.0)
    sets.rain_splash_ground(p, t, y=y, count=30, alpha=0.30)
    sets.fog_band(p, t, y - 26, thickness=90, color=(0.34, 0.30, 0.42), alpha=0.16, depth=0.95)


# ======================================================================= shots
def build() -> Film:
    f = Film(fps=24, width=W, height=H, title="THE EIGHTH GATE — Chapter One")

    # ------------------------------------------------------------------ S01
    def s01_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.014, 0.020, 0.042), bottom=(0.16, 0.10, 0.13))
        p.blob((420, 150), 760, (1.0, 0.50, 0.22), alpha=0.18, depth=0.18, additive=True, soft=1.2)
        sets.clouds(p, t, PAL, depth=0.30, count=5, alpha=0.30, speed=14)
        sets.mountains_ridge(p, t, PAL.far, depth=0.36, seed=47, base_y=60, amp=250, freq=0.0016,
                             rim=(0.36, 0.34, 0.50), rim_w=2.2, rim_a=0.35)
        sets.village(p, t, PAL, depth=0.50, y=196, rows=3, lit=0.55)
        sets.village(p, t, PAL, depth=0.78, y=286, rows=2, lit=0.42, seed=89, hazy=1.2)
        # camera is above the near rooftops: a dark roof edge frames the valley
        sets.village(p, t, PAL, depth=1.30, y=372, rows=1, lit=0.10, seed=97,
                     color=(0.030, 0.028, 0.036), width=4600)
        wet_yard(p, t, y=330, light=0.7)
        # lanterns on posts, framing the shot
        sets.lantern(p, -560, 120, r=26, t=t, sway=7, seed=3, glow=1.7, depth=1.16, cord=190)
        sets.stone_lantern(p, 640, 300, scale=1.25, depth=1.2, t=t, glow=1.3, seed=2)
        sets.rain_splash_ground(p, t, y=330, count=26, alpha=0.35)
        fx.rain(p, t, count=300, alpha=0.20, depth=1.1)
        fx.Embers(count=24, color=(1.0, 0.5, 0.16), seed=5, speed=14).draw(p, t)

    s01 = Shot("s01_village", 4.2,
               CameraTrack().key(0, 150, -30, 0.86, 0.018).key(4.2, 40, -80, 0.96, -0.004, "soft")
               .handheld(0.5),
               s01_draw,
               post=lambda t: Post(bloom=0.44, vignette=0.50, contrast=1.14, saturation=1.02),
               fade_in=1.0)

    # ------------------------------------------------------------------ S02
    def s02_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.012, 0.018, 0.038), bottom=(0.10, 0.07, 0.10))
        sets.mountains_ridge(p, t, PAL.far, depth=0.40, seed=51, base_y=70, amp=190, freq=0.0022,
                             rim=(0.30, 0.30, 0.44), rim_w=2.0, rim_a=0.4)
        sets.village(p, t, PAL, depth=0.62, y=250, rows=2, lit=0.30, seed=91)
        wet_yard(p, t, y=310)
        # shrine wall + torii at the far edge of the yard
        sets.fence(p, t, depth=0.87, x0=-1600, x1=1600, y=300, h=86)
        sets.tree(p, -760, 300, scale=1.15, depth=0.9, t=t, seed=3, sway=1.2,
                  leaf=(0.13, 0.12, 0.13), rim=(0.30, 0.34, 0.46))
        sets.tree(p, 700, 296, scale=1.0, depth=0.92, t=t, seed=5, sway=1.0,
                  leaf=(0.13, 0.12, 0.13), rim=(0.30, 0.34, 0.46))
        sets.torii(p, t, PAL, x=-880, y=300, scale=0.95, depth=0.94,
                   color=(0.115, 0.040, 0.032), light=(1.0, 0.55, 0.24), open_glow=0.05)
        sets.bamboo(p, t, depth=1.30, count=8, x0=470, x1=980, seed=63, sway=0.7,
                    color=(0.010, 0.015, 0.018), top=-900, bottom=700)
        sets.stone_lantern(p, 300, 300, scale=0.95, depth=1.14, t=t, glow=1.1)
        sets.puddle(p, -180, 250, rx=250, ry=44, t=t, depth=1.02, alpha=0.10,
                    light_streak=(1.0, 0.62, 0.32))
        sets.puddle(p, 210, 296, rx=180, ry=30, t=t, depth=1.06, alpha=0.08,
                    light_streak=(0.55, 0.75, 1.0))
        # the boy, mid-repetition: a slow strike, one per ~1.15 s
        cyc = (t / 1.15) % 1.0
        if cyc < 0.42:
            name, ang = "staff_wind", 148.0
        elif cyc < 0.68:
            name, ang = "staff_swing", 96.0
        else:
            name, ang = "staff_follow", 52.0
        u = ease("in_out", clamp(cyc / 0.42)) if cyc < 0.42 else 1.0
        sk = solve(pose_of(name, -60, 150, 1), RIG)
        man(p, sk, BOY, eye_glow=0.25, aura=0.15, light=(0.5, -1.0))
        draw_staff(p, sk, BOY, ang, length=200)
        # splash at the fast part of the swing
        if 0.4 < cyc < 0.75:
            fx.Particles(x=-40, y=262, t0=0.30 + 0.42 * 1.15,
                         count=14, speed=(120, 380), angle=(math.pi * 1.15, math.pi * 1.9),
                         gravity=1300, life=(0.15, 0.4), size=(0.7, 1.6),
                         color=(0.75, 0.88, 1.0), color_end=(0.4, 0.6, 1.0), seed=7,
                         glow=0.5).draw(p, t % 1.15)
        fx.rain(p, t, count=240, alpha=0.17, depth=1.1)
        fx.wind_streaks(p, t, count=18, alpha=0.07, speed=600, depth=0.9)

    s02 = Shot("s02_training", 3.8,
               CameraTrack().key(0, -60, 150, 1.34, 0.012).key(3.8, -100, 128, 1.48, -0.006, "soft")
               .handheld(0.7),
               s02_draw,
               post=lambda t: Post(bloom=0.44, vignette=0.50, contrast=1.13),
               whip_in=0.16)

    # ------------------------------------------------------------------ S03
    def s03_draw(p: Painter, t: float):
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.036, 0.044, 0.072), (0.005, 0.006, 0.011)))
        r = np.random.default_rng(77)
        for i in range(13):
            y = -560 + (i ** 1.5) * 30
            hgt = 16 + (i ** 1.5) * 3.2
            shade = 0.017 + 0.0032 * i
            p.polygon_world([(-4000, y), (4000, y), (4000, y + hgt), (-4000, y + hgt)],
                            (shade, shade * 1.15, shade * 1.95), depth=1.0)
            p.line([(-4000, y), (4000, y)], 0.8 + i * 0.5, (0.20, 0.24, 0.34), alpha=0.32, depth=1.0)
        # the pivot: back foot lifts and plants
        plant = 0.85
        lift = 1.0 - ease("out", clamp(t / plant))
        sk = solve(pose_of("stance", 30, 90 - 60 * lift, 1, leg_b=(-46 - 26 * lift, -14, 96)), RIG)
        man(p, sk, BOY, light=(0.6, -1.0))
        draw_staff(p, sk, BOY, 128, length=200)
        if t > plant:
            u = clamp((t - plant) / 1.0)
            for k in range(3):
                uk = clamp(u - k * 0.1)
                p.circle((sk.to_b[0], sk.to_b[1] + 4), 12 + 130 * ease("expo_out", uk),
                         (0.55, 0.74, 1.0), alpha=(1 - uk) ** 1.5 * 0.5, ring=1.5, additive=True,
                         glow=0.16 * (1 - uk), glow_color=(0.5, 0.72, 1.0))
            fx.Particles(x=sk.to_b[0], y=sk.to_b[1], t0=plant, count=26, speed=(140, 520),
                         angle=(math.pi * 1.08, math.pi * 1.92), gravity=1500, life=(0.18, 0.6),
                         size=(0.8, 2.0), color=(0.80, 0.92, 1.0), color_end=(0.4, 0.6, 1.0),
                         seed=11, glow=0.8).draw(p, t)
        fx.rain(p, t, count=140, alpha=0.16, depth=1.2)
        sets.rain_splash_ground(p, t, y=250, count=16, alpha=0.35)

    s03 = Shot("s03_pivot", 2.0,
               CameraTrack().key(0, 14, 96, 2.55, -0.04).key(2.0, 34, 112, 2.85, -0.015, "soft")
               .handheld(0.8),
               s03_draw,
               post=lambda t: Post(bloom=0.48, vignette=0.55, ca=1.4, contrast=1.14),
               whip_in=0.12)

    # ------------------------------------------------------------------ S04
    def s04_draw(p: Painter, t: float):
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.026, 0.032, 0.054), (0.004, 0.005, 0.010)))
        p.blob((-360, -80), 460, (0.55, 0.42, 0.30), alpha=0.16, depth=0.4, soft=1.1)
        sets.fog_band(p, t, 330, thickness=120, color=(0.30, 0.30, 0.42), alpha=0.30, depth=1.02)
        p.blob((0, 360), 420, (0.22, 0.24, 0.34), alpha=0.35, depth=1.0, soft=1.2)
        sk = solve(pose_of("tired", 0, 232, 1, scale=1.0), RIG)
        hx, hy = sk.head_c
        # rain runs down his face
        for i in range(4):
            ph = i * 1.3
            yy = hy + ((t * 60 + ph * 90) % 120) - 10
            xx = hx - 42 + i * 26
            p.line([(xx, yy), (xx, yy + 8)], 1.6, (0.72, 0.86, 1.0), alpha=0.5, additive=True)
        opened = clamp((t - 1.5) / 0.45)
        draw_character(p, sk, RIG, BOY, eye_glow=0.10 + 0.9 * opened, light=(-0.4, -1.0),
                       aura=0.12 * opened)
        if opened > 0.02:
            # a flash of memory: a warm rim bleeding in behind him
            p.circle((hx - 90, hy - 70), 260, (1.0, 0.55, 0.25), alpha=0.0, depth=0.7,
                     glow=0.22 * opened, glow_color=(1.0, 0.5, 0.2))
        fx.rain(p, t, count=190, alpha=0.15, depth=1.1)
        fx.dust_motes(p, t, count=18)

    s04 = Shot("s04_face", 3.2,
               CameraTrack().key(0, 4, 168, 3.05, 0.014).key(3.2, 10, 162, 3.35, -0.006, "soft")
               .handheld(0.6),
               s04_draw,
               post=lambda t: Post(bloom=0.50, vignette=0.56, ca=1.5, contrast=1.16,
                                   exposure=1.08),
               whip_in=0.14)

    # ------------------------------------------------------------------ S05
    def s05_draw(p: Painter, t: float):
        reveal = ease("in_out", clamp(t / 2.2))
        sets.sky(p, PAL, top=(0.010, 0.014, 0.030), bottom=(0.12, 0.075, 0.10))
        p.blob((0, 210), 620, (1.0, 0.52, 0.22), alpha=0.16, depth=0.3, additive=True, soft=1.3)
        sets.village(p, t, PAL, depth=0.60, y=236, rows=2, lit=0.32, seed=93)
        wet_yard(p, t, y=312)
        sets.temple_wall(p, t, PAL, depth=0.86, y=300, windows=2, spacing=640,
                         color=(0.026, 0.026, 0.040), glow=(1.0, 0.6, 0.25), lit_amount=0.30)
        # the boy, foreground, back to us
        sk_b = solve(pose_of("tired", -250, 180, 1), RIG)
        man(p, sk_b, BOY, eye_glow=0.55, light=(0.5, -1.0))
        # the master, emerging from a deep shadow, lit from behind
        mx = lerp(280, 210, reveal)
        alpha = 0.35 + 0.65 * reveal
        shadow = 1.0 - reveal
        if shadow > 0.02:
            p.blob((mx, 150), 260 + 60 * shadow, (0.0, 0.0, 0.0), alpha=0.55 * shadow, depth=1.05,
                   soft=0.9)
        sk_m = solve(pose_of("staff_guard", mx, 150, -1, scale=1.06), RIG_MASTER)
        man(p, sk_m, MASTER, rig=RIG_MASTER, eye_glow=0.75 * reveal, aura=0.35 * reveal,
            alpha=alpha, light=(-0.3, -1.0))
        draw_staff(p, sk_m, MASTER, 96, length=230, alpha=alpha)
        fx.rain(p, t, count=260, alpha=0.18, depth=1.1)
        fx.Embers(count=30, color=(1.0, 0.5, 0.16), seed=5, speed=16).draw(p, t)

    s05 = Shot("s05_master", 3.4,
               CameraTrack().key(0, -40, 170, 1.12, 0.014).key(3.4, 20, 140, 1.34, -0.006, "soft")
               .handheld(0.5),
               s05_draw,
               post=lambda t: Post(bloom=0.48, vignette=0.52, contrast=1.15, saturation=1.04),
               whip_in=0.18)

    # ------------------------------------------------------------------ S06
    def s06_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.008, 0.012, 0.026), bottom=(0.09, 0.06, 0.085))
        sets.mountains_ridge(p, t, PAL.far, depth=0.36, seed=57, base_y=50, amp=160, freq=0.0026,
                             rim=(0.28, 0.28, 0.42), rim_w=1.8, rim_a=0.35)
        wet_yard(p, t, y=330)
        sets.temple_wall(p, t, PAL, depth=0.9, y=320, windows=1, spacing=0,
                         color=(0.026, 0.026, 0.040), glow=(1.0, 0.6, 0.25), lit_amount=0.55)
        sets.fence(p, t, depth=0.95, x0=-1500, x1=1500, y=318, h=70)
        sets.tree(p, -980, 318, scale=0.95, depth=0.97, t=t, seed=11, sway=1.1,
                  leaf=(0.12, 0.11, 0.12), rim=(0.30, 0.33, 0.44))
        sets.tree(p, 1020, 318, scale=0.9, depth=0.97, t=t, seed=13, sway=1.0,
                  leaf=(0.12, 0.11, 0.12), rim=(0.30, 0.33, 0.44))
        sets.stone_lantern(p, -430, 300, scale=0.85, depth=1.1, t=t, glow=1.0, seed=4)
        sets.stone_lantern(p, 470, 300, scale=0.85, depth=1.1, t=t, glow=1.0, seed=6)
        sets.puddle(p, 40, 250, rx=300, ry=50, t=t, depth=1.04, alpha=0.09,
                    light_streak=(1.0, 0.62, 0.32))
        # three slow beats: wind (0-.42) cut (.42-.62) follow (.62-1.0)
        T = 1.45
        beat = (t / T) % 1.0
        if beat < 0.42:
            name, ang = "staff_wind", 152.0
        elif beat < 0.64:
            name, ang = "staff_swing", 100.0
        else:
            name, ang = "staff_follow", 54.0
        sk = solve(pose_of(name, -60, 150, 1, scale=1.04), RIG_MASTER)
        man(p, sk, MASTER, rig=RIG_MASTER, eye_glow=0.6, aura=0.25, light=(0.5, -1.0))
        draw_staff(p, sk, MASTER, ang, length=230)
        # motion smear just after the cut
        if 0.40 < beat < 0.60:
            a, b = staff_line(sk, ang, 230)
            p.line([a, b], 26, (1.0, 0.62, 0.30), alpha=0.20, depth=1.0, taper=0.2,
                   additive=True, glow=0.5, glow_color=(1.0, 0.6, 0.25))
        # the boy watches, in silhouette at the edge
        sk_b = solve(pose_of("bow_wait", 470, 190, -1, scale=0.98), RIG)
        draw_character(p, sk_b, RIG, BOY, alpha=0.55, eye_glow=0.4, rim_on=True,
                       light=(-0.3, -1.0))
        fx.rain(p, t, count=230, alpha=0.17, depth=1.1)
        if beat > 0.40 and beat < 0.44:
            fx.Particles(x=-10, y=150, t0=(math.floor(t / T) * T) + 0.40 * T, count=12,
                         speed=(120, 380), angle=(0.2, 2.6), gravity=800, life=(0.15, 0.4),
                         size=(0.7, 1.5), color=(1.0, 0.8, 0.5), color_end=(1.0, 0.4, 0.1),
                         seed=13, glow=0.6).draw(p, t)

    s06 = Shot("s06_lesson", 4.4,
               CameraTrack().key(0, 30, 200, 1.22, -0.012).key(2.2, 0, 186, 1.34, 0.006, "soft")
               .key(4.4, -30, 200, 1.26, -0.004, "soft").handheld(0.6),
               s06_draw,
               post=lambda t: Post(bloom=0.44, vignette=0.50, contrast=1.14),
               whip_in=0.16)

    # ------------------------------------------------------------------ S07
    def s07_draw(p: Painter, t: float):
        sets.sky(p, PAL, top=(0.008, 0.012, 0.026), bottom=(0.10, 0.065, 0.09))
        wet_yard(p, t, y=340)
        sets.temple_wall(p, t, PAL, depth=0.9, y=330, windows=1, spacing=0,
                         color=(0.026, 0.026, 0.040), glow=(1.0, 0.6, 0.25), lit_amount=0.55)
        sets.tree(p, -900, 328, scale=0.9, depth=0.96, t=t, seed=15, sway=1.3,
                  leaf=(0.12, 0.11, 0.12), rim=(0.30, 0.33, 0.44))
        sets.stone_lantern(p, -520, 306, scale=0.9, depth=1.08, t=t, glow=1.1, seed=7)
        sets.stone_lantern(p, 560, 306, scale=0.9, depth=1.08, t=t, glow=1.1, seed=8)
        # three strikes in 3.6 s (1.2 s each), alternating wind/cut
        T = 1.2
        k = int(t // T)
        beat = (t % T) / T
        if beat < 0.30:
            name, ang, smear = "staff_wind", 150.0, 0.0
        elif beat < 0.55:
            name, ang, smear = "staff_swing", 98.0, 1.0
        else:
            name, ang, smear = "staff_follow", 52.0, 0.35
        sk = solve(pose_of(name, -40 + k * 16, 150, 1, scale=1.06), RIG_MASTER)
        man(p, sk, MASTER, rig=RIG_MASTER, eye_glow=0.8, aura=0.35 + 0.2 * smear,
            light=(0.5, -1.0))
        draw_staff(p, sk, MASTER, ang, length=230)
        if smear > 0:
            a, b = staff_line(sk, ang, 230)
            for i in range(3):
                p.line([a, b], 30 - i * 8, (1.0, 0.66, 0.32), alpha=0.16 * smear,
                       depth=1.0, taper=0.15, additive=True, glow=0.5 * smear,
                       glow_color=(1.0, 0.6, 0.25))
        # the boy mirrors him, smaller in the background
        bsk = solve(pose_of(name, 420, 205, -1, scale=0.92), RIG)
        draw_character(p, bsk, RIG, BOY, alpha=0.75, eye_glow=0.5, light=(-0.4, -1.0))
        draw_staff(p, bsk, BOY, 180 - ang, length=190, alpha=0.75)
        fx.rain(p, t, count=250, alpha=0.18, depth=1.1)
        fx.wind_streaks(p, t, count=22, alpha=0.09, speed=900, depth=0.95)

    s07 = Shot("s07_faster", 3.6,
               CameraTrack().key(0, -20, 190, 1.30, 0.010).key(1.8, 40, 176, 1.42, -0.004, "soft")
               .key(3.6, -10, 190, 1.34, 0.006, "soft").handheld(0.9),
               s07_draw,
               post=lambda t: Post(bloom=0.46, vignette=0.50, contrast=1.16, ca=1.2),
               whip_in=0.14)

    # ------------------------------------------------------------------ S08
    FREEZE = 1.35

    def s08_draw(p: Painter, t: float):
        # everything except the characters stops advancing after FREEZE
        tf = min(t, FREEZE)
        sets.sky(p, PAL, top=(0.010, 0.014, 0.030), bottom=(0.11, 0.07, 0.10))
        wet_yard(p, tf, y=330)
        sets.temple_wall(p, t, PAL, depth=0.9, y=320, windows=1, spacing=0,
                         color=(0.026, 0.026, 0.040), glow=(1.0, 0.6, 0.25), lit_amount=0.55)
        sets.tree(p, 900, 316, scale=1.0, depth=0.97, t=t, seed=17, sway=1.2,
                  leaf=(0.12, 0.11, 0.12), rim=(0.30, 0.33, 0.44))
        sets.tree(p, -1000, 316, scale=0.85, depth=0.97, t=t, seed=19, sway=1.0,
                  leaf=(0.12, 0.11, 0.12), rim=(0.30, 0.33, 0.44))
        sets.stone_lantern(p, -600, 300, scale=1.0, depth=1.1, t=t, glow=1.2, seed=9)
        # the boy, mid-step back
        step_back = ease("out", clamp(t / FREEZE))
        bsk = solve(pose_of("hit" if t > FREEZE else "stance", 120 + 26 * step_back, 170, -1,
                            scale=1.0, spine=196 if t <= FREEZE else 186), RIG)
        man(p, bsk, BOY, eye_glow=0.85, light=(-0.4, -1.0))
        # the master: palm stop
        msk = solve(pose_of("palm_stop", -95, 150, 1, scale=1.06), RIG_MASTER)
        man(p, msk, MASTER, rig=RIG_MASTER, eye_glow=0.9, aura=0.45, light=(0.5, -1.0))
        # the gap between palm and throat
        hx, hy = msk.hand_f
        gx, gy = bsk.neck
        gap = math.hypot(gx - hx, gy - hy)
        if t > FREEZE:
            u = clamp((t - FREEZE) / 2.2)
            glow = (1 - u) ** 1.2
            p.circle(((hx + gx) / 2, (hy + gy) / 2), 9 + 4 * u, (1.0, 0.9, 0.7),
                     alpha=0.75 * glow, additive=True, glow=0.5 * glow,
                     glow_color=(1.0, 0.78, 0.45))
            for i in range(10):
                a = -math.pi / 2 + (i - 4.5) * 0.16
                p.line([((hx + gx) / 2, (hy + gy) / 2),
                        ((hx + gx) / 2 + math.cos(a) * 190, (hy + gy) / 2 + math.sin(a) * 190)],
                       5, (1.0, 0.85, 0.55), alpha=0.035 * glow, additive=True, taper=2.0)
            # time-stop: rain hangs, then a shockwave of still air
            sets.frozen_rain(p, count=260, alpha=0.55)
            p.circle(((hx + gx) / 2, (hy + gy) / 2), 40 + 300 * ease("expo_out", u),
                     (1.0, 0.9, 0.75), alpha=(1 - u) ** 1.8 * 0.18, ring=1.6, additive=True,
                     glow=0.10 * (1 - u), glow_color=(1.0, 0.8, 0.5))
        else:
            fx.rain(p, tf, count=280, alpha=0.18, depth=1.1)
            fx.Particles(x=msk.hand_f[0], y=msk.hand_f[1], t0=0.0, count=10,
                         speed=(40, 120), angle=(0, 6.28), gravity=0, drag=1.0,
                         life=(0.4, 0.9), size=(1.0, 2.4), color=(1.0, 0.8, 0.5),
                         color_end=(1.0, 0.5, 0.2), seed=17, glow=0.7).draw(p, tf)
        fx.dust_motes(p, t, count=16)

    s08 = Shot("s08_stop", 3.6,
               CameraTrack().key(0, 10, 180, 1.34, 0.010).key(FREEZE, -10, 168, 1.62, 0.004, "impact")
               .key(3.6, -30, 176, 1.50, -0.002, "soft").hit(FREEZE, 14.0, 7.0).handheld(0.5),
               s08_draw,
               post=lambda t: _stop_post(t),
               whip_in=0.12)

    # ------------------------------------------------------------------ S09
    def s09_draw(p: Painter, t: float):
        W, H = p.w, p.h
        k = H / 1080.0
        p.poly([(-200, -200), (W + 200, -200), (W + 200, H + 200), (-200, H + 200)],
               None, gradient=((0.003, 0.003, 0.005), (0.003, 0.003, 0.005)))
        a = ease("out", clamp((t - 0.10) / 0.55))
        b = ease("out", clamp((t - 0.75) / 0.5))
        if a > 0:
            p.text("THE EIGHTH GATE", (W / 2, H / 2 - 96 * k), 34 * k, (0.90, 0.91, 0.96),
                   alpha=a * 0.85, bold=False, tracking=15 * k)
            p.text("CHAPTER ONE", (W / 2, H / 2 - 6 * k), 78 * k, (1, 1, 1), alpha=a, bold=True,
                   glow=1.0 * a, tracking=9 * k)
            p.line([(W / 2 - 250 * k * a, H / 2 - 152 * k), (W / 2 + 250 * k * a, H / 2 - 152 * k)],
                   2.2 * k, (1.0, 0.66, 0.34), alpha=0.8 * a, glow=0.5 * a,
                   glow_color=(1.0, 0.62, 0.3))
        if b > 0:
            p.text("T H E   B O Y   W H O   W A S   T O L D   N O", (W / 2, H / 2 + 92 * k),
                   19 * k, (0.82, 0.83, 0.90), alpha=0.75 * b, bold=False)
        fx.Embers(count=26, color=(1.0, 0.5, 0.16), seed=5, speed=14).draw(p, t)

    s09 = Shot("s09_title", 1.8,
               CameraTrack().key(0, 0, 0, 1.05, 0).key(1.8, 0, 0, 1.0, 0, "soft"),
               s09_draw,
               post=lambda t: Post(bloom=0.42, vignette=0.52, grain=0.030),
               fade_out=0.35)

    for s in (s01, s02, s03, s04, s05, s06, s07, s08, s09):
        f.add(s)
    return f


def _stop_post(t: float) -> Post:
    p = Post(bloom=0.48, vignette=0.50, contrast=1.16, ca=1.3, flash_color=(1, 0.92, 0.8))
    if t >= 1.35:
        u = clamp((t - 1.35) / 2.2)
        # exposure blooms for a beat as time stops, then settles into stillness
        p.exposure = 1.0 + 0.16 * (1 - u) ** 2
        p.bloom = 0.48 + 0.25 * (1 - u) ** 2
        p.saturation = 1.08
    return p


# ======================================================================= audio
def soundtrack(duration: float) -> Mix:
    m = Mix(duration)
    # rain sits under everything but breathes with the edit
    rb = rain_bed(duration, amp=0.30, seed=3)[1]
    env = np.ones_like(rb)
    for (a, b, g) in ((0.0, 4.2, 0.75), (4.2, 13.2, 0.55), (13.2, 21.0, 0.45),
                      (21.0, 24.6, 0.62), (24.6, 27.9, 0.30), (27.9, 30.0, 0.18)):
        i0, i1 = int(a * 48000), int(min(b * 48000, len(env)))
        env[i0:i1] = g
    from scipy.ndimage import uniform_filter1d
    env = uniform_filter1d(env, 2400)
    m.add(0.0, rb * env, gain=1.0)

    # 01 village — distant life, warm and low
    m.add(*boom(0.1, amp=0.30, f0=90, f1=34))
    m.add(*pad(0.0, 5.2, chord(["D2", "A2", "F3"]), amp=0.55, cutoff=800))
    m.add(*chime(0.5, base=660, dur=3.0, amp=0.10))

    # 02 training — the first staff circles
    t = 4.2
    for i in range(3):
        m.add(*whoosh(t + 0.35 + i * 1.15, dur=0.42, f0=420, f1=1800, amp=0.13, seed=20 + i))
    m.add(*pad(t, 3.8, chord(["D2", "A2", "D3"]), amp=0.42, cutoff=700))

    # 03 pivot
    t = 8.0
    m.add(*step(t + 0.85, amp=0.40, pitch=1.15))
    m.add(*whoosh(t + 0.55, dur=0.34, f0=300, f1=2400, amp=0.18))
    m.add(*cloth_rustle(t + 0.8, amp=0.10))

    # 04 face — breathe, then the eyes open
    t = 10.0
    m.add(*breath(t + 0.2, dur=1.1, amp=0.16))
    m.add(*heart(t + 0.9, amp=0.34, pitch=0.95))
    m.add(*heart(t + 1.7, amp=0.28, pitch=0.95))
    m.add(*chime(t + 1.5, base=880, dur=2.6, amp=0.16))
    m.add(*riser(t + 1.4, dur=1.8, amp=0.26, f_end=3600))
    m.add(*pad(t, 3.2, chord(["D2", "F2", "A2"]), amp=0.40, cutoff=900))

    # 05 the master
    t = 13.2
    m.add(*whoosh(t + 0.05, dur=0.8, f0=1400, f1=180, amp=0.22, reverse=True))
    m.add(*taiko(t + 0.55, amp=0.42, pitch=0.72))
    m.add(*braam(t + 0.55, amp=0.42, root=36.7, dur=2.6))
    m.add(*choir(t + 0.9, 2.4, chord(["D3", "A3", "F4"]), amp=0.20))

    # 06 the lesson — three slow beats
    t = 16.6
    for i in range(3):
        b = t + i * 1.45 + 0.61
        m.add(*whoosh(b - 0.22, dur=0.3, f0=520, f1=2200, amp=0.16, seed=30 + i))
        m.add(*wood_hit(b, amp=0.30, pitch=1.0 + 0.05 * i, seed=40 + i))
    m.add(*pad(t, 4.4, chord(["D2", "A2", "D3", "F3"]), amp=0.50, cutoff=1000))
    m.add(*taiko(t + 0.05, amp=0.30, pitch=0.68))

    # 07 faster — three strikes, tighter and louder
    t = 21.0
    for i in range(3):
        b = t + i * 1.2 + 0.62
        m.add(*whoosh(b - 0.26, dur=0.34, f0=600, f1=3000, amp=0.24, seed=50 + i))
        m.add(*wood_hit(b, amp=0.52 + 0.06 * i, pitch=1.05, seed=60 + i))
        m.add(*step(b + 0.04, amp=0.20, pitch=1.2, seed=70 + i))
    m.add(*pad(t, 3.6, chord(["D2", "A2", "D3", "F3"]), amp=0.52, cutoff=1200))
    m.add(*riser(t + 2.2, dur=1.4, amp=0.30, f_end=4800))

    # 08 time stops
    t = 24.6
    m.add(*whoosh(t - 0.05, dur=0.5, f0=700, f1=3000, amp=0.30))
    m.add(*freeze_sting(t + 1.35, amp=0.62, base=1320.0))
    m.add(*braam(t + 1.35, amp=0.55, root=36.7, dur=2.4))
    m.add(t + 1.35, np.zeros(1, np.float32), gain=1.0)
    m.add(t, pad(t, 1.35, chord(["D2", "A2"]), amp=0.45, cutoff=1100)[1] if False else
          np.zeros(int(0.02 * 48000), np.float32))
    m.add(*pad(t + 1.35, 2.2, chord(["Bb1", "F2", "Bb2"]), amp=0.40, cutoff=700))
    m.add(*breath(t + 2.4, dur=1.0, amp=0.20, pitch=0.8))

    # 09 title
    t = 28.2
    m.add(*braam(t + 0.08, amp=0.62, root=36.7, dur=2.4))
    m.add(*boom(t + 0.10, amp=0.55, f0=120, f1=30))
    m.add(*choir(t + 0.22, 1.6, chord(["D3", "A3", "D4"]), amp=0.28))
    m.add(*chime(t + 0.40, base=1180, dur=1.4, amp=0.12))

    m.reverb(0.32, decay=2.6)
    return m


if __name__ == "__main__":
    film = build()
    print(f"duration {film.duration:.2f}s  shots {len(film.shots)}")
