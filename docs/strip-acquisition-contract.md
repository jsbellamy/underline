# Strip acquisition contract

Authority for Underline strip coherence gates. The prototype in
`prototype/strip-coherence/` implements this contract; Nightglass's frozen
animation contract does not govern here.

## Motion classes

| Class | Corpus sample | `grounded` | `loops` | `facing` |
|-------|---------------|------------|---------|----------|
| `idle` | 01-miner-idle | yes | yes | free |
| `blob_idle` | 02-slime-idle | yes | yes | free |
| `emissive` | 03-torch-flicker | yes | yes | free |
| `airborne` | 04-bat-flap | no | yes | free |
| `walk` | 05-miner-walk | yes | yes | fixed |
| `swing` | 06-miner-swing | yes | no | fixed |

Negative controls 07, 08, and 09 declare `idle`.

### Facing (decision 2026-07-26)

`facing` is a class property on `ClassBudget`, not a gate today.

| `facing` | Classes | Meaning |
|----------|---------|---------|
| **fixed** | `walk`, `swing` | Subject faces travel/action direction; a mirrored frame is a defect. Silhouette already catches mirror on both today — recorded so a future class that disables silhouette inherits the rule. |
| **free** | `idle`, `blob_idle`, `emissive`, `airborne` | No declared facing; a mirrored frame is **not** a defect. Mirror is out of scope, not a `KNOWN_GAP`. |

**Reversible commitment:** if Underline later requires bats to face flight direction,
`airborne` moves to `fixed` and mirror becomes a hole needing a chirality gate.

## Budget derivation (C5)

### Runtime estimator (historical pre-α baseline)

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

### AFK acceptance Budgets (α = 0.5)

