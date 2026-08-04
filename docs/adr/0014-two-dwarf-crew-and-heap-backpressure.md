# ADR 0014: Two-dwarf crew and Heap backpressure

## Status

Accepted (2026-08-03)

## Context

ADR 0012 fixed event-jump advance and a single Dwarf's Bag / Haul duty cycle.
The two-dwarf crew wave splits digging from hauling: a **Miner** holds the Face
and drops Ore into a capped **Heap**; a **Hauler** picks Loads from the Heap
into its Bag and departs only when full. Throughput must bind at the Heap under
opening upgrades so the second backpressure point (after the Smelter) is real,
without rewriting Load semantics or desyncing Pane travel speed from economy
state.

## Decision

- **Miner → Heap → Hauler → Cart** are two independently-rated stages joined by
  the capped Heap (Carry Capacity in Loads).
- **Pickup cost, not travel time, is the Hauler's rate limit:**
  `pickupMsPerLoad(n) = 10_000 / (1 + 0.25n)`.
- **`haulSpeedFor(n) = 1 + 0.25n`**, deliberately mirroring `digRateFor`.
- **The Hauler departs only when its Bag is full**, so travel time enters
  throughput as a per-cycle overhead the Miner is not paying.
- **Worked opening rates** (the reason the Heap binds at all):

  | Quantity | Formula | Opening value |
  | --- | --- | --- |
  | Miner | `digRate / (10 · 1.15^advance)` | 0.100000 Loads/s |
  | Hauler | `capacity / (capacity · pickupSec + 8)` | 0.092593 Loads/s |
  | Net into Heap | difference | 0.007407 Loads/s |
  | Time to first stall | `capacity / net` | 1350 s |

- After one Dig Rate Upgrade the Miner is 0.125000 Loads/s, net 0.032407, first
  stall at 308.6 s.
- One Haul Speed Upgrade lifts the Hauler to 0.113636 Loads/s; two lift it to
  0.133929, which is the first point it overtakes a once-upgraded Miner. Haul
  Speed is deliberately weaker per step than Dig Rate.
- **Carry Capacity** has diminishing throughput returns by construction:
  `capacity / (capacity · pickupSec + 8)` tends to `1 / pickupSec` as capacity
  grows, so it buys Heap buffer and trip amortisation rather than raw rate.

## Consequences

### Positive

- Miner and Hauler rates tune independently; Heap depth is a visible buffer
  between Face production and Cart delivery.
- Pickup-limited hauling preserves `HAUL_ROUND_TRIP_MS` and Pane lane speed while
  still letting the Miner outpace the Hauler at opening.
- Full-Bag departure keeps per-cycle travel overhead on the Hauler only.

### Negative

- `dropDamage` scales with Hardness while pickup does not, so a player who stops
  buying Dig Rate sees the Heap go slack at deep Advance. Recorded as a known
  gap, not compensated.

## Rejected alternatives

**Flat Load cadence with constant Ore per Load.** Rejected: preserves Yield but
rewrites `DROPS_PER_FACE` and `oreForDrop` semantics and falsifies
`CONTEXT.md`'s "a Load is worth more on a tougher Face".

**Lengthening `HAUL_ROUND_TRIP_MS` to ~100s.** Rejected: `HAUL_SPEED_PX_PER_MS`
in `src/ui/pane-layout.ts` derives from it, so the Hauler would cross the 202px
lane at ~2 px/s.

**Hauler departs on a partial Bag.** Rejected: removes the per-cycle travel
overhead that makes the Miner outpace the Hauler, and the Heap stops filling.
