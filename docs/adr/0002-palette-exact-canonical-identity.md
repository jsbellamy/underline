# ADR 0002: Palette-exact canonical identity (expand–contract)

## Status

Accepted (2026-07-31). Contracted (2026-08-01, issue #179): the expand phase is
complete and only the palette-exact identity remains.

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
2. **Contract (#176–#179):** Requantize the idle, walk, and swing bundles onto
   the palette-exact identity, then collapse the two identities: the v2 bytes
   move onto the canonical path `assets/first-room/dwarf/identity.png`,
   `identity-locks.json` and `identity.json` bind that single digest, and the
   soft-shaded raster is retired. The canonical path and its 16×24 Frame size are
   unchanged; only its bytes and digest differ.

The soft-shaded raster is not archived under a second name. It survives as
provenance in the idle bundle's draft Frame 0, which is the quantization input
`identity-roles.json` was authored against and is still the source the role map's
reproduction proof runs on.

`assets/first-room/dwarf/idle/provider/source.png` is deliberately **not**
requantized. It is the image-edit generation base, not a Release asset, and
`_verify_release` does not inspect it; `identity.json`'s `notes` records this so
the next acquisition agent does not assume it is palette-exact.

The palette-exact raster (added as `identity-v2.png` by the expand phase, now
committed at `identity.png`) is produced by `pipeline.palette_quantize` with the
committed role map, then hand-corrected for isolated colour islands, broken
outlines, and collapsed value ramps. The role map reproduces the pre-cleanup
raster exactly; the hand-cleanup delta is the diff between that raster and the
committed PNG.

## Consequences

### Positive

- Palette conformance is machine-checkable on the canonical raster, and the
  dwarf Release Frames verify clean against the Master Palette.
- The committed role map makes quantization reproducible and reviewable.
- Expand–contract limited the blast radius: v1 callers kept working until every
  bundle had migrated, and the collapse touched no Release Frame bytes.

### Negative

- Two canonical rasters coexisted between expand and contract; agents working in
  that window had to keep them apart.
- Hand cleanup is expected and must be re-audited if the role map changes.
- The canonical digest changed, so any evidence recorded against `db68353f…`
  predates the contract and must be read as history.

### Runtime mirroring

Runtime mirroring of the canonical identity is a documented contract with no
implementation in this repository (no TypeScript game code yet). This migration
does not affect mirroring behaviour.
