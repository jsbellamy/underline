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

For min-pair cohort, worst-good is the **maximum** min_pair across good strips (highest
agreement threshold the class tolerates). Only derived for `loops=true`. Classes whose
frames legitimately never repeat closely (swing) omit the gate (`max_min_pair=None`).

**Good-strip membership** is a manifest judgment (`contract_expect: PASS` in
`prompts/manifest.json`) about the art — not whether the strip passes under the budgets
being calibrated. `derive_budgets.py` scores every manifest-good PNG regardless of gate
outcome; rows that fail the *current* runtime budgets are flagged but still count toward
worst-good.

Measurements taken after pitch slicing (#2) and per-class anchor handling (#3), on inbox
corpus PNGs. Re-derived 2026-07-26 after fixing the gate-pass exclusion bug and
including samples 13, 15, 16, 18 in their class cohorts. The `idle` cohort also includes
`miner-idle-strip.png` (the adversarial baseline).

Run `npm run prototype:strip:derive-budgets` to reproduce worst-good figures from the
current inbox.

### Monotonicity and separation expiry

The derivation rule is **monotonic in the good cohort only**: as manifest-good samples
accumulate, worst-good can only rise, so derived budgets can only **widen**. Negative
controls (07, 08, 09) are **fixed** — they do not move when good strips are added. C6
therefore cannot converge: every new good sample walks each class toward **UNSEPARATED**
on whichever gate that sample binds.

This pass made the asymmetry visible:

| Class | Gate | Prior budget | New budget | vs 07 (palette) | Headroom left |
|-------|------|--------------|------------|-----------------|---------------|
| `airborne` | palette drift | 0.17 | **0.23** | 0.279 | **0.049** |
| `blob_idle` | palette drift | 0.17 | **0.22** | 0.279 | **0.059** |

Nothing is wrong with the measured numbers; the estimator cannot tighten as evidence
grows. Fixes require either **per-class negative controls** that move with the claim
being tested, or an estimator that is not worst-observed — a percentile of the good
cohort, or fitting directly for separation margin.

**Do not add more good strips to strengthen separation claims.** Good strips can only
widen budgets toward the fixed controls. The highest-value next samples are negatives
that falsify the thinnest claims directly (see **Next corpus priority** below).

### Cohort size (manifest-good strips)

| Class | n | Good samples |
|-------|---|--------------|
| `idle` | 4 | 01, 10, 11, miner-idle-strip |
| `blob_idle` | 3 | 02, 12, 13 |
| `emissive` | 3 | 03, 14, 15 |
| `airborne` | 3 | 04, 16, 17 |
| `walk` | 3 | 05, 18, 19 |
| `swing` | 3 | 06, 20, 21 |

## Separation check (C6)

Every derived budget must be **strictly less than** the measured value of every
negative control on the same gate.

**Limitation:** the corpus has only three negative controls, all **miner-subject idle**
strips (07 palette, 08 identity, 09 recovery). Classes without an adjacent silhouette
gate (`airborne`) or with a thin margin to 08 (`swing`) are validated **indirectly** —
a miner identity-drift number on a different motion class. Per-class negatives are
required before those claims are evidenced.

| Gate | 07-NEG-palette-drift | 08-NEG-identity-drift |
|------|----------------------|------------------------|
| silhouette (adjacent max-pair) | 0.057 | **0.602** |
| min-pair cohort | 0.010 | **0.344** |
| loop | 0.043 | 0.482 |
| palette drift | **0.279** | 0.218 |

### Separation headroom (fragile claims)

| Class | Binding gate | Budget | Control | Margin | Break condition |
|-------|--------------|--------|---------|--------|-----------------|
| `swing` | silhouette | **0.59** | 08 @ 0.602 | **0.012** | Fourth good swing with adjacent sil **> 0.582** makes budget ≥ 0.61 → UNSEPARATED |
| `airborne` | palette drift | **0.23** | 07 @ 0.279 | 0.049 | Another high-drift good flap widens toward 07 |
| `airborne` | min-pair cohort | **0.29** | 08 @ 0.344 | 0.054 | **Unmeasured** for four different flying creatures — 08 is miner idle |

`swing` n=3 adjacent silhouette: 0.565 / 0.492 / 0.359 (06 still worst-good; unchanged
through both re-derivations). Next class likely to fall over after `airborne` silhouette
(which is already UNSEPARATED).

## Class budgets

Widened from n=3 manifest-good cohorts where the prior gate-pass filter had excluded
legitimate art (13-ooze-idle, 15-campfire-flicker, 16-moth-flap, 18-guard-walk). Every
derived budget still separates from both negative controls on its gate.

### `idle`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette (adjacent) | 0.148 | miner-idle-strip | **0.17** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.042 | 01-miner-idle | **0.07** | 0.010 | 0.344 | separated |
| loop | 0.273 | miner-idle-strip | **0.30** | 0.043 | 0.482 | separated |
| palette drift | 0.115 | 11-dwarf-idle | **0.14** | 0.279 | 0.218 | separated |

### `blob_idle`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.337 | 02-slime-idle | **0.36** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.103 | 13-ooze-idle | **0.13** | 0.010 | 0.344 | separated |
| loop | 0.330 | 02-slime-idle | **0.36** | 0.043 | 0.482 | separated |
| palette drift | 0.196 | 13-ooze-idle | **0.22** | 0.279 | 0.218 | separated |

13-ooze-idle widened drift and min-pair. `ceil+0.02` on min_pair is a coarse estimator
for squash idles whose frames legitimately never repeat closely — same reason swing omits
the gate entirely.

### `emissive`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.182 | 15-campfire-flicker | **0.21** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.099 | 03-torch-flicker | **0.12** | 0.010 | 0.344 | separated |
| loop | 0.132 | 15-campfire-flicker | **0.16** | 0.043 | 0.482 | separated |
| palette drift | 0.145 | 03-torch-flicker | **0.17** | 0.279 | 0.218 | separated |

15-campfire-flicker widened silhouette by 0.03 (0.002 over the prior 0.18 budget).

### `walk`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.398 | 05-miner-walk | **0.42** | 0.057 | 0.602 | separated |
| min-pair cohort | 0.143 | 05-miner-walk | **0.17** | 0.010 | 0.344 | separated |
| loop | 0.143 | 05-miner-walk | **0.17** | 0.043 | 0.482 | separated |
| palette drift | 0.164 | 18-guard-walk | **0.19** | 0.279 | 0.218 | separated |

18-guard-walk widened drift; 05 remains binding on silhouette and loop.

### `swing`

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette | 0.565 | 06-miner-swing | **0.59** | 0.057 | 0.602 | separated (0.012 margin) |
| min-pair cohort | — | — | **None** | — | — | not applicable (`loops=false`) |
| loop | — | — | **None** | — | — | not applicable (`loops=false`) |
| palette drift | 0.179 | 06-miner-swing | **0.20** | 0.279 | 0.218 | separated |

Unchanged. The 0.012 margin to 08 on silhouette is **not** a one-sample artifact — and
08 is not a swing strip. A per-class negative (`23-NEG-swing-identity`) is scaffolded
to test this claim directly.

### `airborne` — cohort identity via min-pair; per-frame tamper ungated

| Gate | Worst good | Sample | Derived | vs 07 | vs 08 | Status |
|------|------------|--------|---------|-------|-------|--------|
| silhouette (adjacent) | 0.644 | 04-bat-flap | **None** | 0.057 | 0.602 | excluded — UNSEPARATED |
| min-pair cohort | 0.269 | 17-wisp-float | **0.29** | 0.010 | 0.344 | separated |
| loop | 0.653 | 04-bat-flap | **0.68** | 0.043 | 0.482 | separated |
| palette drift | 0.205 | 16-moth-flap | **0.23** | 0.279 | 0.218 | separated |

16-moth-flap widened drift. Adjacent silhouette remains excluded (`max_silhouette` is
`None`) — a legitimate flap transition is large and max-pair cannot separate good
airborne from identity drift.

`loops=false` classes (swing) omit the min-pair gate — one-shot actions legitimately
never repeat a pose (06 min_pair 0.437 > 08's 0.344).

## Adversarial suite and known gaps

`adversarial.py` mutates each class baseline and checks `MUST_FAIL` mutations against
live gates. Mutations listed in `KNOWN_GAPS` pass today but have no gate — the suite
prints **`GAP`**, never **`ok`**, with the documented reason. Exit code is 0 only when
there are no mismatches (a `MUST_FAIL` mutation that passes is a failure).

| Class | Mutation | Status | Reason |
|-------|----------|--------|--------|
| `airborne` | hop, mirror, slide | **GAP** | No per-frame cohort gate; min_pair blind to single-frame tamper |
| `blob_idle` | mirror (`wrong_pose`) | **GAP** | Symmetric blob; mirror is a silhouette no-op |

**Airborne admission:** live gates are palette drift, loop closure, and min-pair cohort
only. Identity drift across all four frames is caught (08 fails min_pair). Single-frame
hop, mirror, or slide is **not** caught — three clean frames still pair up and min_pair
is unchanged (04-bat-flap baseline min_pair 0.044; tampered frame 2 same). Finding a
per-frame cohort signal that survives single-frame tampering when adjacent silhouette is
disabled remains an open problem; do not assert coverage by dropping `MUST_FAIL` entries.

## Min-pair cohort gate

`coherence_split` reports `silhouette_pairwise` and gates `min_pair_cohort_pass`
when `loops=true` and `max_min_pair` is set. Pass when `min_pair <= max_min_pair`.

| Role | Gate | Catches | Blind to |
|------|------|---------|----------|
| Step motion | `silhouette_budget` (adjacent max-pair) | hop, slide, oversized transitions | identity drift on airborne |
| Cohort identity | `min_pair_cohort_pass` | four-character drift (08) | single-frame tamper |
| Recolour | `palette_drift_pass` | palette swap | — |

Single-frame mirror/hop/slide leaves min_pair unchanged — adjacent silhouette (or
baseline) catches those on grounded classes. See **Adversarial suite and known gaps**
for airborne and symmetric blob_idle holes.

| Sample | class | min_pair | `min_pair_cohort_pass` |
|--------|-------|----------|------------------------|
| 04-bat-flap | airborne | 0.044 | pass (≤0.29) |
| 17-wisp-float | airborne | 0.269 | pass |
| 08-NEG-identity-drift | airborne | 0.344 | **fail** |
| 08-NEG-identity-drift | idle | 0.344 | fail (redundant with silhouette) |

08 is a **miner idle** identity-drift control. Whether four different **flying**
creatures under a shared palette score above `max_min_pair` 0.29 is unmeasured —
`22-NEG-airborne-identity` is scaffolded to test that claim.

## Next corpus priority

Generate **per-class negative controls** before more good strips. Same generation cost;
unlike good strips they can **falsify** a separation claim or raise the control ceiling
instead of only widening budgets.

| ID | `motion_class` | Intended failure | What it tests |
|----|----------------|------------------|---------------|
| `22-NEG-airborne-identity` | `airborne` | `min_pair_cohort_pass` | Four different flying creatures, tight shared palette — airborne cohort gate vs subject-matched incoherence |
| `23-NEG-swing-identity` | `swing` | `silhouette_budget` | Four different grounded fighters at swing poses, shared palette — thinnest silhouette margin (0.59 vs 08's 0.602) |

Prompts are in `prototype/strip-coherence/prompts/`. Drop PNGs into `inbox/` and score
with `npm run prototype:strip:corpus`. A per-class negative that scores **below** the
class budget falsifies the separation claim outright; one that scores above becomes the
authoritative control for that gate.

## Implementation

`MOTION_CLASSES` in `prototype/strip-coherence/strip.py` is the runtime source.
`coherence_split(frames, motion_class=...)` reads budgets from it. Unknown classes
raise `ValueError`. `None` budgets exclude their gate from pass and report `None`.

Per-sample `grounded` was removed from `prompts/manifest.json`; groundedness is
derived from the motion class.
