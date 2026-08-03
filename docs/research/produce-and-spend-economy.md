# Produce-and-spend economy (slice numbers)

**Issue:** [Pin down the produce-and-spend economy](https://github.com/jsbellamy/underline/issues/319)  
**Vocabulary:** `CONTEXT.md` § Game language — Hardness, Yield, Dig Rate, Ore, Smelter, Ingot, Upgrade, Advance.  
**Status:** Provisional numbers for the vertical slice; justified for idle-game feel, not final balance.

Yield stays **constant**; Hardness is derived from Advance via fixed bands (see below).

---

## Sim constants

| Knob | Value | Notes |
| --- | --- | --- |
| Swing | 1 swing animation cycle = 1 Swing | Dig Rate drives Hardness spend and playback speed |
| Yield | 1 Ore / broken block | Constant; 1 Ore → 1 Ingot at the Smelter |
| Opening Dig Rate | 1.0 Swing/sec | → 1 block / 4s → 0.25 Ore/sec before Smelter at opening Hardness |
| Dig Rate Upgrade effect | +0.25 Dig Rate / buy | Additive, fixed; curve lives in price |
| Dig Rate first cost | 5 Ingots | Doubles per Dig Rate buy |
| Opening Smelter throughput | 0.15 Ore/sec | Below opening Dig Rate so Ore backs up |
| Smelter Upgrade effect | +0.05 Ore/sec / buy | Additive, fixed; independent cost ladder |
| Smelter first cost | 5 Ingots | Doubles per Smelter buy (independent ladder) |
| Offline rate | 50% of live rate | Both loops (blocks broken and Ore smelted) |
| Offline cap | 8 hours | |
| Loss | Numbers only rise | Spend is permanent; no decay / fail state |

## Hardness (Advance bands)

Hardness is a property of the current Face from current Advance. After a break, the next Face uses `hardnessFor(newAdvance)`.

| Advance (blocks broken) | Hardness |
| ---: | ---: |
| 0–24 | 4 |
| 25–74 | 5 |
| 75–149 | 6 |
| 150+ | 7 |

Yield stays 1.

## Opening rates (derived)

At Advance 0 (Hardness 4):

- Ore out: `Dig Rate / Hardness × Yield` = `1.0 / 4 × 1` = **0.25 Ore/sec**
- Ingot out (Smelter-bound while Ore is available): **0.15 Ingots/sec**
- Ore backlog growth at open: **0.10 Ore/sec**

## Upgrade ladders (first five)

### Dig Rate Upgrade

| Buy # | Cost (Ingots) | Dig Rate after |
| ---: | ---: | ---: |
| 1 | 5 | 1.25 |
| 2 | 10 | 1.50 |
| 3 | 20 | 1.75 |
| 4 | 40 | 2.00 |
| 5 | 80 | 2.25 |

### Smelter Upgrade

| Buy # | Cost (Ingots) | Smelter throughput after (Ore/sec) |
| ---: | ---: | ---: |
| 1 | 5 | 0.20 |
| 2 | 10 | 0.25 |
| 3 | 20 | 0.30 |
| 4 | 40 | 0.35 |
| 5 | 80 | 0.40 |

## Offline return

Resolve both loops for `min(away, 8h)` at half rate. Show a Dock summary: Advance gained, Ore produced, Ore smelted into Ingots, current Ore backlog — then resume.

## Deferred

- Walk duration between Face advances (affects real Ore/sec slightly; belongs with tick / presentation work).
- High Dig Rate presentation compression / presentation clock (map fog; see Nightglass ADR-0003 analogue).
