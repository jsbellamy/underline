# Verdict

**Question:** Can strip-in-one-render animation be coherence-gated after grid recovery?

**Answer:** **GO — mechanism and numbers, inside a documented envelope.**

Coherence gating works. On a 23-sample corpus (19 good strips across 6 motion classes,
4 negative controls) every control is caught by the gate that should catch it, and
every good strip passes. The gates are:

| gate | reads | catches |
|------|-------|---------|
| `silhouette_budget` | occupancy flips, adjacent frames | motion beyond the class budget |
| `palette_drift_pass` | per-frame colour histograms | recolour |
| `min_pair_cohort_pass` | closest frame pair | "is this one subject?" — wholesale identity drift |
| `displacement_pass` | best-alignment shift vectors | a frame translated (hop/slide) |
| `baseline_row_stable` | declared anchor from frame 0 | subject leaving the ground |

Budgets are **per motion class**, derived gate-agnostically from manifest-good strips —
see [`docs/strip-acquisition-contract.md`](../../docs/strip-acquisition-contract.md),
which is the authority. Port the mechanism *and* the derivation rule; re-derive the
constants against production strips.

**The consumer is Underline, the mining game.** Recovery primitives are vendored from
Nightglass in `pipeline/recovery.py` only; its frozen animation contract does not
constrain what this gate accepts.

### The envelope

Four things are true and not fixable by another prototype pass:

- **Cohorts are n≈3.** Every budget rests on three observations. Thin margins follow:
  swing silhouette 0.034 over its control, airborne drift 0.049, the displacement
  sharpness threshold 0.0014 over 16-moth-flap.
- **Budgets widen monotonically.** `worst-good + margin` only grows as samples
  accumulate while the negative controls stay fixed, so every class drifts toward
  UNSEPARATED. `airborne` already lost its silhouette gate this way. The derivation
  rule needs replacing (a percentile, or separation-aware fitting) before the corpus
  gets much larger.
- **`min_pair` has no independent kill.** Every strip it catches, palette drift also
  catches. It is justified by construction (occupancy vs colour are disjoint signals),
  not by evidence.
- **`airborne` is the weak class.** Silhouette is `None` (UNSEPARATED, confirmed
  against a subject-matched control at 0.652 vs good-worst 0.644), and displacement is
  inapplicable on strips with a degenerate alignment minimum. See the contract's
  known-gaps table.

Growing n by hand has hit diminishing returns. The next real evidence comes from use —
see Open 1.

## Session 2: why the provider strip needed loose budgets

The old gate diffed **cell colours** and called the result "motion". Decomposing the
changed cells on `inbox/miner-idle-strip.png` (`sweep.py` and `probe.py`, one-off
probes, both since deleted):

| pair | changed frac | silhouette flips | shading flips |
|------|--------------|------------------|---------------|
| 0→1  | 0.136 | 3 (16%)  | 16 (84%) |
| 1→2  | 0.486 | 19 (27%) | 52 (73%) |
| 2→3  | 0.490 | 18 (25%) | 54 (75%) |
| 3→0  | 0.366 | 10 (19%) | 43 (81%) |

**73–84% of the "motion" was re-shading, not movement.** The provider drew the same
pose and repainted its shadows.

Two things this ruled out:

- **Not misalignment.** Whole-cell x-shift scan: `dx=0` wins every pair by a wide
  margin (0.14 vs 0.75 at ±1). Slicing is correct *for this strip* — see session 3,
  where the mechanism turns out to be fragile for subjects that change width.
- **Not quantizer resolution.** Sweeping `max_colors` ∈ {4…16} × `merge_dist` ∈
  {64…160} — 24 combinations — the best max-adjacent is **0.390**, and collapsing all
  the way to 5 clusters does not help. No quantizer setting reaches 0.28.

## The fix: split the gate

Colour diff conflated two independent failure modes. Separating them:

- **`silhouette_diff`** — occupancy flips above the baseline row, colour-blind.
  Measures motion only.
- **`palette_drift`** — total-variation distance between per-frame colour histograms.
  Measures recolour only.

Separation is ~2 orders of magnitude on the signal each gate exists to catch:

| | real strip | synthetic pass | synthetic palette_fail |
|---|---|---|---|
| silhouette max-adjacent | 0.130 | 0.192 | 0.250 |
| palette TV drift | 0.106 | 0.026 | **0.742** |

Real strip under strict budgets: silhouette `0.021 / 0.130 / 0.122`, loop `0.069`,
drift max `0.106`. Comfortable margin on every gate.

