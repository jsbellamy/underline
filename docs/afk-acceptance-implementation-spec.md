# AFK animation-Strip acceptance — agent-ready implementation specification

Resolved in [Assemble the agent-ready implementation specification](https://github.com/jsbellamy/underline/issues/30).
Wayfinder map: [Wayfind a trustworthy AFK animation-Strip acceptance pipeline](https://github.com/jsbellamy/underline/issues/17).

This document is the operational contract for AFK Gate-control work. Vocabulary
is defined in `CONTEXT.md`. Measured numbers are reproduced by the proof commands
below — never by memory.

**Checked-in state:** all **17** Separated Promotions in `gate-controls/manifest.json`
are `ACTIVE`. New manifest-backed candidates complete verification through the
production score → acquire → review → verify loop (§12). Wave D estimator
replacement remains out of scope (§11).

## 1. Destination this map locked

Underline's AFK acceptance pipeline for provider animation Strips is specified
when all of the following hold (they do):

1. Every Motion-class / Gate pair has an explicit Acceptance-profile status:
   Separated, Unseparated, or Inapplicable.
2. Every Separated pair has an isolated provider-generated Gate control (or is
   structural and needs none).
3. Unseparated and Inapplicable behavior is explicit.
4. Control scoring, provenance, Promotion, and agent Review are reproducible.
5. Numeric quantization, comparison epsilon, α, and the resulting Budget deltas
   are decided from that evidence.

Production α-Budgets have landed in runtime `MOTION_CLASSES` (Wave B). Building
a non-worst-good production estimator remains out of this map; it must not
re-litigate α, quantization, Acceptance profiles, or the evidence contract.

## 2. Standing authorities (do not fork)

| Concern | Authority |
|---------|-----------|
| Domain vocabulary | `CONTEXT.md` |
| Motion classes, Gates, runtime budgets, corpus | `docs/strip-acquisition-contract.md` |
| α-Budget tables and fragile claims | `docs/alpha-budget-tables.md` |
| Machine-readable Acceptance profiles | `gate-controls/acceptance-profiles.json` |
| Idle / emissive prose profiles | `docs/acceptance-profiles/*.md` |
| Numeric policy | `pipeline/numeric_policy.py` |
| Production Gate-control CLI | `npm run gate-control:score`, `gate-control:acquire`, `gate-control:review`, `gate-control:verify` |
| Code / test seams | `docs/agents/code-style.md` |

If prose and a machine-readable index disagree, fix the drift; do not invent a
third source.

## 3. Acceptance model (locked)

From [Decide how coupled Gate controls change the acceptance model](https://github.com/jsbellamy/underline/issues/37):

Each Motion class owns an **Acceptance profile**. Every pair is exactly one of:

| Status | Automatic pass | Agent Review | Autonomous hard fail |
|--------|----------------|--------------|----------------------|
| **Separated** | `metric <= Budget` | `Budget < metric < C` | `metric >= C` |
| **Unseparated** | `metric <= Budget` | `metric > Budget` | never |
| **Inapplicable** | Gate omitted | — | — |

Rules that must not be reopened:

- `Inapplicable` is reserved for animation semantics (e.g. loop on one-shot
  `swing`). Acquisition difficulty never makes a Gate inapplicable.
- Compound Gate controls are rejected. An autonomous per-Gate hard-fail still
  requires exact one-Gate isolation.
- Structural failures (`dimension_parity`, failed recovery, grounded
  `baseline_row_stable`) remain hard outside Review.
- No further provider generation for the stalled Unseparated pairs listed below.

## 4. Numeric policy (locked)

From [Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38):

| Knob | Value |
|------|-------|
| Canonical precision | 4 decimal places |
| Rounding | ceiling toward worse defect (`Decimal`, not `math.ceil` float trap) |
| Comparison | pass at `metric <= Budget`; fail at `metric > Budget` |
| Comparison epsilon | `0` |
| Evidence | retain integer numerator/denominator alongside the canonical decimal |

Verdicts compare the canonical decimal only. Target vs collateral must not use
different rounding. Existing Measurement runs are immutable; a policy change
appends a new Measurement run when raw bytes exist.

## 5. Gap allocation and Budgets (locked)

From [Choose alpha for separated Gate controls](https://github.com/jsbellamy/underline/issues/28)
and [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29):

```text
α = 0.5
G = ceil₄(worst Manifest-good metric)
C = ceil₄(isolated Gate-control metric)
Separated Budget = ceil₄(G + α × (C − G))
```

Unseparated pairs keep the runtime `ceil₀.₀₁(worst-good) + 0.02` Budget and open
Review above it. Inapplicable Gates are omitted.

Reproduce:

```bash
npm run prototype:strip:alpha-budgets
```

Counts: **17 Separated** · **4 Unseparated** (continuous metric) · **3 Inapplicable**
(α metric Gates) · structural `baseline_row_stable` Separated without a provider
control · `airborne/displacement_pass` Unseparated (binary / often undecidable —
see §6).

Runtime `MOTION_CLASSES` hold the landed α-Budgets and the proof runner verifies
exact equivalence. Fragile claims under α = 0.5:

| Pair | Budget | C | Good headroom | Review width |
|------|-------:|--:|--------------:|-------------:|
| `walk/silhouette_budget` | 0.4136 | 0.4294 | 0.0159 | 0.0158 |
| `blob_idle/min_pair_cohort_pass` | 0.1199 | 0.1371 | 0.0173 | 0.0172 |
| `swing/silhouette_budget` | 0.5860 | 0.6067 | 0.0208 | 0.0207 |

A `displacement_pass` undecidable caveat on a **non-target** Gate does not make
an `ISOLATED` control inadmissible for deriving that target's Budget.

## 6. Acceptance profile matrix (locked)

Machine-readable index: `gate-controls/acceptance-profiles.json`.

The 17 Separated / 4 Unseparated / 3 Inapplicable counts in §5 cover the four
provider-controlled α metric Gates. `static_silhouette_pass` is recorded below
but sits outside those Gate-control counts.

### Separated (provider Gate control required unless structural)

| Pair | Budget | Hard-fail C | Control attempt | Promotion |
|------|-------:|------------:|-----------------|-----------|
| `idle/silhouette_budget` | 0.2239 | 0.3000 | `idle--silhouette_budget--001` | `promo--idle--silhouette_budget` |
| `idle/palette_drift_pass` | 0.1974 | 0.2793 | `idle--palette_drift_pass--001` | `promo--idle--palette_drift_pass` |
| `blob_idle/silhouette_budget` | 0.3951 | 0.4531 | `blob_idle--silhouette_budget--004` | `promo--blob_idle--silhouette_budget` |
| `blob_idle/loop_closure_pass` | 0.3906 | 0.4516 | `blob_idle--loop_closure_pass--004` | `promo--blob_idle--loop_closure_pass` |
| `blob_idle/palette_drift_pass` | 0.2377 | 0.2793 | `blob_idle--palette_drift_pass--001` | `promo--blob_idle--palette_drift_pass` |
| `blob_idle/min_pair_cohort_pass` | 0.1199 | 0.1371 | `blob_idle--min_pair_cohort_pass--005` | `promo--blob_idle--min_pair_cohort_pass` |
| `emissive/silhouette_budget` | 0.3226 | 0.4633 | `emissive--silhouette_budget--001` | `promo--emissive--silhouette_budget` |
| `emissive/loop_closure_pass` | 0.1694 | 0.2067 | `emissive--loop_closure_pass--001` | `promo--emissive--loop_closure_pass` |
| `emissive/palette_drift_pass` | 0.2123 | 0.2793 | `emissive--palette_drift_pass--001` | `promo--emissive--palette_drift_pass` |
| `walk/silhouette_budget` | 0.4136 | 0.4294 | `walk--silhouette_budget--002` | `promo--walk--silhouette_budget` |
| `walk/loop_closure_pass` | 0.2112 | 0.2795 | `walk--loop_closure_pass--002` | `promo--walk--loop_closure_pass` |
| `walk/palette_drift_pass` | 0.2217 | 0.2793 | `walk--palette_drift_pass--001` | `promo--walk--palette_drift_pass` |
| `airborne/loop_closure_pass` † | 0.7032 | 0.7529 | `airborne--loop_closure_pass--002` | `promo--airborne--loop_closure_pass` |
| `airborne/min_pair_cohort_pass` † | 0.3013 | 0.3333 | `airborne--min_pair_cohort_pass--004` | `promo--airborne--min_pair_cohort_pass` |
| `airborne/palette_drift_pass` | 0.2423 | 0.2793 | `airborne--palette_drift_pass--001` | `promo--airborne--palette_drift_pass` |
| `swing/silhouette_budget` | 0.5860 | 0.6067 | `swing--silhouette_budget--002` | `promo--swing--silhouette_budget` |
| `swing/palette_drift_pass` | 0.2294 | 0.2793 | `swing--palette_drift_pass--001` | `promo--swing--palette_drift_pass` |

† Control carries a `displacement_pass` undecidable caveat.

Structural Separated (no provider control): grounded `baseline_row_stable`, and
`dimension_parity` as recovery precondition.

All listed Promotions are **`ACTIVE`** in `gate-controls/manifest.json`. New
candidates still follow the two-phase Promotion path in §8
(`PENDING_VERIFICATION` → full verification → `ACTIVE` or `INVALIDATED`).

### Unseparated

| Pair | Budget | Evidence | Rationale |
|------|-------:|----------|-----------|
| `idle/loop_closure_pass` | 0.30 | `idle--loop_closure_pass--010` | loop/silhouette coupling at shared 0.17 adjacent budget |
| `idle/min_pair_cohort_pass` | 0.07 | `idle--min_pair_cohort_pass--016` | best near-miss 0.0698 still passes under four-place ceiling |
| `emissive/min_pair_cohort_pass` | 0.12 | `emissive--min_pair_cohort_pass--006` | target and collateral both fail after ceiling quantization |
| `walk/min_pair_cohort_pass` | 0.17 | `walk--min_pair_cohort_pass--003` | formal incompatibility with isolating from `loop_closure_pass` at shared f3↔f0 0.17 |
| `airborne/displacement_pass` | n/a (binary) | corpus sharpness floor | class-applicable; no isolatable control while undecidable on measured airborne Strips; when `None`, caveat; when decidable `False`, agent Review (never autonomous hard-fail from a missing C); when `True`, pass |
| `swing/static_silhouette_pass` | 0.88 | production swing reference + corpus | runtime action-stillness Review threshold; no provider Gate-control Promotion |

No further provider generation for the four continuous Unseparated pairs.

### Inapplicable

| Pair | Reason |
|------|--------|
| `airborne/silhouette_budget` | `max_silhouette=None` (not grounded) |
| `airborne/baseline_row_stable` | not grounded |
| `swing/loop_closure_pass` | one-shot; `loops=false` |
| `swing/min_pair_cohort_pass` | one-shot; `max_min_pair=None` |
| `idle/static_silhouette_pass` | no class Budget derived |
| `blob_idle/static_silhouette_pass` | no class Budget derived |
| `emissive/static_silhouette_pass` | no class Budget derived |
| `walk/static_silhouette_pass` | no class Budget derived |
| `airborne/static_silhouette_pass` | no class Budget derived |

## 7. Isolation verdict amendments (locked over #19)

From [Prototype the AFK Gate-control scorer and review packet](https://github.com/jsbellamy/underline/issues/20).
These amend [Specify the Gate-control evidence and promotion contract](https://github.com/jsbellamy/underline/issues/19)
and must ship in production scoring:

1. **Only an undecidable target is `INDETERMINATE`.** A non-target undecidable
   applicable Gate becomes a recorded **caveat**. Isolation requires: recovery
   succeeds, target fails, every other *decidable* applicable Gate passes, and
   undecidable non-targets are named.
2. **Invalid target → `SpecificationError` before scoring.** No Attempt row, no
   Measurement run. Targets that are class-inapplicable or structural never enter
   the ledger.
3. **Review composite is target-Gate-specific.** Evidence panel selection:
   occupancy diff for silhouette / loop / min-pair; quantized per-Frame palette
   histogram for drift; best-alignment shift vectors for displacement.

Isolation enum remains: `ISOLATED` | `NOT_ISOLATED` | `INDETERMINATE`.

Primary-failure order (deterministic): structural recovery → target undecidable →
target too weak → first collateral failure in fixed Gate order
(`dimension_parity`, `baseline_row_stable`, `silhouette_budget`,
`displacement_pass`, `loop_closure_pass`, `min_pair_cohort_pass`,
`palette_drift_pass`).

## 8. Evidence layout and Promotion (locked)

From #19, as amended by #20:

```text
gate-controls/
  manifest.json                 # specifications + promotions
  attempts.jsonl                # append-only compact ledger
  acceptance-profiles.json      # Acceptance-profile index
  reports/<attempt>/<measurement>.json
  provenance/<attempt>.json
  reviews/<attempt>/<review>.json
  reviews/<attempt>/<composite>.png
  verification/<promotion>.json
  raw/<attempt>.png             # retained when required
```

Fail closed on unknown schema versions, broken references, duplicate IDs, or
hash mismatches. Every reference includes SHA-256.

### Isolation Measurement run

Records Attempt ID, timestamp, scorer commit, Gate-configuration hash,
applicable Gate set, structural recovery, raw metrics / thresholds / outcomes,
target Gate, Isolation verdict, caveats, Promotion blockers. Re-scoring appends;
it never overwrites.

### Cursor Image Gen provenance (sole generator for this effort)

Promotion-eligible provenance requires: specification + Attempt IDs;
`generator: "cursor-image-gen"`; exact prompt text + SHA-256; reference-image
hashes if any; generation timestamp; acquiring task/agent identity; repository
commit; raw PNG path, SHA-256, media type, dimensions. Incomplete provenance may
still allow diagnostic measurement; it blocks Promotion. Byte-identical
regeneration is not claimed.

### Two-phase Promotion

1. Write `PENDING_VERIFICATION` only after complete provenance, current
   `ISOLATED` Measurement run, targeted verification, retained raw bytes, and
   approved visual review.
2. Full repository verification against that exact Manifest state.
3. Success → `ACTIVE`; failure → `INVALIDATED` (specification unpromoted).

Only `ACTIVE` Promotions participate in Budget derivation and production
hard-fail boundaries. A later authoritative Measurement run that is no longer
`ISOLATED` invalidates the active Promotion for current use; there is no silent
fallback.

### Retention

Rejected Attempts keep compact row, prompt, provenance metadata, raw hash,
Measurement runs, and primary failure. Discard redundant PNGs after reporting
unless unique evidence for `UNSEPARATED`, `INDETERMINATE`, or a product-level art
decision. Explicit artifact state: `retained` | `discarded`. Discarded Attempts
can never be promoted. Hash-bound Review packets are retained for every reviewed
Attempt even when the raw PNG is discarded.

## 9. AFK acquisition state machine (locked)

Follow Nightglass AFK acquisition discipline, instantiated for Underline:

1. **Report first** — machine-readable Measurement before any visual open.
2. **One primary failure** — stable reason code + rationale + exact prompt delta.
3. **One targeted prompt change per retry.**
4. **Measure before promote.**
5. **Immutable accepted raw + provenance.**
6. **One late visual composite** — hash-bound to the raw PNG.
7. **Targeted verification in the loop; full verification after Promotion write.**
8. **Escalate acquisition** after three consecutive Attempts fail for the same
   Motion class, Gate, and reason code (matching codes count even when secondary
   failures differ).

Infrastructure primary-reason preference: generation → structural recovery →
provenance. Measurement blockers: the agent picks the one primary failure a
single prompt change can best address.

### Observed acquisition cost (operational fact, not a further decision)

From the Gate-control acquisition cohort:

| Class session | Approx. Image Gen calls | Notes |
|---------------|------------------------:|-------|
| `blob_idle` | ~40 | ~15% early structural pitch-fail; collateral silhouette dominant until prompt geometry tightens |
| `idle` (pre-escalation) | ~19 logged | loop/min-pair exhausted into Unseparated |
| `emissive` min-pair | 100+ then stopped | finalized Unseparated under #37/#38 |
| `airborne` | ~7 | palette cross-class reuse; displacement caveat on all three |
| `walk` / `swing` | few | silhouette/loop often via corpus mutation; palette reuses `07` |

Cross-class palette control: corpus `07-NEG-palette-drift` isolates at idle,
blob_idle, emissive, walk, airborne, and swing budgets — no class-specific
palette strip required.

## 10. Agent Review-band rubric (locked)

From [Specify the agent Review-band rubric and audit bundle](https://github.com/jsbellamy/underline/issues/27):

Review is **per-Gate**, not holistic. Each applicable Gate in Review receives
`APPROVE`, `REJECT`, or `UNCERTAIN`. The Strip is approved only when every Gate
review approves. A rejected Gate rejects the Strip.

### Fixed visual questions

| Gate | Question | Required evidence panel |
|------|----------|-------------------------|
| `silhouette_budget` | Intentional pose transition vs identity drift / framing / translation? | Flagged occupancy difference + neighbors |
| `palette_drift_pass` | Intentional subject/Motion-class change (e.g. emissive flicker) vs unintended recolour? | Quantized per-Frame palette histograms + Frames |
| `min_pair_cohort_pass` | Same subject, one coherent animation despite no sufficiently similar pair? | Flagged occupancy comparisons + full Frame row |
| `loop_closure_pass` | Final→first reads as deliberate continuous loop vs pose jump / identity break? | Final→first occupancy + full Frame row |
| `displacement_pass` | Genuine subject motion vs entire Frame translated on the grid? | Flagged in/out alignment vectors + neighbors |
| `static_silhouette_pass` | Adjacent Frames preserve the intended action silhouette rather than only recolouring a held pose? | Adjacent opaque-union overlap + full Frame row |

`static_silhouette_pass` uses this question for runtime ingest Review. It has no
provider Gate-control specification or Promotion, so the production
`gate-control:score` / `gate-control:review` evidence workflow does not accept it
as a target.

### Immutable Review packet (deterministic references)

1. Candidate's Gate-specific composite.
2. Motion class's Budget-binding Manifest-good Strip.
3. For Separated pairs: that pair's promoted Gate control.

Unseparated pairs receive **no** substitute control; the packet must say no
autonomous hard-fail reference exists.

Caveated `ISOLATED` controls remain admissible as the hard-fail reference for
their target Gate. Every caveat is prominent and supports no inference about the
undecidable dimension. Caveat presence alone does not trigger second review;
**reliance** on the caveated dimension does.

### Second-review triggers

Require a fresh second review (same packet, no visibility of first verdict) when:

- Separated metric is at or beyond the inclusive midpoint of the Review band; or
- two or more Gates are in Review; or
- first verdict is `UNCERTAIN`; or
- acceptability depends on a caveated dimension.

Matching `APPROVE`/`REJECT` settles. Disagreement or remaining `UNCERTAIN`
escalates to the human. Same model/version allowed; distinct review identity
required.

### Audit record (every Gate review)

Fixed question + verdict; exact Frames and observed visual feature; candidate
metric, Budget, and Gate-control boundary when present; candidate + reference
hashes; applicable caveats; second-review triggers; free-form rationale;
reviewer/model identity and version; review ID; timestamp; Review-packet hash.
`REJECT` also records one primary Gate/reason code and one Gate-specific retry
intent.

Also escalate on written-requirement conflicts and product-level art choices.
Being Unseparated alone does not escalate.

## 11. Implementation wave — ordered work

Do this work under ordinary implementation tickets (`agent-ready`), not by
reopening the Wayfinder map. Preserve seams in `docs/agents/code-style.md`.

### Wave A — Activate evidence (**complete**)

Wave A is complete for the checked-in cohort: all 17 Separated Promotions are
`ACTIVE` with approved Gate reviews and full-repository verification records.
Fail closed if any Separated pair lacks an `ACTIVE` Promotion before Budget
landing.

Proof (regression seam — re-run on every change):

```bash
npm test
npm run prototype:strip:corpus
npm run prototype:strip:adversarial
npm run prototype:strip:alpha-budgets
```

### Wave B — Land α-Budgets in runtime (**complete**)

Wave B landed in #62. Runtime policies, tri-state ingest, characterization
baselines, and the α-Budget equivalence proof are current.

1. Replace applicable Separated entries in `MOTION_CLASSES` with the α-Budgets
   from `docs/alpha-budget-tables.md` / `acceptance-profiles.json`.
2. Keep Unseparated Budgets at their runtime values; implement Review (not hard
   fail) above Budget.
3. Omit Inapplicable Gates.
4. Teach `coherence_split` / ingest the tri-state outcome:
   `PASS` | `REVIEW` | `FAIL`, plus structural hard fail.
5. Keep `npm run prototype:strip:derive-budgets` as the pre-α baseline check or
   retire it explicitly once α derivation is the sole authority — do not leave
   two disagreeing oracles.
6. Update characterization tests with explained diffs; never silent rebase.

Proof: `npm test`, `npm run prototype:strip:corpus` (expect Review-band rows where
metrics sit between Budget and C), `npm run prototype:strip:alpha-budgets`
(exit 0, tables match runtime).

### Wave C — Production AFK loop (**landed**)

Production modules live under `pipeline/` with canonical npm commands (§12):

1. `pipeline/gate_control.py` — measurement-only scorer (`gate-control:score`).
2. `pipeline/gate_control_acquire.py` — acquisition state machine
   (`gate-control:acquire`: record, promote, retention).
3. `pipeline/gate_review.py` — Review-packet builder + Gate-review audit writer
   per §10 (`gate-control:review`).
4. `pipeline/gate_verification.py` — manifest-backed full-repository verification
   (`gate-control:verify`).

The temporary `corpus/strip-coherence/` compatibility shims were retired
after the production commands landed.

Remaining polish (non-blocking for the checked-in cohort): tighter acquisition
CLI ergonomics and end-to-end wiring in a future runtime/UI slice.

### Wave D — Estimator follow-on (optional, separate decision)

The contract's worst-good + fixed-negative estimator is monotonic toward
Unseparated as good strips accumulate. A later decision may replace it with a
percentile or margin-fit estimator. That decision is **out of this map**; do not
smuggle it into Wave B.

## 12. Commands (production operator path and proof seam)

### Production Gate-control workflow

Canonical operator commands (see `package.json`):

```bash
# 1. Score — isolation Measurement run (does not mutate Manifest)
npm run gate-control:score -- <strip.png> --motion-class <class> --target-gate <gate>

# 2. Acquire — record Attempts, provenance, Promotion candidates
npm run gate-control:acquire -- record --help
npm run gate-control:acquire -- promote --help

# 3. Review — per-Gate agent judgment in the Review band
npm run gate-control:review -- --help

# 4. Verify — full-repository Promotion verification (manifest-backed)
npm run gate-control:verify -- run --promotion-id <promo-id>
```

Numeric policy for Measurement runs: `pipeline/numeric_policy.py`.

### Historical / proof commands

Every measured claim cites a command and a row of its output:

```bash
npm test                              # pytest suite
npm run prototype:strip:corpus        # inbox vs prompts/manifest.json
npm run prototype:strip:adversarial   # per-class mutations must reject
npm run prototype:strip:derive-budgets  # historical pre-α Budget baseline evidence
npm run prototype:strip:alpha-budgets   # α=0.5 Separated budgets + fragile claims (runtime oracle)
npm run prototype:strip:displacement
npm run prototype:strip:sharpness
```

Rescoring an existing Measurement run under the numeric policy:

```bash
PYTHONPATH=. python3 corpus/strip-coherence/rescore_measurement.py \
  gate-controls/reports/<attempt>/<measurement>.json
```

### Adversarial suite — retained gaps

`npm run prototype:strip:adversarial` must reject every required mutation.
Exactly **two** documented strip gaps remain, both on corpus baseline
`04-bat-flap`: **hop** and **slide**, caused by `displacement_pass: None`
(degenerate alignment minimum). The strengthened `blob_idle` slide and
`emissive` mirror cases are required rejection checks, not known gaps. See
`docs/strip-acquisition-contract.md` § Adversarial suite and strip gaps.

## 13. Decision index (do not restate — zoom the ticket)

| Decision | Ticket |
|----------|--------|
| Reproducible Budget baseline | [Reconcile the reproducible Budget baseline](https://github.com/jsbellamy/underline/issues/18) |
| Evidence + Promotion contract | [Specify the Gate-control evidence and promotion contract](https://github.com/jsbellamy/underline/issues/19) |
| Scorer + review packet (+ #19 amendments) | [Prototype the AFK Gate-control scorer and review packet](https://github.com/jsbellamy/underline/issues/20) |
| Coupled-Gate acceptance model | [Decide how coupled Gate controls change the acceptance model](https://github.com/jsbellamy/underline/issues/37) |
| Numeric quantization | [Choose bounded numeric quantization for isolation verdicts](https://github.com/jsbellamy/underline/issues/38) |
| Idle profile | [Finalize the idle Acceptance profile from existing controls](https://github.com/jsbellamy/underline/issues/21) |
| Blob-idle controls | [Acquire isolated blob-idle Gate controls](https://github.com/jsbellamy/underline/issues/22) |
| Emissive profile | [Finalize the emissive Acceptance profile from existing controls](https://github.com/jsbellamy/underline/issues/23) |
| Airborne controls | [Acquire isolated airborne Gate controls](https://github.com/jsbellamy/underline/issues/24) |
| Walk controls | [Acquire isolated walk Gate controls](https://github.com/jsbellamy/underline/issues/25) |
| Swing controls | [Acquire isolated swing Gate controls](https://github.com/jsbellamy/underline/issues/26) |
| Review-band rubric | [Specify the agent Review-band rubric and audit bundle](https://github.com/jsbellamy/underline/issues/27) |
| α = 0.5 | [Choose alpha for separated Gate controls](https://github.com/jsbellamy/underline/issues/28) |
| α-Budget tables | [Re-derive Budgets and rebuild fragile-claim evidence](https://github.com/jsbellamy/underline/issues/29) |
| This specification | [Assemble the agent-ready implementation specification](https://github.com/jsbellamy/underline/issues/30) |

## 14. Out of scope (unchanged from the map)

- Colony progression, economy, mining gameplay, other game-system design.
- Runtime animation playback and state-machine implementation.
- Choosing or building the Blender/Aseprite character-rig source pipeline.
- Replacing the production estimator (Wave D above) without a fresh decision.
