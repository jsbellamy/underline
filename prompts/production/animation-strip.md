# Production prompt kit — animation Strip

Normative authority for provider-rendered animation **Strips** in the first-room
**Art Cohort**. Use glossary terms from `CONTEXT.md`. Visual identity lives in
`docs/first-room-art-direction.md`; palette membership in
`assets/palettes/first-room.json`.

## Transport raster vs releasable art

| Stage | What it is |
|-------|------------|
| **Provider transport raster** | The wide PNG returned by an image provider — magenta-keyed, possibly upscaled logical Cells, bundled with provenance. Input to ingest only. |
| **Releasable art** | Draft / Polished / Release **Frames** exported after ingest pass and final polish — exact logical geometry, Master Palette opaque RGB, binary alpha. |

Never ship a provider transport raster. Never treat inbox corpus Strips as
production identity.

## Required Strip geometry

Every production animation Strip must declare and honor:

| Property | Value |
|----------|-------|
| Frame count | 4 |
| Frame size | 16×24 logical Cells |
| Facing | Right (runtime mirrors for left) |
| Gutter | 2 full magenta logical Cells between each Frame |
| Background key | Flat magenta `#FF00FF` everywhere outside Frames and gutters |
| Layout | One horizontal row — no margins, labels, numbers, or extra rows |
| Pitch | `frame_w + gutter` = 18 logical Cells stride (16 + 2) |

Logical Cells are flat square blocks at provider scale — no anti-aliasing,
blur, gradient, or dithering within a Cell.

## Master Palette

Opaque RGB in every Frame must be drawn only from
`assets/palettes/first-room.json` (id `first-room`). `#FF00FF` is transport
key only and is not a palette color.

## Motion class and timing

Declare the **Motion class** (`idle`, `walk`, `swing`, `emissive`, etc.) and
match first-room timing from `docs/first-room-art-direction.md`.

## Polish profile (required)

Every production Strip request must name a checked-in **Polish profile** id
(for example `miner` in `polish-profiles/`). The profile is the art-direction
audit authority after ingest — fixed visual questions, Motion-class overrides,
and `PASS` / `EDIT` / `UNCERTAIN` verdicts.

Init a Polish Bundle with:

```bash
npm run strip:polish -- init <accepted-strip.png> --polish-profile <id>
```

## Dwarf-miner walk and swing — image-edit lifecycle

`dwarf-miner` **walk** and **swing** Strips must be acquired by **image-edit**
from the original idle provider Strip, not by fresh text-to-image redraw.

There are two deliberately different identity inputs:

| Input | Use |
|-------|-----|
| `identity.json` → `generation_source` | The original idle provider Strip. Use this detailed provider artwork as the image-edit generation base. |
| `identity.json` → `identity_png` | The post-ingest identity anchor. Use this 16×24 Release Frame only for deterministic Identity Lock evaluation after ingest. |

Never upscale `identity.png` into a generation canvas: its ingest-reduced Cells
have already discarded the provider artwork’s detail.

1. Copy the hash-bound generation source declared by the dwarf identity:

```bash
npm run strip:polish -- seed \
  --identity-declaration assets/first-room/dwarf/identity.json \
  --out <seed.png> [--json]
```

2. Submit `<seed.png>` as the **image-edit base** (edit source). The command
   copies the original idle provider Strip byte-for-byte.
3. Bind `assets/first-room/dwarf/identity.png` separately as the post-ingest
   identity anchor (`--identity-reference`) for validation.
4. **Forbid** fresh text-to-image generation for these Motion classes.
5. Record the declared provider-source hash as `edit_source_sha256` in every
   image-edit Attempt’s provenance.
6. Run Identity Lock only after provider recovery has produced logical Frames.
7. Generate **sequential immutable Attempts** until one passes provenance,
   automatic Identity Lock, coherence Gates, polish, and visual audit.
8. Record every rejection and predecessor edge in the attempt ledger; never cap
   Attempt count with a fixed quota.
9. Visual audit judges motion readability and exposed identity **outside** the
   locked regions, but must cite the automatic Identity Lock PASS in the check
   report.

Identity Lock rules live in `assets/first-room/dwarf/identity-locks.json`.

## Provenance

Bundle the provider PNG with a complete provenance sidecar before ingest.
Incomplete provenance blocks Promotion and polish init. See
`docs/afk-acceptance-implementation-spec.md` for required fields.

## Ingest contract

Production ingest (`npm run strip:ingest`) scores the recovered Strip against
the declared Motion class via `coherence_split`. Review-band and hard-fail
Strips export no Frames. Gate and Budget authority:
`docs/strip-acquisition-contract.md`.

## Prompt template skeleton

```text
TRUE chunky pixel art sprite strip ONLY. Four <MOTION> frames of <SUBJECT> in one
horizontal row, facing RIGHT.

Canvas: very wide panoramic strip — aspect ratio roughly 3:1. Four frames fill
most of the width.

Each frame on an exact 16×24 logical pixel grid rendered large — every logical
pixel is one clean flat square block. No anti-aliasing, blur, gradient, or
dithering.

<Motion-specific pose and baseline rules. Feet on bottom row for grounded classes.>

Between each frame: two full magenta logical Cells of empty gutter.

Flat solid magenta #FF00FF background everywhere else. Master Palette
membership only — see assets/palettes/first-room.json. Neutral upper-left
highlights, warm shadows.

Frame order left→right: frame_0 … frame_3. Loop rules per Motion class.

Polish profile: <id>.

Do not add margins, labels, numbers, or extra rows. One row of four frames only.
```
