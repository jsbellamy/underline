# ADR 0008: Anatomy-first character acquisition

## Status

Proposed (2026-08-02, issue #300). Amends [ADR 0007](0007-swing-cell-author-acquisition.md)
for walk; does not change [ADR 0002](0002-palette-exact-canonical-identity.md).

## Context

Five successive derivations of `assets/first-room/dwarf/parts.json` — #297, three
passes on #299, and the re-role on #300 — were each structurally valid and
anatomically wrong, and each failed at the same boundary: beard versus sleeve
versus glove versus pickaxe haft. Issue #300 diagnosed the cause correctly. The
Master Palette renders five distinct objects from one role,
`earth-leather-beard`, at overlapping values, so **colour cannot decide anatomy**.

#300 re-roled the tool to `stone` and the gloves to `skin` so those two parts
became mechanically derivable. That worked, and a human approved the result. But
it treats the symptom. The workflow still derives semantics from material, so the
next character with a value-blended region reproduces the failure, and the fix
required a human to arbitrate individual Cells across several review rounds.

Finishing #300 surfaced a second, larger problem. The walk bundle's palette-exact
Identity Lock compares **role histograms** over the lock rectangle and, in
`palette_exact` mode, ignores `occupancy_difference` entirely. Walk passed for
this long at an occupancy difference of ~0.48. Projecting the canonical glove
footprint onto each walk Frame at the offset the lock itself selects, `(0,1)`,
lands it on Cells the walk role map calls `blue-metal` and `amber-emission` —
the helmet and lamp — and only 3–4 of the 28 tool Cells land on any opaque Cell.

The walk strip is not a pose of the canonical character. Nothing in the pipeline
ever asserted that it was, because the only binding between a Motion and the
canonical identity is a colour-mix comparison. Motions are acquired
independently and then checked for resemblance, rather than derived from a shared
body.

## Decision

**Anatomy is authoritative before colour, and Motions are posed from the
canonical body rather than checked against it.**

### Acquisition order

1. Establish the opaque silhouette from the reference.
2. Propose a mutually exclusive semantic part map covering **every** opaque Cell —
   not merely an outer silhouette — carrying stable part IDs, a parent graph,
   pivots and grips, rigid/deformable classification, z-order, and occlusion.
3. Validate coverage, exclusivity, connectivity, required topology, and landmark
   relationships mechanically.
4. Render a false-colour part sheet and obtain **human approval of anatomy while
   it is still independent of palette similarity**.
5. Only then assign material/palette roles to the approved parts and quantize
   deterministically through `pipeline.palette_quantize`.
6. Compile a canonical character: raster, semantic map, rig, palette/material
   bindings, and synchronized evidence.
7. Build every Motion from the same semantic part identities and rig.

### The seam

Two operations, with quantization, outline ownership, digest propagation, and
evidence generation behind them:

- **compile** — an approved part map plus a material map plus a palette becomes a
  canonical character and all synchronized outputs.
- **pose** — a compiled character plus a pose plan becomes a Frame, emitting both
  the raster **and** its transformed part map.

"Same body map" means stable part IDs, topology, pivots, and ownership — **not**
identical Cell coordinates. Each pose emits a transformed per-Frame map. Rigid
parts such as the pickaxe transform differently from deformable parts such as the
beard.

### Scope against ADR 0007

ADR 0007 kept **walk** on identity-locked provider image-edit and moved only
**swing** to Cell-author. This ADR amends that: walk moves to part-map-driven
authoring, extending the existing Motion Author (`strip:author`,
`motion-pose-plan/0`) so operations address stable part IDs with their pivots and
parent graph instead of raw lock rectangles. Swing's Cell-author lifecycle is
unchanged and gains part addressing for free.

Provider generation remains the source of the **initial reference**. It stops
being the source of individual Motion rasters for a character that already has a
compiled canonical body.

## Consequences

### Positive

- Anatomy is decided once, reviewed once, and reused, instead of being
  re-litigated per Motion from ambiguous colour.
- Human review happens on false colour, where beard/glove/sleeve/haft are
  unambiguous, rather than on a raster where they are the same brown.
- A Motion cannot drift from the canonical body, because it is derived from it.
  The walk failure mode — a strip that resembles the character's colour mix
  without sharing its anatomy — becomes unrepresentable.
- Re-roling a material stops invalidating every Motion. Under #300 the canonical
  histogram moved and every walk Frame's lock distance roughly doubled; a posed
  Motion would have inherited the new roles.
- Per-Frame part maps unlock downstream work that needs to know which Cells are
  the hand: grip attachment, tool swaps, damage tinting, occlusion sorting.

### Negative

- Walk's existing provider strip and its evidence do not survive. Walk must be
  re-derived, and its historical bundle becomes reference-only.
- The pose plan becomes richer and correspondingly harder to author by hand.
  Deformable parts such as the beard need a transform model beyond translation.
- Compile and pose are a larger seam than the current per-Motion lifecycle, and
  Gate/evidence plumbing must move behind it without loosening ADR 0002.

### Limit

This ADR records order and seam only. It does not by itself change any Gate,
Budget, threshold, or checked-in bundle. It does **not** relax
[ADR 0002](0002-palette-exact-canonical-identity.md): compiled output is still
palette-exact and still produced by `quantize_cells` from a role map, never
painted.

The `palette_exact` Identity Lock gap this ADR describes — gating on role
histogram while ignoring `occupancy_difference` — is a defect in the current
lock and is tracked as #302; it must be fixed regardless of whether this ADR
is accepted. Implementation of the seam is #303 (part-addressed posing) and
#304 (re-deriving walk).
