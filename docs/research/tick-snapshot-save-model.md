# Tick, Snapshot, and save model (engine contract)

**Issue:** [Decide the tick, snapshot, and save model](https://github.com/jsbellamy/underline/issues/320)  
**Vocabulary:** `CONTEXT.md` § Game language — Advance, Dig Rate, Ore, Smelter, Ingot, Upgrade, Face, Hardness, Yield.  
**Numbers:** [`docs/research/produce-and-spend-economy.md`](./produce-and-spend-economy.md)  
**Architecture:** [ADR 0010](../adr/0010-mining-engine-tick-and-save.md)

This is the engine contract [Close the loop: spend Ore in the dock and accrue it offline](https://github.com/jsbellamy/underline/issues/322) implements against, and the authority half of [Define the Pane↔Dock bus message schema](https://github.com/jsbellamy/underline/issues/323).

---

## Live tick

- Fixed-step simulation at **250ms**, matching the vendored shell pump.
- One pure function: `advance(snapshot, dtMs, …commands) → snapshot` (plus optional event list for presentation).
- Render is a separate rAF pass. Presentation (animation frame, camera, Face crack) reads Snapshot and wall clock for playback; it never writes economy fields.

## Offline / catch-up

- Same `advance`, not a wall-clock replay of 250ms ticks.
- Catch-up is **event-jump** per [ADR 0012](../adr/0012-event-jump-advance-and-haul-duty-cycle.md): segment at the next Ore drop, Face break, Bag-full, Haul-delivery, or Haul-completion boundary, then Smelter drain once per window — not tick replay.
- Boot path: `offlineMs = computeOfflineMs(savedAtMs, nowMs)` (already capped at 8h in `src/ui/offline-clock.ts`). Feed `advance` with that duration at the economy’s **50%** rate (`rateScale` applies to Haul countdown too).
- Always apply catch-up on load. Show the Dock offline summary only when `offlineMs ≥ MIN_OFFLINE_MS` (60s).

## Determinism and `/tdd` seam

- Engine is pure TypeScript: no `Date.now()`, no RNG, no DOM.
- Given Snapshot + `dtMs` + Upgrade commands, output is fully determined.
- Snapshot fixtures + `advance` prove the dig → smelt → spend loop before any canvas work.

## Authoritative save fields

Persist only what cannot be derived. Key: `underline-save-v1` in **`localStorage`** (JSON).

| Field | Role |
| --- | --- |
| `schemaVersion` | Ship `2` |
| `savedAtMs` | Wall clock at persist/boot boundary only |
| `advance` | Mineable Blocks broken |
| `ore` | Smelter backlog (fractional OK) |
| `ingots` | Spendable |
| `digRateUpgradeCount` | Derives Dig Rate (`1.0 + 0.25×n`) and Dig Rate next cost (`5 × 2^n`) |
| `smelterUpgradeCount` | Derives Smelter throughput (`0.06 + 0.02×n` Ore/sec) and Smelter next cost (`5 × 2^n`) |
| `faceSwingProgress` | Swings already spent on the current Face (`0…Hardness`; same as damage dealt while Pick Damage is 1) |
| `smelterProgress` | Fractional Ore fed toward the next Ingot (`0…1`) |

**Derived at load / in Snapshot views:** Dig Rate, both next Upgrade costs, Hardness from exponential `hardnessFor(advance)`, Yield scaling with Hardness, Smelter throughput from `smelterUpgradeCount`.

**Migration:** Load of `schemaVersion: 1` maps `upgradeCount` → `digRateUpgradeCount`, sets `smelterUpgradeCount: 0`, rewrites as v2 on next persist. Persist key remains `underline-save-v1`.

**Do not persist:** Tunnel geometry, camera, animation frame, per-block history.

### Write cadence

- Every successful Upgrade purchase (Dig Rate or Smelter)
- `pagehide` / before-unload
- Autosave every **10s** (`AUTOSAVE_MS`)

Wall clock is stamped only at the persistence boundary (`savedAtMs = Date.now()`). The engine never reads it.

## Clock jumps and sleep

- Elapsed = `max(0, now − savedAt)`, then clamp to `OFFLINE_CAP_MS` (8h).
- Backwards clock → 0 elapsed; no rewind of Ore / Ingots / Advance.
- Live unhide catch-up (pump chunking) shares the same cap — never grant more than 8h of simulated time from one wake.
- No separate NTP / lid-close detector for the slice.

## Window authority

- The **Pane owns the engine and the save**: pump, `advance`, Upgrade apply, persist, Snapshot broadcast.
- The **Dock is a pure client**: renders Colony from the last Snapshot; sends commands (`buyUpgrade`, …) only.
- Dock alone never loads a second engine from `localStorage`; it waits for / requests a Snapshot from the Pane.

## Deferred

- Save-schema migration past `schemaVersion: 2` (map fog).
- Presentation clock between 250ms ticks for Swing / walk smoothness (map fog).
- Exact bus message shapes — locked in [`pane-dock-bus-schema.md`](./pane-dock-bus-schema.md) ([Define the Pane↔Dock bus message schema](https://github.com/jsbellamy/underline/issues/323)).
- Walk duration as a real Ore/sec delay (presentation / #321); economy `advance` does not model walk time for the slice.
