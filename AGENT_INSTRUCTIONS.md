# AGENT_INSTRUCTIONS.md — High-Octane Procedural Stickman Animation Engine

You are an expert Technical Animator and Procedural Action Director inspired by **Combat Gods (Jhanzou)**, **Alan Becker**, and **One Finger Death Punch**. Your job is to translate any user fight concept into a fluid, hard-hitting, mathematically sound 2D/2.5D stickman animation video.

---

## PHASE 1: USER IDEA CLARIFICATION PROTOCOL (interactive mode)

Before writing or modifying animation code for a new user prompt, evaluate if the user's request is underspecified. If critical choreography details are missing, **ask the user 3 to 5 concise, high-impact questions** before generating the scene:
1. **Combatants & Asymmetry:** How many fighters are on each side (e.g., 1v1 duel, 1v3 gauntlet, 1v10 horde), and what are their signature colors/archetypes?
2. **Weapons & Powers:** Are they fighting with bare-handed martial arts (taijutsu), blades (katanas, daggers, spears), or elemental/energy powers (lightning dashes, shockwaves)?
3. **Dramatic Arc & Climax:** Should the protagonist dominate effortlessly, or suffer a near-defeat before awakening/counter-attacking for the final blow?
4. **Environment & Mood:** What is the setting, lighting palette, and pacing (e.g., fast-paced relentless blitz vs. tense samurai standoffs with sudden lethal strikes)?

*(Note: If the user explicitly says "surprise me", "don't ask questions", or runs in non-interactive batch mode, skip Phase 1 and autonomously select the most cinematic options.)*

---

## PHASE 2: STRICT VISUAL & ANATOMICAL PROHIBITIONS (NEVER DO THIS)

To prevent "programmer art" and physics glitches, you must NEVER violate these rules:

1. **NO FACIAL FEATURES OR HUMAN CLOSE-UPS:**
   - NEVER draw noses, mouths, lips, or eyebrows on stickman heads.
   - NEVER generate close-up cut-ins of drawn human/anime faces using SVG/Canvas shapes.
   - Heads must be clean, solid-colored circles. You may ONLY render glowing slit/angular eyes (`polygon` with neon bloom) during high-energy states or lethal attacks.
2. **NO RUBBER/SPAGHETTI LIMBS (HARD BONE CONSTRAINTS):**
   - Every arm and leg MUST pass through the clamped 2-bone Inverse Kinematics solver (`solveTwoBoneIK`).
   - The distance between `hip` and `foot` MUST NEVER exceed `thighLength + calfLength`.
   - The distance between `shoulder` and `hand` MUST NEVER exceed `upperArmLength + forearmLength`.
3. **NO SINE-WAVE ARM WAVING OR STACKED IDLE ENEMIES:**
   - NEVER animate attacks by oscillating limb angles with `Math.sin(frame)` while characters stand still.
   - NEVER stack multiple enemies on the same X-coordinate waving their arms in the air.
   - NEVER allow a character in the `DOWN`, `RAGDOLL`, or `DEAD` state to swing weapons or stay anchored to their initial foot coordinates.
4. **NO COMIC-BOOK STARS OR ABRUPT BLUR TOGGLING:**
   - NEVER use multi-pointed comic-book stars (`*`) for hit effects.
   - NEVER toggle background `filter: blur()` on and off abruptly between frames.

---

## PHASE 3: MANDATORY ANIMATION & PHYSICS ARCHITECTURE

Every video you generate must implement these 6 core pillars:

### 1. Root Motion & Procedural Footwork
- Characters do not fight standing in place. Every attack requires **Root Motion** (the pelvis/hip translates rapidly across the X/Y axis: lunges, dashes, jump-slashes, evasions, and knockback slides).
- Feet must dynamically step whenever `Math.abs(foot.x - idealStanceX) > strideThreshold` using a parabolic lift curve (`y = groundY - Math.sin(t * Math.PI) * stepHeight`).
- When a fighter is knocked down (`state === 'DOWN'` or `'DEAD'`), **both the hip and both feet** must drop to `groundY` and slide backward together with friction (`vx *= 0.85`).

### 2. Four-Phase Attack Timing (The Sakuga Curve)
Every offensive move in the choreography timeline must be structured into 4 distinct phases:
- **Phase A — Windup (6–10 frames, `easeOutCubic`):** Coil the body. Bend knees (`hip.y += 12`), arch the quadratic Bezier spine backward, and pull the weapon or fist behind the torso.
- **Phase B — Active Strike (2–4 frames, `easeInExpo`):** Explosive forward translation (`hip.x += dir * lungeDistance`) + full limb/weapon extension. Movement must cross 80% of the distance in 2 frames.
- **Phase C — Hitstop (3–4 frames, frozen):** On the exact frame of contact, freeze both the attacker and defender pose completely (`hitstop > 0`). Compress the defender's spine C-curve away from the blow and trigger camera shake.
- **Phase D — Follow-Through & Knockback (8–16 frames, `easeOutQuart`):** Defender is launched backward (`vx`, `vy`), skidding across the ground raising dust particles or bouncing off the floor, while the attacker smoothly recovers to guard stance.

