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
| Frame size | 16×24 logical Cells (swing: 24×24) |
| Facing | Right (runtime mirrors for left) |
| Gutter | 2 full magenta logical Cells between each Frame |
| Background key | Flat magenta `#FF00FF` everywhere outside Frames and gutters |
| Layout | One horizontal row — no margins, labels, numbers, or extra rows |
| Pitch | `frame_w + gutter` logical Cells stride — 18 for 16×24 classes (16 + 2), 26 for swing (24 + 2) |

Logical Cells are flat square blocks at provider scale — no anti-aliasing,
blur, gradient, or dithering within a Cell.

## Provider canvas safe inset (clipping)

The logical Strip geometry above (16×24 Frames — swing 24×24 — gutter=2 magenta Cells) defines
**recovery slicing** — it is not the full provider canvas margin.

When submitting to an image **provider**, keep the subject — dwarf, tools, and
pickaxe arc included — inside a **safe empty magenta inset** around the logical
Strip row. The subject bounding box must **not** touch the provider transport
raster edges (top, bottom, left, or right). Paint uninterrupted flat magenta
`#FF00FF` between the subject and each canvas edge.

This safe inset is **outside** the logical Strip / gutters. It is provider
canvas margin for layout, **not** a change to gutter=2 or Frame size.

Touching a provider canvas edge trips recovery **`provider_clipping`** — discard
the Attempt and regenerate with more inset margin. Do not crop or paint the
provider PNG after generation to clear clipping.

Prefer compact tool arcs that fit inside the safe inset rather than widening
logical Frames or shrinking gutter width.

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

## Dwarf-miner walk — image-edit lifecycle

`dwarf-miner` **walk** Strips must be acquired by **image-edit** from the
original idle provider Strip, not by fresh text-to-image redraw.

### Two inputs — do not conflate them

Walk uses **two different PNGs** with **two different jobs**. Confusing them is
the most common acquisition failure.

| Role | Canonical path | Typical size | When it is used |
|------|----------------|--------------|-----------------|
| **Edit source** (generation canvas) | `assets/first-room/dwarf/idle/provider/source.png` | Provider transport raster (e.g. 1536×1024) | Submitted to the image provider as the **image-edit base**. Already contains four identical idle Frames on magenta — this *is* the “four-copy seed.” |
| **Post-ingest identity anchor** (lock evidence) | `assets/first-room/dwarf/identity.png` | 16×24 logical Cells | Bound as `--identity-reference` for Identity Lock **after** ingest only. Never submitted as the edit canvas. |

Both paths are declared and hash-bound in `assets/first-room/dwarf/identity.json`:

| `identity.json` key | Points at | Purpose |
|-----------------------|-----------|---------|
| `generation_source` | `idle/provider/source.png` | Edit source — detailed provider artwork |
| `identity_png` | `identity.png` | Post-ingest lock anchor — ingest-reduced Release Frame |

**`identity.png` is not the seed command’s input file.** The seed command reads
`identity.json` and emits the image-edit seed from `generation_source`. When
`seed_pad_px` is declared (64 for dwarf), it adds a uniform `#FF00FF` border of
that width on all four sides around the generation-source interior; otherwise it
copies `generation_source` byte-for-byte. It does **not** read `identity.png`,
does **not** upscale `identity.png`, and does **not** construct a four-copy strip from `identity.png`.

### Seed command — exact behavior

```bash
npm run strip:polish -- seed \
  --identity-declaration assets/first-room/dwarf/identity.json \
  --out <seed.png> [--json]
```

For walk and every 16×24 Motion class, omit `--motion-class` — the command
emits the uniform magenta-pad seed byte-for-byte.

This command:

1. Loads `assets/first-room/dwarf/identity.json`.
2. Verifies `identity_png` is a 16×24 Release Frame (sanity check only).
3. Writes `generation_source` → `<seed.png>` with the declared `seed_pad_px`
   transform (dwarf: 64 px `#FF00FF` border around the interior).
4. Emits JSON including `generation_source_sha256` (idle interior binding),
   `dimensions`, and `sha256` (padded seed digest — must match
   `edit_source_sha256` in provenance).

The output `<seed.png>` is already a four-Frame idle strip. Image-edit prompts
for walk describe editing **that canvas** — changing legs/boots while locked
regions stay fixed.

