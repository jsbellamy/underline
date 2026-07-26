# Strip coherence prototype (LOGIC)

## Question

Can a **single provider strip render** (N animation frames side-by-side on one logical grid)
be ingested through the existing Nightglass/SideScape grid-recovery primitives, sliced into
per-frame cell matrices, and **accepted or rejected by deterministic coherence gates** —
without cross-generation jitter?

## What this prototype does

1. **Recover** one wide logical grid from a magenta-keyed PNG (`recover_strip_cells`).
2. **Slice** into N frames using a declared layout (`frame_w`, `frame_h`, `frame_count`, `gutter`).
3. **Report** coherence metrics (`coherence_report`): shape parity, baseline row, palette set,
   adjacent cell-diff fractions, loop closure.

Synthetic fixtures prove the gates fire on known-good and known-bad strips before any
provider generation is involved.

## Run

From repo root:

```bash
npm run prototype:strip          # interactive TUI
npm run prototype:strip:smoke    # synthetic pass/fail self-check
```

## Verdict

Record the answer in `NOTES.md` when done, then delete this folder or use `pipeline/strip.py`
as the production gate module.
