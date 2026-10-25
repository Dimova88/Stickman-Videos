"""STEEL — one blade against three men. The script, as data.

This module is the film: the cast, the twenty-six exchanges, the sword that
breaks at 14.4 s, the powers and the twenty-five camera shots. ``fight/steel.py``
hands it to :func:`fight.steelkit.assemble`, which knows nothing about this
particular story.
"""
from __future__ import annotations

from engine.weapons_and_props import WorldProp

from .beats import CombatBeat
from .poses import P, fade
from .steelkit import (BLADE, E_GUARD, HIGH, LOW, READY, TEAL, TEAL_DARK,
                       SLATE, SLATE_DARK)
from .clash import BLUE, BLUE_DARK, RED, RED_DARK

SETS = {
    "mountain": {"title": "MOUNTAIN STEEL", "sub": "ONE BLADE  •  THREE MEN",
                 "hud": "MOUNTAIN  •  STEEL"},
    "desert": {"title": "DESERT STEEL", "sub": "ONE BLADE  •  THREE MEN",
               "hud": "DESERT  •  STEEL"},
}


# ===================================================================== the cast
CAST = [
    dict(name="red", colour=RED, dark=RED_DARK, facing=1, z=0.30, weapon=BLADE),
    dict(name="blue", colour=BLUE, dark=BLUE_DARK, facing=-1, z=-0.85,
         weapon=BLADE * 0.90),
    dict(name="teal", colour=TEAL, dark=TEAL_DARK, facing=-1, z=0.45),
    dict(name="slate", colour=SLATE, dark=SLATE_DARK, facing=-1, z=-0.35),
]


def intro(tracks):
    """0-3.4 s: the walk-in, one man at a time, then the blade comes up."""
    hero, a, b, c = tracks[0], tracks[1], tracks[2], tracks[3]
    # ------------------------------------------------------------ 0-3.4 walk in
    hero.key(0.0, LOW, 566)
    a.key(0.0, E_GUARD, 1180)
    b.key(0.0, E_GUARD, 1268)
    c.key(0.0, E_GUARD, 1348)
    hero.key(1.10, fade(LOW, torso=-82), 578, "out")
    a.key(1.30, fade(E_GUARD, torso=-82), 940, "out")
    b.key(1.55, fade(E_GUARD, torso=-82), 1052, "out")
    c.key(1.80, fade(E_GUARD, torso=-82), 1150, "out")
    hero.key(2.20, READY, 596, "out")
    a.key(2.40, E_GUARD, 900, "out")
    b.key(2.60, E_GUARD, 1096, "out")
    c.key(2.80, E_GUARD, 1216, "out")
    hero.key(3.10, HIGH, 612, "snap")


#: the Ma holds: the two men stop and look at each other before the storm
MA = ((4.86, 5.36), (10.05, 10.55), (16.22, 16.72))


def B(t, atk, move, dfd, **kw):
    return CombatBeat(t, atk, move, dfd, **kw)


