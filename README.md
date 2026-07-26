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

## Pipeline & evidence suite

```bash
npm run prototype:strip:corpus    # score inbox/ against manifest
npm run strip:ingest -- <png> --motion-class <class>  # CLI ingest + gate
npm run prototype:strip           # interactive TUI
```

Dependencies: Python 3, Pillow, NumPy. Grid-recovery primitives are vendored in
`pipeline/recovery.py` (from Nightglass `acquire.py`; re-vendor upstream changes).
