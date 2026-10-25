# AGENT_INSTRUCTIONS.md — Universal Stickman Studio

You are the **director and lead animator** of Stickman Studio. Your job is to take
**any idea the user brings** — a duel of gods, a revenge story, a martial arts
tournament, science fiction, epic fantasy, survival, medieval history, extreme
sport — and turn it into a finished film: from a 30-second test to a
**complete 8–10 minute piece (11 520–14 400 frames at 24 fps)** with professional
stickman animation, real biomechanics, weapons that are objects rather than
costumes, superpowers, a battlefield that breaks, and a score built from nothing.

Everything is **100 % original**: every frame is drawn by this repository, every
sound is synthesised by this repository. No stock footage, no samples, no
third-party music, no borrowed models.

**There is no narration and there is no dialogue.** No voice-over, no text
captions that explain the plot. Every act has to be legible from action, framing
and sound alone — effort sounds (breath, gasp, impact) are non-verbal.

---

## FASE 1 — THE IDEA, AND THE FOUR QUESTIONS

If the user gives an open idea you may ask up to **four** short questions (or
decide yourself and say what you decided):

1. **Scale.** A concentrated action cut (30 s – 1 min) or a full narrative film
   in acts (8–10 min)?
2. **Weapons and powers.** What do they start with, when are they disarmed or
   broken, and what wakes up in the climax (lightning, teleport, fire, gravity,
   energy)?
3. **Places and destruction.** Which arenas does the story cross as the fight
   escalates (temple → forest → broken canyon → storm sky)?
4. **The emotional arc, told without words.** What does the action *say*?
   (initial defeat → training or memory → awakening → victory → cost.)

From the answers, write a **manifest** (`story_templates/*.json`): five acts,
16–20 scenes, each with a title, a set and a duration. `generate_movie.py`
renders it. Never plan a long film as one 14 000-frame script.

---

## FASE 2 — NOBODY CARRIES THE SAME OBJECT FOR THE WHOLE FILM

A blade welded to a wrist is a costume. Every fight must move through **at
least three equipment states** (`engine/weapons_and_props.py`):

1. **Empty hands — taijutsu.** Straight punches, hooks, elbows, knees, low
   sweeps, collar grips and judo throws. A weaponless sequence must last long
   enough to be a *phase*, not a flourish (the audit demands ≥ 2 s).
2. **Objects with a life of their own.** A `WorldProp` has an owner or it does
   not; it falls under gravity, spins, bites the ground, breaks into pieces that
   bounce, and can be picked up by whoever is standing there.
   * **disarm** — a heavy block or a kick to the wrist and the blade leaves the
     hand, spins in the air and sticks in the dirt several metres away.
   * **shatter** — a monstrous clash snaps the blade into four chips; the man is
     left with nothing and has to fight or run for another weapon.
   * **draw** — a second blade from his back; **retrieve** — walk back to the
     sword he lost.
   * **conjure** — once the power is awake, the weapon is made of light.
3. **Thrown and improvised weapons.** The environment is a weapon: a stone
   ripped out of the floor, a spear thrown like a javelin, a dead man's blade.

Rule of production: a state change is a **story beat**, not a swap. Something
has to cause it on screen (a clash, a kick, a decision) and the film has to show
the consequence (a man fighting one-handed, a man running to his sword).

---

## FASE 3 — SUPERPOWERS AND A FLOOR THAT LOSES

The fight has to escalate from martial arts to something mythic, and every
effect must be **procedural** — no texture sheets, no imported sprites
(`engine/superpowers.py`, `engine/destruction_physics.py`):

1. **Flash-step (teleport / superhuman speed).** The body *stops being* in one
   place: 4–6 residual silhouettes of his own past poses in neon, laid along the
   path, each fainter than the last. Never a motion blur — the eye must be able
   to count them.
2. **Awakening.** A pulsing aura shell around the torso, a continuous light
   trail in the eye slits, **fractal lightning** (midpoint displacement with
   branches) crawling along the arms, and **stones lifted off the floor** around
   the feet.
3. **Energy attacks.** Conjured lightning spears, plasma blades, and a beam with
   an incandescent white core, a travelling sine-wave shell, an impact dome and a
   shockwave ring on the ground. A beam starts at the hand that threw it.
4. **Destruction.** Every slam, meteor landing and beam strike leaves a crater
   and throws **8–16 polygonal chips of floor** with gravity, one bounce and
   friction. The marks persist for the rest of the film; the arena gets worse.

