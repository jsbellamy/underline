# Agent guide

This is the source of truth for every agent working on Underline, regardless of
which tool or model is driving. Tool-specific files (for example `CLAUDE.md`)
layer on top of this document; put changes to shared guidance here or in the
docs it routes to, not in a tool-specific file.

The game is TypeScript; Python is confined to the asset pipeline. Grid-recovery
primitives are vendored in `pipeline/recovery.py` (from Nightglass `acquire.py`);
re-vendor upstream changes rather than editing the copy in place.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues on `jsbellamy/underline`. See
`docs/agents/issue-tracker.md`.

### Issue implementer

`docs/agents/issue-implementer.md` is the shared implementer process. Two
rules from it: `Closes #<N>` appears only when every Contract claim in the
reviewed completion matrix is `met`; an `unmet` or `needs manual` row routes to
a blocked report or a `Diagnostic:`-prefixed draft PR instead. An asset slice
may not modify pipeline code, gate code, or checked-in characterization tests
to make its own artifact pass.

### Triage labels

See `docs/agents/triage-labels.md` for the canonical role → label mapping and
which labels this repo has actually created.

### Domain docs

This is a single-context project with `CONTEXT.md` at the root and architectural
decisions under `docs/adr/`. See `docs/agents/domain.md`.

### Cursor Composer pin

On Cursor, every Composer 2.5 session and subagent uses the **standard pin**
`composer-2.5[fast=false]` only. Orchestrator spawn rules:
`docs/agents/cursor-composer-pin.md`.

### Reading discipline

Read the report, not the render.

Nearly everything an agent needs to judge is already recorded as text: a gate
report, a corpus scorecard, a derived-budget table, a doc index. The text costs a
fraction of the artifact it describes, and an image or a large document read
early in a task is re-read on every later request of that task — in an agentic
loop a "request" is a tool-call round trip, not a user prompt, so a long task
pays that cost dozens of times over.

This repo is built around that rule: every gate emits a machine-readable verdict
so the strip PNG itself never has to be opened to know whether it passed. Open a
strip only when judgement genuinely requires seeing it — an art call no
measurement answers. Open one composite rather than a directory, and open it
late. Where a runtime supports subagents, run that review in one: it opens the
artifact, answers the question, and returns text, so the artifact never enters
the main task's context.

For a compact, read-only Polish Bundle baseline, use
`npm run --silent strip:polish -- check <bundle> --summary-json`. Reserve the
complete `--json` payload and immutable fingerprinted report for diagnosis that
needs fields absent from the summary.

The same rule governs source, not just artifacts. The pipeline's core modules
run to two thousand lines each, so a whole-file read of one costs more per round
trip than any strip PNG. An issue's `## Touches` `read:` lines are symbol-scoped
for that reason — `pipeline/strip.py :: layout_for_motion_class` names a
function, not a module. Resolve the whole manifest at once with

```bash
npm run --silent agents:anchors -- --issue <N>
```

which prints each anchored function, constant, or doc section as numbered
source, then appends a read-only `planned test selection` footer forecasting
the local `test:changed` gate from the manifest's write paths (`modify:`,
`create:`, `add:`, `delete:`). It also reports directory and binary entries that need their appropriate
inspection tool. A named text anchor that does not resolve is a manifest defect:
return it for repair instead of compensating with a whole-file read. A whole-file
read of a module over ~800 lines is a deliberate choice that belongs in the PR
body, not a default.

### Final-polish agent audit

For a profiled Polish Bundle, run
`npm run strip:polish -- brief <bundle> --json` before opening art. The embedded,
hash-bound Polish profile is the art-direction authority: answer every fixed
question and applicable Motion-class question with `PASS`, `EDIT`, or
`UNCERTAIN`. Report `UNCERTAIN` instead of inventing intent.

Read the machine report first, then inspect one late composite or GIF at native
scale and enlarged with nearest-neighbor scaling. Apply the fewest permitted
Cell edits for `EDIT` verdicts, regenerate the preview, and run
`npm run strip:polish -- check <bundle>`. A profile guides visual judgment; it
does not override structural locks, coherence Gates, or PASS-only finalization.

Non-legacy bundles require independent blinded visual review before `finalize`.
Build the immutable packet with
`npm run strip:polish -- review-packet <bundle> [--json]`, author each
`reviews/review--NN.json` record in a separate session (two reviews when Motion
overrides apply or review 1 is unresolved), then validate with
`npm run strip:polish -- validate-reviews <bundle> [--json]` before release.
`check` stays structural and does not substitute for validated review evidence.

### Strip acquisition contract