### Image-edit acquisition order

1. Run the seed command above to produce `<seed.png>`.
2. Submit `<seed.png>` to the provider as the **image-edit base** (edit source) —
   the image being edited. Do **not** generate a new image from the prompt alone.
   Also supply `identity.png` only if the provider workflow needs a separate
   visual reference — it is still **not** the generation canvas.
3. On `strip:polish init`, pass:
   - `--edit-source <seed.png>` (the idle provider Strip copy)
   - `--identity-reference assets/first-room/dwarf/identity.png` (16×24 anchor)
4. **Forbid** fresh text-to-image generation for walk.
5. Record the padded seed digest (`sha256` from `seed --json`) as
   `edit_source_sha256` in every image-edit Attempt's provenance. The digest must
   equal the `seed_pad_px` transform of `identity.json` → `generation_source`
   (not raw `generation_source.sha256`, which remains the idle interior binding).
   `init` and `/2` `check`/`finalize` reject any other digest with
   `edit_source_not_generation_source`.
6. Run Identity Lock only after provider recovery has produced logical Frames.
7. Generate **sequential immutable Attempts** until one passes provenance,
   automatic Identity Lock, coherence Gates, polish, and visual audit on the
   **unmodified** provider transport raster (plus only permitted post-ingest
   Polished Cell edits). A failed Identity Lock, baseline, `provider_clipping`,
   clipping, or pitch check requires another Attempt — never a script or hand paint of the
   provider PNG to force PASS.
8. Record every rejection and predecessor edge in the attempt ledger; never cap
   Attempt count with a fixed quota. When rejecting for Identity Lock, set
   `rejection_reason` to `identity_lock` and record `rejection_detail` from the
   machine-readable check report (schema `identity-lock-near-miss/0`).
9. Visual audit judges motion readability and exposed identity **outside** the
   locked regions, but must cite the automatic Identity Lock PASS in the check
   report. Inspect Release Frames beside the idle provider Strip and idle
   Release Frames; reject art that reads as an upscaled or tiled `identity.png`
   rather than an edit of idle-provider outline, shading, helmet lamp, and tool
   construction. Also reject hard flat Identity Lock stamps or seams where
   painted lock Cells meet softer generated shading in `provider/source.png` or
   Draft Frames. Identity Lock PASS alone does not satisfy the audit when the
   edit source was not the idle provider Strip or when lock Cells were painted
   into the provider raster after generation.

### Explicitly forbidden substitutes (walk)

| Forbidden | Why |
|-----------|-----|
| Fresh text-to-image from `identity.png` or a prompt alone | Loses provider-detail canvas; breaks `/2` image-edit evidence |
| Upscaling `identity.png` (16×24) into a generation canvas | Ingest-reduced Cells discard provider detail; not reversible; rejected as `edit_source_not_generation_source` |
| Tiling `identity.png` into a four-Frame “seed” | Same failure mode as upscaling; must use idle provider bytes |
| `prototype/strip-coherence/inbox/*` corpus Strips as the edit source | Motion evidence only — see `docs/first-room-art-direction.md` |
| Mechanical merge of corpus motion + identity upper body without a ledgered Attempt | Bypasses provenance and does not replace a clean image-edit Attempt |
| Reusing the pre-`/2` walk `provider/source.png` from issues #110/#111 | Those bundles were text-to-image acquisitions, not image-edit from the idle seed |
| Post-editing `provider/source.png` after generation to clear Gates (near-magenta wipe to exact `#FF00FF`, Frame shifts for baseline, painting/stamping Identity Lock or flat identity colors into pitch sample centers or locked regions) | Produces hard flat lock blocks and seams that confuse cell recovery; Identity Lock PASS no longer proves a clean idle-seed edit. `check_bundle` rejects magenta wipe with `provider_magenta_wipe` and reports edit-source lock continuity as `provider_post_edit` / `edit_source_continuity_fail`. Regenerate until lock/baseline pass without provider painting |

Identity Lock rules live in `assets/first-room/dwarf/identity-locks.json`.

## Dwarf-miner swing — Cell-authored acquisition lifecycle

`dwarf-miner` **swing** Strips are acquired by **Cell-authored acquisition** —
not image-edit, not fresh text-to-image, and not a newly generated pose
reference. See [ADR 0007](../../docs/adr/0007-swing-cell-author-acquisition.md).