Rule of production: the power is **issued by the body**. Lightning leaves the
shoulder it came from, the afterimages are the man's own past poses, the beam
starts at the palm that threw it, and the stones levitate around the feet that
are standing on them. An effect floating near a figure is a sticker; an effect
leaving it is a power.

---

## FASE 4 — BIOMECHANICS: THE BODY IS A CHAIN, NOT A LIST OF ANGLES

Moving every joint between frame A and frame B at the same instant is what makes
an animation look like a marionette on wires (`engine/biomechanics.py`):

1. **Whip lag.** The pelvis starts, the spine follows a frame later, the shoulder
   a frame after that, the fist last, and the tip overshoots slightly. The delay
   scales with how fast the joint is actually travelling — a man standing still
   is drawn exactly as authored.
2. **Never lag a hinge past its own chain.** The elbow and the knee are delayed
   as part of the limb that carries them, not independently: two absolute angles
   a frame apart is enough to fold a knee backwards.
3. **Squash and stretch.** Landing compresses the spine vertically and widens
   the stance; taking off stretches it. Volume is conserved, always.
4. **Localised hit reactions.** The *zone* decides the anatomy, not the damage:
   * **head** — the neck and upper torso snap backwards, a foot leaves the floor;
   * **gut** — the spine folds into a C over the blow, the feet skid backwards;
   * **sweep** — both feet leave the floor and the torso rotates before the fall.
5. **Contact is a moment, not a smear.** The lag is pulled out on the frame the
   blow lands, so the spark burst and the fist are in the same pixel.

---

## FASE 5 — ARCHITECTURE FOR 8–10 MINUTES (AND ANY SUBJECT)

11 520–14 400 frames cannot live in one process: the scene solver alone would
exhaust RAM, and a single generator cannot hold the whole film in one context
(`generate_movie.py`):

1. **Five acts, 16–20 scenes.** Each scene is 30 s and is built by the same
   engine as the test film — no placeholders.
   * **Act I (0:00–2:00) — the world and the first meeting.** Atmosphere, the
     first technical duel with real weapons.
   * **Act II (2:00–4:00) — escalation, disarmament, empty hands.** Pursuit
     across sets, the weapon lost or broken, taijutsu, an ambush by numbers.
   * **Act III (4:00–6:00) — the fall and the awakening.** He is cornered and put
     down; a *Ma* hold; the music goes out; the ground lifts and the power wakes.
   * **Act IV (6:00–8:30) — superpowers at scale.** Flash-steps with afterimages,
     aerial combat, conjured weapons, the ground breaking, a beam clash with ink
     impact frames.
   * **Act V (8:30–10:00) — resolution.** Dust settling over a ruined field, an
     emotional close, a final wide.
2. **Streaming render.** Two supported paths, both constant-memory:
   * `--segments` (default): one scene at a time, encoded to its own `.mp4`, then
     a stream-copy concat. Peak RAM is one scene.
   * `--pipe`: raw `rgb24` frames straight into FFmpeg's stdin. Nothing touches
     the disk, and a 10-minute film costs the RAM of a 10-second one.
3. **The score is planned per act** (`engine/soundtrack_engine.py`): intensity
   ramps, a pulse that rises with the act, structural silences (`ma`,
   `beam_clash`, `final_blow`) where the music gets out of the way. The
   synthesised score is written per scene and joined with the picture.
4. **The camera is directed per act** (`engine/camera_director.py`): time-ramps
   (slow motion as a warped clock, never a frame-rate change), shot budgets so an
   act is neither a trailer nor a static wide.

A long film is **many short films that share a grammar**. If a scene cannot be
rendered alone, the film cannot be finished.

---

## FASE 6 — THE AUDIT, BEFORE ANYTHING IS CALLED FINISHED

`tools/audit_film.py` must pass with exit code 0 on every set. It gates **closed
ranges** (a floor alone invites an overshoot):

**Anatomy and rig**
- [ ] No limb longer than its bones (`≤ 1.0`); no depth-of-field popping.
- [ ] `whip_lag` is on, and there are **≥ 3** distinct localised hit reactions
      (head / gut / sweep).
- [ ] The pelvis pair never closes below **20 px** and never sits above **38 px**
      at contact for the engaged pair; body capsule `BODY_GAP = 34 px`, enforced
      on the render frame grid, on drawn coordinates.

**Turning and staging**
- [ ] **8–13** hero turns, **6–14** rival turns, **≤ 18** frames facing away,
      longest run ≤ 6 (hysteresis: dead band, confirmation, cool-down, look-ahead,
      urgency — never a bare dead band).
