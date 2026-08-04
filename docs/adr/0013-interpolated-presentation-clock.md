# ADR 0013: Interpolated presentation clock

## Status

Accepted (2026-08-03)

## Context

The Dwarf swing clip has nine frames over a 1000 ms cycle at Dig Rate 1, but
the sim pump advances presentation state only on 250 ms ticks while the render
loop runs every animation frame. Every frame inside a tick window therefore drew
the same `frameIndex`, skipping intermediate frames and producing uneven motion.

Nightglass diagnosed and fixed the same class of bug in
[ADR-0003](https://github.com/jsbellamy/nightglass/blob/main/docs/adr/0003-interpolated-presentation-clock.md):
motion updated at sim cadence (~4 Hz) while pixels updated at display cadence
(~30 Hz), which reads as uneven frame rate.

ADR 0010 fixed the economy on a 250 ms sim tick; that cadence must not change.

## Decision

Run **two clocks**:

1. **Sim clock** — `MinePresenter.simNowMs`, advanced by `dtMs` inside
   `advanceMs` on each pump tick. Economy stays on this path; mining audio
   **cues** are stamped here but not played (see Audio below).
2. **Presentation clock** — `mountPaneShell` caches `lastSimNowMs` and
   `lastTickAtMs` on each tick and, on every render frame, samples:

   ```ts
   const elapsed = Math.max(0, clockNow() - lastTickAtMs);
   const presentationNowMs = Math.floor(
     lastSimNowMs + Math.min(elapsed, PUMP_INTERVAL_MS),
   );
   ```

   **One-tick clamp:** never extrapolate more than `PUMP_INTERVAL_MS` past the
   cached sim time. If a tick is late (GC, throttling), unclamped interpolation
   would run ahead of the sim and **rewind** when the tick lands; holding until
   the sim catches up is preferred to visible backward motion. The result is
   floored to integer milliseconds.

`MinePresenter.snapshot(nowMs?)` defaults `nowMs` to `simNowMs` when omitted;
`render` passes the interpolated presentation value.

**Swing phase from the engine (Underline divergence from Nightglass ADR-0003):**
while `animation === "swing"`, clip phase is the fractional part of
`faceSwingProgress`, interpolated across the tick:

```
progress = faceSwingProgressAtLastTick + digRate * (nowMs - lastSimNowMs) / 1000
swingFraction = progress - floor(progress)
```

Interpolation is suppressed while `haulRemainingMs > 0`. Walk and idle clips use
clock-absolute `frameIndexAt(nowMs)` on `DwarfAnimController`; the tick path no
longer calls `anim.advanceMs`.

**Swing impact alignment (#377):** `frameIndexForSwingFraction` phase-shifts the
clip so `SWING_IMPACT_FRAME` (pick contact) is displayed when `swingFraction`
is 0 — i.e. when `faceSwingProgress` crosses an integer. Walk and idle are
unchanged.

**Audio release (#378, Nightglass ADR-0003 departure):** `advanceMs` passes
`MiningEvent`s from `advanceLive` to `MiningAudio.handleEvents(events,
windowStartSimMs, dtMs)` using the sim time *before* `dtMs` is applied, so each
cue's absolute time is `windowStart + event.atMs`. Nothing plays on the tick
path. `mountPaneShell`'s `render` calls `releaseAudioDueTo(presentationNowMs())`
before `snapshot`; `releaseDueTo` schedules due cues on the `AudioContext`
timeline at `currentTime` plus offset rather than firing immediately.

## Consequences

### Positive

- Every swing frame is drawable within a cycle at display cadence.
- Swing animation re-anchors to simulation every tick and cannot accumulate
  phase error.
- ADR 0010's 250 ms sim tick and Snapshot ownership are unchanged.

### Negative

- Presentation state (`simNowMs`, cached tick anchors) is transient and
  meaningless across sessions — not persisted in `MiningSnapshot`.

## Source

Ported from Nightglass ADR-0003 (interpolated presentation clock). Underline
derives swing phase from `faceSwingProgress` rather than clip elapsed time.