`docs/strip-acquisition-contract.md` is the authority for motion classes, gates,
budgets, the budget-derivation rule, and known gaps. Read it before changing any
gate, budget, or class property. Production AFK Budget changes cite
`npm run prototype:strip:alpha-budgets`, the runtime-equivalence oracle (see
`docs/alpha-budget-tables.md`). `npm run prototype:strip:derive-budgets`
reproduces the historical pre-α baseline only.

Budgets are **per motion class** and derived from manifest-good strips plus the
contract's single named legacy idle baseline. Do not add good strips to
strengthen a separation claim; under the current derivation rule good strips can
only widen budgets toward the fixed negative controls. The contract's "Next
corpus priority" section owns which samples are worth adding.

### Code style and test seams

`docs/agents/code-style.md` is this repo's documented coding standard: the layout
and style rules for the TypeScript game and the Python asset pipeline, and the
standing seam agreement for the `/tdd` (red-green) workflow. Changes are
test-first at its seams, and code review judges every diff against its rules — a
breach is a documented-standard violation, not a judgement call.

### Gate blind review

Promotion-verification issues that write `gate-controls/reviews/*/review--*.json`
need two **blinded** visual audits before `/code-review` — see
`docs/agents/issue-implementer.md` step 7. On Cursor, delegate each audit to the
`gate-blind-review` subagent (`.cursor/agents/gate-blind-review.md`). Standard
pin: `docs/agents/cursor-composer-pin.md`.

### Code review (Cursor)

On Cursor, `/code-review` spawns `code-review-standards` and `code-review-spec`
(`.cursor/agents/code-review-standards.md`, `.cursor/agents/code-review-spec.md`)
for the Standards and Spec axes — standard pin `composer-2.5[fast=false]` per
`docs/agents/cursor-composer-pin.md`.

### Evidence

There is no browser or native harness in this repo yet. Every claim is proved by
a command whose output is text:

```bash
npm test                                # test suites (pytest today; TS tests as they land)
npm run test:fast                       # same, minus the slow budget-CLI tests — inner loop only
npm run test:changed                    # tests mapped from the diff against main — the local pre-publish gate
npm run prototype:strip:corpus          # score inbox/ against prompts/manifest.json
npm run prototype:strip:adversarial     # per-class mutations — gates must reject
npm run prototype:strip:derive-budgets  # historical pre-α Budget baseline (worst-good)
npm run prototype:strip:alpha-budgets   # α=0.5 Separated Budgets + fragile claims (runtime oracle)
npm run prototype:strip:displacement    # displacement falsification + coverage
npm run prototype:strip:sharpness       # alignment-minimum margins, corpus-wide
```

`.github/workflows/ci.yml` runs the full suite (`npm test`) and the per-file
isolation sweep on every PR that touches the asset pipeline; `test:changed` is
the fast local gate, not a substitute for that CI run.

The pipeline jobs are gated on a surface check. The game is TypeScript under
`src/` and Python is confined to the asset pipeline, so a PR whose every
changed path is game surface skips the suite, the isolation sweep, and
external-acceptance — they have nothing to prove about it. `scripts/ci_surfaces.py`
owns that rule for both CI and `test:changed`, and it is fail-safe: a single
non-game path anywhere in the diff runs everything, an unrecognised top-level
directory is not game surface, and a diff CI cannot compute runs everything.
Pushes to `main` always run the full set. A skipped job reports as skipped and
still satisfies a required status check, which is why the gate is a job-level
`if:` and not a workflow-level `paths:` filter.

The isolation sweep's throughput model and budget
are recorded in
`docs/adr/0005-isolation-sweep-throughput-target.md`: CI's reported `wall_s`
is the measurement of record, `wall_s` ≤ 180s is the standing budget, and
there is no per-file ceiling.

A claim cites the command and the row of its output that shows the fact. A claim that no command can see is not yet evidenced — say so
rather than substituting a weaker seam.

## Git workflow

One branch per issue (`issue-<N>-<slug>`, based on `main`); never work directly
on `main`. Finish with a pull request that includes `Closes #<N>` and a
completion matrix: one row per issue Contract claim, keyed by its claim ID and
citing the command output that satisfies its Proof mapping.

## Delegating work

These instructions are model-neutral: do not require a particular provider,
model, or effort setting to delegate work. Shared implementer process lives in `docs/agents/issue-implementer.md`. On
Cursor, the orchestrator spawns `issue-implementer-code` or
`issue-implementer-asset` (`.cursor/agents/issue-implementer-code.md`,
`.cursor/agents/issue-implementer-asset.md`) by slice type — model and slice
rules are preloaded there. The orchestrator independently owns the acceptance
gate — green tests and a scope-matching file list are necessary but never
sufficient.

**Cursor orchestrators:** parent chat and Task spawn rules for Composer 2.5 live
in `docs/agents/cursor-composer-pin.md` — use `composer-2.5[fast=false]` only;
spawn by subagent name with no inline `model`.
