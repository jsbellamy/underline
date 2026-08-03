# ADR 0011: Audio without gates

## Status

Accepted (2026-08-03)

## Context

Issue #346 ships the first game audio: a pick swing and a block break. Raster art
under `assets/` is governed by `docs/strip-acquisition-contract.md` — Gates,
Budgets, and acceptance profiles. Audio has no equivalent pipeline today, and the
slice that introduces clips must not invent one ad hoc. Placing binaries under
`assets/` would also widen CI: `scripts/select_changed_tests.py` treats `assets/`
as whole-suite, and `scripts/ci_surfaces.py` excludes it from game-surface
short-circuiting.

## Decision

- **Content:** two CC0 clips under `src/audio/` (`swing`, `break`) with a
  hash-bound `audio-pack/0` manifest and a typed reader in `src/data/`.
- **Bundling:** `src/ui/audio-clips.ts` resolves manifest `relative_path` values
  through `import.meta.glob`, mirroring dwarf frame URLs.
- **CSP:** Tauri `media-src 'self' data:` so Vite-inlined or bundled media can
  load in the packaged app.
- **No gate:** audio quality and fit are a human art call; C2 duration/sample
  bounds and manifest hashes are the only mechanical checks. Playback is a later
  slice.

## Consequences

### Positive

- `src/` placement keeps `test:changed` and pipeline CI scoped; no change to
  `ci_surfaces.py` or `select_changed_tests.py`.
- Hash-bound manifest gives the same provenance discipline as sprite packs
  without pretending a Gate exists.
- A future playback slice can import URLs without re-sourcing clips.

### Negative

- No automated rejection of a clip that sounds wrong but meets C2 bounds.
- `src/audio/` mixes content with code tree; a later ADR may split if the pack
  grows.

## Rejected alternatives

**`assets/audio/` with whole-suite CI.** Rejected: every clip tweak would run the
full pytest suite and pipeline jobs for bytes no Python module reads.

**Invent a lightweight audio Gate.** Rejected: out of scope for #346; would
duplicate strip machinery without a corpus or adversarial contract.
