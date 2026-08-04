# Produce-and-spend economy (slice numbers)

**Issue:** [Pin down the produce-and-spend economy](https://github.com/jsbellamy/underline/issues/319)  
**Vocabulary:** `CONTEXT.md` § Game language — Hardness, Yield, Pick Damage, Load, Bag, Carry Capacity, Haul, Haul Speed, Cart, Dig Rate, Ore, Smelter, Ingot, Upgrade, Advance.  
**Status:** Provisional numbers for the vertical slice; justified for idle-game feel, not final balance.

Hardness grows exponentially with Advance; Yield scales with Hardness. Ore drops during mining; only Ore delivered by a Haul reaches the Colony.

---

## Sim constants

| Knob | Value |
| --- | --- |
| Face Hardness | `1000 × 1.15^Advance` damage |
| Pick Damage | `1.5^k` damage per Swing (opening `k = 0` → 1); first cost 5 Ingots, doubling |
| Ore drop | every 1% of the Face's Hardness → 100 drops per Face |
| Ore per drop | `1 × 1.15^Advance` (Ore per Face `100 × 1.15^Advance`; a flat 0.1 Ore per damage) |
| Carry Capacity | 10 Loads opening, +5 per Upgrade, first cost 5 Ingots, doubling |
| Full Bag | mining suspends until the Haul delivers |
| Haul round trip | 8000 ms, mining suspended for its whole duration |
| Smelter throughput | `0.06 × 1.5^n` Ore/sec (opening `n = 0` → 0.06) |
| Dig Rate | 1.0 Swing/sec opening, +0.25 per Upgrade (unchanged) |
| Offline | 50% rate, 8h cap; the rate scale applies to the Haul countdown too |
| Loss | Numbers only rise | Spend is permanent; no decay / fail state |

## Hardness and Yield (exponential curve)

Hardness is the Face's total damage capacity from current Advance. After a break, the next Face uses `hardnessFor(newAdvance)`.

| Quantity | Formula |
| --- | --- |
| Face Hardness | `1000 × 1.15^Advance` damage |
| Pick Damage | `1.5^k` damage per Swing (opening 1) |
| Ore per Face | `100 × 1.15^Advance` (100 drops × `1 × 1.15^Advance` per drop) |

## Opening rates (derived)

At Advance 0 (Hardness 1000, Pick Damage 1 at `pickDamageUpgradeCount = 0`):

- First Face: **1000 Swings** ≈ **16.7 min** at opening Dig Rate (1.0 Swing/sec)
- Gross Ore out: **0.1 Ore/sec** (`100 Ore / 1000 s` mining time)
- Haul duty cycle: **100 s** mining / **8 s** hauling = **0.926**, so **0.0926 Ore/sec** delivered
- Smelter drains **0.06 Ore/sec**, so Ore backs up at **0.033 Ore/sec**

## Upgrade ladders (first five)

### Dig Rate Upgrade

| Buy # | Cost (Ingots) | Dig Rate after |
| ---: | ---: | ---: |
| 1 | 5 | 1.25 |
| 2 | 10 | 1.50 |
| 3 | 20 | 1.75 |
| 4 | 40 | 2.00 |
| 5 | 80 | 2.25 |

### Pick Damage Upgrade

| Buy # | Cost (Ingots) | Pick Damage after |
| ---: | ---: | ---: |
| 1 | 5 | 1.5 |
| 2 | 10 | 2.25 |
| 3 | 20 | 3.375 |
| 4 | 40 | 5.0625 |
| 5 | 80 | 7.59375 |

### Smelter Upgrade

| Buy # | Cost (Ingots) | Smelter throughput after (Ore/sec) |
| ---: | ---: | ---: |
| 1 | 5 | 0.09 |
| 2 | 10 | 0.135 |
| 3 | 20 | 0.2025 |
| 4 | 40 | 0.30375 |
| 5 | 80 | 0.455625 |

### Carry Capacity Upgrade

| Buy # | Cost (Ingots) | Carry Capacity after (Loads) |
| ---: | ---: | ---: |
| 1 | 5 | 15 |
| 2 | 10 | 20 |
| 3 | 20 | 25 |
| 4 | 40 | 30 |
| 5 | 80 | 35 |

## Why the ladders are multiplicative

Pick Damage and Smelter throughput both grow ×1.5 per Upgrade while costs
double. That pairing is deliberate: each buy takes roughly 1.33× longer to
afford than the last, so per-Face time still grows without bound even as
Upgrades stack — the accepted shape, not a defect.

Measured consequence for Advance (before this wave → after):

| Horizon | before | after |
| --- | --- | --- |
| Day 1 | Advance 26, 2.8 h/Face | Advance 64, 1.4 h/Face |
| Day 30 | Advance 53, 92 h/Face | Advance 123, 42 h/Face |
| Day 365 | Advance 72, 1086 h/Face | Advance 166, 449 h/Face |

## Offline return

Resolve mining, Haul delivery, and Smelter drain for `min(away, 8h)` at half rate (the rate scale applies to the Haul countdown too). Show a Dock summary: Advance gained, Ore produced, Ore smelted into Ingots, current Ore backlog — then resume.

## Deferred

- Prestige / reset mechanics.
- Haul distance growing with Advance.
- A Haul Speed upgrade ladder.
- Cart / Face art (Art Cohort work, #113).
- High Dig Rate presentation compression / presentation clock (map fog; see Nightglass ADR-0003 analogue).
- Ore per second is `0.1 × damage per second` regardless of Advance, because
  `oreForDrop` and `dropDamageFor` both scale `1.15^Advance` and cancel. Advance
  is therefore economically neutral. Left as-is deliberately.
