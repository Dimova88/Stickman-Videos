"""THE EMPTY HAND — a 30-second duel at the blue hour. The script, as data.

One man with a sword, one man who takes it off him. The film is built on the
beat sheet in ``BATTLE_SCRIPT.md``; the timings here are the same sheet, in
frames: 30.2 s at 24 fps, 725 frames.

    act I    0.0 - 9.2    the blade is drawn, used, and knocked out of his hand
    act II   9.2 - 15.7   empty hands: elbows, knees, a sweep, a throw
    act III  15.7 - 26.0  the rival lights up, the hero takes the blade back,
                          breaks it, and makes one out of light

What the second film changes, as a *script* rather than a fork of the renderer:
a two-man cast, a night plate, a weapon that is drawn at 2.55 s and sticks in
the ground at 7 s before it is picked up again at 10.6, and a rival who owns the
awakening instead of the hero.
"""
from __future__ import annotations

from engine.weapons_and_props import WorldProp

from .beats import CombatBeat
from .poses import P, fade
from .steelkit import (BLADE, E_BACK, E_GUARD, HIGH, LOW, READY)

GOLD = (226, 168, 74)
GOLD_DARK = (140, 96, 30)
VIOLET = (158, 116, 202)
VIOLET_DARK = (92, 62, 130)

SETS = {
    "night": {"title": "THE EMPTY HAND", "sub": "ONE BLADE  •  ONE MAN",
              "hud": "BLUE HOUR  •  DUEL"},
}

CAST = [
    dict(name="gold", colour=GOLD, dark=GOLD_DARK, facing=1, z=0.24,
         weapon=BLADE),
    dict(name="violet", colour=VIOLET, dark=VIOLET_DARK, facing=-1, z=-0.16,
         weapon=BLADE * 0.95),
]


def intro(tracks):
    """0 - 3.4 s: two men walk into the same pool of moonlight."""
    gold, violet = tracks[0], tracks[1]
    gold.key(0.0, LOW, 474)
    violet.key(0.0, E_GUARD, 1236)
    gold.key(0.95, fade(LOW, torso=-82), 492, "out")
    violet.key(1.25, fade(E_GUARD, torso=-82), 1130, "out")
    gold.key(2.05, READY, 520, "out")
    violet.key(2.30, E_GUARD, 1062, "out")
    # the draw (the blade is a prop: it leaves the scabbard at 2.55) and the
    # guard that answers it
    gold.key(2.86, HIGH, 546, "snap")
    violet.key(3.05, E_GUARD, 1018, "out")


def B(t, atk, move, dfd, **kw):
    return CombatBeat(t, atk, move, dfd, **kw)


#: three holds: the two men stop and look at each other before each gear change
MA = ((9.20, 9.70), (15.20, 15.70), (20.90, 21.40))

