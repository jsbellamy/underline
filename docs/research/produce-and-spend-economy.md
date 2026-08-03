# Produce-and-spend economy (slice numbers)

**Issue:** [Pin down the produce-and-spend economy](https://github.com/jsbellamy/underline/issues/319)  
**Vocabulary:** `CONTEXT.md` § Game language — Hardness, Yield, Dig Rate, Ore, Smelter, Ingot, Upgrade, Advance.  
**Status:** Provisional numbers for the vertical slice; justified for idle-game feel, not final balance.

Hardness and Yield stay **constant with Advance** (already locked by [Name the mining-colony domain](https://github.com/jsbellamy/underline/issues/314)).

---

## Sim constants

| Knob | Value | Notes |
| --- | --- | --- |
| Swing | 1 swing animation cycle = 1 Swing | Dig Rate drives Hardness spend and playback speed |
| Hardness | 4 Swings / Mineable Block | Constant |
| Yield | 1 Ore / broken block | Constant; 1 Ore → 1 Ingot at the Smelter |
| Opening Dig Rate | 1.0 Swing/sec | → 1 block / 4s → 0.25 Ore/sec before Smelter |
| Smelter throughput | 0.15 Ore/sec | Fixed for the slice; below Dig Rate so Ore backs up |
| Upgrade effect | +0.25 Dig Rate per buy | Additive, fixed; curve lives in price |
| First Upgrade cost | 5 Ingots | ~30–40s from cold start at opening rates |
| Cost curve | Doubles each buy | 5 → 10 → 20 → 40 → … |
| Offline rate | 50% of live rate | Both loops (blocks broken and Ore smelted) |
| Offline cap | 8 hours | |
| Loss | Numbers only rise | Spend is permanent; no decay / fail state |

## Opening rates (derived)

- Ore out: `Dig Rate / Hardness × Yield` = `1.0 / 4 × 1` = **0.25 Ore/sec**
- Ingot out (Smelter-bound while Ore is available): **0.15 Ingots/sec**
- Ore backlog growth at open: **0.10 Ore/sec**

## Upgrade ladder (first five)

| Buy # | Cost (Ingots) | Dig Rate after |
| ---: | ---: | ---: |
| 1 | 5 | 1.25 |
| 2 | 10 | 1.50 |
| 3 | 20 | 1.75 |
| 4 | 40 | 2.00 |
| 5 | 80 | 2.25 |

## Offline return

Resolve both loops for `min(away, 8h)` at half rate. Show a Dock summary: Advance gained, Ore produced, Ore smelted into Ingots, current Ore backlog — then resume.

## Deferred

- Walk duration between Face advances (affects real Ore/sec slightly; belongs with tick / presentation work).
- High Dig Rate presentation compression / presentation clock (map fog; see Nightglass ADR-0003 analogue).