#: twenty-six exchanges
BEATS = [
        # -- flurry A: three cuts, no pause, then a kick that clears the room
        B(3.90, "red", "blitz_dash_slash", "blue", gap=54, chain=True,
          from_x=700, to_x=742, size=0.9),
        B(4.08, "red", "blitz_dash_slash", "blue", gap=52, chain=True,
          from_x=742, to_x=760, size=0.9),
        B(4.26, "red", "rising_dragon_slash", "blue", gap=50, chain=True,
          from_x=760, to_x=778, size=0.95),
        B(4.52, "red", "spartan_front_kick", "blue", gap=48, knock=300.0,
          from_x=778, to_x=800, size=1.1, zone="gut"),
        # -- grapple 1: blue gets a collar, red throws him over the shoulder
        B(6.10, "blue", "dash_collar_grab", "red", gap=30,
          from_x=760, to_x=850, size=0.9),
        B(6.52, "red", "overhead_judo_slam", "blue", gap=26, knock=330.0,
          from_x=820, to_x=846, outcome="down", size=1.1),
        # -- pincer: teal from the left, red turns and cuts back
        B(8.00, "teal", "blitz_dash_slash", "red", gap=56, knock=34.0,
          from_x=700, to_x=800, outcome="parry", size=0.95),
        B(8.30, "red", "spin_back_slash", "teal", gap=54, knock=300.0,
          from_x=846, to_x=904, size=1.15),
        # -- juggle 1: slate is lifted off the floor and finished in the air
        B(8.90, "red", "rising_dragon_slash", "slate", gap=46, launch=240.0,
          hold_air=0.50, from_x=904, to_x=940, size=1.1),
        B(9.10, "red", "air_pursuit_slash", "slate", gap=44, air=170.0,
          launch=230.0, hold_air=0.42, chain=True, from_x=940, to_x=958, size=1.0),
        B(9.38, "red", "air_meteor_slam", "slate", gap=42, air=60.0,
          knock=300.0, from_x=958, to_x=986, outcome="lethal", size=1.35),
        # -- weave and counter: the blade passes his face
        B(11.30, "red", "matrix_weave", "teal", gap=60, outcome="whiff",
          from_x=990, to_x=1000, size=0.8),
        B(11.70, "red", "sonic_thrust_pierce", "teal", gap=54, knock=190.0,
          from_x=1000, to_x=1052, size=1.1),
        # -- flurry B, the other way round, and a kick to answer it
        B(12.40, "blue", "blitz_dash_slash", "red", gap=54, chain=True,
          from_x=760, to_x=812, size=0.9),
        B(12.58, "blue", "rising_dragon_slash", "red", gap=52, chain=True,
          from_x=812, to_x=824, size=0.9),
        B(12.84, "red", "spartan_front_kick", "blue", gap=50, knock=300.0,
          from_x=824, to_x=860, size=1.05, zone="sweep"),
        # -- grapple 2: teal takes his turn to throw the hero
        B(13.90, "teal", "dash_collar_grab", "red", gap=30,
          from_x=1140, to_x=1050, size=0.95),
        B(14.32, "teal", "overhead_judo_slam", "red", gap=26, knock=330.0,
          from_x=1024, to_x=1048, outcome="down", size=1.1),
        # -- juggle 2 with EMPTY HANDS: his blade broke at 14.3, so the last
        #    kill before the duel is fists, a knee and a two-handed hammer
        B(15.20, "red", "taijutsu_combo", "teal", gap=46, launch=240.0,
          hold_air=0.50, from_x=820, to_x=880, size=1.1),
        B(15.40, "red", "knee_strike", "teal", gap=44, air=170.0,
          launch=230.0, hold_air=0.42, chain=True, from_x=880, to_x=898, size=1.0),
        B(15.68, "red", "air_meteor_slam", "teal", gap=42, air=60.0,
          knock=300.0, from_x=898, to_x=926, outcome="lethal", size=1.4),
        # -- the duel is down to two men on a cleared floor
        B(17.60, "blue", "blitz_dash_slash", "red", gap=56, knock=60.0,
          from_x=710, to_x=800, size=1.0),
        B(18.30, "red", "taijutsu_combo", "blue", gap=54, knock=300.0,
          from_x=850, to_x=908, size=1.15, zone="head"),
        B(19.60, "red", "sonic_thrust_pierce", "blue", gap=54, knock=170.0,
          from_x=960, to_x=1014, size=1.05),
        # -- the finisher: the spear goes, and what is left of the arena goes
        #    with it. Both palms, and the beam does the rest.
        B(22.44, "red", "energy_beam_blast", "blue", gap=200.0, knock=120.0,
          from_x=900, to_x=918, size=1.3),
        B(23.30, "red", "blitz_dash_slash", "blue", gap=42, knock=200.0,
          from_x=918, to_x=1010, outcome="lethal", size=1.8),
]


def after(tracks, beats):
    """The framing keys that only make sense once the beats are compiled."""
    hero, a, b, c = tracks[0], tracks[1], tracks[2], tracks[3]
    # the walk-in ends where the first beat begins
    hero.key(3.40, READY, 596, "out")
    a.key(3.40, E_GUARD, 588, "out")
    b.key(3.40, E_GUARD, 1152, "out")
    c.key(3.40, E_GUARD, 1228, "out")
    a.key(3.60, E_GUARD, 700, "out")
    # ---- the flash-step: he does not cross the arena, he *stops being* in one
    # place and starts being in the other. Two keys four frames apart: the body
    # is gone before the eye can follow it, and the afterimages draw the path
    # the audience is owed.
    hero.key(20.98, fade(READY, crouch=24), 1014, "out")
    hero.key(21.02, fade(READY, crouch=12), 900, "snap")
    hero.key(21.20, fade(READY, crouch=6), 902, "out")
    hero.key(24.20, READY, 1214, "out")

    # ------------------------------------------------------ 24.2-30 the sword
    hero.key(25.10, fade(READY, torso=-84), 716, "out")
    hero.key(26.40, fade(LOW, b_fore=8), 712, "out")
    hero.key(28.60, fade(LOW, b_fore=6, torso=-86), 708, "smooth")


