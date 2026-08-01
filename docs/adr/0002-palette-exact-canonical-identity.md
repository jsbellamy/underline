# ADR 0002: Palette-exact canonical identity (expand)

## Status

Accepted (2026-07-31)

## Context

The first-room dwarf canonical identity (`assets/first-room/dwarf/identity.png`) is
hash-bound through `identity.json`, `identity-locks.json`, and the idle release
Frame 0 binding — all three reference sha256 `db68353f…`. That raster carries
268 opaque Cells and 255 unique RGB values; **zero** opaque Cells are exact Master
Palette colours from `assets/palettes/first-room.json`.

The Master Palette was therefore hash-bound but never pixel-checked. Global
nearest-colour role assignment (`propose_seed_role_map`) maps 40 of 268 Cells to
`amber-emission`, collapsing beard value ramps and polluting the beard/chest
cluster. Role-segmented quantization is required before palette conformance can
be enforced.

One raster serves three bindings today. Retiring or rewriting `identity.png` in a
single step would break every consumer at once.

## Decision

Run an **expand–contract** migration:

1. **Expand (this ADR):** Add `identity-v2.png` beside the canonical raster, with
   a committed per-Cell role map (`identity-roles.json`) and an additive
   `palette_exact_identity` entry in `identity-locks.json` (schema
   `identity-lock/2`). The v1 `db68353f…` binding and all current
   `evaluate_identity_lock` callers remain unchanged.
2. **Contract (later issue):** Repoint consumers from v1 to v2 and retire the
   soft-shaded raster.

`identity-v2.png` is produced by `pipeline.palette_quantize` with the committed
role map, then hand-corrected for isolated colour islands, broken outlines, and
collapsed value ramps. The role map reproduces the pre-cleanup raster exactly;
the hand-cleanup delta is the diff between that raster and the committed v2 PNG.

## Consequences

### Positive

- Palette conformance is machine-checkable on the v2 raster without disturbing
  walk/swing Identity Lock evaluation against v1.
- The committed role map makes quantization reproducible and reviewable.
- Expand–contract limits blast radius: v1 callers keep working until contract.

### Negative

- Two canonical rasters coexist until contract; agents must not confuse them.
- Hand cleanup is expected and must be re-audited if the role map changes.

### Runtime mirroring

Runtime mirroring of the canonical identity is a documented contract with no
implementation in this repository (no TypeScript game code yet). This migration
does not affect mirroring behaviour.