BEATS = [
    # ---------------------------------------------------- act I: steel
    # he opens with two cuts and the hero answers both; the third is his
    B(3.94, "violet", "blitz_dash_slash", "gold", gap=56, chain=True,
      from_x=1018, to_x=968, outcome="parry", size=0.95),
    B(4.16, "violet", "blitz_dash_slash", "gold", gap=54, chain=True,
      from_x=968, to_x=944, outcome="parry", size=0.95),
    B(4.40, "gold", "rising_dragon_slash", "violet", gap=52, knock=150.0,
      from_x=910, to_x=944, size=1.05, zone="gut"),
    B(4.78, "gold", "blitz_dash_slash", "violet", gap=52, outcome="parry",
      from_x=944, to_x=962, size=0.9),
    B(5.08, "violet", "spin_back_slash", "gold", gap=50, knock=130.0,
      from_x=996, to_x=958, size=0.95, zone="head"),
    # -- the disarm: the hero commits to a cut, the rival catches it and turns
    #    it out of his hand. From here to 10.6 s he is a man with nothing.
    B(5.62, "gold", "blitz_dash_slash", "violet", gap=50, outcome="parry",
      from_x=902, to_x=936, size=1.05),
    # ---------------------------------------------------- act II: empty hands
    B(6.34, "gold", "matrix_weave", "violet", gap=50, outcome="whiff",
      from_x=930, to_x=922, size=0.85),
    B(6.76, "gold", "taijutsu_combo", "violet", gap=46, knock=300.0,
      from_x=922, to_x=944, size=1.1, zone="head"),
    B(7.44, "gold", "spartan_front_kick", "violet", gap=48, knock=300.0,
      from_x=944, to_x=966, size=1.05, zone="sweep"),
    B(8.12, "violet", "dash_collar_grab", "gold", gap=30,
      from_x=1150, to_x=1010, size=0.95),
    B(8.48, "gold", "overhead_judo_slam", "violet", gap=26, knock=330.0,
      from_x=1000, to_x=1030, outcome="down", size=1.15),
    # ---------------------------------------------------- act III: the blade
    # he walks to where it stuck, takes it back, and the duel goes up a gear
    B(9.86, "gold", "matrix_weave", "violet", gap=56, outcome="whiff",
      from_x=800, to_x=792, size=0.8),
    B(10.20, "violet", "blitz_dash_slash", "gold", gap=54, outcome="parry",
      from_x=1080, to_x=1010, size=0.95),
    B(10.94, "gold", "blitz_dash_slash", "violet", gap=54, chain=True,
      from_x=820, to_x=846, size=0.95),
    B(11.16, "gold", "blitz_dash_slash", "violet", gap=52, chain=True,
      from_x=846, to_x=852, size=0.9),
    B(11.40, "gold", "rising_dragon_slash", "violet", gap=50, knock=260.0,
      from_x=852, to_x=868, size=1.15),
    B(12.10, "violet", "aerial_helm_breaker", "gold", gap=52, knock=300.0,
      from_x=1120, to_x=1040, size=1.1, zone="head"),
    B(12.90, "violet", "blitz_dash_slash", "gold", gap=54, outcome="parry",
      from_x=1030, to_x=980, size=0.95),
    B(13.12, "gold", "parry_riposte_spin", "violet", gap=52,
      from_x=930, to_x=944, size=1.0),
    B(13.40, "gold", "spin_back_slash", "violet", gap=52, knock=280.0,
      from_x=944, to_x=930, size=1.1),
    B(14.16, "violet", "dash_collar_grab", "gold", gap=30,
      from_x=1090, to_x=1000, size=0.95),
    B(14.52, "violet", "overhead_judo_slam", "gold", gap=26, knock=330.0,
      from_x=1000, to_x=1020, outcome="down", size=1.1),
    # ---------------------------------------------------- act IV: the awakening
    # the rival lights up: aura, stones and lightning are *his*, not the hero's
    B(16.06, "violet", "blitz_dash_slash", "gold", gap=52, knock=300.0,
      from_x=1150, to_x=1030, size=1.15, zone="gut"),
    B(16.86, "gold", "matrix_weave", "violet", gap=52, outcome="whiff",
      from_x=890, to_x=886, size=0.85),
    B(17.28, "gold", "taijutsu_combo", "violet", gap=48, knock=300.0,
      from_x=886, to_x=930, size=1.15, zone="head"),
    B(18.06, "violet", "spin_back_slash", "gold", gap=52, knock=280.0,
      from_x=1080, to_x=1000, size=1.1),
    B(18.86, "gold", "matrix_weave", "violet", gap=52, outcome="whiff",
      from_x=900, to_x=896, size=0.85),
    B(19.26, "gold", "blitz_dash_slash", "violet", gap=52, outcome="parry",
      from_x=896, to_x=920, size=0.95),
    # -- the juggle: he takes the man off the ground and keeps him there
    B(19.60, "gold", "rising_dragon_slash", "violet", gap=48, launch=240.0,
      hold_air=0.58, from_x=920, to_x=952, size=1.1, air=120.0),
    B(19.80, "gold", "air_pursuit_slash", "violet", gap=46, air=215.0,
      launch=230.0, hold_air=0.50, chain=True, from_x=952, to_x=966, size=1.0),
    B(20.06, "gold", "air_meteor_slam", "violet", gap=44, air=170.0, knock=300.0,
      from_x=966, to_x=990, size=1.35),
    # ---------------------------------------------------- act V: light
    B(21.44, "gold", "energy_beam_blast", "violet", gap=200.0, knock=120.0,
      from_x=980, to_x=996, size=1.3),
    B(22.24, "gold", "blitz_dash_slash", "violet", gap=50, outcome="parry",
      from_x=880, to_x=914, size=1.15),
    B(23.30, "gold", "blitz_dash_slash", "violet", gap=44, knock=200.0,
      from_x=900, to_x=986, outcome="lethal", size=1.8),
]


