# ADR 0016: Heap Spill and the unstalled Miner

## Status

Accepted (2026-08-04)

## Context

ADR 0014 accepted a capped Heap as the Tunnel's second backpressure point and
bound Miner throughput against Hauler pickup by **stalling the Miner when the
Heap is full**. Its worked opening rates (Miner 0.100000 Loads/s vs Hauler
0.092593 Loads/s, net 0.007407 Loads/s into the Heap) explain why the Heap
binds at all; this ADR cites that table rather than restating it.

The idle Miner at a full Heap reads as broken rather than backpressured. The
player still needs a real bind — throughput past a full Heap must remain the
Hauler's rate — but the Face should keep Advancing and the Miner should keep
Swinging while overflow Ore is destroyed instead of entering the economy.

## Decision

- **Amends ADR 0014:** the Heap is still the Tunnel's second backpressure
  point, but it binds by **destroying Ore rather than stopping the Miner**.
  Throughput past a full Heap is still the Hauler's rate; the difference is that
  the Miner keeps animating and the Face keeps Advancing.
- **Advancing through a Spill is economically neutral.** `oreForDrop(a) = 1.15^a`
  rises exactly as fast as the Miner's Loads/s falls
  (`digRate / (10 · 1.15^a)`), so Ore per second is flat across Advance.
  Mining into a full Heap costs no future rate.
- **Spill is self-limiting.** The Hauler's Loads/s is flat in Advance while the
  Miner's falls, so continuing to mine ends the overflow on its own unless the
  player buys Dig Rate. This is the same mechanism as ADR 0014's recorded "Heap
  goes slack at deep Advance" negative, now working in the player's favour.
- **`HEAP_BASE_LOADS` is 20, decoupled from `carryCapacityFor`'s base of 10**,
  so the Heap's buffer and the Bag's size tune independently. The cap is
  `20 + 5n` and still grows by `UPGRADE_CARRY_CAPACITY` per Carry Capacity
  Upgrade, preserving ADR 0014's "Carry Capacity buys Heap buffer" property.
- **Known consequence:** the cap exceeds `HEAP_RENDER_CEILING` 24 from the first
  Carry Capacity Upgrade, so past that point the drawn pile tops out before the
  Heap is economically full. Accepted: the falling-and-vanishing Spill body is
  the tell, not the pile's height.

## Consequences

### Positive

- A full Heap no longer idles the Miner; Spill is visible destruction rather
  than a frozen Face.
- Ore per second stays flat across Advance even while Loads/s falls, so Spill
  does not punish deep Tunnel progress.
- Self-limiting overflow lets the bind clear without a Dig Rate purchase when
  the Hauler eventually overtakes the falling Miner rate.
- Independent Heap base (`20`) and Bag base (`10`) preserve separate tuning
  levers for buffer depth vs trip size.

### Negative

- The drawn pile can top out before the Heap is economically full once Carry
  Capacity is upgraded; height alone no longer signals fullness.
- Destroyed Ore is permanently lost — a full Heap is visibly wasteful rather
  than merely slow.

## Rejected alternatives

**Keeping the stall.** Rejected: the idle Miner is the behaviour being removed.

**Capping `heapLoads` at the render ceiling** so the pile always reads full.
Rejected: couples economy tuning to bin geometry.

**Banking overflow Ore at a reduced rate.** Rejected: the point of the decision
is that Ore is destroyed, and a partial credit makes a full Heap
indistinguishable from a slow one.
