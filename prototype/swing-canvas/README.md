# Swing action canvas spike

**Question:** What action-canvas size lets the dwarf swing clear both horizontal
boundary columns without wasting more logical Cells than necessary?

**Run:**

```bash
npm run prototype:swing-canvas
```

Reads polished dwarf `walk`, `idle`, and `swing` Frames from
`assets/first-room/dwarf/*/polished/frame-*.png`. Writes
`prototype/swing-canvas/out/scoreboard.json` and per-variant colour plus
two-tone silhouette PNGs under `prototype/swing-canvas/out/variants/`.

## Experiment rules

1. **Baseline (C1)** — measure the shipped 16×24 polished Frames for all three
   motions. These numbers justify the spike; the runner must reproduce them from
   the assets.
2. **Candidates (C2)** — re-canvas only the swing Frames:
   - `24x24` — embed each 16×24 Frame at `x=4` (planted-boot origin preserved,
     +4 Columns each side).
   - `32x24` — embed at `x=8` (+8 Columns each side).
   - `overlay` — keep body Cells in place; flood-fill `blue-metal` and
     `earth-leather-beard` Cells connected to a skin/green-cloth grip seed into a
     tool mask, composite body + tool on 24×24 at `x=4`. Record the boolean
     separation mask per Frame.
3. **Measurements (C3)** — per variant and Frame: alpha bbox, occupancy,
   opaque Cell counts in each boundary Column and Row, and
   `static_silhouette_fraction` for each adjacent Frame pair
   (`1 − occupancy_differences / total_cells`).
4. **Verdict (C4)** — `NOTES.md` picks one recommendation with measured
   justification.

No `assets/`, pipeline, gate, or contract files are modified.