def after(tracks, beats):
    """The outro: the winner walks out of the moonlight."""
    gold, violet = tracks[0], tracks[1]
    gold.key(24.60, READY, 1004, "out")
    gold.key(26.20, fade(READY, torso=-84), 940, "out")
    gold.key(28.20, fade(LOW, b_fore=10), 700, "smooth")
    gold.key(30.10, fade(LOW, b_fore=8, torso=-86), 520, "smooth")


def props(tracks, hero, wrist, t_end):
    """The object timeline: drawn, lost, recovered, broken, replaced by light."""
    katana = WorldProp("katana_gold", "katana", "gold", length=BLADE,
                       state="sheathed")
    katana.hold(2.55, "gold")                       # out of the scabbard
    x, y = wrist(tracks["gold"], 5.62)
    katana.launch(5.62, x, y, vx=-3.4, vy=-15.0, av=-0.44)   # disarmed
    katana.hold(10.60, "gold")                      # picked up out of the dirt
    x, y = wrist(tracks["gold"], 22.24)
    katana.shatter(22.24, x, y, pieces=4)           # and broken on his guard

    light = WorldProp("blade_light", "energy_spear", None, length=BLADE * 1.25,
                      colour=(255, 214, 140), state="unarmed", glow=1.0)
    light.conjure(23.04, "gold", t_end=29.60)

    rival = WorldProp("katana_violet", "katana", "violet", length=BLADE * 0.95)
    return [katana, rival, light]


#: the powers belong to two different men: the rival wakes up, the hero spends
#: everything he has left
POWERS = [
    {"kind": "awakening", "t": 16.00, "who": "violet", "ramp": 2.0},
    {"kind": "flash_step", "t": 18.94, "who": "gold", "count": 6, "spacing": 0.018},
    {"kind": "beam", "t0": 21.24, "t1": 21.78, "who": "gold", "on": "violet",
     "power": 1.15},
]


def destruction(tracks):
    """Where the floor takes the hit, measured from the body that hit it."""
    out = []
    for t, who in ((8.48, "violet"), (14.52, "gold"), (20.06, "violet"),
                   (21.70, "violet"), (22.24, "gold"), (23.30, "violet")):
        out.append({"t": t, "x": float(tracks[who].sample(t)[1]),
                    "power": 1.35 if t >= 21.0 else 1.0})
    return out


WALLS = {
    "violet": (23.30, 1140.0),
}

DUEL = dict(
    words=SETS,
    cast=CAST,
    hero="gold",
    intro=intro,
    beats=BEATS,
    after=after,
    titles=lambda words: [
        dict(t0=24.20, t1=25.60, text="K.O.", style="ko"),
        dict(t0=25.60, t1=30.20, text=words["title"], style="title"),
        dict(t0=25.62, t1=30.20, text=words["sub"], style="sub"),
        dict(t0=0.0, t1=30.0, text=words["hud"], style="hud"),
    ],
    props=props,
    powers=POWERS,
    destruction=destruction,
    lanes={"violet": 300.0},
    waiting=E_GUARD,
    walls=WALLS,
    ma=MA,
    ink=(5.62, 23.30),
    trim=3.2,
    guard=READY,
    #: shape gates for this film: a duel has one opponent, so the hero turns
    #: rarely; the beat sheet is denser than the three-man film's, because a
    #: two-body fight has no crowd to choreograph
    gates=dict(hero_turns=(0, 3), rival_turns=(0, 4), beats=(28, 40), dual_air=8),
    shots=(),
)


