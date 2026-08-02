# ADR 0007: Swing Cell-author acquisition

## Status

Accepted (2026-08-01, issue #278).

## Context

Repository authorities still required image-edit for both dwarf walk and swing,
contradicting the accepted providerless Cell-author path for swing. Walk remains
identity-locked provider image-edit from the idle generation source (issue #126).
Swing needs exact 24×24 action-canvas control and connected pose requirements
(ADR 0003) that provider editing cannot guarantee at the Cell level.

Issues **#234** (`strip:polish init-cell`), **#276** (cell-delta ledger), and
**#277** (`strip:author` Motion Author CLI) delivered the providerless lifecycle
surface. This ADR records the durable decision before swing re-acquisition (#127).

## Decision

**Walk** remains identity-locked **provider image-edit** from the idle generation
source. No change to walk acquisition workflow or #126 scope.

**Swing** is authored by **Cell-authored acquisition**:

1. All four target Frames start from canonical idle **Release Frame 0** (the
   palette-exact post-ingest identity anchor per ADR 0002).
2. A checked-in **pose plan** (`motion-pose-plan/0`) declares intended Frame
   operations and base mapping `[0, 0, 0, 0]`.
3. **Motion Author** (`strip:author`) applies the pose plan under Identity Lock,
   palette, and geometry constraints, emitting authored Frames and a
   `cell-delta-ledger/0` sidecar.
4. **`strip:polish init-cell`** initializes the Polish Bundle from authored
   Frames, the ledger, and the pose plan — no provider transport raster, no
   provider Attempt, no `animation-attempt-ledger/0`.
5. Provenance uses schema `cell-author-provenance/0` with
   `generation_mode=cell-author`.

Swing uses **no new image generation** and **no provider Attempt**. Corpus motion
samples and PR #169 are reference evidence only; generating new pose concepts is
out of scope.

**`init-cell` is a distinct providerless lifecycle** from provider `init`. The
generic Cell-author capability does **not** silently migrate another Motion class;
only swing is in scope for this decision.

Provider image-edit remains suitable for walk. Swing's choice is driven by exact
24×24 action-canvas control and connected pose requirements.

This ADR cites [ADR 0002](0002-palette-exact-canonical-identity.md) (palette-exact
identity), [ADR 0003](0003-swing-action-canvas.md) (24×24 swing canvas), and
[ADR 0004](0004-pre-attestation-acquisitions.md) (no fabricated historical
provenance).

## Consequences

### Positive

- Walk and swing have distinct, non-contradictory authoritative workflows.
- Swing acquisition is replayable: exact Cell deltas in `cell-delta-ledger/0`
  reproduce authored Frames from declared base Release Frames.
- The post-ingest identity anchor remains validation evidence, never a
  generation canvas.
- Downstream Identity Lock, coherence Gates, polish, and `check`/`finalize`
  behavior is unchanged — only the initialization branch differs.

### Negative

- Operators must learn two dwarf-miner acquisition paths (image-edit for walk,
  Cell-author for swing).
- Swing bundles carry `cell_authoring` manifest bindings instead of provider
  provenance and attempt-ledger rows.

### Limit

This ADR records the decision and workflow only — no runtime behavior, Gate,
Budget, or checked-in bundle changes. Swing re-acquisition is #127.
