# ADR 0017: Trip-based hauling

## Status

Accepted (2026-08-04)

## Context

ADR 0014 modelled the Hauler as lifting Loads into a Bag until full, then
making one 8s round trip. Ore moved only once per full Bag, delivery fired at
the round-trip midpoint, and there was no unload step for the Pane or for Haul
Speed Upgrades to attack.

The two-dwarf crew wave needs a finer cadence: the **Trip** is the unit of
hauling work. Each Trip lifts one Load, travels to the Cart, unloads (crediting
Ore on arrival), and returns.

## Decision

- **Supersedes ADR 0014 in part:** the Hauler departs after
  `HAULER_GRAB_SIZE` (1) Load reaches its Bag, not when the Bag is full. The
  one-Dwarf Crew is unchanged — it still departs on a full Bag at
  `carryCapacityFor(...)`.
- **Trip cycle:** Lift (`PICKUP_MS_PER_LOAD = 3_000` at opening) + Travel +
  Unload. `HAUL_TRAVEL_MS = 4_000` (both legs combined), `UNLOAD_MS = 4_000`
  (fixed dwell at the Cart), `HAUL_ROUND_TRIP_MS = HAUL_TRAVEL_MS + UNLOAD_MS`.
  Ore is credited when travel-out ends: `HAUL_DELIVERY_MS = UNLOAD_MS +
  HAUL_TRAVEL_MS / 2` (6_000 ms into the countdown).
- **Worked opening rates** (Heap backpressure survives):

  | Quantity | Formula | Opening |
  | --- | --- | --- |
  | Miner | `digRate / (10 · 1.15^advance)` | 0.100000 L/s |
  | Hauler | `1 / (pickupSec + travelSec + unloadSec)` | 0.090909 L/s |
  | Net into Heap | difference | 0.009091 L/s |
  | Time to fill a 20-Load Heap | `20 / net` | 2200 s |

- One Haul Speed Upgrade lifts the Hauler to 0.096154 L/s; two reach 0.100000
  L/s, exactly the opening Miner.
- **Interim presentation:** the Pane still interpolates both Dwarves' Haul as a
  50/50 out-and-back arc, so Cart arrival no longer coincides with delivery.
  Issue #5 replaces that arc with the constant-speed lane and the unload dwell.

## Consequences

### Positive

- Ore credits at Cart arrival, giving the Pane and upgrades a named unload phase.
- Trip cadence exposes Lift, Travel, and Unload as separate simulation beats.
- Slower per-Trip pickup (3s vs 10s) with one-Load departure raises net Heap
  accumulation while keeping `HAUL_ROUND_TRIP_MS` at 8s.

### Negative

- Discrete simulation peaks the Heap near half capacity before the first Face
  break; the 2200 s row is the constant-rate equilibrium time, not a literal
  `heapLoads === 20` snapshot at that horizon once Advance rises.
- Cart arrival and Ore credit diverge until #5 lands the lane presentation.

## Rejected alternatives

**Keep full-Bag departure with faster pickup.** Rejected: preserves ADR 0014's
batch semantics and leaves no unload beat for the Pane.

**Credit Ore at the round-trip midpoint.** Rejected: contradicts Cart-arrival
semantics and keeps delivery invisible to unload presentation.
