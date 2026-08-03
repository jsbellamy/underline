# ADR 0010: Mining engine tick, Snapshot, and Pane-owned save

## Status

Accepted (2026-08-03)

## Context

The vertical slice needs one deterministic place where Dig Rate, discrete Face
breaks, Smelter throughput, Upgrades, and offline catch-up meet. Nightglass left
its combat Engine behind; Underline must not invent a second wall-clock story
for live play versus relaunch. Issue #320 locked the contract; detail lives in
`docs/research/tick-snapshot-save-model.md`.

## Decision

- **Live:** fixed 250ms sim ticks via the vendored pump; pure `advance(dtMs)`.
- **Offline:** the same `advance` with closed-form / event-jump catch-up (not
  tick-replay), at the economy’s 50% rate, capped at 8h.
- **Seam:** deterministic Snapshot; UI and presentation never mutate economy
  fields; wall clock exists only at persist/boot.
- **Save:** JSON in `localStorage` (`underline-save-v1`); Pane is the sole
  writer; Dock is Snapshot/command client only. Ship `schemaVersion: 2`; load of
  v1 maps `upgradeCount` → `digRateUpgradeCount`, sets `smelterUpgradeCount: 0`,
  rewrites as v2 on next persist (persist key name unchanged).

## Consequences

### Positive

- `/tdd` can prove both loops with Snapshot fixtures before canvas work.
- Eight hours away stays bounded; dual-window drift is impossible with one owner.
- Bus schema (#323) stays a thin Snapshot + command set.

### Negative

- `localStorage` is single-machine and webview-scoped; a later Tauri filesystem
  save would be a new decision.
- Schema migration past `schemaVersion: 2` remains map fog until the next breaking change.

## Rejected alternatives

**Derive all live state from wall-clock on demand.** Rejected: discrete Hardness
and two coupled loops make a pure closed form awkward for interactive Upgrades;
fixed ticks match the shell already vendored.

**Replay 250ms ticks for offline.** Rejected: unbounded work for long absences;
closed-form / event-jump is enough while rates are constant between buys.

**Dock (or both windows) owns a save.** Rejected: two writers drift; Nightglass
kept authority on the Pane side for the same reason.
