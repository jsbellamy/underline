# α-Budget tables (AFK acceptance)

Resolved in [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29).

Reproduce:

```bash
npm run prototype:strip:alpha-budgets
```

## Rule

From [Choose alpha for separated Gate controls](https://github.com/jsbellamy/underline/issues/28) and
[Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38):

- `G` = four-place upward-quantized worst Manifest-good metric
- `C` = four-place upward-quantized isolated Gate-control metric
- `α = 0.5`
- **Separated** `Budget = ceil₄(G + 0.5 × (C − G))`
  - `metric <= Budget` → automatic pass
  - `Budget < metric < C` → agent Review
  - `metric >= C` → autonomous hard fail
- **Unseparated** keeps the runtime `ceil₀.₀₁(worst-good)+0.02` Budget; Review is open above it; no hard-fail boundary
- **Inapplicable** Gates are omitted

Runtime `MOTION_CLASSES` project these α-Budgets from
`gate-controls/acceptance-profiles.json` (landed in
[#62](https://github.com/jsbellamy/underline/issues/62), verified by
`npm run prototype:strip:alpha-budgets`). The historical pre-α
`ceil₀.₀₁(worst-good)+0.02` estimator remains available only via
`npm run prototype:strip:derive-budgets`.

Four-place ceiling uses Decimal quantization (`pipeline/numeric_policy.py`)
so exact four-place values such as walk loop control `0.2795` are not pushed to `0.2796`
by IEEE float.

All **17** Separated Promotions in `gate-controls/manifest.json` are **`ACTIVE`**;
none remain pending verification. Budget derivation and hard-fail boundaries use
only active Promotions.

## Separated pairs

| Pair | G | C (hard-fail) | Budget | Old runtime | Δ | Good headroom | Review width | Binding good | Control |
|------|---:|---:|---:|---:|---:|---:|---:|---|---|
| `idle/silhouette_budget` | 0.1477 | 0.3000 | **0.2239** | 0.17 | +0.0539 | 0.0762 | 0.0761 | miner-idle-strip | `idle--silhouette_budget--001` |
| `idle/palette_drift_pass` | 0.1154 | 0.2793 | **0.1974** | 0.14 | +0.0574 | 0.0820 | 0.0819 | 11-dwarf-idle | `idle--palette_drift_pass--001` |
| `blob_idle/silhouette_budget` | 0.3371 | 0.4531 | **0.3951** | 0.36 | +0.0351 | 0.0580 | 0.0580 | 02-slime-idle | `blob_idle--silhouette_budget--004` |
| `blob_idle/loop_closure_pass` | 0.3295 | 0.4516 | **0.3906** | 0.35 | +0.0406 | 0.0611 | 0.0610 | 02-slime-idle | `blob_idle--loop_closure_pass--004` |
| `blob_idle/palette_drift_pass` | 0.1961 | 0.2793 | **0.2377** | 0.22 | +0.0177 | 0.0416 | 0.0416 | 13-ooze-idle | `blob_idle--palette_drift_pass--001` |
| `blob_idle/min_pair_cohort_pass` | 0.1026 | 0.1371 | **0.1199** | 0.13 | −0.0101 | 0.0173 | 0.0172 | 13-ooze-idle | `blob_idle--min_pair_cohort_pass--005` |
| `emissive/silhouette_budget` | 0.1818 | 0.4633 | **0.3226** | 0.21 | +0.1126 | 0.1408 | 0.1407 | 15-campfire-flicker | `emissive--silhouette_budget--001` |
| `emissive/loop_closure_pass` | 0.1321 | 0.2067 | **0.1694** | 0.16 | +0.0094 | 0.0373 | 0.0373 | 15-campfire-flicker | `emissive--loop_closure_pass--001` |
| `emissive/palette_drift_pass` | 0.1453 | 0.2793 | **0.2123** | 0.17 | +0.0423 | 0.0670 | 0.0670 | 03-torch-flicker | `emissive--palette_drift_pass--001` |
| `walk/silhouette_budget` | 0.3977 | 0.4294 | **0.4136** | 0.42 | −0.0064 | 0.0159 | 0.0158 | 05-miner-walk | `walk--silhouette_budget--002` |
| `walk/loop_closure_pass` | 0.1429 | 0.2795 | **0.2112** | 0.17 | +0.0412 | 0.0683 | 0.0683 | 05-miner-walk | `walk--loop_closure_pass--002` |
| `walk/palette_drift_pass` | 0.1640 | 0.2793 | **0.2217** | 0.19 | +0.0317 | 0.0577 | 0.0576 | 18-guard-walk | `walk--palette_drift_pass--001` |
| `airborne/loop_closure_pass` | 0.6533 | 0.7529 | **0.7032** | 0.68 | +0.0232 | 0.0499 | 0.0497 | 04-bat-flap | `airborne--loop_closure_pass--002` † |
| `airborne/min_pair_cohort_pass` | 0.2692 | 0.3333 | **0.3013** | 0.29 | +0.0113 | 0.0321 | 0.0320 | 17-wisp-float | `airborne--min_pair_cohort_pass--004` † |
| `airborne/palette_drift_pass` | 0.2053 | 0.2793 | **0.2423** | 0.23 | +0.0123 | 0.0370 | 0.0370 | 16-moth-flap | `airborne--palette_drift_pass--001` |
| `swing/silhouette_budget` | 0.5652 | 0.6067 | **0.5860** | 0.59 | −0.0040 | 0.0208 | 0.0207 | 06-miner-swing | `swing--silhouette_budget--002` |
| `swing/palette_drift_pass` | 0.1794 | 0.2793 | **0.2294** | 0.20 | +0.0294 | 0.0500 | 0.0499 | 06-miner-swing | `swing--palette_drift_pass--001` |

† Control carries a `displacement_pass` undecidable caveat. A caveat on a
non-target Gate does not make the control inadmissible for deriving the target
Gate's Budget; the caveat is recorded on the row and does not block α allocation.

## Unseparated pairs

| Pair | G | Budget | Old runtime | Δ | Good headroom | Hard-fail | Review |
|------|---:|---:|---:|---:|---:|---|---|
| `idle/loop_closure_pass` | 0.2733 | **0.30** | 0.30 | 0 | 0.0267 | none | open above Budget |
| `idle/min_pair_cohort_pass` | 0.0420 | **0.07** | 0.07 | 0 | 0.0280 | none | open above Budget |
| `walk/min_pair_cohort_pass` | 0.1429 | **0.17** | 0.17 | 0 | 0.0271 | none | open above Budget |
| `emissive/min_pair_cohort_pass` | 0.0989 | **0.12** | 0.12 | 0 | 0.0211 | none | open above Budget |
| `swing/static_silhouette_pass` | 0.6886 | **0.88** | 0.86 | +0.02 | 0.1914 | none | open above Budget |

`static_silhouette_pass` is tuned against the single production reference bundle
(`assets/first-room/dwarf/swing/polished`), not the corpus battery
`prototype:strip:alpha-budgets` reproduces — its `G` is that bundle's worst adjacent
pair, not a Manifest-good cohort maximum. Re-derived for union normalization
(issue #208; see `docs/strip-acquisition-contract.md` § Static silhouette gate for
the corpus separation table).

## Inapplicable pairs

| Pair | Reason |
|------|--------|
| `airborne/silhouette_budget` | class property `max_silhouette=None` (not grounded) |
| `swing/loop_closure_pass` | one-shot swing; `loops=false` |
| `swing/min_pair_cohort_pass` | one-shot swing; `max_min_pair=None` |
| `idle/static_silhouette_pass` | no budget derived for the class |
| `blob_idle/static_silhouette_pass` | no budget derived for the class |
| `walk/static_silhouette_pass` | no budget derived for the class |
| `airborne/static_silhouette_pass` | no budget derived for the class |
| `emissive/static_silhouette_pass` | no budget derived for the class |

Structural `baseline_row_stable` remains Separated without a provider Gate control
and is outside the α table. Airborne `displacement_pass` is **Unseparated** (binary /
often undecidable): no promoted Gate control and no α-Budget row; see
[`docs/afk-acceptance-implementation-spec.md`](afk-acceptance-implementation-spec.md)
§6.

## Fragile claims (rebuilt)

Thinnest Separated good-headroom / Review-width margins under α = 0.5:

| Pair | Budget | Control C | Good headroom | Review width |
|------|---:|---:|---:|---:|
| `walk/silhouette_budget` | 0.4136 | 0.4294 | **0.0159** | **0.0158** |
| `blob_idle/min_pair_cohort_pass` | 0.1199 | 0.1371 | **0.0173** | **0.0172** |
| `swing/silhouette_budget` | 0.5860 | 0.6067 | **0.0208** | **0.0207** |

These replace the prior corpus-negative fragile-claim table (swing vs 23, airborne vs
22/07) for AFK acceptance. Corpus negatives remain separation references for the
historical pre-α estimator (`npm run prototype:strip:derive-budgets`).