> **Corrected in session 4.** The 0.742 is *synthetic* — colours swapped
> wholesale. On real provider output the drift separation is far tighter: the worst
> passing sample is 03-torch-flicker at **0.145** and the negative control
> 07-NEG-palette-drift is **0.290**, against a 0.15 budget. That is a ~2× gap, not
> ~100×, and 03 clears the budget by 0.005. The silhouette split is still the right
> design; the drift *budget* is not yet evidenced.

## The gates still reject (`prototype:strip:adversarial`)

Mutating the real strip's frames, each mutation trips exactly its intended gate:

| mutation | verdict | tripped |
|----------|---------|---------|
| untouched | PASS | — |
| recolour frame 2 | FAIL | `palette_drift_pass` (drift 0.993) |
| hop frame 2 +3 rows | FAIL | `baseline_row_stable`, `silhouette_budget` (0.436) |
| mirror frame 2 | FAIL | `silhouette_budget` (0.668) |
| slide frame 2 +3 cols | FAIL | `silhouette_budget` (0.468) |

Clean 0.130 vs worst-bad 0.436 — the budget sits in a real gap, not on a knife edge.

## Learnings (don't re-discover)

- Recover the **full raster**, not tight fg bbox — gutters disappear otherwise.
- Pin pitch to declared `pitch_px`; silhouette bbox ≠ full logical frame height.
- Provider strips: auto slice on empty columns, `margin_cells=0`. Note this keys on the
  subject's own transparent columns, not the declared gutter (session 3).
- **Never gate animation on a colour cell-diff.** Providers re-shade freely between
  frames; colour diff reads that as motion and forces budgets so loose they stop
  discriminating. Gate silhouette and palette separately.
- `baseline_cells_locked` and `palette_set_equal` are retired — ground shadow bleed
  makes the first always-false on provider output, and the second is trivially true
  after quantizing to a shared palette. Both were noise.