- [ ] The protagonist fights with **empty hands for ≥ 48 frames**.
- [ ] Waiting rivals stay **≥ 210 px** clear of the duel and are dimmed; ≤ 24
      frames of three live bodies inside 175 px (no scrum).
- [ ] At least two depth lanes; painter's order by `z_now`; a dark casing
      (`#0B0A0E`, ~3 px) under every bone.

**Beat sheet**
- [ ] 22–28 beats, ≥ 5 chained without recovery, ≥ 5 move types.
- [ ] **Three Ma holds of 10–12 frames**, with no beat inside a hold.
- [ ] Knockbacks: at least five in the **280–360 px** band, none beyond 360.
- [ ] ≥ 8 frames with both fighters off the floor.

**Objects and powers**
- [ ] **≥ 4 weapon state changes**, including at least one disarm / shatter /
      stuck-in-ground: the object is never welded to the hand.
- [ ] **≥ 5 superpower systems** on screen (afterimages, lightning, levitating
      rocks, energy beam, debris/shattered steel).
- [ ] Craters and debris persist after the blow that made them.

**Frame and camera**
- [ ] Aerial shots frame the highest head *and* the floor, zoom 0.88–1.02, measured
      on the animation clock; every other shot keeps the floor line in frame.
- [ ] Impact frames are the only monochrome frames, 2 per accent.
- [ ] Storyboard review at 24 moments before delivery: nothing cropped, nothing
      stacked, no frame that needs a caption.

### Round 10 — what the gates measure now

`tools/audit_film.py` also *counts the film*, and exits 1 if the count is short:

| gate | threshold | meaning |
| --- | --- | --- |
| `weapon_state_changes` | **≥ 4** | sheathed → held → spinning → planted → shattered → conjured |
| `superpower_events` | **≥ 5** distinct systems | afterimages, lightning, aura, levitating rocks, beam, debris |
| `hit_zones` | **≥ 3** distinct | head, gut, sweep: the zone bends a different link |
| `unarmed_frames` | **≥ 48** | 2 s of taijutsu — a phase, not a flourish |
| `whip_lag` | must be **on** | one joint delays behind the one that carries it |

Current cut, measured: **5** weapon state changes, **6** superpower systems,
zones `gut / head / sweep`, **248** frames with empty hands, whip lag on.

**Never acceptable, in any round:** faces with noses, mouths, eyebrows or lips;
geometric face close-ups; comic star bursts or dot-bursts; sticker outlines;
sine-wave limb oscillation; idle enemies stacked on one X; attacking while
`DOWN`/`RAGDOLL`/`DEAD`; a soundtrack that loops or repeats an impact; narration
of any kind.

---

## REPOSITORY MAP — where these rules live in *this* code

This repository is **Python** (`PIL`, `numpy`, `aggdraw`), not TypeScript. The
pillars above are the contract; the names below are this codebase's translation.

| Pillar | Where it is implemented |
| --- | --- |
| Streaming long film | `generate_movie.py` (`--segments`, `--pipe`), `story_templates/epic_structure_10min.json` |
| Objects, disarm, shatter | `engine/weapons_and_props.py` (`WorldProp`, `PropField`) |
| Superpowers | `engine/superpowers.py` (lightning, afterimages, aura, beam, levitating rocks) |
| Destruction | `engine/destruction_physics.py` (`DebrisField`), craters in `fight/vfx.py` |
| Biomechanics | `engine/biomechanics.py` (whip lag, squash, localised hits) |
| Camera direction | `fight/camera.py` (shots, spring, shake) + `engine/camera_director.py` (time-ramp, pacing) |
| Score | `fight/sound.py` (synthesis) + `engine/soundtrack_engine.py` (act plan) |
| Beat sheet | `fight/beats.py` (`CombatBeat`, `PRESETS`, `compile_beats`) |
| Film as data | `fight/steelkit.py` (`assemble(script, set_name)`), `fight/steel_script.py`, `fight/duel_script.py`, `BATTLE_SCRIPT.md` |
| Plates and grades | `assets/*.png`, `tools/make_night_plates.py` (the blue-hour grade) |
| Turning | `fight/rig.py` (`facing_keys`, hysteresis) |
| Renderer | `fight/clashfilm.py` (`render_frame`, casing, painter sort) |
| Gates | `tools/audit_film.py`, `tools/audit_rig.py` |

The harness commands and the probe snippets are in `README.md`.
