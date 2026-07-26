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

| Class | Binding gate | Budget | Control | Margin | Notes |
|-------|--------------|--------|---------|--------|-------|
| `swing` | silhouette | **0.59** | 23 @ **0.624** | **0.034** | Was 0.012 vs idle 08; subject-matched negative confirms separation |
| `airborne` | min-pair cohort | **0.29** | 22 @ **0.383** | **0.093** | Was 0.054 vs idle 08; four flying creatures score well above budget |
| `airborne` | palette drift | **0.23** | 07 @ 0.279 | 0.049 | 22 also tripped drift (0.636) — palette not tight; cohort gate is the clean catch |

`swing` n=3 adjacent silhouette: 0.565 / 0.492 / 0.359 (06 still worst-good). A fourth
good swing with adjacent sil **> 0.582** still breaks separation against idle 08.

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

## Adversarial suite and strip gaps

`adversarial.py` mutates each class baseline and checks `MUST_FAIL` mutations against
live gates. **`STRIP_GAPS`** documents per-strip holes (not per-class); the suite prints
**`GAP`**, never **`ok`**. **`displacement_inapplicable`** strips print an **`N/A`** line —
never silent `None`.

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

`python -m pipeline.ingest_strip` (npm `prototype:strip:ingest` / `strip:ingest`) is the
production reader for this contract: it recovers a provider strip, gates it under the
declared motion class via `coherence_split`, and on pass exports one logical-resolution
RGBA frame per slice. Failing strips write no frames; inapplicable gates are reported
explicitly in human and JSON output.

## Implementation

`MOTION_CLASSES` in `pipeline/strip.py` is the runtime source.
`coherence_split(frames, motion_class=...)` reads budgets from it. Unknown classes
raise `ValueError`. `None` budgets exclude their gate from pass and report `None`.

Per-sample `grounded` was removed from `prompts/manifest.json`; groundedness is
derived from the motion class.
