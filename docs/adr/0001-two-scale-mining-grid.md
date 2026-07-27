# ADR 0001: Two-scale mining grid

## Status

Accepted (2026-07-27)

## Context

Underline's cave is built from modular edge pieces and mineable ore. Two grid
scales compete:

1. **16×16 Rendering Tiles** — small enough for readable autotile edges and
   background variation at the 320×180 viewport.
2. **32×32 Mineable Blocks** — large enough for players to recognize ore type,
   cluster geometry, and mining feedback at native scale.

A single 16×16 mining target was considered: one Rendering Tile per
user-targetable block.

## Decision

Retain **16×16 Rendering Tiles** for world assembly (cave edges, backgrounds,
modular terrain) and define **Mineable Blocks** as atomic **32×32** mining
targets occupying a 2×2 Rendering Tile footprint.

Autotile masks and edge treatments apply to Mineable Blocks. Rendering Tiles
provide the modular substrate; Mineable Blocks provide the player-facing mining
unit.

The first-room **Master Palette** (`assets/palettes/first-room.json`) and art
direction (`docs/first-room-art-direction.md`) encode this split.

## Consequences

### Positive

- Ore clusters remain legible at native scale — angular cyan crystal geometry
  and value steps survive in a 32×32 Cell grid.
- Cave backgrounds and edge modules stay fine-grained at 16×16 without
  forcing ore recognition into half that resolution.
- Autotile kit exercises real exposed edges on Mineable Blocks while
  backgrounds tile cheaply.

### Negative

- Two scales must stay aligned: every Mineable Block snaps to an even
  Rendering Tile grid; tooling and prompts must declare both units.
- Artists must not conflate a Rendering Tile texture with a Mineable Block
  target.

## Rejected alternative

**Single 16×16 mining target** — one Rendering Tile per mineable cell.

Rejected because ore recognition and mining feedback collapse at native
320×180 scale: cyan crystal clusters, earth/leather value separation, and
pickaxe contact reads blur together when the atomic target is only 16×16
logical Cells. Readable terraces in the Terraced Shaft composition also need
walk surfaces that do not compete with ore-sized noise on every background
Cell.
