# THE EMPTY HAND

**A 30-second duel. One blade, one man, and what a man does when the blade is gone.**

| | |
|---|---|
| **Format** | 1280 × 720, 24 fps, 30.2 s (725 frames), stereo 44.1 kHz |
| **Set** | the blue hour — moon, stars, cold stone (`assets/night_background.png`) |
| **Cast** | **GOLD**, a duelist with a katana · **VIOLET**, the man who takes it off him |
| **Render** | `python tools/render_clash.py --set duel-night --out renders/duel_night_720p.mp4` |
| **Source** | this sheet, transcribed to `fight/duel_script.py` |

> A duelist draws his blade, loses it in the first ten seconds, fights the next
> five with his hands, takes the blade back, learns the man across from him is
> something more than a swordsman, and answers it with a weapon he makes out of
> the air.

---

## Cast and staging

**GOLD** — right-facing, forward depth lane (`z = 0.24`), warm ochre. Carries a
katana that spends a third of the film in the dirt. He is the only fighter whose
weapon changes state, and the only one who ever has *no* weapon.

**VIOLET** — left-facing, a half-step back (`z = -0.16`), cold violet. Carries one
sword for the whole film and never loses it. He owns the awakening: the aura,
the stones, the lightning are *his*, and the hero has to survive them.

The camera never looks at the moon except by accident: the light source is the
top-left, and every shot keeps the fighters' feet on the stone.

---

## The beat sheet

Timecodes are contact times. Everything between them is windup, travel, hitstop
and recovery, compiled by `fight/beats.py`.

### ACT I — steel · 0.00 – 9.20

| Time | Beat | What happens | Camera | Sound |
|---|---|---|---|---|
| 0.00 | — | Gold walks in from the left, Violet from the right. Two men, one pool of moonlight. | wide, slow drift | wind, a single low string |
| 2.55 | draw | The katana leaves the scabbard — a *prop*, not a costume. | push in | steel hiss |
| 2.86 | guard | Gold's high guard answers it. Violet's blade comes up level. | medium | score enters |
| 3.94 | blitz ×1 | Violet cuts; Gold parries. | high, from the ledge | steel ring |
| 4.16 | blitz ×2 | Chained: the second cut is already moving. | holds | steel ring, tighter |
| 4.40 | rising dragon | Gold answers under it and opens Violet's ribs. | medium | body hit |
| 4.78 | blitz | Gold presses; Violet parries. | tight | steel ring |
| 5.08 | spin back | Violet turns through him, catches Gold across the head. | whip | steel + skull |
| **5.62** | **the disarm** | Gold commits to a cut, Violet catches the blade and turns it out of his hand. **The katana leaves the hand here.** | whip, on the hand | steel ring, then nothing |
| 6.34 | weave | Unarmed, Gold slips the next cut by a hand's width. | tight, low | air |
| 6.76 | taijutsu | Two punches and an elbow: the first time the fight is *physical*. | tight | fists |
| 7.44 | front kick | A sweep takes Violet's legs and puts him 300 px downrange. | high | thud, dust |
| 8.12 | collar grab | Violet gets a grip on him. | medium | cloth |
| 8.48 | judo slam | Gold throws him over the shoulder. The floor takes it. | whip, following the body | impact, debris |
| **9.20–9.70** | **Ma 1** | Both men stop. Twelve frames of nothing but breathing. | slow push | drop out |

### ACT II — the empty hand · 9.70 – 15.70

| Time | Beat | What happens | Camera | Sound |
|---|---|---|---|---|
| 9.86 | weave | The blade passes where his head was. | tight | air |
| 10.20 | blitz | Violet's cut is *parried* — with a forearm. | tight | arm hit |
| **10.60** | **the pickup** | Gold reaches down, takes his katana out of the dirt. Six transitions old by now. | medium, follows the hand | steel drawn from stone |
| 10.94 | blitz ×1 | Back to steel. Two cuts, no recovery. | tight | steel ring |
| 11.16 | blitz ×2 | — chained | — | steel ring |
| 11.40 | rising dragon | Violet is thrown 260 px. | medium | body hit |
| 12.10 | helm breaker | Violet comes down on him from above. | high | steel + ground |
| 12.90 | blitz | Parried. | tight | steel ring |
| 13.12 | riposte | Gold turns the parry into an attack in one motion. | tight | steel ring |
| 13.40 | spin back | And 280 px of knockdown behind it. | medium | body hit |
| 14.16 | collar grab | Violet takes *his* turn. | medium | cloth |
| 14.52 | judo slam | Gold goes over. | whip | impact, debris |
| **15.20–15.70** | **Ma 2** | The last quiet second. | slow push | drop out |