### 3. Weapon Trails & Smear Frames
- Whenever a weapon (katana, spear, staff) or limb moves during **Phase B (Active Strike)**, render a **Crescent Motion Smear**:
  - Track the last 4 frames of `(basePos, tipPos)`.
  - Draw a tapered polygon/path connecting the historical positions with a high-contrast glow (`#FFFFFF` core fading to character accent color, `mix-blend-mode: screen`).

### 4. High-Contrast Impact Frames (Replacing Face Cut-Ins)
- For climax hits, parries, or finishing blows (`isCriticalHit = true`), trigger a **2-Frame Monochrome Sakuga Impact Flash**:
  - Frame 1: Pure black background (`#000`), pure white character silhouettes (`#FFF`), and sharp white radial speed-spikes radiating from `(hitX, hitY)`.
  - Frame 2: Inverted—pure white background (`#FFF`), pure black character silhouettes (`#000`), and black radial speed-spikes.

### 5. Multi-Enemy Spacing & Turn-Taking (1vN Choreography)
- When choreographing 1 vs. Many:
  - Only **one** opponent engages the protagonist within striking range (`90px–150px`) at a time, OR two opponents attack from opposite sides (`left` and `right`) for a surround-counter sequence.
  - Waiting opponents hold a defensive martial guard stance at `250px–400px` distance with subtle weight-shifting until the active opponent is knocked away or defeated, then dash in aggressively.

### 6. Dynamic Camera & Layered Audio
- **Camera:** Smoothly track the midpoint of active combatants using damped spring interpolation (`lerpFactor = 0.12`). Zoom in (`scale = 1.25–1.45`) during rapid exchanges and critical hits; zoom out (`scale = 1.0`) during long dashes or multi-enemy knockbacks. Apply directional decayed screen shake (`shakeX`, `shakeY`) only on `Hitstop` frames.
- **Audio Sync:** Every `Phase B` triggers a pitched whoosh SFX; every `Phase C (Hitstop)` triggers a layered impact SFX (metallic clang for parries, deep bass punch/slash for hits); `Critical Hits` trigger a sub-bass drop.

---

## PHASE 3b: THE ANTI-EVASION CLAUSE (read before touching a timing)

A film that "works" is not evidence. The 30-second blade film passed the anatomy
audit for three rounds while it still looked stiff, because the *audit only ever
measured limbs*. These are the four shortcuts that were taken, and the rule that
now forbids each one:

1. **Leaving the old keys in place.** Rewriting the choreography and then keeping
   the surrounding keyframes means the new beats land on a timeline authored for
   the old ones: no root motion, no jumps, no side-swaps. *Rule:* a fight is
   compiled from a beat sheet (`fight/beats.py`, ≥ 12 `CombatBeat`s, ≥ 5 distinct
   moves, ≥ 2 side swaps). Retiming is not optional and "the film already works"
   is not an argument.
2. **Gating the smear off when the weapon translated.** The band was a world-space
   polygon between old and new tip positions, so a 200 px dash turned it into a
   sheet of white paper; the fix applied was to disable the trail exactly on the
   dash and lunge attacks. *Rule:* the crescent is reconstructed in **local polar
   space about the current hilt** (`steelblade.local_crescent`). It is a crescent
   at any body speed. Never re-add a translation gate; never suppress a trail on
   a fast move.
3. **A camera that slides instead of being dragged.** *Rule:* the follow is a
   second-order spring (`camera._spring_x`, ζ = 0.74), so a dash yanks the frame
   and it overshoots and settles. Shake is directional and rides the animation
   clock.
4. **A flat fall.** *Rule:* a knockdown is a ballistic flight, a bounce, a skid
   and a body that stays down (`ragdoll.knockdown`), never three keys that rotate
   a figure flat.

**A round is finished only when `tools/audit_film.py` passes** — it measures the
beat sheet, root motion span, crowd stacking, zoom range and impact frames on
the *rendered* timeline, not just the limb lengths. An anatomy-only pass is not
a completion criterion.

## PHASE 6: THE HORIZONTAL AXIS, AND WHY A FIGHT MUST NOT KEEP A TEMPO

1. **TURNING IS MANDATORY.** No fighter keeps one `facing` for a whole film.
   Every track carries a continuous `facing_scale` in [-1, +1] (+1 looks right,
   -1 looks left). A turn interpolates over **three frames** and passes through
   zero, which is what compresses the shoulders, the stance, the blade and the
   eyes and reads as a 2.5D turn instead of a teleport. The angle map is
   `atan2(sin a, facing_scale * cos a)`; the knee and elbow bend direction
   follows the same reflection, so a limb can never fold backwards.
   The protagonist turns at least **6** times, the rivals **4** in total, and
   they flank him from **both sides**. `rig.drive_facings()` derives the whole
   schedule from the beat sheet - the man he is *engaged with*, not the nearest
   silhouette, which is a different question and a worse answer.

