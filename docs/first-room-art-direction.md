# First-room art direction

Authoritative visual contract for Underline's first playable room. Every new
first-room asset, prompt, and issue must use the glossary terms in
`CONTEXT.md` — especially **Mineable Block** (never "tile" for a mining
target) and **Rendering Tile** for 16×16 world assembly.

Authority for motion-class geometry and ingest gates remains
`docs/strip-acquisition-contract.md`. This document owns game-art identity,
scale, lighting, and the approved room composition.

## Style and camera

- Warm, rugged storybook pixel art.
- Side-on orthographic camera — no perspective foreshortening on terrain or
  characters.
- 320×180 logical viewport displayed at integer scale only (no fractional
  upscaling).

## Player miner

- Animation **Frames** are 16×24 logical Cells (swing uses a 24×24 action
  canvas), authored facing right and mirrored at runtime for left-facing poses.
- Short, broad, heavily bearded dwarf miner.
- Oversized blue lamp helmet, green work clothes, thick gloves, sturdy boots,
  belt and buckle, and a weighty pickaxe.
- Neutral upper-left local highlights and warm shadows on the character —
  consistent with terrain lighting below.

## World scale

- **Rendering Tiles** are 16×16 logical Cells for cave edges and backgrounds.
- **Mineable Blocks** are atomic 32×32 mining targets — each occupies a 2×2
  area of Rendering Tiles (see `docs/adr/0001-two-scale-mining-grid.md`).

## Lighting

- Neutral upper-left local highlights and warm shadows across terrain and
  props.
- Broad lantern glow and ore emission are **not** baked into terrain textures;
  runtime lighting owns those effects.

## Ore identity

- Cyan crystal ore is distinguished by angular cluster geometry and value
  pattern as well as hue — not hue alone.

## Autotile kit

- 16-case cardinal **Autotile masks** with bit values north=1, east=2,
  south=4, west=8.
- Three interior texture variants within the kit.
- Masks select Mineable Block edge treatments, not Rendering Tile corners.

## Approved room composition

**Variant B — Terraced Shaft** is the approved first-room composition:

- Readable walking terraces for traversal.
- Vertical mining space below the walk line.
- Enough exposed Mineable Block edges to exercise the full Autotile kit.

The throwaway browser prototype validated this layout as a composition decision;
its placeholder pixels and prototype code are evidence for the layout choice, not
production art inputs.

## Master Palette

The first-room **Master Palette** is `assets/palettes/first-room.json`
(schema `master-palette/0`, id `first-room`). Every opaque RGB value in a
first-room **Art Cohort** asset must be a member of that palette.

Magenta `#FF00FF` is provider transport key only — it is not a palette member
and must not appear in releasable art.

## Animation timing

Frame durations are milliseconds per Frame slot in order:

| Motion class | Loop | Durations (ms) | Notes |
|--------------|------|----------------|-------|
| `idle` | yes | `[200, 200, 200, 200]` | Subtle breathing |
| `walk` | yes | `[125, 125, 125, 125]` | Four-step cycle |
| `swing` | no | `[150, 80, 60, 180]` | Mining contact at entry to Frame 3; return to idle after final hold |
| `emissive` (lantern) | yes | `[160, 160, 160, 160]` | Helmet lamp flicker |

Swing is a one-shot: Frame 3 is the strike pose; the game returns to idle after
the final hold rather than looping swing→swing.

## Dwarf walk and swing — distinct acquisition paths

Production dwarf **walk** and **swing** use **different authoritative workflows**
(ADR 0007). Walk remains identity-locked provider image-edit; swing uses
Cell-authored acquisition from canonical idle Release Frame 0.

### Walk — image-edit from idle provider

Production dwarf **walk** is acquired by **image-edit** from the idle provider
Strip, not by redrawing from `identity.png`. Two files serve different roles:

| File | Role |
|------|------|
| `assets/first-room/dwarf/idle/provider/source.png` | Edit source — provider generation canvas (four identical idle Frames) |
| `assets/first-room/dwarf/identity.png` | Post-ingest identity anchor — Identity Lock evidence only (16×24) |

The identity anchor is palette-exact against the Master Palette (ADR 0002). The
edit source is **not**, and is not meant to be: it is a provider generation
canvas, never a Release asset, so palette verification does not inspect it.

Copy the edit source with `strip:polish seed` against
`assets/first-room/dwarf/identity.json` (applies `seed_pad_px: 64` magenta
border). Provenance `edit_source_sha256` must equal the padded seed digest from
`seed --json` (the `seed_pad_px` transform of `identity.json` →
`generation_source`), not raw `generation_source.sha256`; a tiled or upscaled
`identity.png` seed is rejected. Keep `provider/source.png` as the unmodified
provider Attempt — do not paint Identity Lock cells, wipe magenta, or shift
Frames in the transport raster to clear Gates; regenerate until lock and
baseline pass cleanly. Keep walk subjects inside a safe empty magenta inset away
from provider canvas edges — `provider_clipping` requires regeneration, not
provider painting. Visual audit for walk must compare Release Frames to the idle
provider Strip and idle Release Frames — Identity Lock PASS alone does not prove
the edit came from idle or that the provider raster was unpainted. Full rules:
`prompts/production/animation-strip.md` § Dwarf-miner walk.

### Swing — Cell-authored acquisition

Production dwarf **swing** is acquired by **Cell-authored acquisition** — not
image-edit, not fresh text-to-image, and not a newly generated pose reference.

1. Start all four target Frames from canonical idle **Release Frame 0** (the
   palette-exact post-ingest identity anchor at `identity.png`).
2. Run the checked-in pose plan through `strip:author` (Motion Author) to emit
   authored Frames and a `cell-delta-ledger/0` sidecar.
3. Initialize with `strip:polish init-cell` — no provider directory, no Attempt
   ledger, no provider transport raster.
4. Bind `--identity-reference assets/first-room/dwarf/identity.png` for Identity
   Lock validation only; it is never a generation canvas.

Swing uses base mapping `[0, 0, 0, 0]` from idle Release Frame 0. Existing
corpus motion samples and PR #169 are reference evidence for pose readability;
generating new pose concepts is out of scope. Full rules:
`prompts/production/animation-strip.md` § Dwarf-miner swing.

## Corpus miner Strips — motion evidence, not identity

The provisional corpus miner Strips in `prototype/strip-coherence/prompts/`
(`01-miner-idle`, `05-miner-walk`, `06-miner-swing`, `14-lantern-flicker`) are
**motion and pipeline evidence** — they exercise ingest gates, budgets, and
Polish profiles. They are **not** the production art identity for the first-room
miner and are **not** valid edit sources for walk or swing acquisition.

Production miner art must match this document's miner description, Master
Palette membership, and the production prompt kits under `prompts/production/`.

## Production prompt authority

| Kit | Path |
|-----|------|
| Animated Strip | `prompts/production/animation-strip.md` |
| Static sheet | `prompts/production/static-sheet.md` |