Separated Motion-class/Gate pairs use the Gap allocation factor decided in
[Choose alpha for separated Gate controls](https://github.com/jsbellamy/underline/issues/28):

`Budget = ceil₄(G + 0.5 × (C − G))`

where `G` is the four-place upward-quantized worst Manifest-good metric and `C` is the
quantized isolated Gate-control metric. Unseparated pairs keep the runtime Budget above
and Review open with no hard-fail boundary. Full tables, deltas, and headroom live in
[`docs/alpha-budget-tables.md`](alpha-budget-tables.md); reproduce with
`npm run prototype:strip:alpha-budgets`. Runtime `MOTION_CLASSES` projects these
Budgets from `gate-controls/acceptance-profiles.json` (landed in
[#62](https://github.com/jsbellamy/underline/issues/62)); the pre-α tables in this
section remain historical evidence for `npm run prototype:strip:derive-budgets`.

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

**Limitation:** 07/08/09 are **miner-subject idle** strips. Per-class negatives `22` and
`23` now evidence the airborne min-pair and swing silhouette claims directly (see
**Per-class negative controls**).

| Gate | 07-NEG-palette | 08-NEG-identity (idle) | 22-NEG-airborne-identity | 23-NEG-swing-identity |
|------|----------------|------------------------|----------------------------|-------------------------|
| silhouette (adjacent max-pair) | 0.057 | **0.602** | 0.652 | **0.624** |
| min-pair cohort | 0.010 | 0.344 | **0.383** | 0.321 |
| loop | 0.043 | 0.482 | 0.663 | 0.624 |
| palette drift | **0.279** | 0.218 | 0.636 | 0.244 |

### Separation headroom (fragile claims)

**AFK acceptance (α = 0.5 Gate controls)** — thinnest Separated good-headroom /
Review-width margins. Reproduce with `npm run prototype:strip:alpha-budgets`; full
table in [`docs/alpha-budget-tables.md`](alpha-budget-tables.md).

| Pair | Budget | Gate control C | Good headroom | Review width |
|------|--------|----------------|---------------|--------------|
| `walk/silhouette_budget` | **0.4136** | 0.4294 | **0.0159** | **0.0158** |
| `blob_idle/min_pair_cohort_pass` | **0.1199** | 0.1371 | **0.0173** | **0.0172** |
| `swing/silhouette_budget` | **0.5860** | 0.6067 | **0.0208** | **0.0207** |

**Runtime corpus negatives (α runtime)** — subject-matched controls vs current Budgets:

| Class | Binding gate | Budget | Control | Margin | Notes |
|-------|--------------|--------|---------|--------|-------|
| `swing` | silhouette | **0.59** | 23 @ **0.624** | **0.034** | Subject-matched negative vs runtime Budget |
| `airborne` | min-pair cohort | **0.29** | 22 @ **0.383** | **0.093** | Subject-matched negative vs runtime Budget |
| `airborne` | palette drift | **0.23** | 07 @ 0.279 | 0.049 | 22 also tripped drift (0.636) |

`swing` n=3 adjacent silhouette: 0.565 / 0.492 / 0.359 (06 still worst-good).

## Class budgets

### Runtime budgets (α = 0.5 — `MOTION_CLASSES`)

Projected from `gate-controls/acceptance-profiles.json`. Separated pairs use the α
Budget; Unseparated pairs keep the pre-α runtime value; Inapplicable gates are
`None`. Reproduce with `npm run prototype:strip:alpha-budgets`.

| Class | silhouette | loop | palette drift | min-pair |
|-------|------------|------|---------------|----------|
| `idle` | 0.2239 | 0.30 | 0.1974 | 0.07 |
| `blob_idle` | 0.3951 | 0.3906 | 0.2377 | 0.1199 |
| `emissive` | 0.3226 | 0.1694 | 0.2123 | 0.12 |
| `walk` | 0.4136 | 0.2112 | 0.2217 | 0.17 |
| `swing` | 0.5860 | — | 0.2294 | — |
| `airborne` | — | 0.7032 | 0.2423 | 0.3013 |

### Historical pre-α derivation (evidence only)

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
| loop | 0.330 | 02-slime-idle | **0.35** | 0.043 | 0.482 | separated |
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

## Adversarial suite and strip gaps

`adversarial.py` mutates each class baseline and checks `MUST_FAIL` mutations against
live gates. Every required mutation must yield a non-`PASS` production outcome under the
locked Acceptance profiles — class-specific mutation strength is tuned in the runner,
not by widening Budgets. **`STRIP_GAPS`** documents per-strip holes (not per-class); the
suite prints **`GAP`**, never **`ok`**. **`KNOWN_GAPS`** is empty after α-budget
activation; only the two airborne displacement cases below remain documented gaps.
**`displacement_inapplicable`** strips print an **`N/A`** line — never silent `None`.

| Strip | Mutation | Status | Reason |
|-------|----------|--------|--------|
| `04-bat-flap` | hop, slide | **GAP** | `displacement_pass: None` — degenerate alignment minimum (margin 0.0000 at 3→0) |

On **`16-moth-flap`** and **`17-wisp-float`**, hop and slide trip **`displacement_pass`**
(live gate). Mirror (`wrong_pose`) is **out of scope** on `facing: free` classes. On
`facing: fixed` classes (`walk`, `swing`), silhouette already rejects mirror.

## Antisymmetric displacement gate (`displacement_pass`)

A translated frame shows up as an equal-and-opposite pair of best-alignment shifts.
Legitimate motion does not return (swing's `(+3,+1)` never comes back), so antisymmetry
separates "frame was moved" from "subject moved."

**Rule:** frame `k` is tampered when in-shift and out-shift are approximately opposite
(residual `|in+out| ≤ 1` Chebyshev) with `|in| ≥ 2`. `loops=True` scans all frames
including wrap-around. **Airborne only** — grounded classes already catch hop/slide via
`baseline_row_stable` and `silhouette_budget`.

### Applicability precondition (`displacement_pass: None`)

Before gating, compute **alignment sharpness** per transition: margin between best and
next-best **distinct** shift at `DISPLACEMENT_PROBE_SPAN`. If the strip's **minimum
margin** falls below `min_alignment_sharpness`, report `displacement_pass: None` and
exclude from pass — same pattern as `max_silhouette: None` on airborne.

| Strip | min margin | worst pair | `displacement_pass` on clean |
|-------|------------|------------|------------------------------|
| 04-bat-flap | **0.0000** (tie) | 3→0 | **None** — undecidable |
| 16-moth-flap | 0.0164 | 1→2 | pass (headroom **0.0014** — thinnest applicable) |
| 17-wisp-float | 0.0171 | 3→0 | pass (headroom 0.0021) |
| 22-NEG-airborne-identity | **0.0000** | 0→1 | **None** — undecidable (negative control) |

**Inapplicable counts — two scopes (not a contradiction):**

| Tool | Count | Scope |
|------|-------|-------|
| `corpus.py` | **2** | Every manifest PNG scored against its `motion_class` gate (`04-bat-flap`, `22-NEG-airborne-identity`) |
| `adversarial.py` | **1** | Class mutation baselines only (`04-bat-flap` for airborne; negatives not in the battery) |

Both must surface inapplicable strips explicitly — never silent `None`.

**Threshold derivation (n=3 airborne good, 2026-07-26):**

`min_alignment_sharpness = floor(min applicable margin) − 0.001 = 0.0164 − 0.001 = **0.015**`

Sits in the empty interval between 04's 0.0000 and 16's 0.0164. Inherits the same
monotonic-widening risk as other budgets — more airborne strips can only push the floor
toward degeneracy.

**04's holdout is well-posedness, not tuning:** the 3→0 transition has two shifts tied
at 0.597 — the reported shift is whichever candidate the scan visited first. Antisymmetry
cannot hold reliably when there is no stable shift to be antisymmetric about.

**Two spans — do not conflate:**

| Constant | Value | Purpose |
|----------|-------|---------|
| `REGISTRATION_SPAN` | ±1 | Silhouette budget — minimise shift to absorb jitter |
| `DISPLACEMENT_PROBE_SPAN` | ±4 | Displacement evidence — read shift as signal |

Run `npm run prototype:strip:displacement` for tamper grids;
`npm run prototype:strip:sharpness` for corpus-wide sharpness.

## Alignment sharpness (diagnostic)

Margins are in **silhouette-fraction units** — the objective being minimised is the
silhouette fraction at each candidate shift. A `reg_min` of 0.0040 means switching to
the runner-up shift changes the silhouette value by 0.0040. The shift may be ambiguous;
the number is not. Ambiguity is self-limiting: transitions most likely to flip are those
where flipping changes the value least.

**Two gate kinds:**

| Kind | Examples | Degeneracy effect |
|------|----------|-------------------|
| **Value-valued** | silhouette, drift, min-pair | Error bounded at the margin — small, quantified |
| **Vector-valued** | displacement | Signal destroyed — `displacement_pass: None` |

Do not read low `reg_min` as "silhouette numbers are suspect." Separation claims hold when
runner-up uncertainty is an order of magnitude below the margin — e.g. swing budget
**0.59** vs `23-NEG-swing-identity` at **0.624** (margin **0.034**), with `23`'s
`reg_min` **0.0040**.

**Displacement undecidable** (`disp_min < 0.015` on airborne):

| Strip | disp_min | note |
|-------|----------|------|
| 04-bat-flap | 0.0000 | good strip; STRIP_GAPS hop/slide |
| 22-NEG-airborne-identity | 0.0000 | negative control; other gates still trip |

**16-moth-flap** at disp_min **0.0164** is the thinnest strip above the precondition
(headroom 0.0014) — first expected to flip inapplicable as more airborne samples arrive.
**17-wisp-float** has headroom 0.0021.

Run `npm run prototype:strip:sharpness` for the full table.

## Min-pair cohort gate

`coherence_split` reports `silhouette_pairwise` and gates `min_pair_cohort_pass`
when `loops=true` and `max_min_pair` is set. Pass when `min_pair <= max_min_pair`.

| Role | Gate | Catches | Blind to |
|------|------|---------|----------|
| Step motion | `silhouette_budget` (adjacent max-pair) | hop, slide, oversized transitions | identity drift on airborne |
| Cohort identity | `min_pair_cohort_pass` | four-character drift (08) | single-frame tamper |
| Frame translation | `displacement_pass` | hop, slide on applicable airborne | strips below sharpness floor; mirror |
| Recolour | `palette_drift_pass` | palette swap | — |

Single-frame hop/slide on grounded classes is caught by adjacent silhouette (or
baseline). Airborne hop/slide on applicable strips is caught by **`displacement_pass`**;
on `04-bat-flap` the gate is **`None`** (degenerate alignment). Mirror on `facing: free`
classes is out of scope.

| Sample | class | min_pair | `min_pair_cohort_pass` |
|--------|-------|----------|------------------------|
| 04-bat-flap | airborne | 0.044 | pass (≤0.29) |
| 17-wisp-float | airborne | 0.269 | pass |
| 08-NEG-identity-drift | airborne | 0.344 | **fail** |
| 08-NEG-identity-drift | idle | 0.344 | fail (redundant with silhouette) |
| 22-NEG-airborne-identity | airborne | **0.383** | **fail** |

22 is the subject-matched control: four different flying creatures under a shared palette
trip `min_pair_cohort_pass` (0.383 > 0.29). Also tripped `palette_drift_pass` (0.636) —
palette was not as tight as 08; the cohort gate is the intended catch.

## Per-class negative controls (generated)

| ID | `motion_class` | Tripped gates | Key metrics | vs budget |
|----|----------------|---------------|-------------|-----------|
| `22-NEG-airborne-identity` | `airborne` | `min_pair_cohort_pass`, `palette_drift_pass` | min_pair **0.383**, sil 0.652 | > 0.29 ✓ |
| `23-NEG-swing-identity` | `swing` | `silhouette_budget`, `palette_drift_pass` | sil **0.624**, min_pair 0.321 | > 0.59 ✓ |

Both strips **falsify the separation claim** if their measured gate were at or below the
budget; neither does. `23` raises the swing silhouette ceiling from 0.602 (idle proxy)
to 0.624 while keeping 0.034 margin. `22` confirms airborne cohort identity is gated
with 0.093 margin — wider than the 0.054 idle proxy suggested.

## Next corpus priority

Per-class negatives for the two thinnest claims are **done** (`22`, `23`). Further
negatives are lower priority than fixing the derivation estimator (monotonic worst-good
vs fixed controls). Do not add more good strips to strengthen separation.

## Consumers

`python -m pipeline.ingest_strip` (npm `strip:ingest`) is the
production reader for this contract: it recovers a provider strip, gates it under the
declared motion class via `coherence_split`, and on automatic pass exports one
logical-resolution RGBA frame per slice. Review-band and hard-fail strips write no
frames; inapplicable gates are reported explicitly in human and JSON output.

### Final polish (post-ingest)

`python -m pipeline.final_polish_cli` (npm `strip:polish`) consumes the current
production contract after ingest. It does not supersede the AFK acquisition
evidence model, add Gates, or change Budgets.

1. **`init`** accepts only a provider Strip that currently passes production
   ingest (`PASS`). It requires `--provenance <source.json>` validating schema
   `animation-strip-provenance/0` (provider SHA-256, motion class, Strip layout,
   generation mode, and prompt hash). It creates a retained provider copy, the
   provenance sidecar at `provider/source.source.json`, an
   `animation-attempt-ledger/0` document at `provider/attempts.json`, immutable
   Draft Frames, and seeded Polished Frames (one per logical Frame slot).
   `REVIEW` and `FAIL` ingest outcomes create no Polish Bundle. New bundles use
   manifest schema `final-polish-bundle/2` with hash bindings for provenance and
   the attempt ledger. Optional `--polish-profile <id>` copies a checked-in
   Polish profile into the bundle and binds its schema, id, path, and SHA-256.
   For profile `dwarf-miner` with Motion class `walk` or `swing`, `init`
   additionally requires `--identity-reference` and `--edit-source`, copies
   those bytes to `reference/identity.png` and `provider/edit-source.png`,
   requires `generation_mode=image-edit`, and binds the canonical identity hash
   and seed-strip hash in provenance. These are **two different files**:
   `--edit-source` must be the idle provider Strip at
   `assets/first-room/dwarf/idle/provider/source.png`, obtained via
   `npm run strip:polish -- seed --identity-declaration
   assets/first-room/dwarf/identity.json` (byte-for-byte copy of
   `identity.json` → `generation_source`; already four identical idle Frames).
   `--identity-reference` must be `assets/first-room/dwarf/identity.png`
   (16×24 post-ingest Release Frame from `identity.json` → `identity_png`).
   The seed command does **not** take `identity.png` as input. Never upscale
   the identity anchor into a generation canvas. Corpus inbox Strips and
   text-to-image redraws are not valid edit sources. On `init` and on every
   `/2` `check`/`finalize`, provenance `edit_source_sha256` and the bound
   `provider/edit-source.png` bytes must equal
   `identity.json` → `generation_source.sha256`; a self-consistent tiled or
   upscaled `identity.png` seed is rejected with
   `edit_source_not_generation_source`. The checked-in `provider/source.png`
   must be the **unmodified** provider Attempt output: do not wipe near-magenta,
   shift Frames for baseline, or paint/stamp Identity Lock (or flat identity)
   colors into pitch sample centers or locked regions to force Gate PASS. Those
   post-edits create hard flat lock blocks and seams that poison cell recovery
   while still allowing Identity Lock PASS. Subjects must stay inside a safe empty magenta inset away from provider canvas edges; touching an edge is
   `provider_clipping` and requires regeneration — see
   `prompts/production/animation-strip.md` § Provider canvas safe inset.
   `check_bundle` hard-rejects a magenta-wiped provider relative to
   `provider/edit-source.png` with `provider_magenta_wipe`, and reports
   edit-source lock continuity under `provider_post_edit` (FAIL → overall FAIL
   via `edit_source_continuity_fail`). Failed lock/baseline/clipping/pitch
   requires another Attempt. See
   `prompts/production/animation-strip.md` § Dwarf-miner walk and swing. Existing
   unprofiled `/0` and profiled
   `/1` bundles remain valid for `check` and `finalize` under legacy rules.
2. The four Polished Frames remain exact `16×24` RGBA with binary alpha, exact
   per-Frame Draft alpha masks, and opaque RGB values drawn only from the
   combined Draft palette (only RGB may differ from Draft; alpha is locked).
3. **`brief`** is read-only: for a profiled bundle, it reports the profile
   identity, fixed visual questions, applicable Motion-class overrides, editing
   rules, audit workflow, and `PASS` / `EDIT` / `UNCERTAIN` verdict vocabulary.
   A bundle without a profile has no authoritative semantic brief.
4. **`check`** is read-only: for `/2` bundles it revalidates every evidence hash
   and semantic binding (provenance, identity reference, edit source, attempt
   ledger) before structural polish and coherence Gates. It reports every visible
   changed Cell (Draft vs Polished RGB at occupied coordinates) and runs the
   exact Polished Frames through the current Motion-class Acceptance profiles
   via `coherence_split`.
   For applicable dwarf-miner Frames, Identity Lock `/1` first selects the
   lowest-distance permitted registration, then enforces declared alpha
   occupancy and Master Palette role-distribution limits, exact boot occupancy,
   grounded lamp/eye/buckle landmarks, and the swing relational constraints.
   Its report records selected offsets, per-check measurements and thresholds,
   landmark positions, and the first failure.
5. **`finalize`** repeats current-policy validation (including `/2` evidence
   bindings), records a hash-bound immutable report for every valid outcome,
   and produces Release Frames only on automatic `PASS`; `REVIEW` and `FAIL`
   have no override.
6. The provider Strip, provenance sidecar, attempt ledger, optional identity and
   edit-source inputs, Draft, Polished, Release, Polish profile, and report
   hashes preserve the derivation chain. A missing, malformed, hash-mismatched,
   or semantically unbound evidence record makes a `/2` bundle invalid. A
   missing, malformed, identity-mismatched, or hash-mismatched embedded profile
   makes a profiled bundle invalid.

**Attempt ledger rows** (`animation-attempt-ledger/0`) record each provider
Attempt. Accepted rows require null `rejection_reason` and `rejection_detail`.
Rejected rows require a non-empty `rejection_reason`. Optional `rejection_detail`
carries structured near-miss evidence when a rejection is close to passing. For
Identity Lock failures, set `rejection_reason` to `"identity_lock"` and populate
`rejection_detail` from the machine-readable check report (schema
`identity-lock-near-miss/0`; helper `identity_lock_rejection_detail()` in
`pipeline/identity_lock.py`). Ledgers without `rejection_detail` remain valid.

**Structural polish invariants** (alpha mask, palette membership, provenance
reproduction) are enforced before coherence Gates run. Failures on these
invariants are structural hard failures — they do not become new Gates and do
not change any Budget.

The checked-in `miner` Polish profile asks fixed questions about identity
anchors, semantic separation, temporal consistency, native-scale contrast, and
outline continuity. Its `walk` override asks about alternating-leg readability
and belt/buckle stability. Its `swing` override asks about face/hand and
hand/tool separation plus the tool arc. Intentional pose occlusion is not a
missing feature. These questions guide an agent's visual verdict; they do not
become coherence Gates and the validator does not answer them automatically.

Aseprite is optional: an operator may edit Polished Frames in Aseprite or by
direct Cell-coordinate changes to the `polished/` PNG sequence. Automatic accent
recognition, Aseprite project generation or automation, original raster
generation, actual miner pixel edits, runtime playback, and game-asset
integration remain outside this wave. Visual examples such as a one-Cell black
eye, a one-Cell-high belt, a stable buckle color, or intentional outline
continuity illustrate the kind of edits an operator might make; the validator
does not recognize those semantics.

### Static assets (post-recovery)

`python -m pipeline.static_asset_cli` (npm `asset:static`) is the production
lifecycle for uniform static provider sheets. It does not assign a Motion class,
run coherence Gates, or change Strip Budgets.

1. **`init`** runs existing raw candidate gates, recovers one logical sheet with
   vendored `pipeline.recovery` primitives, verifies declared sheet geometry from
   a `static-sheet-spec/0` document, and pitch-slices each declared item. It
   retains the provider PNG and provenance sidecar, embeds a hash-bound spec and
   Master Palette, and seeds immutable Draft and Polished item PNGs. Invalid
   input creates no bundle.
2. Polished items remain exact declared dimensions in RGBA with binary alpha,
   exact Draft alpha masks, and opaque RGB values drawn only from the bound
   Master Palette.
3. **`check`** is read-only: it reports every changed Cell and every structural
   violation. Outcome is `PASS` or `FAIL` only — semantic art judgment is
   outside this structural check.
4. **`finalize`** repeats current validation, writes an immutable hash-bound
   report for every valid check, and copies items to `release/` only on `PASS`.
   Existing conflicting Release bytes fail rather than overwrite.

`npm run prototype:strip:corpus` and `npm run prototype:strip:adversarial` consume the
same production tri-state outcomes — they do not derive or own Budget numbers.
`npm run prototype:strip:derive-budgets` remains the explicitly historical pre-α
baseline estimator only.

## Implementation

`MOTION_CLASSES` in `pipeline/strip.py` is the runtime projection of
`gate-controls/acceptance-profiles.json` (Budgets and Gate status) joined with class
metadata (`grounded`, `loops`, `facing`, displacement sharpness). Construction fails
closed when any provider-controlled Separated pair lacks its referenced `ACTIVE`
Promotion. `coherence_split(frames, motion_class=...)` emits tri-state
`PASS` / `REVIEW` / `FAIL` outcomes per Gate plus structural hard failure.
Unknown classes raise `ValueError`. `None` budgets exclude their gate from pass and
report `None`.

Per-sample `grounded` was removed from `prompts/manifest.json`; groundedness is
derived from the motion class.
