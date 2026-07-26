# Strip acquisition contract

Authority for Underline strip coherence gates. The prototype in
`prototype/strip-coherence/` implements this contract; Nightglass's frozen
animation contract does not govern here.

## Motion classes

| Class | Corpus sample | `grounded` | `loops` |
|-------|---------------|------------|---------|
| `idle` | 01-miner-idle | yes | yes |
| `blob_idle` | 02-slime-idle | yes | yes |
| `emissive` | 03-torch-flicker | yes | yes |
| `airborne` | 04-bat-flap | no | yes |
| `walk` | 05-miner-walk | yes | yes |
| `swing` | 06-miner-swing | yes | no |

Negative controls 07, 08, and 09 declare `idle`.

## Budget derivation (C5)

For each class and each applicable gate:

`budget = ceil_to_0.01(worst measured value across that class's good strips) + 0.02`

Measurements taken after pitch slicing (#2) and per-class anchor handling (#3), on
the inbox corpus PNGs (2026-07-25). `idle` also includes `miner-idle-strip.png`
(the adversarial baseline).

## Separation check (C6)

Every derived budget must be **strictly less than** the measured value of every
negative control on the same gate:

| Gate | 07-NEG-palette-drift | 08-NEG-identity-drift |
|------|----------------------|------------------------|
| silhouette | 0.057 | **0.602** |
| loop | 0.043 | 0.482 |
| palette drift | **0.279** | 0.218 |

## Class budgets

### `idle`

| Gate | Worst good | Derived | vs 07 | vs 08 | Status |
|------|------------|---------|-------|-------|--------|
| silhouette | 0.148 (miner-idle-strip) | **0.17** | 0.057 | 0.602 | separated |
| loop | 0.273 (miner-idle-strip) | **0.30** | 0.043 | 0.482 | separated |
| palette drift | 0.114 (miner-idle-strip) | **0.14** | 0.279 | 0.218 | separated |

Corpus sample 01-miner-idle: sil 0.095, loop 0.147, drift 0.073.

### `blob_idle`

| Gate | Worst good (02) | Derived | vs 07 | vs 08 | Status |
|------|-----------------|---------|-------|-------|--------|
| silhouette | 0.337 | **0.36** | 0.057 | 0.602 | separated |
| loop | 0.330 | **0.36** | 0.043 | 0.482 | separated |
| palette drift | 0.141 | **0.17** | 0.279 | 0.218 | separated |

### `emissive`

| Gate | Worst good (03) | Derived | vs 07 | vs 08 | Status |
|------|-----------------|---------|-------|-------|--------|
| silhouette | 0.160 | **0.18** | 0.057 | 0.602 | separated |
| loop | 0.130 | **0.16** | 0.043 | 0.482 | separated |
| palette drift | 0.145 | **0.17** | 0.279 | 0.218 | separated |

### `walk`

| Gate | Worst good (05) | Derived | vs 07 | vs 08 | Status |
|------|-----------------|---------|-------|-------|--------|
| silhouette | 0.398 | **0.42** | 0.057 | 0.602 | separated |
| loop | 0.143 | **0.17** | 0.043 | 0.482 | separated |
| palette drift | 0.117 | **0.14** | 0.279 | 0.218 | separated |

### `swing`

| Gate | Worst good (06) | Derived | vs 07 | vs 08 | Status |
|------|-----------------|---------|-------|-------|--------|
| silhouette | 0.565 | **0.59** | 0.057 | 0.602 | separated (0.012 margin) |
| loop | — | **None** | — | — | not applicable (`loops=false`) |
| palette drift | 0.179 | **0.20** | 0.279 | 0.218 | separated |

One-shot actions do not return to frame 0; measured loop closure 0.550 is the
action completing, not incoherence.

### `airborne` — UNSEPARATED (silhouette)

| Gate | Worst good (04) | Derived | vs 07 | vs 08 | Status |
|------|-----------------|---------|-------|-------|--------|
| silhouette | 0.644 | would be **0.67** | 0.057 | **0.602** | **UNSEPARATED** |
| loop | 0.653 | **0.68** | 0.043 | 0.482 | separated |
| palette drift | 0.145 | **0.17** | 0.279 | 0.218 | separated |

**UNSEPARATED:** good airborne silhouette (0.644) plus derivation headroom
(ceil + 0.02 → 0.67) exceeds identity-drift negative control 08 (0.602).
Silhouette alone cannot distinguish a good airborne strip from identity drift.
`max_silhouette` is `None`; the silhouette gate is excluded from pass.

## Implementation

`MOTION_CLASSES` in `prototype/strip-coherence/strip.py` is the runtime source.
`coherence_split(frames, motion_class=...)` reads budgets from it. Unknown classes
raise `ValueError`. `None` budgets exclude their gate from pass and report `None`.

Per-sample `grounded` was removed from `prompts/manifest.json`; groundedness is
derived from the motion class.