# ==================================================================== camera
# Twenty-five shots for a duel in the dark. The night plate is low-contrast, so
# the lens stays a little closer than it did in the sunset film: two bodies and
# a blade have to fill a frame that is mostly blue.
SHOTS = (
    dict(t0=0.00, t1=2.40, anchor="action", zoom=0.94, z1=1.00, follow=0.35,
         dof=0.05, style="cut", ground=0.81),
    dict(t0=2.40, t1=3.70, anchor="action", zoom=1.06, z1=1.12, follow=0.9,
         dof=0.08, style="cut", ground=0.79),
    # -- the first cuts, from the ledge
    dict(t0=3.70, t1=4.34, anchor="high", zoom=0.98, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=4.34, t1=5.10, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.08, style="cut", ground=0.78, zoom_hit=0.06),
    # -- the disarm: whip to the hand, because that is where the film turns
    dict(t0=5.10, t1=5.94, anchor="action", zoom=1.18, follow=1.0, dof=0.12,
         style="whip", ground=0.77, zoom_hit=0.12),
    # -- empty hands: tight and low, so the missing sword is the subject
    dict(t0=5.94, t1=6.60, anchor="action", zoom=1.14, z1=1.20, follow=0.8,
         dof=0.10, style="cut", ground=0.79),
    dict(t0=6.60, t1=7.20, anchor="action", zoom=1.10, z1=1.16, follow=1.0,
         dof=0.08, style="cut", ground=0.78, zoom_hit=0.05),
    dict(t0=7.20, t1=7.90, anchor="high", zoom=1.00, z1=1.06, follow=0.7,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    # -- the throw: the camera follows the body over the shoulder
    dict(t0=7.90, t1=8.80, anchor="action", zoom=1.12, follow=1.0, dof=0.12,
         style="whip", ground=0.77, zoom_hit=0.10),
    dict(t0=8.80, t1=9.70, anchor="action", zoom=1.16, z1=1.24, follow=0.35,
         dof=0.07, style="cut", ground=0.80),
    # -- walking to the blade, taking it, and the flurry that follows
    dict(t0=9.70, t1=10.80, anchor="action", zoom=1.06, z1=1.12, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    dict(t0=10.80, t1=11.90, anchor="action", zoom=1.12, z1=1.20, follow=1.0,
         dof=0.09, style="cut", ground=0.78, zoom_hit=0.07),
    dict(t0=11.90, t1=12.70, anchor="high", zoom=0.98, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=12.70, t1=13.90, anchor="action", zoom=1.10, z1=1.18, follow=1.0,
         dof=0.08, style="cut", ground=0.78),
    # -- the second throw, and the hold before the storm
    dict(t0=13.90, t1=14.90, anchor="action", zoom=1.14, follow=1.0, dof=0.12,
         style="whip", ground=0.77, zoom_hit=0.10),
    dict(t0=14.90, t1=15.90, anchor="action", zoom=1.12, z1=1.20, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    # -- the awakening: pull out, the stones have to be in shot
    dict(t0=15.90, t1=17.10, anchor="high", zoom=0.96, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.92, ground=0.85),
    dict(t0=17.10, t1=18.40, anchor="action", zoom=1.08, z1=1.16, follow=1.0,
         dof=0.07, style="cut", ground=0.78, zoom_hit=0.06),
    # -- the flash-step: a whip that lands on the man who is not there
    dict(t0=18.40, t1=19.40, anchor="action", zoom=1.10, follow=1.0, dof=0.10,
         style="whip", ground=0.78, zoom_hit=0.10),
    # -- the juggle: both men off the floor, and the floor still in shot
    dict(t0=19.40, t1=20.60, anchor="air", zoom=0.92, z1=1.02, follow=1.0,
         dof=0.08, style="cut", ground=0.70),
    dict(t0=20.60, t1=21.40, anchor="down", zoom=1.32, follow=1.0, dof=0.20,
         style="whip", ground=0.74),
    # -- the beam: the widest frame in the film, because something is crossing it
    dict(t0=21.40, t1=22.30, anchor="action", zoom=1.02, z1=1.10, follow=0.5,
         dof=0.05, style="cut", ground=0.80),
    # -- the blade breaks in his hand
    dict(t0=22.30, t1=23.30, anchor="action", zoom=1.16, follow=1.0, dof=0.12,
         style="whip", ground=0.77, zoom_hit=0.12),
    # -- and then there is a blade made of light
    dict(t0=23.30, t1=24.60, anchor="winner", zoom=1.20, follow=1.0, dof=0.14,
         style="cut", ground=0.80),
    dict(t0=24.60, t1=26.20, anchor="action", zoom=1.10, z1=1.16, follow=0.5,
         dof=0.10, style="cut", ground=0.82),
    # -- the field: the winner leaves, the man he put down stays in frame
    dict(t0=26.20, t1=28.20, anchor="field", zoom=0.96, z1=0.92, follow=0.4,
         dof=0.14, style="whip", ground=0.86),
    # -- and the last two seconds are his alone: the camera stops following the
    #    field and walks out with the man, so the title is not a freeze-frame
    dict(t0=28.20, t1=30.20, anchor="winner", zoom=1.10, z1=1.04, follow=1.0,
         dof=0.16, style="smooth", ground=0.83),
)

DUEL["shots"] = SHOTS
