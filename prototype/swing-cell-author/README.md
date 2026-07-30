# PROTOTYPE — swing Cell author (throwaway)

**Question:** Can an agent hand-author a readable four-Frame dwarf swing at
the 16×24 polished Cell grid, starting from idle polished `frame-0`, preserving
Identity Lock regions, without Cursor Image Gen?

This does **not** close #127. It only tests feasibility. If it works, pipeline /
contract changes for a `cell-author` acquisition path can be discussed later.

## Run

```bash
npm run prototype:swing-cell-author
```

Writes scored frames, grid overlays, and `out/scoreboard.json` under
`prototype/swing-cell-author/out/`.

## Rules of this experiment

- Edit source for pose work: `assets/first-room/dwarf/idle/polished/frame-0.png`
- Reference swing silhouettes: `assets/first-room/dwarf/swing/polished/frame-*.png` (pose hint only)
- Never paint into swing Identity Lock rectangles (helmet/face, belt-core, boots)
- New subject Cells use Master Palette RGB only
- Score with `pipeline.identity_lock.evaluate_identity_lock` (motion class `swing`)
