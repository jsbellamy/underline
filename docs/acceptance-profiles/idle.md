# Idle Acceptance profile

Resolved in [Finalize the idle Acceptance profile from existing controls](https://github.com/jsbellamy/underline/issues/21).

Machine-readable index: [`gate-controls/acceptance-profiles.json`](../../gate-controls/acceptance-profiles.json).

## Separated

α-Budgets from [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29)
(`npm run prototype:strip:alpha-budgets`). Hard-fail is the Gate-control metric `C`.

| Gate | Budget | Hard-fail C | Control | Promotion |
|------|--------|-------------|---------|-----------|
| `silhouette_budget` | 0.2239 | 0.3000 | `idle--silhouette_budget--001` | `promo--idle--silhouette_budget` (`ACTIVE`) |
| `palette_drift_pass` | 0.1974 | 0.2793 | `idle--palette_drift_pass--001` (corpus `07` cross-class) | `promo--idle--palette_drift_pass` (`ACTIVE`) |

`baseline_row_stable` is structural and does not require a provider Gate control.

## Unseparated

### `loop_closure_pass` (budget 0.30)

Nine provider attempts (`idle--loop_closure_pass--001` … `--009`) never produced an
`ISOLATED` control. The acquisition frontier couples loop failure to adjacent
silhouette at the shared **0.17** adjacent budget:

| Attempt | Loop | Silhouette (adj max) | Outcome |
|---------|------|----------------------|---------|
| `--001` | **0.3095** (fail) | **0.2025** (fail) | target fails, collateral fails |
| `--006` | 0.1707 (pass) | **0.1707** (fail) | fixing collateral drops loop below budget |

Recorded as `idle--loop_closure_pass--010` in `gate-controls/attempts.jsonl`
(`GATE_UNSEPARABLE`). No further provider generation.

### `min_pair_cohort_pass` (budget 0.07)

Fifteen provider attempts; best scored near-miss is `idle--min_pair_cohort_pass--011`
at **0.0698** (raw). Under [Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38):

- stored value `0.0698` lies in `[0.06975, 0.06985)`;
- four-place ceiling yields only `0.0698` or `0.0699`;
- both pass the inclusive `0.0700` Budget;
- the target Gate therefore does not fail, so no isolated control exists.

Rescored Measurement run (schema `gate-control-measurement/1`):

```bash
PYTHONPATH=. python3 prototype/strip-coherence/rescore_measurement.py \
  gate-controls/reports/idle--min_pair_cohort_pass--011/2026-07-26T16-29-49+00-00.json
```

Recorded as `idle--min_pair_cohort_pass--016` in `gate-controls/attempts.jsonl`
(`GATE_UNSEPARABLE`). No further provider generation.
