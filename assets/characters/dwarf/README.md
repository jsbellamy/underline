# Dwarf (game character)

This is the dwarf the **game** uses. It was generated outside this repo and did
**not** go through the strip-acquisition pipeline: no Gate score, no Identity
Lock, no part map, and no conformance to `assets/palettes/first-room.json`.
Treat it as game content, not as a Release asset — do not feed it to
`gate-control:*` or `strip:polish` verification.

The pipeline-produced 16×24 dwarf at [`assets/first-room/dwarf/`](../../first-room/dwarf/)
is **retired from the game** but stays in place as the canonical fixture for the
pipeline test suite (10 test files, plus ADRs and the `dwarf-miner` polish
profile reference it). Don't delete it.

## Layout

Frames are 26×18, uniformly cropped from the pack's 36×36 canvas at
`(5, 9)–(31, 27)` — the union content bbox across every frame. That single crop
keeps animation alignment intact and, because the box is centered on the source
canvas, preserves east/west mirror symmetry. Feet sit on the bottom row.

| Animation | Frames | Notes |
| --- | --- | --- |
| `idle/` | 1 | Static pose from the pack's east/west rotations. East and west are *not* pixel mirrors here — they are separately drawn. |
| `walk/` | 8 | West is a pixel-exact mirror of east. |
| `swing/` | 9 | Pickaxe raised overhead. West is a pixel-exact mirror of east. |

Only east and west facings were imported; the source pack's other six
directions were dropped.

`manifest.json` (`external-sprite-pack/0`) hash-binds every imported frame to
its source file.
