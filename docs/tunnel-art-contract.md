# Tunnel art contract

Normative authority for **game** tunnel scenery — backgrounds and tile sheets
that ship under `src/assets/tunnel/`. This contract is deliberately outside the
first-room Art Cohort: no Master Palette membership, no Gate score, no Identity
Lock, and no conformance to `assets/palettes/first-room.json`.

Provider transport raws are archived under `assets-raw/tunnel/`; the offline
build in `pipeline/tunnel_art.py` is the only path to committed runtime PNGs.

## Separation from first-room art

| Lineage | Palette | Gates | Pipeline |
| ------- | ------- | ----- | -------- |
| First-room cohort | `assets/palettes/first-room.json` | Strip / static gates | `pipeline/static_asset.py`, strip acquisition |
| Tunnel game art | Palette-free | None | `pipeline/tunnel_art.py` |

The two lineages share zero colors in practice and must not be mixed.

## Asset classes

### `background`

| Field | Value |
| ----- | ----- |
| **Asset class** | `background` |
| **Raw** | `assets-raw/tunnel/background/<key>.png` — any resolution |
| **Sidecar** | `assets-raw/tunnel/background/<key>.source.json`, schema `tunnel-art-source/0` |
| **Runtime destination** | `src/assets/tunnel/background/<key>.png` — exactly **480×112** |
| **Runtime shape** | Single RGBA band, binary alpha |
| **Visual vocabulary** | Painted tunnel scenery; no logical-pixel identity |
| **Geometry** | Center-crop to 480:112 aspect, then `NEAREST` resize to 480×112 |
| **Review context** | Scenery band for the tunnel playfield |
| **Validator** | `npm run assets:verify` |

**Exemption — may resize and is palette-free.** Scenery carries no logical-pixel
identity, so the provider's large painting is cropped and downscaled to the
runtime band. The sidecar `reduction` records `crop_box`, `crop_size`,
`resample: "NEAREST"`, and `runtime_size: [480, 112]`.

### `tile-sheet`

| Field | Value |
| ----- | ----- |
| **Asset class** | `tile-sheet` |
| **Raw** | `assets-raw/tunnel/tile-sheet/<key>.png` — magenta-keyed logical grid |
| **Sidecar** | `assets-raw/tunnel/tile-sheet/<key>.source.json`, schema `tunnel-art-source/0` |
| **Runtime destination** | `src/assets/tunnel/tiles/<key>/<item>.png` — each exactly **16×16** |
| **Runtime shape** | Per-item RGBA, binary alpha, one logical Cell per pixel |
| **Visual vocabulary** | Crisp pixel tiles; every logical Cell is identity |
| **Geometry** | Grid recovery at pitch 16 using `pipeline/recovery.py`; **no resize** |
| **Review context** | Tunnel floor/wall assembly tiles |
| **Validator** | `npm run assets:verify` |

**Exemption — may never be resized.** Every logical Cell is identity. A sheet
whose grid cannot be recovered at exactly 16×16 is regenerated, never rescaled
into shape. The sidecar `reduction` records `cell_w: 16`, `cell_h: 16`,
`columns`, `gutter`, `items` (ids in row-major order), and `resample: null`.

## Archived Raw Bundle schema

A complete bundle is `<key>.png` plus `<key>.source.json` under the class
directory. Schema `tunnel-art-source/0` carries at minimum:

| Field | Purpose |
| ----- | ------- |
| `provider` | Generator identity |
| `acquisition_tool` | Tool that produced the raw |
| `prompt` | Exact generation prompt string |
| `raw_sha256` | SHA-256 of the archived PNG |
| `asset_class` | `background` or `tile-sheet` |
| `runtime_destination` | Repo-relative runtime path or directory |
| `source_resolution` | `[width, height]` of the archived PNG |
| `reduction` | Class-specific crop/grid record (see above) |

The archived raw is immutable evidence. Everything below it is provider-neutral
and reproducible with no provider, model, GPU, or network.

## Discovery

`pipeline/tunnel_art.py` discovers bundles by `<key>.source.json` stem under each
class directory, in lexicographic order. A sidecar without a matching PNG, or a
PNG without a sidecar, is a **verification failure** naming the key and which
half is missing — never silently skipped. Adding an asset is create-only: drop
the pair in and discovery finds it without editing a key list.

## Build and verify

| Command | Action |
| ------- | ------ |
| `npm run assets:build` | Write every runtime PNG and `src/assets/tunnel/manifest.json` |
| `npm run assets:verify` | Rebuild in memory, compare against committed runtime PNGs |

Re-running the build over unchanged raws produces byte-identical output. Verify
emits a machine-readable report on both pass and fail paths — per key:
`outcome`, `asset_class`, `raw_sha256`, `runtime_sha256`, and the tripped reason
on failure.

## Runtime pack manifest

The build writes `src/assets/tunnel/manifest.json`, schema `tunnel-art-pack/0`,
hash-binding every runtime PNG to its archived raw. Per entry:

| Field | Purpose |
| ----- | ------- |
| `relative_path` | Repo-relative runtime PNG path |
| `sha256` | SHA-256 of the runtime PNG |
| `source_relative_path` | Repo-relative archived raw path |
| `source_sha256` | SHA-256 of the archived raw |

## Prompt shells

### Background

```text
Wide painted tunnel scenery band for a side-view mining game. Atmospheric depth,
rock strata, distant supports. No characters, UI, or text. Full-color painting
at high resolution; the build pipeline center-crops to 480:112 and downscales
with nearest-neighbor.
```

### Tile sheet

```text
TRUE chunky pixel art tile sheet ONLY. <N> tunnel tiles on a uniform 16×16 logical
grid.

Canvas: wide sheet — magenta #FF00FF background and gutters.
Cells: crisp flat colors, one color per logical pixel, no anti-aliasing.
Grid: uniform <COLUMNS>-column layout, <GUTTER>-pixel magenta gutters.
Items (row-major): <ITEM_ID_LIST>.
Each item is exactly 16×16 logical pixels. No outer labels or metadata.
```
