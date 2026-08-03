# ADR 0012: Event-jump advance and haul duty cycle

## Status

Accepted (2026-08-03)

## Context

ADR 0010 fixed live ticks, offline catch-up, and Snapshot ownership. The mining
economy wave replaces discrete Hardness bands with exponential Face capacity,
Ore drops during mining (not only at break), and a Bag / Haul loop that suspends
digging until delivered Ore reaches the Cart. Live play and offline return must
stay on one `advance(dtMs)` path with exact chunk neutrality — no separate
tick-replay story for long absences.

## Decision

- **`advance(dtMs)` resolves mining by event jump:** segment the window at the
  next Ore drop, Face break, Bag-full, Haul-delivery, or Haul-completion
  boundary — not by replaying 250ms ticks — so live and offline play share one
  code path and chunk neutrality is exact.
- **Haul countdown scales with `rateScale`** like every other rate (including
  offline's 50% rate).
- **Smelter still drains once per window** after the mining / haul loop for that
  `advance` call.
- **Snapshot field deferral:** the field stays named `faceSwingProgress` because
  Pick Damage is 1, so Swings on the Face and damage dealt are the same number.
  Rename waits for the first Pick Damage other than 1.

## Consequences

### Positive

- Event boundaries align with player-visible moments (drops, bag full, haul
  complete) without tick-replay cost for 8h offline.
- One `advance` implementation covers Pane ticks and Dock relaunch catch-up.
- Haul duty cycle and Smelter backlog compose in the same windowed drain step
  ADR 0010 already assumed.

### Negative

- Event-jump segmentation is more branches than closed-form band math; tests must
  pin boundary order (drop before break, bag-full before haul start, etc.).
- `faceSwingProgress` naming is slightly misleading once Pick Damage can differ
  from 1; the rename is deferred, not forgotten.

## Rejected alternatives

**Tick replay for offline only.** Rejected: two paths diverge on chunk boundaries
and Upgrade timing; ADR 0010 already rejected this for the pre-haul engine.

**Instant Bag delivery (no Haul countdown).** Rejected: the Pane travel animation
and mining downtime share Haul Speed; skipping the countdown would desync
presentation from economy state.

**Rename `faceSwingProgress` to `faceDamageProgress` now.** Rejected: Pick
Damage is 1 for this wave; the rename buys no clarity until damage per Swing can
differ.
