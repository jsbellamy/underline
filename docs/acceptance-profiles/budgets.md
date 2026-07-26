# Budget derivation (α = 0.5)

Resolved in [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29).

Machine-readable table: [`gate-controls/budget-derivation.json`](../../gate-controls/budget-derivation.json).

Reproduce:

```bash
npm run prototype:strip:derive-budgets      # worst-good G per class (C5 baseline)
PYTHONPATH=. python3 prototype/strip-coherence/derive_alpha_budgets.py
```

## Rules

Let `G` be the four-place ceiling of the worst Manifest-good metric for the
Motion-class/Gate pair, and `C` the four-place ceiling of the promoted Gate-control
metric.

| Status | Budget | Automatic pass | Review band | Hard fail |
|--------|--------|----------------|-------------|-----------|
| **Separated** | `ceil₄(G + 0.5 × (C − G))` | `metric ≤ Budget` | `Budget < metric < C` | `metric ≥ C` |
| **Unseparated** | `ceil₀.₀₁(G) + 0.02` (legacy C5) | `metric ≤ Budget` | `metric > Budget` | none |
| **Inapplicable** | omitted | — | — | — |

`α = 0.5` per [Choose alpha for separated Gate controls](https://github.com/jsbellamy/underline/issues/28).
Numeric policy per [Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38).

**Headroom** = `Budget − G` (automatic-pass room above worst-good).
**Δ** = new Budget minus the prior C5 runtime Budget in `pipeline/strip.py` (specification delta; runtime update is a later wave).

## Complete table

| Class | Gate | Status | G | C | Budget | Prior | Δ | Headroom | Review width | Hard fail |
|-------|------|--------|---:|---:|---:|---:|---:|---:|---:|---:|
| `airborne` | `palette_drift_pass` | Separated | 0.2053 | 0.2793 | **0.2423** | 0.23 | +0.0123 | 0.0370 | 0.0370 | 0.2793 |
| `airborne` | `loop_closure_pass` | Separated | 0.6533 | 0.7529 | **0.7032** | 0.68 | +0.0232 | 0.0499 | 0.0497 | 0.7529 |
| `airborne` | `min_pair_cohort_pass` | Separated | 0.2692 | 0.3333 | **0.3013** | 0.29 | +0.0113 | 0.0321 | 0.0320 | 0.3333 |
| `airborne` | `silhouette_budget` | Inapplicable | — | — | — | — | — | — | — | — |
| `blob_idle` | `silhouette_budget` | Separated | 0.3371 | 0.4531 | **0.3951** | 0.36 | +0.0351 | 0.0580 | 0.0580 | 0.4531 |
| `blob_idle` | `palette_drift_pass` | Separated | 0.1961 | 0.2793 | **0.2377** | 0.22 | +0.0177 | 0.0416 | 0.0416 | 0.2793 |
| `blob_idle` | `loop_closure_pass` | Separated | 0.3295 | 0.4516 | **0.3906** | 0.35 | +0.0406 | 0.0611 | 0.0610 | 0.4516 |
| `blob_idle` | `min_pair_cohort_pass` | Separated | 0.1026 | 0.1371 | **0.1199** | 0.13 | −0.0101 | 0.0173 | 0.0172 | 0.1371 |
| `emissive` | `silhouette_budget` | Separated | 0.1818 | 0.4633 | **0.3226** | 0.21 | +0.1126 | 0.1408 | 0.1407 | 0.4633 |
| `emissive` | `palette_drift_pass` | Separated | 0.1454 | 0.2793 | **0.2124** | 0.17 | +0.0424 | 0.0670 | 0.0669 | 0.2793 |
| `emissive` | `loop_closure_pass` | Separated | 0.1321 | 0.2067 | **0.1694** | 0.16 | +0.0094 | 0.0373 | 0.0373 | 0.2067 |
| `emissive` | `min_pair_cohort_pass` | Unseparated | 0.0989 | — | **0.12** | 0.12 | 0 | 0.0211 | open | — |
| `idle` | `silhouette_budget` | Separated | 0.1477 | 0.3000 | **0.2239** | 0.17 | +0.0539 | 0.0762 | 0.0761 | 0.3000 |
| `idle` | `palette_drift_pass` | Separated | 0.1154 | 0.2793 | **0.1974** | 0.14 | +0.0574 | 0.0820 | 0.0819 | 0.2793 |
| `idle` | `loop_closure_pass` | Unseparated | 0.2733 | — | **0.30** | 0.30 | 0 | 0.0267 | open | — |
| `idle` | `min_pair_cohort_pass` | Unseparated | 0.0420 | — | **0.07** | 0.07 | 0 | 0.0280 | open | — |
| `swing` | `silhouette_budget` | Separated | 0.5652 | 0.6067 | **0.5860** | 0.59 | −0.0040 | 0.0208 | 0.0207 | 0.6067 |
| `swing` | `palette_drift_pass` | Separated | 0.1794 | 0.2793 | **0.2294** | 0.20 | +0.0294 | 0.0500 | 0.0499 | 0.2793 |
| `swing` | `loop_closure_pass` | Inapplicable | — | — | — | — | — | — | — | — |
| `swing` | `min_pair_cohort_pass` | Inapplicable | — | — | — | — | — | — | — | — |
| `walk` | `silhouette_budget` | Separated | 0.3977 | 0.4294 | **0.4136** | 0.42 | −0.0064 | 0.0159 | 0.0158 | 0.4294 |
| `walk` | `palette_drift_pass` | Separated | 0.1640 | 0.2793 | **0.2217** | 0.19 | +0.0317 | 0.0577 | 0.0576 | 0.2793 |
| `walk` | `loop_closure_pass` | Separated | 0.1429 | 0.2796 | **0.2113** | 0.17 | +0.0413 | 0.0684 | 0.0683 | 0.2796 |
| `walk` | `min_pair_cohort_pass` | Unseparated | 0.1429 | — | **0.17** | 0.17 | 0 | 0.0271 | open | — |

## Fragile claims

### Thinnest Separated Review bands

These pairs have the least room between automatic pass and autonomous hard fail:

| Rank | Pair | Review interval | Width |
|------|------|-----------------|------:|
| 1 | `walk/silhouette_budget` | (0.4136, 0.4294) | **0.0158** |
| 2 | `blob_idle/min_pair_cohort_pass` | (0.1199, 0.1371) | **0.0172** |
| 3 | `swing/silhouette_budget` | (0.5860, 0.6067) | **0.0207** |
| 4 | `airborne/min_pair_cohort_pass` | (0.3013, 0.3333) | 0.0320 |
| 5 | `airborne/palette_drift_pass` | (0.2423, 0.2793) | 0.0370 |

`walk/silhouette_budget`, `blob_idle/min_pair_cohort_pass`, and `swing/silhouette_budget` are the binding fragile claims for Review-band width. All three remain strictly control-bounded after four-place ceiling quantization.

### Palette drift vs corpus `07`

Every class that applies `palette_drift_pass` shares corpus `07` as the promoted
Gate control (`C = 0.2793`). Under α-derived Budgets the margin from Budget to hard
fail is uniform at **0.0370**; the prior C5 Budgets were tighter against `07` on
classes whose worst-good drift was low (`idle` margin was 0.139, now 0.082).

### Unseparated pairs

Four pairs remain review-only above Budget with no autonomous hard-fail boundary:
`idle/loop_closure_pass`, `idle/min_pair_cohort_pass`, `emissive/min_pair_cohort_pass`,
`walk/min_pair_cohort_pass`. Their Budgets are unchanged from the C5 derivation
(Δ = 0).

### Largest specification deltas

`emissive/silhouette_budget` (+0.1126) and `idle/palette_drift_pass` (+0.0574) widen
most under α. These are expected: the promoted controls sit far above worst-good on
those Gates, and the midpoint rule splits that gap evenly. Runtime `MOTION_CLASSES`
update is deferred to the implementation wave ([#30](https://github.com/jsbellamy/underline/issues/30)).
