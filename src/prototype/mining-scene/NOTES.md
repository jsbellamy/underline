# Prototype: mining scene at 480×112

**Question:** What is actually on screen in the 480×112 Pane?

## Answer (2026-08-03)

Composition for the slice Pane:

| Decision | Choice |
| --- | --- |
| Dwarf scale | **3×** (78×54), integer nearest-neighbor |
| Camera | Dwarf planted on screen; Tunnel / Face scroll under him |
| Numbers | Dig Rate, Ore, Ingots are **Dock-only** — Pane stays clean |
| Colony open | Small corner chip on the Pane |
| Face / Tunnel | Cyan Face (first-room cyan ramp); crack grows with Swing progress; excavated hollow behind; solid stone ahead |
| Extra Pane state | Sprite only — `idle` / `swing` / `walk`. No Ore pile, no Smelter widget |
| First open | Idle Dwarf, uncracked Face east, rock ahead, Colony chip — no empty-state copy |
| Chrome | No Dig Rate line — Tunnel uses the full 480×112 |

Throwaway variants under this directory answered the question; absorb into
[Render the dwarf mining in the Pane](https://github.com/jsbellamy/underline/issues/321)
and delete.

**Run (until deleted):** `npm run prototype:mining-scene` →
`http://localhost:1420/?prototype=mining-scene&variant=A&moment=first-open`
