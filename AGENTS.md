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

### Triage labels

See `docs/agents/triage-labels.md` for the canonical role → label mapping and
which labels this repo has actually created.

### Domain docs

This is a single-context project with `CONTEXT.md` at the root and architectural
decisions under `docs/adr/`. See `docs/agents/domain.md`.

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

### Strip acquisition contract

`docs/strip-acquisition-contract.md` is the authority for motion classes, gates,
budgets, the budget-derivation rule, and known gaps. Read it before changing any
gate, budget, or class property. Its measured tables are reproduced by
`npm run prototype:strip:derive-budgets` — cite the command output, not a
remembered number.

Budgets are **per motion class** and derived from manifest-good strips. Do not
add good strips to strengthen a separation claim; under the current derivation
rule good strips can only widen budgets toward the fixed negative controls. The
contract's "Next corpus priority" section owns which samples are worth adding.

### Code style and test seams

`docs/agents/code-style.md` is this repo's documented coding standard: the layout
and style rules for the TypeScript game and the Python asset pipeline, and the
standing seam agreement for the `/tdd` (red-green) workflow. Changes are
test-first at its seams, and code review judges every diff against its rules — a
breach is a documented-standard violation, not a judgement call.

### Evidence

There is no browser or native harness in this repo yet. Every claim is proved by
a command whose output is text:

```bash
npm test                                # test suites (pytest today; TS tests as they land)
npm run prototype:strip:corpus          # score inbox/ against prompts/manifest.json
npm run prototype:strip:adversarial     # per-class mutations — gates must reject
npm run prototype:strip:derive-budgets  # per-class worst-good → budgets
npm run prototype:strip:displacement    # displacement falsification + coverage
npm run prototype:strip:sharpness       # alignment-minimum margins, corpus-wide
```

A claim cites the command and the row of its output that shows the fact. A claim that no command can see is not yet evidenced — say so
rather than substituting a weaker seam.

## Git workflow

One branch per issue (`issue-<N>-<slug>`, based on `main`); never work directly
on `main`. Finish with a pull request that includes `Closes #<N>` and a
completion matrix: one row per issue Contract claim, keyed by its claim ID and
citing the command output that satisfies its Proof mapping.

## Delegating work

These instructions are model-neutral: do not require a particular provider,
model, or effort setting to delegate work. A reusable issue-implementation
subagent is defined in `.agents/issue-implementer.md`. The orchestrator
independently owns the acceptance gate — green tests and a scope-matching file
list are necessary but never sufficient.

## Cursor Cloud specific instructions

The runtime is **Python 3 only**; `requirements.txt` (Pillow, numpy, pytest) is
the whole dependency set and is installed by the startup update script. `node`/
`npm` are present but act only as a script launcher — `package.json` declares no
Node deps, so there is no `npm install` step. Commands are the `npm run …`
wrappers and `npm test` documented in the Evidence and README sections above; all
already set `PYTHONPATH=.` and must run from the repo root. There is no server or
web UI to start.

Non-obvious gotchas:

- `npm run strip:ingest` (and the gate generally) **exits non-zero on a FAIL
  verdict** — that is the gate rejecting a strip, not a broken environment.
- The evidence probes intentionally print `GAP`, `displacement inapplicable`, and
  `Frozen ledger` lines for documented known gaps; these are expected and the
  commands still exit 0.
- `npm run prototype:strip` is an interactive terminal TUI and needs a real TTY;
  it is not runnable in a non-interactive shell.
