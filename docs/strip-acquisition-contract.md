# Strip acquisition contract

Authority for Underline strip coherence gates. The prototype in
`prototype/strip-coherence/` implements this contract; Nightglass's frozen
animation contract does not govern here.

## Motion classes

| Class | Corpus sample | `grounded` | `loops` |
|-------|---------------|------------|---------|
| `idle` | 01-miner-idle | yes | yes |
| `blob_idle` | 02-slime-idle | yes | yes |
| `emissive` | 03-torch-flicker | yes | yes |
| `airborne` | 04-bat-flap | no | yes |
| `walk` | 05-miner-walk | yes | yes |
| `swing` | 06-miner-swing | yes | no |

Negative controls 07, 08, and 09 declare `idle`.

## Budget derivation (C5)

For each class and each applicable gate:

`budget = ceil_to_0.01(worst measured value across that class's good strips) + 0.02`

For min-pair cohort, worst-good is the **maximum** min_pair across passing strips
(highest agreement threshold the class tolerates). Only derived for `loops=true`.

Measurements taken after pitch slicing (#2) and per-class anchor handling (#3), on
inbox corpus PNGs that **pass** under the prior contract. Re-derived 2026-07-26
after expanding the corpus to n≥2 passing strips per class (samples 10–21). The
`idle` cohort also includes `miner-idle-strip.png` (the adversarial baseline).

Run `npm run prototype:strip:derive-budgets` to reproduce worst-good figures from
the current inbox.

### Cohort size (passing strips)

| Class | n | Passing samples |
|-------|---|-----------------|
| `idle` | 4 | 01, 10, 11, miner-idle-strip |
| `blob_idle` | 2 | 02, 12 |
| `emissive` | 2 | 03, 14 |
| `airborne` | 2 | 04, 17 |
| `walk` | 2 | 05, 19 |
| `swing` | 3 | 06, 20, 21 |

Near-miss strips (13, 15, 16, 18) ingest but fail one gate — excluded from
worst-good; regenerate when tightening budgets further.

## Separation check (C6)

Every derived budget must be **strictly less than** the measured value of every
negative control on the same gate:

| Gate | 07-NEG-palette-drift | 08-NEG-identity-drift |
|------|----------------------|------------------------|
| silhouette (adjacent max-pair) | 0.057 | **0.602** |
| min-pair cohort | 0.010 | **0.344** |
| loop | 0.043 | 0.482 |
| palette drift | **0.279** | 0.218 |

## Class budgets

**Re-derivation result:** numeric budgets are **unchanged** from the n=1 pass.
Multi-sample evidence confirms the prior constants; `idle` worst-good is still
bound by `miner-idle-strip` (loop 0.273), not the new corpus idles.

### `idle`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette (adjacent) | 0.148 | miner-idle-strip | **0.17** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.042 | 01-miner-idle | **0.06** | 0.010 | 0.344 | separated |
| loop | 0.273 | miner-idle-strip | **0.30** | 0.043 | 0.482 | separated |
| palette drift | 0.115 | 11-dwarf-idle | **0.14** | 0.279 | 0.218 | separated |

Corpus: 01 sil 0.095 / loop 0.147; 10 sil 0.024 / loop 0.015; 11 sil 0.108 /
loop 0.000.

### `blob_idle`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.337 | 02-slime-idle | **0.36** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.025 | 12-jelly-idle | **0.05** | 0.010 | 0.344 | separated |
| loop | 0.330 | 02-slime-idle | **0.36** | 0.043 | 0.482 | separated |
| palette drift | 0.141 | 02-slime-idle | **0.17** | 0.279 | 0.218 | separated |

12-jelly-idle is well inside budget (sil 0.264 / loop 0.202).

### `emissive`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.160 | 03-torch-flicker | **0.18** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.099 | 03-torch-flicker | **0.12** | 0.010 | 0.344 | separated |
| loop | 0.130 | 03-torch-flicker | **0.16** | 0.043 | 0.482 | separated |
| palette drift | 0.145 | 03-torch-flicker | **0.17** | 0.279 | 0.218 | separated |

14-lantern-flicker is inside budget on all gates.

### `walk`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.398 | 05-miner-walk | **0.42** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.143 | 05-miner-walk | **0.17** | 0.010 | 0.344 | separated |
| loop | 0.143 | 05-miner-walk | **0.17** | 0.043 | 0.482 | separated |
| palette drift | 0.117 | 05-miner-walk | **0.14** | 0.279 | 0.218 | separated |

19-scout-walk is much looser (sil 0.099 / loop 0.084) — 05 remains binding.

### `swing`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.565 | 06-miner-swing | **0.59** | 0.057 | 0.602 | separated (0.012 margin) |
| min-pair cohort | — | — | **None** | — | — | not applicable (`loops=false`) |
| loop | — | — | **None** | — | — | not applicable (`loops=false`) |
| palette drift | 0.179 | 06-miner-swing | **0.20** | 0.279 | 0.218 | separated |

n=3 confirms 06 remains worst-good; 20 and 21 are inside budget. The 0.012
margin to 08 on silhouette is **not** a one-sample artifact.

### `airborne` — cohort identity via min-pair

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette (adjacent) | 0.644 | 04-bat-flap | **None** | 0.057 | 0.602 | excluded — UNSEPARATED |
| min-pair cohort | 0.269 | 17-wisp-float | **0.29** | 0.010 | 0.344 | separated |
| loop | 0.653 | 04-bat-flap | **0.68** | 0.043 | 0.482 | separated |
| palette drift | 0.145 | 04-bat-flap | **0.17** | 0.279 | 0.218 | separated |

Adjacent silhouette remains excluded (`max_silhouette` is `None`) — a legitimate
flap transition is large and max-pair cannot separate good airborne from identity
drift. **`min_pair_cohort_pass`** gates on `silhouette_pairwise.min_pair` instead:
looping cohorts must revisit a pose; four different characters do not.

`loops=false` classes (swing) omit the min-pair gate — one-shot actions legitimately
never repeat a pose (06 min_pair 0.437 > 08's 0.344).

## Min-pair cohort gate

`coherence_split` reports `silhouette_pairwise` and gates `min_pair_cohort_pass`
when `loops=true` and `max_min_pair` is set. Pass when `min_pair <= max_min_pair`.

| Role | Gate | Catches | Blind to |
|------|------|---------|----------|
| Step motion | `silhouette_budget` (adjacent max-pair) | hop, slide, oversized transitions | identity drift on airborne |
| Cohort identity | `min_pair_cohort_pass` | four-character drift (08) | single-frame tamper |
| Recolour | `palette_drift_pass` | palette swap | — |

Single-frame mirror/hop/slide leaves min-pair unchanged — adjacent silhouette (or
baseline) must still catch those on grounded classes. Airborne has no adjacent
silhouette gate; hop/mirror/slide remain ungated there today.

| Sample | class | min_pair | `min_pair_cohort_pass` |
|--------|-------|----------|------------------------|
| 04-bat-flap | airborne | 0.044 | pass (≤0.29) |
| 17-wisp-float | airborne | 0.269 | pass |
| 08-NEG-identity-drift | airborne | 0.344 | **fail** |
| 08-NEG-identity-drift | idle | 0.344 | fail (redundant with silhouette) |

## Implementation

`MOTION_CLASSES` in `prototype/strip-coherence/strip.py` is the runtime source.
`coherence_split(frames, motion_class=...)` reads budgets from it. Unknown classes
raise `ValueError`. `None` budgets exclude their gate from pass and report `None`.

Per-sample `grounded` was removed from `prompts/manifest.json`; groundedness is
derived from the motion class.
