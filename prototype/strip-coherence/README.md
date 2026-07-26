# Strip coherence evidence suite

Standing regression corpus for the strip-acquisition contract in
[`docs/strip-acquisition-contract.md`](../../docs/strip-acquisition-contract.md).

## What the corpus is

23 provider-strip PNGs in `inbox/` scored against `prompts/manifest.json`.
Every budget in the contract is derived from manifest-good strips here; gates
are proved by adversarial mutations and negative controls 07–09.

Production gate code lives in `pipeline/strip.py`. CLI ingest is
`pipeline/ingest_strip.py` (`npm run strip:ingest`).

## Adding a sample

1. Write a prompt in `prompts/<id>.txt` (follow existing samples).
2. Generate the strip and drop `<id>.png` into `inbox/`.
3. Add a manifest entry with `id`, `motion_class`, and `contract_expect`
   (plus `contract_expect_gates` for expected failures). See
   `prompts/manifest.json` for the exact fields.
4. Score: `npm run prototype:strip:corpus`

## Re-deriving budgets

After the corpus changes, run `npm run prototype:strip:derive-budgets` and
update the contract's measured tables per
`docs/strip-acquisition-contract.md`.

## Runners

From repo root:

```bash
npm run prototype:strip          # interactive TUI
npm run prototype:strip:smoke    # synthetic pass/fail self-check
npm run strip:ingest             # gate strip PNG (--motion-class required)
npm run prototype:strip:corpus   # score inbox/ against manifest
npm run prototype:strip:derive-budgets
npm run prototype:strip:adversarial
npm run prototype:strip:displacement
npm run prototype:strip:sharpness
npm test
```
