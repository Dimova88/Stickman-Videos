# AGENT_INSTRUCTIONS — how a fight gets made in this repo

Read this before touching a single frame. It is the contract between the
creative director (the human) and whoever is animating — a person or an agent.
Everything below was written after a film shipped with melted legs, faces drawn
out of polygons and a comic star where a hit should have been.

The repo is Python. Any instruction that arrives as TypeScript, C# or a
YouTube tutorial is a description of an *effect*, never of a file to create.
Translate the constraint, not the code.

---

## 0. The clarification protocol

Ask before animating, not after rendering.

1. **Restate the shot in one sentence** ("a wide two-shot: hero parries, rival
   is thrown left"). If you cannot, you do not understand the shot yet.
2. **Name every moving body and where it starts and ends.** Positions that are
   not chosen are positions that will collide.
3. **Name the camera**: angle, height, whether it cuts inside the beat.
4. **Name the sound event** for every impact before it is animated. An impact
   with no sound is a bug.
5. **Only then** write keys. If a request is ambiguous about any of the four,
   ask one question and wait — a wrong 90-frame render costs more than a
   message.

Never invent story. The director owns the idea, the script and the cut; the
animator owns the physical truth of the frame.

---

## 1. Prohibitions

These are hard. A frame that breaks one is not "a style choice".

| Never | Because |
| --- | --- |
| Noses, mouths, lips, eyebrows, eyes drawn as shapes on a stickman head | at 40 px across they read as programmer art. Heads are silhouettes; the only feature allowed is a pair of glowing angular slits in a high-energy state. |
| A drawn human close-up built from primitives | same reason, ten times over. The dramatic accent is the two-frame ink hit. |
| Comic multi-point stars, white blobs with dots around them | a star has a fixed symmetric outline: it reads as a sticker. Use a hot bloom, irregular needles and falling debris. |
| Sine-wave limb oscillation, "waving" a sword | a limb travels along a path with anticipation and follow-through. If it looks like `sin(t)`, it is wrong. |
| Stacked idle enemies on one X | two bodies on the same spot destroy depth and read as one broken body. |
| Any attack, guard or "recover" key while a fighter is `DOWN` / `RAGDOLL` / `DEAD` | a body on the floor does not swing. Attacks are gated by state, not by willpower. |
| Feet pinned while the hips travel | that is what "spaghetti legs" means: the FK chain overshoots and the ankle floats. |
| Snapping `blur()` on and off | depth of field is continuous. Mix the blurred plate by depth, never toggle it. |
| Silhouette-only shots, OTS (over-the-shoulder) framings, an audience of dark shapes | both fighters are always drawn. The exception is the two-frame ink hit, which is a drawing of one blow, not a shot style. |
| Voice, narration, or any recognisable third-party audio | the film is original, or it cannot be monetised. Effort sounds stay non-verbal. |

---

## 2. The six pillars

### 2.1 Root motion

The hips are the body. Everything else follows.

* A foot is a **world-space target**, never an angle. The leg is solved to it.
* Reach is clamped: `maxReach = (l1 + l2) * 0.99`. A solved leg is never
  straighter than 99 % of its bones, so the knee always has one visible bend.
* A planted foot must not slide. If the hips move further than `maxStride`, the
  foot takes a step: a 6-frame interpolation with a parabolic lift.
* Rigid down state: once a body is on the floor, the pelvis is pinned at ground
  level, the shoulders are fixed relative to it, the feet are laid out in front,
  horizontal velocity decays (`vx *= 0.85`), and **no attack key may be authored
  until the body is up**.

### 2.2 Four-phase timing

Every action is four beats, not one:

1. **anticipation** — the pose loads, the weight shifts, the camera holds;
2. **strike** — 1–3 frames, the only time the limb is at full extension;
3. **impact** — hitstop. The world freezes for 2–4 frames, the blow rings out;
4. **recovery** — the body pays for it: overshoot, settle, back to guard.

A contact with no anticipation reads as a teleport. A contact with no recovery
reads as a loop. Both are worse than a missed hit.

### 2.3 Weapon smears

A katana at 24 fps is a hairline. It needs three things in the same frame:

* a **trail** built from a 4-frame buffer of `{hilt, tip}` samples — never from
  the current frame alone, which is a single line;
* a **bright edge** on the leading side only, so the smear has a direction;
* **continuity**: the trail must touch the blade's guard. A crescent floating
  two centimetres from the sword is exactly the "floating lines" bug.

Blades are tapered and pointed. A blade with a square end is a plank.

### 2.4 Impact frames

On the heaviest hits — the clash, the finisher, a killing blow — the film stops
being a photograph of a fight and becomes a drawing of one blow:

* **frame 1**: white silhouettes on black, radial needles from the contact;
* **frame 2**: the same drawing inverted, black on white;
* both frames come from the **real bodies**, drawn through the real camera with
  the colours swapped. Nothing is re-posed, so nothing can drift out of step.

Two frames. Rare. Never a resting composition.

### 2.5 1-vs-many spacing

One fighter engages; the others **wait, and are visibly somewhere else**.

* the engaged rival stands 100–160 units from the hero;
* every other rival is at least 260 units away, in its own lane, and is allowed
  to fall out of frame while the hero fights;
* a rival that is down stays down in its own lane until it is its turn;
* switching who is engaged is a *beat* (a step in, a step out), never a
  teleport.

### 2.6 Camera and audio sync

* A shot's zoom, height and depth of field change **continuously** inside the
  shot; a cut is the only place a hard change is allowed.
* Every camera move has a reason: the push follows the blow, the pull follows
  the body away, the whip follows the blade.
* Audio is derived from the same event list the picture uses — impacts, foot
  plants, the ink frames. If the picture and the score read two different
  timelines, one of them is wrong.
* Music reacts: it stops dead for a blade lock, drops out before the last blow,
  and peaks on it. A loop is a defect.

---

## 3. Pre-render checklist

Run through this before a 720-frame render, and again before calling the render
done.

- [ ] **Restore point** committed and tagged (`restore/<name>`) before the batch.
- [ ] **Every fighter faces its opponent** for the whole shot.
- [ ] **No two bodies closer than the spacing rule** at any frame — measure, do
      not eyeball.
- [ ] **No attack keys while down.** Grep the track for keys between the
      knockdown and the get-up.
- [ ] **Legs**: no frame where the ankle is further from the hip than the leg is
      long; no frame where a foot slides while planted.
- [ ] **Heads**: no feature but the slits. The ink frame inverts them too.
- [ ] **Blades**: no frame where the whole sword is a 1 px line; the smear
      touches the guard.
- [ ] **Depth of field** has no discontinuity inside a shot.
- [ ] **Impact frames** are two frames, and the frames either side are normal.
- [ ] **Audio**: no loop, no repeated impact sample, music drops out where the
      picture stops.
- [ ] **Sample the film**: pull frames at every second, view them as a contact
      sheet, and look for the frame that embarrasses you. There is always one.
- [ ] **Measure the claim.** "Fixed" is a number (a distance, a delta, a
      spectrum), not an adjective.

---

## 4. Where things live

| Path | What |
| --- | --- |
| `fight/core.py` | the rig: ten segments, FK solve, two-bone IK, the pose vector |
| `fight/poses.py` | the pose library — the floor poses are authored here, not ad hoc |
| `fight/ragdoll.py` | knockdown flight, bounce, skid and the get-up |
| `fight/clashfilm.py` | the renderer: camera, bodies, trails, impacts, HUD, ink frames |
| `fight/clash.py`, `fight/steel.py` | the choreography: keys, impacts, shots, score map |
| `fight/vfx.py` | contact shadows, dust, craters, bloom, the ink frame |
| `fight/sound.py` | foley, taiko score, mix. No samples, everything synthesised |
| `tools/render_clash.py` | the harness (`--set`, `--storyboard`, `--start/--end`) |
| `tools/audio_report.py` | loudness / spectrum report for a score |

Render with:

```bash
.venv/bin/python tools/render_clash.py --w 1280 --set steel-mountain \
    --out renders/steel_clash_720p.mp4
```

Probe a single frame without rendering the film:

```python
import fight.clashfilm as F
sc = F.scene("steel-mountain")
F.render_frame(16.90, sc).save("/tmp/frame.png")
```