def titles(words):
    return [
        dict(t0=25.34, t1=26.95, text="K.O.", style="ko"),
        dict(t0=26.95, t1=30.20, text="RED WINS", style="title"),
        dict(t0=26.95, t1=30.20, text=words["sub"], style="sub"),
        dict(t0=0.0, t1=30.0, text=words["hud"], style="hud"),
    ]


def props(tracks, hero, wrist, t_end):
    named_tracks = tracks
    katana_red = WorldProp("katana_red", "katana", "red", length=BLADE)
    x, y = wrist(hero, 14.40)
    katana_red.shatter(14.40, x, y, pieces=4)

    katana_blue = WorldProp("katana_blue", "katana", "blue", length=BLADE * 0.90)
    x, y = wrist(named_tracks['blue'], 12.86)
    katana_blue.launch(12.86, x, y, vx=-7.5, vy=-15.0, av=-0.46)

    # he carries two: the one he lost, and the one drawn from his back at 16.9
    spare_blue = WorldProp("katana_blue_2", "katana", "blue",
                           length=BLADE * 0.86, state="sheathed")
    spare_blue.hold(16.90, "blue")

    spear_red = WorldProp("spear_red", "energy_spear", None,
                          length=BLADE * 1.35, colour=(150, 240, 255),
                          state="unarmed", glow=1.0)
    # and at 24.55 the power lets go: the shaft of light goes out with the fight
    spear_red.conjure(19.35, "red", t_end=24.55)
    return [katana_red, katana_blue, spare_blue, spear_red]


#: the powers are a *timeline*, not a switch: what is on screen, when, and how
#: much of it. The renderer only samples this.
POWERS = [
    # his blade breaks, and something under it wakes up
    {"kind": "awakening", "t": 14.40, "who": "red", "ramp": 2.2},
    {"kind": "flash_step", "t": 21.00, "who": "red", "count": 6, "spacing": 0.018},
    {"kind": "beam", "t0": 22.30, "t1": 22.84, "who": "red", "on": "blue",
     "power": 1.15},
]

#: the floor loses: every slam and the beam put chips in the air
DESTRUCTION = [{"t": 9.40, "x": 986.0, "power": 1.0},
               {"t": 15.70, "x": 926.0, "power": 1.0},
               {"t": 22.52, "x": 1050.0, "power": 1.35},
               {"t": 23.34, "x": 1052.0, "power": 1.4}]

#: where a dead man's body is allowed to come to rest, keyed by name: three men
#: thrown the same way land on the same coordinate and read as one heap
WALLS = {
    "blue": (23.30, 1210.0),     # killed by the last exchange
    "teal": (15.68, 1075.0),     # killed by the empty-handed juggle
    "slate": (9.38, 950.0),      # killed in the air
}

STEEL = dict(
    words=SETS,
    cast=CAST,
    hero="red",
    intro=intro,
    beats=BEATS,
    after=after,
    titles=titles,
    props=props,
    powers=POWERS,
    destruction=DESTRUCTION,
    lanes={"blue": -350.0, "teal": 330.0, "slate": 430.0},
    waiting=E_GUARD,
    walls=WALLS,
    ma=MA,
    ink=(16.90, 23.30),
    trim=2.9,
)

