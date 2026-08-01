# Strip coherence evidence suite

Standing regression corpus for the strip-acquisition contract in
[`docs/strip-acquisition-contract.md`](../../docs/strip-acquisition-contract.md).

## What the corpus is

23 provider-strip PNGs in `inbox/` scored against `prompts/manifest.json`: 18
PASS samples and five negative controls (07, 08, 09, 22, 23). Budgets are
derived from manifest-good strips plus the one documented legacy idle baseline,
`miner-idle-strip.png`; see the contract's good-cohort rule. Gates are proved by
adversarial mutations and the five negative controls.

Production gate code lives in `pipeline/strip.py`. CLI ingest is
`pipeline/ingest_strip.py` (`npm run strip:ingest`).

## Production vs this directory

| Role | Location | npm commands |
|------|----------|--------------|
| **Production operator path** | `pipeline/gate_control*.py`, `pipeline/gate_review.py`, `pipeline/gate_verification.py` | `gate-control:score`, `gate-control:acquire`, `gate-control:review`, `gate-control:verify` |
| **Historical / proof tooling** | Runners in this directory (`corpus.py`, `adversarial.py`, `derive_budgets.py`, …) | `prototype:strip:*` |

Numeric policy for four-place ceiling quantization lives at
`pipeline/numeric_policy.py`.

## Adding a sample

1. Write a prompt in `prompts/<id>.txt` (follow existing samples).
2. Generate the strip and drop `<id>.png` into `inbox/`.
3. Add a manifest entry with `id`, `motion_class`, and `contract_expect`
   (plus `contract_expect_gates` for expected failures). See
   `prompts/manifest.json` for the exact fields.
4. Score: `npm run prototype:strip:corpus`

## Re-deriving budgets

After the corpus changes, run `npm run prototype:strip:alpha-budgets` and update
production Budget evidence per `docs/alpha-budget-tables.md` and
`docs/strip-acquisition-contract.md`. Use
`npm run prototype:strip:derive-budgets` only to reproduce the historical pre-α
baseline.

## Proof runners

From repo root:

```bash
npm run prototype:strip          # interactive TUI
npm run prototype:strip:smoke    # synthetic pass/fail self-check
npm run strip:ingest             # gate strip PNG (--motion-class required)
npm run prototype:strip:corpus   # score inbox/ against manifest
npm run prototype:strip:derive-budgets  # historical pre-α baseline
npm run prototype:strip:alpha-budgets   # production runtime oracle
npm run prototype:strip:adversarial
npm run prototype:strip:displacement
npm run prototype:strip:sharpness
npm test
```