### ACT III — what Violet is · 15.70 – 21.40

| Time | Beat | What happens | Camera | Sound |
|---|---|---|---|---|
| **16.00** | **awakening** | Violet's aura lights: a ring at the pelvis, eight stones lift off the floor, lightning crawls the arms. It is *not* the hero's power. | pull out, hold the floor | sub drop, crackle |
| 16.06 | blitz | He moves inside it and puts Gold 300 px away. | wide | impact |
| 16.86 | weave | Gold slips the follow-up. | tight | air |
| 17.28 | taijutsu | Fists into a man made of light. | tight | fists |
| 18.06 | spin back | Violet answers. | medium | body hit |
| 18.86 | weave | Another slip. | tight | air |
| **18.94** | **flash-step** | Gold stops being in one place. Six residual silhouettes draw the path he did not walk. | whip | reversed riser |
| 19.26 | blitz | The cut lands out of nowhere. | tight | steel ring |
| **19.60–20.10** | **the juggle** | Rising dragon: Violet leaves the floor. Air pursuit: Gold follows him up. Meteor slam: both men come down. **Both airborne for nine frames.** | air — highest head and the floor in one frame | three hits, one held breath |
| 20.90–21.40 | **Ma 3** | Beat. | slow push | silence |

### ACT IV — light · 21.40 – 30.20

| Time | Beat | What happens | Camera | Sound |
|---|---|---|---|---|
| **21.24–21.78** | **the beam** | Gold plants both palms and fires. White core, plasma shell, a ray that keeps going *past* Violet, an impact dome twice as wide as the beam. | the widest frame in the film | charge, roar, ring |
| 22.24 | the break | Gold's katana meets Violet's guard and **shatters** into four pieces that bounce and stay. | whip to the hands | steel, then shards |
| **23.04** | **conjure** | He makes another one out of light. It has no scabbard and it will not outlive the fight. | medium | rising tone |
| **23.30** | **the kill** | One cut. Violet goes down and stays down. | tight, winner | final impact |
| 24.20 | **K.O.** | The card. | — | hit and tail |
| 25.60 | **THE EMPTY HAND** | The title, and the winner walking out of the moonlight with a blade of light in his hand. It goes out at 29.6. | field: he leaves frame left, the body stays in frame right | resolve |

---

## What the film is built to prove

1. **A weapon is an object.** It is sheathed at 0.0, drawn at 2.55, knocked out of
   the hand at 5.62, spins, sticks in the ground at 6.96, is picked up at 10.60,
   shattered at 22.24 and replaced by a conjured blade at 23.04. Six state
   changes, none of them welded to a wrist.
2. **The empty hand is a phase, not a pose.** From 5.62 to 10.60 the hero has no
   weapon: 208 frames of elbows, knees, sweeps, a collar grab and a throw.
3. **Powers belong to characters.** Violet awakens; Gold spends. The awakening is
   an environmental event (stones leave the floor, lightning, aura) and the beam
   is a *choice*, made once, at the end.
4. **The camera is a participant.** 27 shots: two high-angle frames for the
   exchanges that need both men, whips that land on the disarm, the break and the
   kill, one aerial frame that keeps the floor in shot, and a final field shot
   that leaves nobody cropped by the border.
5. **No narration.** Every story beat is in the choreography, the camera and the
   score. The only text on screen is the HUD line, the K.O. and the title.

## Gates

The film is checked by `tools/audit_film.py --set duel-night` and
`tools/audit_rig.py --set duel-night`; both exit non-zero on failure. The gates
are the round-10 ones: bones ≤ 1.0, `BODY_GAP`, Z-buffer, ground visible in
aerials, `wrong_facing_frames ≤ 18`, `weapon_state_changes ≥ 4`,
`superpower_events ≥ 5` systems, `whip_lag == True`, plus this film's own beat
sheet (three Ma holds, three hit zones, thirteen dual-air frames). 34 beats and
zero hero turns are declared by the script (`gates=`) — a duel has one opponent
to face, so a turn count calibrated on a 1-vs-3 pincer says nothing about it.