- `pipeline/recovery.py` `sample_cells` already does a central-60% per-channel median,
  so "per-cell majority vote instead of centre sample" (old open item #1) was moot —
  the sampling was never the problem.

## Session 3: corpus to break the overfit

Nine prompts in `prompts/`, expected verdicts in `prompts/manifest.json`, scored by
`npm run prototype:strip:corpus`. Drop `<sample-id>.png` into `inbox/`; pending
samples are not failures, contradicted predictions are.

The corpus is built to *discriminate*, not to go green:

| # | sample | class | predicted | probes |
|---|--------|-------|-----------|--------|
| 01 | miner-idle | idle | PASS | the sample the budgets came from |
| 02 | slime-idle | idle | PASS | curved limbless shape — gate keyed to the miner? |
| 03 | torch-flicker | emissive | PASS | legitimate colour churn vs the 0.15 drift budget |
| 04 | bat-flap | airborne | PASS | no planted baseline — untested assumption |
| 05 | miner-walk | locomotion | **FAIL** | idle-derived budget vs real locomotion |
| 06 | miner-swing | one-shot | **FAIL** | non-looping action vs the loop gate |
| 07 | NEG-palette-drift | negative | FAIL (drift) | pose held, colours swapped |
| 08 | NEG-identity-drift | negative | FAIL (silhouette) | four characters, shared palette |
| 09 | NEG-no-gutter | negative | FAIL (recover\|slice) | must fail before the gates |

05 and 06 are predicted to fail **while being good strips**. If they do, "coherent" is
not one number and budgets are per-motion-class. 04 and 07/08 test whether the two
gates are genuinely independent.

### Finding: slicing ignores the declared gutter

`slice_frames_auto` splits on fully-transparent columns, which are the *subject's* own
empty columns — not the gutter. Rendering a strip with `gutter=0` still yields four
segments, 5 cells wide each: the miner's body. So recovered "frames" are content
bboxes, which is why the real strip reports 13–14 cols against a declared 16 (old open
item #3). The prompt's gutter spec does nothing for slicing; it only helps by keeping
subjects apart.

**The hazard this creates:** `normalize_frame_widths` crops every frame to the
narrowest segment, from the left. The idle survived only because all four frames'
content sat at x=0..12. A walk cycle with spreading legs gives varying widths at
varying offsets, and the resulting misalignment presents as a *silhouette-budget*
failure — impersonating exactly what sample 05 exists to measure. `corpus.py` now flags
uneven `segment_widths` so this cannot be misread; the real strip already trips the
flag (`[13, 14, 13, 13]`). Confirm with `probe.py`'s x-shift scan before believing any
silhouette failure on a flagged row.

### Finding: sample 09 fails at recovery, not slicing

Verified synthetically: a ground line spanning the canvas trips `acquire.raw_clipping`
("subject clipped at left/right") before slicing runs. The manifest accepts either
layer.

## Session 4: corpus filled, 9/9 scored

All nine PNGs generated and scored. **7/9 predictions held.** Both surprises are
expected-PASS samples that failed.

| # | sample | want | got | max sil | loop | drift | tripped |
|---|--------|------|-----|---------|------|-------|---------|
| 01 | miner-idle | PASS | PASS | 0.095 | 0.151 | 0.073 | — |
| 02 | slime-idle | PASS | **FAIL** | 0.300 | 0.300 | 0.146 | silhouette, loop |
| 03 | torch-flicker | PASS | PASS | 0.160 | 0.130 | 0.145 | — |
| 04 | bat-flap | PASS | **FAIL** | 0.651 | 0.603 | 0.151 | baseline, silhouette, loop, drift |
| 05 | miner-walk | FAIL | FAIL | 0.391 | 0.132 | 0.114 | silhouette |
| 06 | miner-swing | FAIL | FAIL | 0.382 | 0.515 | 0.188 | silhouette, loop, drift |
| 07 | NEG-palette-drift | FAIL | FAIL | 0.133 | 0.142 | **0.290** | drift only |
| 08 | NEG-identity-drift | FAIL | FAIL | 0.571 | 0.503 | 0.228 | silhouette, loop, drift |
| 09 | NEG-no-gutter | FAIL | FAIL | — | — | — | recover |

**07 tripped drift and only drift** while holding silhouette at 0.133 — the two gates
are genuinely independent on real provider output, which is what 07 existed to prove.

### The two surprises are different failures

Six of nine samples carry the uneven-width confound, so every silhouette failure was
re-checked under a ±3 col / ±1 row shift scan on the *raw* segments (`align.py`, a
one-off probe, deleted once pitch slicing settled the question).

- **02-slime-idle was a false failure.** Best shift drops max-adjacent
  `0.385 → 0.256` (below 0.28) with dx/dy of ±1 on every pair. The gate is not keyed
  to the miner's shape — it is keyed to frames whose content happens to start at the
  same x. **The prediction was right and the gate was wrong.** This is the
  left-crop hazard session 3 predicted, landing in the sample that was not built to
  test it.
- **04-bat-flap is a real failure.** Best shift only reaches `0.667 → 0.569`,
  double the budget. A wing flap genuinely flips that much occupancy, and
  `baseline_row_stable` trips because an airborne subject has no planted baseline to
  be stable about. **The premise was wrong**: that gate is only meaningful for
  grounded subjects.

So with 04 alongside the predicted 05 and 06, **three motion classes exceed an
idle-derived budget while being good strips.** "Coherent" is not one number.

### Refuted: centroid + baseline anchoring

Session 3 proposed replacing left-crop with content-centroid-x + baseline-y anchoring.
The scan scores it, and it is **worse than left-crop** on the samples that matter:
05 `0.398 → 0.443`, 06 `0.550 → 0.634`, 07 `0.170 → 0.200`. The centroid moves *with*
the pose, so anchoring to it partly cancels the motion in the frames with the most
motion. Do not build it.

Search-based alignment (take the best shift) does work, and re-running the adversarial
mutations under the same search confirms it does not hand an attacker a free pass —
but it eats most of the margin:

| mutation | left-crop | best-shift | vs 0.28 budget |
|----------|-----------|------------|----------------|
| slide +3 cols | 0.468 | **0.293** | rejects by 0.013 |
| hop +3 rows | 0.436 | 0.350 | rejects |
| mirror | 0.668 | 0.401 | rejects |

A gate that rejects a deliberate 3-column slide by 0.013 is on a knife edge. Search
alignment is not free — it buys 02 at the cost of the translation adversary.

## Session 5: scope belongs to Underline, not Nightglass

This prototype **vendors Nightglass recovery primitives** in `pipeline/recovery.py`
but the consumer is **Underline, the mining game**. Nightglass's frozen
`docs/animation-contract.md` — one hand-authored planted idle, everything else a runtime
transform — governs Nightglass and **does not constrain Underline**. A mining game
plausibly wants idle, walk, and a pickaxe swing, which is why 05 and 06 were written in
the first place.

**Therefore session 4's conclusion stands: budgets are per-motion-class.** 04, 05 and 06
are good strips that a single idle-derived budget rejects. Do not treat them as negative
controls; 07/08/09 are the only negative controls.

Underline has no design docs yet, so the motion-class list is **an open input, not a
derivable fact** — see Next pass.

### What 04 actually measured (independent of scope)

Per-frame bbox on the raw segments: `y=15..23 / 19..23 / 19..25 / 19..23`, widths
`13 / 15 / 12 / 16`. The body did stay put; the *wingspan* is what swings. Two distinct
things then happen, and session 4 conflated them:

1. **`baseline_row` is defined as the lowest opaque row**, which for a bat is the
   wingtip — it moves 23→25. So the gate reads a stationary bat as an unstable
   baseline. That is a **definitional artifact**, and it also shifts the region
   `silhouette_diff` compares, inflating the number.
2. **Even so, the motion is genuinely large** — 0.569 at best alignment. On a small
   body the wings *are* most of the silhouette.

The anchor a strip is gated against should be **declared once for the strip**, not
re-derived per frame from the lowest opaque row.

## Next pass: make the silhouette numbers trustworthy

**Goal — slice on declared pitch instead of content bboxes, then re-derive budgets per
motion class from the corrected numbers.**

Every budget conclusion on record is contaminated. Six of nine samples carry the
uneven-width confound, so their silhouette figures are part motion and part left-crop
misalignment, in unknown proportion. Per-motion-class budgets cannot be set on numbers
that are not trusted — the alignment fix is a prerequisite, not a parallel task.

Ordered:

1. **Slice on declared pitch.** `slice_frames_auto` returns content bboxes and throws
   away each frame's position in the strip. Slice at `frame_w + gutter` from a detected
   phase so position survives. Both dead ends from session 4 (centroid anchoring,
   shift-search) act after the information is already gone.
2. **Re-run the corpus.** Exit criterion: **02-slime-idle passes without a shift
   search**, and `corpus.py` reports no uneven-width confounds. If 02 still fails, the
   left-crop diagnosis was wrong and that is the finding.
3. **Re-run adversarial.** The slide/hop/mirror margins must not shrink. Pitch slicing
   should *restore* them (0.468 rather than search's 0.293) because a slid frame stays
   slid when position is preserved.
4. **Then, and only then, set budgets per motion class** from the corrected silhouette
   figures — one budget per class in Underline's list.
5. **Declare the anchor.** Feed a per-strip anchor into `baseline_row_stable` rather
   than re-deriving the lowest opaque row per frame (fixes 04's artifact).

**Open input, needed before step 4:** Underline has no design docs, so *which motion
classes the mining game ships* is Jake's call, not something to infer from the corpus.
The corpus currently guesses idle / locomotion / one-shot / airborne / emissive. Steps
1–3 do not depend on the answer.

**Not in this pass:** the drift budget (Open 3) and the port (Open 4). Both need the
class list settled first.

## Open

Closed since session 5: pitch slicing with bounded registration (issue #2), the
declared strip anchor (#3), per-motion-class budgets (#4), and the drift budget, now
re-derived at n=3 per class. The alignment question is settled — `align.py` and
`sweep.py` are deleted.

1. **Port into Underline.** Underline is the consumer; grid recovery lives in
   `pipeline/recovery.py` and the gate library in `pipeline/strip.py`. The prototype
   runners remain here for corpus scoring and budget derivation — they import the
   production modules under `pipeline/`.
   (If Nightglass ever wants strips, that is a separate ask under its own frozen
   contract — do not conflate them again.)
2. **Replace the budget derivation rule.** `worst-good + margin` cannot converge:
   budgets only widen, controls are fixed. Needs a percentile or a separation-aware
   fit before the corpus grows much further. See the envelope above.
3. **Is `min_pair` load-bearing?** No strip in the corpus is caught by it alone. The
   discriminating case — identity drift under a genuinely tight shared palette — is a
   question about what the provider actually emits, not about the gate.
4. **`airborne` per-frame tamper.** hop/slide are gated only where the alignment
   minimum is non-degenerate; mirror is out of scope under `facing: free`. If Underline
   ever requires flight-direction facing, `airborne` moves to `fixed` and mirror
   becomes a hole needing a chirality gate.
5. **Vertical trim** — recovered grid is 43 rows (full image height); frames are 13–14
   cols vs declared 16. Content bbox trim may want normalizing before gates.
6. **Pitch score** — recovered scores are low (~0.04–0.06) and pass via an `or`
   threshold; worth validating against `MIN_GRID_SCORE` intent.

## Commands

```bash
npm run prototype:strip              # TUI: [1-3] synthetic, [4] inbox
npm run prototype:strip:smoke        # synthetic pass/fail fixtures
npm run prototype:strip:adversarial  # per-class mutations — gates must reject
npm run prototype:strip:inbox        # JSON on latest inbox PNG
npm run prototype:strip:corpus       # score inbox/ against prompts/manifest.json
npm run prototype:strip:derive-budgets  # per-class worst-good → budgets
npm run prototype:strip:displacement # antisymmetric displacement falsification + coverage
npm run prototype:strip:sharpness    # alignment-minimum margins, corpus-wide
npm test                             # pytest
```