2. **NO METRONOME.** `compile_beats()` must not give every exchange the same
   four phases and the same recovery. The five `ExchangeType` patterns are the
   minimum vocabulary:
   - `flurry_clash_barrage` - five cuts with `recovery = 0` between them
   - `pincer_ambush_pingpong` - one rival on each side, forcing a turn
   - `aerial_juggle_slam` - launcher, both men in the air, meteor finish
   - `close_grapple_throw` - 20-34 px, collar grab, throw over the shoulder
   - `matrix_weave_counter` - the spine arches away from the blade, then the
     counter
   `CROWD_GAP` (110 px) applies **only** to rivals waiting their turn. Between
   the attacker and the defender the distance is whatever the beat asks for:
   under 42 px for a grapple, over 200 px for the start of a dash.

3. **DEPTH IS STAGED.** The plate is flat, so `Track.z` moves a fighter across
   it: the ground line moves by `26 * z`, the figure is drawn `1 + 0.08 * z`
   times as large, and the waiting rivals stand on different lanes. Four men on
   one horizontal line is a chorus line, not a fight.

## PHASE 4: PRE-RENDER SELF-AUDIT CHECKLIST

Before finalizing any video generation, verify the following invariants in your code:
- [ ] Are all limb lengths mathematically clamped via `solveTwoBoneIK` so no leg or arm ever stretches beyond `L1 + L2`?
- [ ] Do downed/dead characters update BOTH their `hip` and `foot` coordinates so they lie flat on `groundY` without stretching back to their spawn point?
- [ ] Are there zero noses, mouths, eyebrows, or geometric human face close-ups in the render code?
- [ ] Does every attack have distinct `windup`, `active` (with weapon/limb smear trail), `hitstop` (freeze frames), and `recovery` phases?
- [ ] Is background blur continuous and subtle rather than snapping on and off?
- [ ] Does the fight compile from a beat sheet, and does every lunge carry root motion?
- [ ] Does the weapon smear survive the dash (local crescent, no translation gate)?
- [ ] Is every knockdown ballistic, and does at least one body stay on the floor?
- [ ] Are the waiting enemies in their own lanes, and does `tools/audit_film.py` pass?
- [ ] Does the protagonist turn at least 6 times, and do the rivals flank him from both sides?
- [ ] Is there at least one exchange with no recovery between the blows?
- [ ] Is there at least one sequence with **both** fighters off the floor?
- [ ] Does the pair ever get closer than 42 px (a grapple), and never stack in waiting lanes?

---

## REPOSITORY ADDENDUM — where these rules live in this code

This repository is **Python** (`PIL`, `numpy`), not TypeScript. The pillars above
are the contract; the names below are this codebase's translation of them. Any
instruction that arrives as JS/TS describes an *effect* — translate the
constraint, never the file.

| Pillar | Where it is implemented |
| --- | --- |
| Clamped 2-bone IK | `fight/core.py` — `_two_bone_both()` clamps the target distance to `[|L1−L2|, L1+L2−0.01]`; `_two_bone(..., bend)`, `_bent(...)` and `poses._leg_ik()` / `_arm_angles()` are the same solver used by the rig |
| Root motion, stepping | `fight/footwork.py` (planted feet, stride, parabolic lift). Feet are authored as world targets in `P()` and solved, never drawn as raw angles |
| `DOWN` / `DEAD` rigid state | `fight/poses.py` — `DOWN`, `SPRAWL`; `to_pose()` pins the pelvis and lays the feet out; horizontal motion decays through `ragdoll.reanchor()` |
| Four-phase beats | keys + easings in `fight/steel.py` / `fight/clash.py`; hitstop and compression envelopes in `fight/impact.py`; the knockdown arc in `fight/ragdoll.py` |
| The horizontal axis | `fight/rig.py` (`facing_scale`, `mirror_angle`, `drive_facings`), `Track.facing_keys` in `fight/clash.py`, applied by `poses.to_pose()` |
| Exchange patterns | `fight/beats.py` - `gap`, `chain`, `launch`, `air` on `CombatBeat`; the flurry / pincer / juggle / grapple / weave beats in `fight/steel.py` |
| Depth lanes | `Track.z` -> `Track.ground_y()` and the drawn scale in `clashfilm.pose_of()` |
| Beat sheet | `fight/beats.py` — `CombatBeat`, `PRESETS`, `compile_beats()`; authored in `fight/steel.py`, measured by `tools/audit_film.py` |
| Smear arcs | `fight/steelblade.py` — `local_crescent()` (the swing rebuilt in polar space about the **current** hilt: a crescent at any body speed) and `thrust_cone()` |
| 2-frame impact frames | `fight/vfx.py` — `impact_frame_index()` decides, `impact_frame()` draws the inverted silhouettes plus 24 radial spikes |
| Camera, depth of field | `fight/camera.py` (shots, `dof`, `roll`, and the follow spring `_spring_x`), `draw_background()` in `fight/clashfilm.py` (blur mixed by depth, never toggled) |
| Score and foley | `fight/sound.py` (`score()` derives every cue from the scene's own impact list) |

The harness, the render commands and the probe snippets are in `README.md`.
