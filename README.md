# Underline

Mining game with a **strip-acquisition pipeline** (`pipeline/`): recover a wide
logical grid from one magenta-keyed provider render, slice into frames, and gate
temporal coherence deterministically.

The **standing corpus** in `prototype/strip-coherence/` (23 provider strips) is
permanent regression evidence. Gate budgets and separation claims are defined in
[`docs/strip-acquisition-contract.md`](docs/strip-acquisition-contract.md).

The original prototype question and its answer are recorded in
[`prototype/strip-coherence/NOTES.md`](prototype/strip-coherence/NOTES.md).

Agents: start at [AGENTS.md](AGENTS.md), then [CONTEXT.md](CONTEXT.md) and
the contract above.

## Gate-control production path

Operational Gate-control work uses the production modules under `pipeline/` and
the canonical npm commands below. The checked-in manifest holds **17 ACTIVE**
Promotions across all Separated Motion-class / Gate pairs; new candidates follow
the same score → acquire → review → verify loop.

```bash
# 1. Score a candidate Strip for isolation (measurement-only)
npm run gate-control:score -- <strip.png> --motion-class <class> --target-gate <gate>

# 2. Record Attempts, provenance, and Promotion candidates
npm run gate-control:acquire -- record --help   # see subcommands: record, promote, …

# 3. Gate review — per-Gate agent judgment in the Review band
npm run gate-control:review -- --help

# 4. Full-repository Promotion verification (manifest-backed)
npm run gate-control:verify -- run --promotion-id <promo-id>
```

AFK acceptance authority: [`docs/afk-acceptance-implementation-spec.md`](docs/afk-acceptance-implementation-spec.md).

## Final-polish production path

After a provider Strip passes production ingest, final polish turns accepted art
into releasable Frames. Edit the `polished/` PNG sequence (in Aseprite or by
direct Cell-coordinate changes), then validate and release.

```bash
npm run strip:polish -- init <provider.png> --provenance <source.json> \
  --motion-class <class> --out <bundle> \
  [--polish-profile <id>] [--identity-reference <identity.png>] \
  [--edit-source <seed-strip.png>] [--json]
npm run strip:polish -- brief <bundle> [--json]
npm run strip:polish -- check <bundle> [--json]
npm run strip:polish -- finalize <bundle> [--json]
```

New Polish Bundles use schema `final-polish-bundle/2`. `init` requires a validated
`animation-strip-provenance/0` sidecar (`--provenance`). The sidecar is copied to
`provider/source.source.json` and hash-bound in the manifest together with an
`animation-attempt-ledger/0` row in `provider/attempts.json`. Incomplete,
malformed, or hash-mismatched provenance rejects `init` without creating a bundle.
Provenance evidence cannot convert ingest `FAIL` or `REVIEW` into `PASS`.

For `dwarf-miner` with Motion class `walk` or `swing`, `init` additionally
requires two **different** inputs:

| Flag | File | Role |
|------|------|------|
| `--edit-source` | `assets/first-room/dwarf/idle/provider/source.png` (via seed below) | Image-edit **generation canvas** — four identical idle Frames on magenta |
| `--identity-reference` | `assets/first-room/dwarf/identity.png` | Post-ingest **Identity Lock anchor** only (16×24; never the edit canvas) |

Create the edit source from its hash-bound declaration — **not** from
`identity.png`:

```bash
npm run strip:polish -- seed \
  --identity-declaration assets/first-room/dwarf/identity.json \
  --out <seed.png>
```

`seed` copies `identity.json` → `generation_source`
(`idle/provider/source.png`) byte-for-byte. It does not read or upscale
`identity.png`. Submit `<seed.png>` to the provider as the image-edit base.

Those bytes are copied to `provider/edit-source.png` and
`reference/identity.png`, bound in the manifest, and must match
`generation_mode=image-edit` with the canonical identity hash in
`reference_image_sha256` and the idle-provider hash in `edit_source_sha256`.
Keep `provider/source.png` as the unmodified provider Attempt — do not paint
Identity Lock cells into the transport raster to clear Gates; regenerate until
lock and baseline pass. Full acquisition rules:
`prompts/production/animation-strip.md` § Dwarf-miner walk and swing.

Existing `final-polish-bundle/1` bundles (including the checked-in dwarf
`idle` bundle) remain readable under their legacy rules; see
[ADR 0004](docs/adr/0004-pre-attestation-acquisitions.md) for why `/1` is
retained. `check` and `finalize` revalidate every `/2` evidence hash and semantic
binding before polish or Release Frames.

