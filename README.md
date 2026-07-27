# Underline

Mining game with a **strip-acquisition pipeline** (`pipeline/`): recover a wide
logical grid from one magenta-keyed provider render, slice into frames, and gate
temporal coherence deterministically.

The **standing corpus** in `prototype/strip-coherence/` (23 provider strips) is
permanent regression evidence. Gate budgets and separation claims are defined in
[`docs/strip-acquisition-contract.md`](docs/strip-acquisition-contract.md).

The original prototype question and its answer are recorded in
[`prototype/strip-coherence/NOTES.md`](prototype/strip-coherence/NOTES.md).

Agents: start at [AGENTS.md](AGENTS.md), then [CONTEXT.md](CONTEXT.md) and
the contract above.

## Gate-control production path

Operational Gate-control work uses the production modules under `pipeline/` and
the canonical npm commands below. The checked-in manifest holds **17 ACTIVE**
Promotions across all Separated Motion-class / Gate pairs; new candidates follow
the same score → acquire → review → verify loop.

```bash
# 1. Score a candidate Strip for isolation (measurement-only)
npm run gate-control:score -- <strip.png> --motion-class <class> --target-gate <gate>

# 2. Record Attempts, provenance, and Promotion candidates
npm run gate-control:acquire -- record --help   # see subcommands: record, promote, …

# 3. Gate review — per-Gate agent judgment in the Review band
npm run gate-control:review -- --help

# 4. Full-repository Promotion verification (manifest-backed)
npm run gate-control:verify -- run --promotion-id <promo-id>
```

AFK acceptance authority: [`docs/afk-acceptance-implementation-spec.md`](docs/afk-acceptance-implementation-spec.md).

## Corpus analysis and proof tooling

Historical corpus scoring and budget derivation remain under `prototype:strip:*`.
These commands score the standing inbox, derive measured tables, and prove gate
separation — they are not the production operator path above.

```bash
npm run prototype:strip:corpus          # score inbox/ against manifest
npm run prototype:strip:adversarial     # per-class mutations must reject
npm run prototype:strip:alpha-budgets   # α=0.5 Separated budgets + fragile claims
npm run prototype:strip:derive-budgets  # historical pre-α Budget baseline
npm run strip:ingest -- <png> --motion-class <class>  # CLI ingest + gate
npm run prototype:strip                 # interactive TUI
```

Dependencies: Python 3, Pillow, NumPy. Grid-recovery primitives are vendored in
`pipeline/recovery.py` (from Nightglass `acquire.py`; re-vendor upstream changes).
