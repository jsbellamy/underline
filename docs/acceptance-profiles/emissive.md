# Emissive Acceptance profile

Resolved in [Finalize the emissive Acceptance profile from existing controls](https://github.com/jsbellamy/underline/issues/23).

Machine-readable index: [`gate-controls/acceptance-profiles.json`](../../gate-controls/acceptance-profiles.json).

## Separated

α-Budgets from [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29)
(`npm run prototype:strip:alpha-budgets`). Hard-fail is the Gate-control metric `C`.

| Gate | Budget | Hard-fail C | Control | Promotion |
|------|--------|-------------|---------|-----------|
| `palette_drift_pass` | 0.2123 | 0.2793 | `emissive--palette_drift_pass--001` (corpus `07` cross-class) | `promo--emissive--palette_drift_pass` (`ACTIVE`) |
| `silhouette_budget` | 0.3226 | 0.4633 | `emissive--silhouette_budget--001` | `promo--emissive--silhouette_budget` (`ACTIVE`) |
| `loop_closure_pass` | 0.1694 | 0.2067 | `emissive--loop_closure_pass--001` | `promo--emissive--loop_closure_pass` (`ACTIVE`) |

`baseline_row_stable` is structural and does not require a provider Gate control.

## Unseparated

### `min_pair_cohort_pass` (budget 0.12)

Five provider attempts (`emissive--min_pair_cohort_pass--001` … `--005`) never produced an
`ISOLATED` control. The best coupled near-miss is `--002`:

| Gate | Raw metric | Ceiling | Budget | Outcome |
|------|------------|---------|--------|---------|
| `min_pair_cohort_pass` (target) | 0.1217 | 0.1217 or 0.1218 | 0.12 | fail |
| `silhouette_budget` (collateral) | 0.2727 | 0.2727 or 0.2728 | 0.21 | fail |

Under [Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38), both the target and collateral still fail after four-place ceiling quantization, so no isolated control exists. Attempt `--005` (min-pair **0.1280**, silhouette **0.3395**) shows the same coupling at higher amplitude.

Rescored Measurement run (schema `gate-control-measurement/1`):

```bash
PYTHONPATH=. python3 prototype/strip-coherence/rescore_measurement.py \
  gate-controls/reports/emissive--min_pair_cohort_pass--002/2026-07-26T17-59-19+00-00.json
```

Recorded as `emissive--min_pair_cohort_pass--006` in `gate-controls/attempts.jsonl`
(`GATE_UNSEPARABLE`). No further provider generation.