Exit codes: `0` `PASS`, `1` `FAIL`, `2` invalid or structural error, `3`
`REVIEW`. `polished/` is the editor-facing PNG sequence; `release/` is written
only on automatic `PASS`.

For a prompt-independent miner audit, initialize with `--polish-profile miner`.
The profile is copied into the Polish Bundle and hash-bound by its manifest.
Before editing, a cold-start agent runs `brief` to read the fixed visual
questions, applicable Motion-class questions, editing rules, and audit workflow.
The verdicts are `PASS`, `EDIT`, and `UNCERTAIN`; an agent reports `UNCERTAIN`
instead of inventing intent. The profile guides visual judgment but does not
add deterministic Gates or replace `check`.

Production first-room assets use subject-specific profiles:

| Profile id | Intended production asset |
|------------|---------------------------|
| `dwarf-miner` | First-room player miner Strips (`idle`, `walk`, `swing`) |
| `lantern` | First-room hanging lantern `emissive` Strip |
| `miner` | Corpus motion and pipeline evidence Strips (unchanged) |

The generic `miner` profile remains for corpus Strips and existing `/0` bundles.
The validator does not recognize the semantic questions in any profile.

Aseprite is optional: an operator may edit Polished Frames in Aseprite or by
direct Cell-coordinate changes to the `polished/` PNG sequence. Automatic accent
recognition, Aseprite project generation or automation, original raster
generation, actual miner pixel edits, runtime playback, and game-asset
integration remain outside this wave. Visual examples such as a one-Cell black
eye, a one-Cell-high belt, a stable buckle color, or intentional outline
continuity illustrate the kind of edits an operator might make; the validator
does not recognize those semantics.

Final-polish authority: [`docs/strip-acquisition-contract.md`](docs/strip-acquisition-contract.md)
(Consumers → Final polish).

## Static-asset production path

Uniform static provider sheets (Rendering Tiles, Mineable Blocks, props, UI
glyphs) use a separate lifecycle from four-Frame animation Strips. Recovery and
pitch-slicing reuse vendored grid primitives; structural checks bind opaque RGB
to the embedded Master Palette. Static assets do not acquire a Motion class or
coherence Gates.

```bash
npm run asset:static -- init <provider.png> --provenance <source.json> --spec <spec.json> --out <bundle> [--json]
npm run asset:static -- check <bundle> [--json]
npm run asset:static -- finalize <bundle> [--json]
```

Exit codes: `0` `PASS`, `1` `FAIL`, `2` invalid or structural error. `polished/`
is the editor-facing PNG sequence; `release/` is written only on automatic
`PASS`. Human and JSON modes expose manifest, spec, and palette hashes, changed
Cells, violations, report path, and Release paths.

Static-sheet prompt authority: [`prompts/production/static-sheet.md`](prompts/production/static-sheet.md).
Static-asset authority: [`docs/strip-acquisition-contract.md`](docs/strip-acquisition-contract.md)
(Consumers → Static assets).

## Asset pack validation and preview

Animation and static Release bundles share one hash-bound `asset-pack/0` manifest
with first-room playback metadata and a preview-only Terraced Shaft scene
description. The validator checks PASS reports, Release hashes, Master Palette
membership, and approved timing/contact metadata; preview composes only bound
Release bytes into deterministic 320×180 and 4× nearest-neighbor PNGs.

```bash
npm run asset:pack -- check <manifest.json> [--json]
npm run asset:pack -- preview <manifest.json> --out <dir> [--json]
```

Exit codes: `0` valid pack, `2` invalid manifest/hash/report/palette/metadata error.
Preview scene metadata is review evidence — not a TypeScript runtime map format.

## Corpus analysis and proof tooling

Historical corpus scoring and budget derivation remain under `prototype:strip:*`.
These commands score the standing inbox, derive measured tables, and prove gate
separation — they are not the production operator path above.

```bash
npm run prototype:strip:corpus          # score inbox/ against manifest
npm run prototype:strip:adversarial     # per-class mutations must reject
npm run prototype:strip:alpha-budgets   # α=0.5 Separated budgets + fragile claims
npm run prototype:strip:derive-budgets  # historical pre-α Budget baseline
npm run strip:ingest -- <png> --motion-class <class>  # CLI ingest + gate
npm run prototype:strip                 # interactive TUI
```

Dependencies: Python 3, Pillow, NumPy. Grid-recovery primitives are vendored in
`pipeline/recovery.py` (from Nightglass `acquire.py`; re-vendor upstream changes).
