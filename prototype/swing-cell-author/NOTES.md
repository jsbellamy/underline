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
## Impact pass (follow-up)

First draft only relocated the pickaxe (read as a pivot). Impact model now uses
permitted Identity Lock offsets + art-direction timing:

| Frame | Body | Tool | ms |
|-------|------|------|----|
| 0 | coil back helmet/belt `dx=-1` | high wind-up | 150 |
| 1 | neutral | long head-height whip | 80 |
| 2 | commit forward `dx=+1` | crossing down | 60 |
| 3 | squash `(+1,+1)` | tip ahead of planted boots | 180 |

Re-run still Identity Lock PASS; body mass sells weight, not just tool teleport.

## Tool mass / arm attachment

Wide ~5×4 head floated metal away from the grip (arm read as detached).
Reverted toward the impact-pass tool size (~4×3), kept socket into the handle,
and painted continuous forearm/hand bridges torso→grip on every Frame.
Still Identity Lock PASS.
