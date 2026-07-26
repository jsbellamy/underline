# Underline

Throwaway testbed for **provider strip animation**: recover a wide logical grid from one
magenta-keyed render, slice into frames, and gate temporal coherence deterministically.

Nightglass / SideScape already solve single-subject grid recovery; this repo asks whether
**multi-frame strips** can be promoted from the same ingest path.

Agents: start at [AGENTS.md](AGENTS.md), then [CONTEXT.md](CONTEXT.md) and
[docs/strip-acquisition-contract.md](docs/strip-acquisition-contract.md).

## Prototype

**Question:** After one provider render of an N-frame strip, can recovered logical cells be
sliced and coherence-gated (baseline row, palette set, adjacent diff, loop closure) such
that pass/fail is a report you read — not a visual judgement call?

```bash
npm run prototype:strip
```

Drop provider raws in `prototype/strip-coherence/inbox/` and press `[4]` in the TUI.

Dependencies: Python 3, Pillow, NumPy. Grid-recovery primitives are vendored in
`pipeline/recovery.py` (from Nightglass `acquire.py`; re-vendor upstream changes).

**PROTOTYPE — delete or absorb when answered.** See `prototype/strip-coherence/NOTES.md`.