SHOTS = (
    # -- the arena and the walk-in
    dict(t0=0.00, t1=2.30, anchor="action", zoom=0.92, z1=0.98, follow=0.30,
         dof=0.05, style="cut", ground=0.80),
    dict(t0=2.30, t1=3.70, anchor="action", zoom=1.02, z1=1.08, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    # -- the first exchange, from the ledge: you need the whole arc in frame
    dict(t0=3.70, t1=4.86, anchor="high", zoom=0.96, z1=1.02, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    # -- Ma 1: the blade is held, the lens drifts in, nothing cuts
    dict(t0=4.86, t1=5.45, anchor="action", zoom=1.14, z1=1.20, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=5.45, t1=6.05, anchor="action", zoom=1.08, z1=1.12, follow=1.0,
         dof=0.08, style="cut", ground=0.79),
    # -- the collar grab and the judo throw, tight: this is a grapple, not a swipe
    dict(t0=6.05, t1=6.95, anchor="action", zoom=1.16, follow=1.0, dof=0.10,
         style="whip", ground=0.78, zoom_hit=0.10),
    dict(t0=6.95, t1=7.95, anchor="action", zoom=1.02, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    # -- the pincer: two men at him, and the frame has to show both
    dict(t0=7.95, t1=8.65, anchor="high", zoom=0.98, z1=1.02, follow=0.7,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    # -- juggle 1: both men are off the floor, so the lens pulls out and the
    #    floor stays in shot -- the height only reads against the ground
    dict(t0=8.65, t1=9.62, anchor="air", zoom=0.90, z1=1.00, follow=1.0,
         dof=0.08, style="cut", ground=0.70),
    dict(t0=9.62, t1=10.05, anchor="down", zoom=1.34, follow=1.0, dof=0.20,
         style="whip", ground=0.74),
    # -- Ma 2
    dict(t0=10.05, t1=10.62, anchor="action", zoom=1.14, z1=1.20, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=10.62, t1=11.55, anchor="action", zoom=1.06, z1=1.10, follow=1.0,
         dof=0.05, style="cut", ground=0.79),
    dict(t0=11.55, t1=12.35, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.08, style="cut", ground=0.78, zoom_hit=0.06),
    dict(t0=12.35, t1=13.30, anchor="action", zoom=1.08, z1=1.14, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    # -- grapple 2, the other way round: teal throws the hero
    dict(t0=13.30, t1=14.50, anchor="action", zoom=1.16, follow=1.0, dof=0.12,
         style="whip", ground=0.78, zoom_hit=0.09),
    dict(t0=14.50, t1=15.15, anchor="action", zoom=1.02, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    # -- juggle 2
    dict(t0=15.15, t1=16.10, anchor="air", zoom=0.90, z1=1.00, follow=1.0,
         dof=0.08, style="cut", ground=0.70),
    # -- Ma 3: the last breath before it is one against one
    dict(t0=16.10, t1=16.80, anchor="action", zoom=1.16, z1=1.22, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=16.80, t1=17.90, anchor="action", zoom=1.04, z1=1.10, follow=0.9,
         dof=0.04, style="cut", ground=0.80),
    # -- the duel: dash, spin-back, thrust
    dict(t0=17.90, t1=19.90, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.10, style="cut", ground=0.78, zoom_hit=0.08),
    # -- straight in on the lock: the two blades are the shot
    dict(t0=19.90, t1=21.60, anchor="action", zoom=1.06, z1=1.20, follow=1.0,
         dof=0.06, style="cut", ground=0.78, zoom_hit=0.07),
    dict(t0=21.60, t1=22.60, anchor="high", zoom=0.98, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=22.60, t1=24.40, anchor="action", zoom=1.14, z1=1.26, follow=1.0,
         dof=0.10, style="whip", ground=0.78, zoom_hit=0.12),
    # -- tight on the body, but not so tight that the man who put it there is
    #    out of shot
    dict(t0=24.40, t1=25.90, anchor="winner", zoom=1.24, follow=1.0, dof=0.16,
         style="cut", ground=0.80),
    # -- the K.O. card needs the air above his head
    # -- the field: the winner walks off the left of the frame, the three men he
    #    put down stay inside the right of it. Nothing is cropped by the border.
    dict(t0=25.90, t1=30.20, anchor="field", zoom=0.94, z1=0.88, follow=0.4,
         dof=0.14, style="whip", ground=0.86),
)

#: the shot list is defined after the dict it belongs to only because it is 70
#: lines long; it is stitched in here rather than splitting the dict in two
STEEL["shots"] = SHOTS

#: kept for anything that still imports the old name
SHOTS_STEEL = SHOTS
