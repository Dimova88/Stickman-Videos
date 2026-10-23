# THE EIGHTH GATE

**Format** stick-figure anime short → **8-minute** film (target)
**Logline** A nameless fighter walks through the gate he was forbidden to open,
and finds the one person he could never beat waiting on the other side.

> Status: **Chapter 0 — "The Door"** is built as a 30-second teaser
> (`scenes/eighth_gate.py`, `renders/eighth_gate_1080p.mp4`). Everything below
> it is the roadmap for the 8-minute cut.

---

## Rules of the picture

1. **No dialogue in the teaser.** Everything is told with bodies, light and
   sound. Chapter 1 onwards may use sparse, single-line voice (a narrator, not
   a character), because a wordless 8 minutes is hard to retain viewers on.
2. **One colour has meaning.** Orange = the gate, the past, the master.
   Blue-white = the boy, the present. Red = the rival. Eyes glow only when a
   character decides something.
3. **Every hit costs something.** After each exchange the fighters breathe, the
   camera settles, and the world reacts (dust, water, birds).
4. **The camera is a character.** It never floats idly; it either pushes in with
   intent or holds completely still while the world moves.

## Chapter 0 — The Door (0:00 – 0:30) — *built*

| # | len | shot | sound |
| --- | --- | --- | --- |
| 1 | 2.6 s | Void. One lantern far away. Slow push. | bell, sub drop, low pad |
| 2 | 3.4 s | Wide: moon, ridge, a lone figure. Warm glow on the horizon. | braam, pad swell, distant wind |
| 3 | 4.0 s | Low angle: the torii gate and its steps in rain. | reversed whoosh, rain bed, taiko |
| 4 | 2.0 s | Macro: a bare foot landing on wet stone, ripples. | step, splash, breath |
| 5 | 3.0 s | Extreme close-up: the face, the eye ignites. | heartbeat ×2, riser, chime |
| 6 | 3.0 s | The gate opens — light pours out under the lintel. | braam + boom + taiko on the flash |
| 7 | 3.5 s | Reverse: the rival stands in the doorway, arms crossed. | choir, heartbeat, wind |
| 8 | 3.0 s | Face-off, low wide, two colours in one frame. | taiko, riser |
| 9 | 3.5 s | Dash → clash → impact frame → aftermath. | whoosh, slash, boom (everything on 1.05 s) |
| 10 | 2.0 s | Title. | final braam, choir tail |

**Timing rule used throughout:** the only audio that is allowed to be perfectly
on the grid is the clash at 25.55 s. Everything before it drifts slightly late,
so the hit *feels* like it lands.

## Chapter 1 — The Boy Who Was Told No (0:30 – 2:00)

* Cold open: a village at the foot of the mountain, rain on a shrine roof.
* The master (orange, older, slower) teaches a strike in three movements. The
  boy copies; the copy is wrong. Repeat *three* times, faster each time.
* Beat: the master's hand stops an inch from the boy's throat, without touching
  it. Held 1.5 s. Cut to black on the exhale.
* Music: solo taiko + low strings. No choir yet.

## Chapter 2 — Eight Gates (2:00 – 4:00) — *the training montage*

* Seven gates, seven trials, seven short scenes (8–12 s each) — the montage the
  audience came for. Each gate is a different environment (bamboo, snow, water,
  fire, ruins, sky, dark) and a different lesson.
* Each trial ends with a **single-frame** flash of the boy's eye.
* Hard cut to the eighth gate being *absent* — a stone wall with no door.
* Music: pulse builds one semitone every gate (D → D# → E …), the last one cut
  dead to silence.

## Chapter 3 — The Door (4:00 – 5:30)

* The teaser, expanded. The wall opens; the rival steps out.
* First exchange: five blows in three seconds, all in one unbroken camera move.
* The boy loses the exchange and the ground (falls through a roof).
* Music: full theme for the first time.

## Chapter 4 — The Other Side (5:30 – 7:00)

* The boy is inside the gate: the memory of the master, inverted colours.
* Reveal: the rival *is* the master's other student — the one who was told yes.
* The fight becomes a conversation. Two attack patterns answering each other.
* Music: choir + taiko trading phrases.

## Chapter 5 — The Eighth Blow (7:00 – 8:00)

* Climax in the rain, one continuous 40-second shot, camera circling.
* The final blow is never shown connecting: cut to white, cut to the empty gate
  at dawn with two sets of footprints leading away.
* Title card → end card (next chapter teaser, 6 s).

---

## Production notes

* **Shot budget:** ~70 shots for 8 minutes (≈7 s average), of which 25 are
  micro-shots under 2 s.
* **Render budget:** 11 520 frames at 24 fps; at the current engine speed
  (≈2 fps at 1080p on 2 cores) that is ~1.6 hours, split across nights.
* **Reusable assets:** every environment in `pipeline/core/sets.py` is
  parameterised by a `Palette`, so Chapters 1–5 reuse the same geometry with
  new light. New sets needed: village roofs, snow field, water surface, ruins,
  sky/clouds above the cloud line, inverted "memory" world.
* **New poses needed:** ~18 more (grapple, throw, fall, rise, kneel-to-stand,
  sheath, unsheath, guard-break, aerial spin, wall-run, roof-land, breathing
  idle ×3 variants, two formal bows).
* **Monetisation:** all visuals are generated by this repository, all audio is
  synthesised by `pipeline/core/audio.py` — no third-party footage, music or
  samples, so Content ID has nothing to match. Fonts are Noto Sans (OFL).
* **Retention design:** cold open under 5 s, title only at the end of the
  teaser, and a hard cut to black with a sound cue every 20–30 s.
