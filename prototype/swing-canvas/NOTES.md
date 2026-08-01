# Verdict

**Recommendation: `24x24` action canvas** — embed the existing 16×24 swing Frames
at `x=4` on a 24×24 logical grid (planted-boot origin unchanged, +4 Columns each
side).

## Measured justification

| Variant | Clears both boundary Columns on all four Frames? | Emptiest Frame unused share (`1 − occupancy`) | `static_silhouette_fraction` min adjacent pair |
|---------|---------------------------------------------------|-----------------------------------------------|-----------------------------------------------|
| `24x24` | **Yes** — boundary left/right opaque counts are `0` on every Frame | **77.8%** (Frame 3, occupancy `0.222`) | `0.752` (pair `3→0`) |
| `32x24` | **Yes** — same zero boundary load | **83.3%** (Frame 3, occupancy `0.167`) | `0.814` (pair `3→0`) |
| `overlay` | **Yes** on the composite (matches `24x24` geometry) | **77.8%** (same composite as `24x24`) | `0.752` (pair `3→0`) |

Baseline swing on 16×24 **does not** clear the boundary Columns: left edge load
`[0, 2, 11, 7]`, right `[0, 6, 4, 0]` (Frames 1–3 touch at least one edge).
Walk never touches either boundary Column; idle right-edge load is posture drift,
not tool arc.

`32x24` buys 5.5 percentage points more empty canvas on the sparsest Frame but
no additional clearance—the arm and pickaxe already fit inside `24x24` with zero
boundary Cells. The extra width only dilutes occupancy.

## C4 answers

### Does the variant clear both boundary columns on all four Frames?

- **`24x24`:** Yes.
- **`32x24`:** Yes.
- **`overlay`:** Yes on the 24×24 composite measurements.

### How much of the canvas is unused on the emptiest Frame?

- **`24x24`:** **77.8%** unused (Frame 3 occupancy `0.222` of 576 Cells).
- **`32x24`:** **83.3%** unused (Frame 3 occupancy `0.167` of 768 Cells).
- **`overlay`:** **77.8%** (identical composite to `24x24`).

### Does the tool arc read at native scale?

Judged on `out/variants/*/frame-*-silhouette.png` at 1× and enlarged with
nearest-neighbor: **yes for `24x24` and `32x24`** — the pickaxe head, handle,
and rear-arm sweep remain separated in the two-colour silhouette through Frames
1–3 without clipping. Frame 0 is wind-up (tool tucked); Frame 3 follow-through
still reads. **`overlay`** matches `24x24` silhouettes where separation
succeeds.

### For `overlay` only: is the body layer byte-identical to today's Frames?

**No as a whole raster** — the body layer omits tool-mask Cells. **Yes for
non-tool Cells** on Frames 0–2 (`overlay_body_byte_identical` in
`scoreboard.json`). Frame 3 separation **failed** (`no grip seed found`); treat
overlay as a failed variant for that Frame, not a blocker for the pad decision.

## Why not `32x24` or `overlay`?

- **`32x24`** — strictly more empty margin with no measured clearance gain over
  `24x24`.
- **`overlay`** — same composite dimensions and silhouette as `24x24`, but adds
  palette-role flood-fill complexity and loses Frame 3 to a failed grip seed.
  No measurement advantage for the follow-up re-authoring wave.

## Follow-up inputs

- Lock **24×24** `frame_w` / `frame_h` for swing bundles with body origin at
  Column 4 (boot row unchanged at `y=21–23`).
- Re-author swing Frames into the wider canvas rather than padding at ingest.
- Walk/idle remain 16×24 per `docs/first-room-art-direction.md`.

## C1 editorial note

Walk Frames 2–3 alpha bbox in `scoreboard.json` (`x1-14 y7-23`, `x1-13 y7-23`)
differs from the issue table row (`x2-14 y7-23` for all four Frames). Occupancy,
swing edge loads, and all other baseline fields match the Contract table exactly
against current polished assets.
