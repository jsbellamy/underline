# NOTES — swing Cell-author prototype

## Question

Can an agent hand-author a readable four-Frame dwarf swing at the 16×24
polished Cell grid, starting from idle polished `frame-0`, preserving Identity
Lock regions, without Cursor Image Gen?

## Command

```bash
npm run prototype:swing-cell-author
```

## Machine result (filled after run)

- `identity_lock`: PASS
- `lock_region_mutations`: [0, 0, 0, 0]
- `occupancy`: [0.6823, 0.6641, 0.6458, 0.651]
- Artifacts under `prototype/swing-cell-author/out/`

## Visual verdict

Inspected `out/idle-plus-authored-grid.png`, `out/authored-strip-grid.png`,
`out/reference-swing-strip-grid.png`, and `out/authored-swing.gif`.

| Question | Rating |
|----------|--------|
| Same idle dwarf across frames | PASS |
| Readable pickaxe arc f0→f3 | PASS |
| Boots planted | PASS |
| Frame 3 ground contact ahead of boots | PASS |
| Feasibility vs image-gen path | PASS |

Art is crude (flat palette tool on soft idle shading) but readable as a prototype.

## Implications if feasible

Today’s polish stage cannot change silhouette; #127 requires image-edit of the
padded idle provider. A working Cell-author path would need a new acquisition
mode (e.g. `generation_mode: cell-author`) that:

1. Starts from idle Release / polished Cells (not upscaled into a fake provider)
2. Allows silhouette edits outside Identity Lock rects
3. Records Attempts as Cell deltas + hashes rather than provider transport PNGs
4. Still runs Identity Lock, motion/coherence gates, and visual audit

## Verdict

**PASS** — Cell hand-author from idle polished 16×24 is feasible: Identity Lock
PASS with zero lock-region mutations, readable swing arc/contact, no image gen.
Worth a follow-up respec if we want this to replace Cursor Image Gen for #127.