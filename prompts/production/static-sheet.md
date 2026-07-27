# Production prompt kit — static sheet

Normative authority for provider-rendered static sprite sheets in the first-room
**Art Cohort** — terrain **Rendering Tiles**, **Mineable Block** textures,
props, and UI glyphs that are not animation Strips.

Visual identity: `docs/first-room-art-direction.md`. Palette:
`assets/palettes/first-room.json`.

## Transport raster vs releasable art

| Stage | What it is |
|-------|------------|
| **Provider transport raster** | The sheet PNG from an image provider — magenta-keyed, possibly upscaled logical Cells, with provenance sidecar. Input to recovery and slicing only. |
| **Releasable art** | Exported logical-resolution RGBA items — crisp Cells, Master Palette opaque RGB, binary alpha, no gutters or labels. |

Never ship a provider transport raster. Gutter columns and magenta margins exist
only to keep provider items separated during recovery.

## Sheet geometry

| Property | Requirement |
|----------|-------------|
| **Cells** | Crisp logical Cells — one flat color per Cell, no anti-aliasing or subpixel blur |
| **Item grid** | Declare a uniform grid: every item the same width and height in logical Cells |
| **Gutter** | Two magenta logical Cells between adjacent items horizontally and vertically |
| **Background** | Flat magenta `#FF00FF` outside items and gutters |
| **Margins** | None — no outer border, labels, numbers, or metadata rendered into the sheet |
| **Alignment** | Items snap to the declared grid; do not float items on an irregular layout |

Declare item size explicitly in the prompt (for example 16×16 Rendering Tile,
32×32 Mineable Block, or 16×24 static Frame).

## Master Palette membership

Every opaque RGB Cell must be a member of `assets/palettes/first-room.json`
(id `first-room`). `#FF00FF` is provider transport key only — not a palette
member and not permitted in releasable exports.

## Mineable Block vs Rendering Tile

Prompts must name the asset kind correctly:

- **Rendering Tile** — 16×16 world assembly unit (edges, backgrounds).
- **Mineable Block** — 32×32 atomic mining target (2×2 Rendering Tiles).

Do not call a Mineable Block a tile.

## Provenance sidecar expectations

Each provider sheet ships beside a JSON sidecar (for example
`<basename>.source.json`) containing at minimum:

| Field | Purpose |
|-------|---------|
| `prompt` | Exact generation prompt text |
| `provider` | Generator identity and model |
| `attempt_ids` | Provider attempt identifiers when available |
| `master_palette_id` | `first-room` for this cohort |
| `item_geometry` | Declared item width, height, gutter, and grid layout |
| `asset_kind` | `rendering-tile`, `mineable-block`, `prop`, etc. |
| `raw_sha256` | Hash of the bundled transport PNG |
| `created_at` | ISO-8601 timestamp |

Incomplete provenance blocks downstream Promotion and polish workflows. Match
the provenance discipline in `docs/afk-acceptance-implementation-spec.md`.

## Recovery

Grid recovery uses vendored primitives in `pipeline/recovery.py`. Recovery
reports (text) precede opening transport rasters — read the report, not the
render.

## Prompt template skeleton

```text
TRUE chunky pixel art static sheet ONLY. <N> <ASSET_KIND> items on a uniform
grid.

Canvas: wide sheet — aspect ratio fits the declared grid.

Each item on an exact <W>×<H> logical pixel grid rendered large — every logical
pixel is one clean flat square block. No anti-aliasing, blur, gradient, or
dithering.

<Per-item art direction aligned with docs/first-room-art-direction.md.>

Between each item: two full magenta logical Cells of gutter horizontally and
vertically.

Flat solid magenta #FF00FF background everywhere else. Master Palette
membership only — assets/palettes/first-room.json.

Grid: <rows>×<cols> of <W>×<H> items, uniform spacing.

Do not add margins, labels, numbers, or metadata text. Items only.
```
