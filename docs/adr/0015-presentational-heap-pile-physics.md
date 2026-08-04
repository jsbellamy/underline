# ADR 0015: Presentational Heap pile physics

## Status

Accepted (2026-08-04)

## Context

ADR 0014 capped the Heap in Loads and bound Miner throughput against Hauler pickup.
The renderer originally placed Ore on a fixed 32 px slot grid (`heapLoads` → slot index),
which mis-sized rocks at native 6–14 px radii, let slot 18 render at `bottom` 110 inside
a 112 px Pane, and hid a Load at the pickup midpoint without a body-level model.
Issue #455 delivered a deterministic circle-pile solver; issue #456 exposed per-variant
radius and content-centre geometry from the tunnel art pack; issue #457 wired the solver
into `createMinePresenter` and published settled body positions on `TunnelSnapshot.heapOre`;
issue #458 switched the renderer to those bodies and retired the slot grid.

## Decision

- The pile is **presentational only**. Engine `heapLoads` is the single source of truth;
  no save field, no snapshot persistence, no change to ADR 0014's rates. A pile of N
  always settles the same way from `HEAP_PILE_SEED`, so an unchanged Heap looks continuous
  across a reload.
- The solver steps on the **presentation clock**, not wall time, and the presenter clamps
  `stepTo` monotone (`Math.max(pile.nowMs, nowMs)`). This extends ADR 0013 rather than
  contradicting it: rendering stays a function of `presentationNowMs`, and equal times
  remain idempotent.
- **No rotation**, decided rather than deferred: rotating pixel art off the pixel grid
  resamples it, and quarter-turn snapping was considered and declined.
- **Bodies are circles** sized from `content_box` mean half-extent, because with no
  rotation a circle proxy is invisible at 32 px while axis-aligned boxes stack like
  brickwork.
- **Rendered bodies are capped** at `HEAP_RENDER_CEILING` 24 while `heapLoads` keeps
  counting, which also closes the existing defect where grid slot 18 rendered at `bottom`
  110 inside a 112 px Pane.
- The renderer reconciles DOM from `heapOre` keyed by solver body id and paints
  `carriedVariantIndex` for the lifted Load. Settled pile elements use presenter positions
  directly; bag-bound falls for a one-Dwarf Crew keep the Bag arc via `fallingOre`.

## Consequences

### Positive

- `TunnelSnapshot` carries pane-ready `heapOre` positions keyed by stable solver body ids.
- Pickup midpoint lift matches `pileTargetCount` and `carriedVariantIndex` on the snapshot.
- Offline catch-up and construction pre-settle from `HEAP_PILE_SEED` without special cases.
- Mid-pile removal keeps surviving DOM nodes and variants because elements are keyed by id.

### Negative

- `snapEquals` no longer compares `heapLoads`; the renderer reads `heapOre` and
  `carriedVariantIndex` instead.

## Rejected alternatives

**Authoritative persisted bodies.** Rejected: costs a save-schema bump and ties economy
recovery to solver determinism.

**Third-party physics dependency.** Rejected: the repo ships one runtime dependency and the
problem is 24 circles.

**Non-integer downscaling of the Ore art to shrink the pile.** Rejected: breaks #442's
native-scale decision, and physics already nests rocks at true 6–14 px radii instead of
a 36 px lattice.
