# ADR 0003: Swing action canvas (24×24)

## Status

Accepted (2026-08-01, issue #210). Amended 2026-08-02 (issue #293).

## Context

Issue #170 measured the reference swing re-canvassed into 24×24, 32×24, and a
tool-overlay variant. Baseline swing on 16×24 loads its boundary columns — left
`[0, 2, 11, 7]`, right `[0, 6, 4, 0]` — while walk never touches either.
Swing is the only motion class that runs out of canvas. Left-edge pressure
exceeds right-edge pressure, so the widening is symmetric: +4 columns each side.

The spike recommended **24×24 with the planted-boot origin preserved at column
4**. Boundary clearance in the spike is **true by construction** — 16 columns of
content embedded at `x=4` in a 24-wide Frame cannot touch a boundary. The spike
shows today's clipped swing fits a wider box; it does not show a re-authored arc
fits. 24×24 is adopted as a decision under that stated assumption, not as a
measured result.

32×24 is rejected: it adds margin with no measured clearance gain and leaves
83.3% of the emptiest Frame unused against 24×24's 77.8%. The overlay variant is
rejected: it matches 24×24's composite geometry, adds palette-role flood-fill
complexity, and failed grip separation on Frame 3.

Frame geometry became per-motion-class in issue #209 (`resolve_class_frame_geometry`);
this ADR is the first class-specific size override.

## Decision

Adopt a **24×24 action canvas** for swing:

- `_CLASS_META.swing`: `frame_w: 24`, `frame_h: 24`, `canonical_origin: (1, 0)`.
- `identity-locks.json` `motion_classes.swing`: `frame_size: [24, 24]`; every
  lock rectangle and landmark x coordinate shifts +1 relative to the 16×24 walk
  baseline (issue #293 moved the origin from column 4 to column 1; lock
  rectangles and landmarks followed −3 in x). Y coordinates, permitted offsets,
  tolerances, and relational constraints are unchanged.
- Walk, idle, blob_idle, airborne, and emissive remain 16×24 with origin `(0, 0)`.
- The identity anchor (`identity.png`) stays 16×24; swing embeds it at column 1.

Height is unchanged. The spike measured Frame 0 spanning `y1–23` at 16×24 and did
not evaluate a taller canvas.

## Consequences

### Positive

- Swing Frames gain horizontal margin without changing the planted-boot row or
  the 16×24 identity anchor; origin 1 shifts three columns of symmetric margin
  to the right flank where the authored chop needs them (issue #293).
- Per-class geometry is now exercised in production metadata and Identity Lock,
  not only in the resolver from #209.
- The #170 measurements and rejection rationale are retained here after the
  24×24 production bundle landed in #219/#220.

### Negative

- Swing bundles and Release Frames now use the adopted 24×24 canvas.
- `strip:polish init` resolves the provider Strip layout from the Motion class, so
  swing Attempts are recovered at 24 logical Cells; legacy `/0` and `/1` bundles
  keep the 16×24 provenance expectation on `check`.
- Identity Lock swing evaluation requires 24×24 attempt Frames with the anchor
  embedded at `(1, 0)` — callers cannot pass bare 16×24 rasters for swing.
- Strip pitch and gutter semantics for swing differ from the global default
  (`pitch_px` still derives from per-class `frame_w`).

### Limit

Boundary clearance is assumed, not re-measured on re-authored art. If a
re-authored swing arc still clips at 24×24, the canvas decision must be
revisited with fresh measurements.

**Origin amendment (issue #293).** The Limit clause above was tested against the
re-authored swing arc. The arc does not clip at 24×24, but at origin `(4, 0)` it
cannot satisfy ground-contact clearance ahead of the boots while keeping column
23 clear (issue #127 C5). The pickaxe tool footprint in the idle release
Frame — 21 `stone` Cells in a 6×7 bounding box — needs a seven-column window
between the boots lock's right edge and column 22; only origin `(1, 0)` keeps
all eight lattice-exact contact orientations available. Width stays 24; 32×24
remains rejected.

A general `recanvas` or `migrate-layout` command is deliberately deferred. New
bundles now materialize the class canvas during initialization, and swing is the
only concrete migration so far. Add a migration command only when another
existing bundle needs one, with explicit dry-run, hash, report, and Release Frame
semantics for that use case.