### Base Frame and pose plan

All four target Frames start from canonical idle **Release Frame 0** — the
palette-exact post-ingest identity anchor at `assets/first-room/dwarf/identity.png`
(16×24). Swing embeds this anchor at column 1 in the 24×24 action canvas (ADR
0003, amended by issue #293). The canonical identity is validation evidence and is **never** an upscaled
generation canvas.

The checked-in pose plan (`motion-pose-plan/0`) declares intended Frame
operations and base mapping `[0, 0, 0, 0]` — every swing Frame derives from
idle Release Frame 0. Corpus motion samples and PR #169 are reference evidence
for pose readability only; generating new pose concepts is out of scope.

### Motion Author — exact behavior

```bash
npm run strip:author -- \
  --base-bundle <idle-finalized-bundle> \
  --pose-plan <pose-plan.json> \
  --identity-locks assets/first-room/dwarf/identity-locks.json \
  --palette assets/palettes/first-room.json \
  --frames-out <authored-frames-dir> \
  --ledger-out <cell-delta-ledger.json> [--json]
```

Motion Author applies the declarative pose plan under Identity Lock, palette, and
geometry constraints. It emits authored logical Frames and a replayable
`cell-delta-ledger/0` sidecar.

### Cell-author initialization order

1. Finalize the idle provider bundle so Release Frame 0 is available as the base.
2. Author the checked-in pose plan through `strip:author` to produce authored
   Frames and `cell-delta-ledger/0`.
3. On `strip:polish init-cell`, pass:
   - `<authored-frames-dir>` (logical frame PNGs from Motion Author)
   - `--base-bundle <idle-finalized-bundle>`
   - `--cell-delta-ledger <cell-delta-ledger.json>`
   - `--pose-plan <pose-plan.json>`
   - `--specification-id first-room/dwarf/swing`
   - `--motion-class swing`
   - `--polish-profile dwarf-miner`
   - `--identity-reference assets/first-room/dwarf/identity.png`
   - `--authoring-agent <agent-id>` and `--authoring-session-id <session-id>`
4. **Forbid** provider image-edit, fresh text-to-image, and newly generated pose
   references for swing.
5. No provider directory, no `animation-attempt-ledger/0`, and no provider
   Attempt are created. Provenance uses schema `cell-author-provenance/0`.
6. Run Identity Lock, coherence Gates, polish, and visual audit on the authored
   Frames through the same downstream `check`/`finalize` path as provider bundles.
7. Record authoring agent and session in `cell-author-provenance/0`.

### Explicitly forbidden substitutes (swing)

| Forbidden | Why |
|-----------|-----|
| Provider image-edit from idle seed | Swing uses Cell-authored acquisition (ADR 0007) |
| Fresh text-to-image from `identity.png` or a prompt alone | No provider raster; breaks cell-author provenance |
| Upscaling `identity.png` into a generation canvas | Identity anchor is validation evidence only |
| Newly generated pose reference images | Out of scope; corpus and PR #169 are reference evidence only |
| `prototype/strip-coherence/inbox/*` corpus Strips as edit source | Motion evidence only — not a substitute for Cell-authored Frames |
| Reusing the pre-`/2` swing `provider/source.png` from issues #110/#111 | Legacy text-to-image acquisition, not Cell-authored |

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

Each frame on an exact 16×24 logical pixel grid (swing: 24×24) rendered large — every logical
pixel is one clean flat square block. No anti-aliasing, blur, gradient, or
dithering.

<Motion-specific pose and baseline rules. Feet on bottom row for grounded classes.>

Between each frame: two full magenta logical Cells of empty gutter.

Keep the subject (including tools and pickaxe arc) inside a safe empty magenta
inset so the bounding box does not touch the provider canvas edges. This inset
is outside the logical Strip / gutters (gutter=2 unchanged).

Flat solid magenta #FF00FF background everywhere else. Master Palette
membership only — see assets/palettes/first-room.json. Neutral upper-left
highlights, warm shadows.

Frame order left→right: frame_0 … frame_3. Loop rules per Motion class.

Polish profile: <id>.

Do not add margins, labels, numbers, or extra rows. One row of four frames only.
```
