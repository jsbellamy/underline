# ADR 0009: Vendored Pane+Dock shell from Nightglass

## Status

Accepted (2026-08-03)

## Context

Underline's vertical slice needs an always-on-top **Pane** and a companion
**Dock**, with BroadcastChannel transport, dock geometry, and a render pump.
Nightglass already ships that shell for a combat domain. Copying ad hoc without
a single provenance record would scatter upstream citations the way
`pipeline/recovery.py` already forbids for grid recovery.

Issue #315 inventoried what transfers; issue #316 scaffolds the app.

## Decision

Vendor the shell modules listed in `docs/vendor/pane-dock-shell.md` from
Nightglass commit `7047b2a28565d28598a4420b8762c7f49b1898f5`.

- **One** vendor manifest (`docs/vendor/pane-dock-shell.md`) plus **this** ADR
  record provenance. Do not restate Nightglass paths in every consumer doc.
- Re-vendor upstream changes rather than editing clean copies in place.
- Adapted files may rename tile→Pane and drop combat types; they still cite the
  Nightglass source path and SHA in their file header.
- Do not vendor Battle Tile presentation, combat Dock surfaces, Engine offline
  catch-up, combat sprite cast, or `TileCommand*` / `applyTileCommand`.

## Consequences

### Positive

- Shell geometry and transport land once, with the same re-vendor discipline as
  `pipeline/recovery.py`.
- Mining-specific bus schema, animation playback, and economy stay free to
  diverge without forking combat code.

### Negative

- Adapted modules can drift if edited in place without re-vendoring; headers and
  the manifest must stay the authority for the next sync.
- Interim Pane chrome (24px Dig Rate line + 86px Tunnel band = 110 content px
  inside a 112 outer with 1px borders) still mirrors Nightglass until a later
  ticket decides mining chrome.

## Rejected alternative

**Rewrite the two-window shell from scratch.** Rejected because the geometry,
dock port, pump, and bus transport are already proven and game-agnostic enough
to adapt; a rewrite would burn the vertical-slice budget on solved windowing.
